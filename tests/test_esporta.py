import httpx
import pytest
import respx

from normattiva import Normattiva
from normattiva._http import Trasporto
from normattiva.errori import (
    ConnectionError,
    ExportFailedError,
    OverloadedError,
    TooManyResultsError,
    UnexpectedResponseError,
)
from normattiva.esporta import Corpus, Export, ExportStatus, Progress
from normattiva.modelli import ExportMode, Format
from tests.dati import FIXTURES, carica

BASE = "https://esempio.invalid/api"
TOKEN = "802ecf87-b3bf-43f3-9d85-c0851d7d5021"
STATO = f"/ricerca-asincrona/check-status/{TOKEN}"
SCARICO = f"/collections/download/collection-asincrona/{TOKEN}"

ARCHIVIO = (FIXTURES / "export_multivigente.zip").read_bytes()


def stato(codice: int, **oltre) -> dict:
    return {"stato": codice, "descrizioneStato": "", "percentuale": 0.0, **oltre}


class Orologio:
    def __init__(self) -> None:
        self.adesso = 0.0
        self.attese: list[float] = []

    def tempo(self) -> float:
        return self.adesso

    def attendi(self, quanto: float) -> None:
        self.attese.append(quanto)
        self.adesso += quanto


@pytest.fixture
def orologio() -> Orologio:
    return Orologio()


@pytest.fixture
def api():
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        yield router


@pytest.fixture
def client(orologio: Orologio) -> Normattiva:
    with Normattiva(
        base_url=BASE,
        requests_per_second=0,
        sleep=orologio.attendi,
        clock=orologio.tempo,
    ) as normattiva:
        yield normattiva


@pytest.fixture
def esportazione(api, client: Normattiva) -> Export:
    api.post("/ricerca/avanzata").respond(200, json=carica("ricerca_avanzata"))
    api.post("/ricerca-asincrona/nuova-ricerca").respond(202, text=TOKEN)
    api.put("/ricerca-asincrona/conferma-ricerca").respond(200, json=stato(1))
    return client.start_export(anno=1990, numero=241)


class TestAvvio:
    def test_richiesta_e_conferma(self, api, client: Normattiva) -> None:
        api.post("/ricerca/avanzata").respond(200, json=carica("ricerca_avanzata"))
        nuova = api.post("/ricerca-asincrona/nuova-ricerca").respond(202, text=TOKEN)
        conferma = api.put("/ricerca-asincrona/conferma-ricerca").respond(200, json=stato(1))
        esportazione = client.start_export(anno=1990, numero=241)
        assert esportazione.token == TOKEN
        assert nuova.call_count == 1
        assert conferma.call_count == 1

    def test_corpo_della_richiesta(self, api, client: Normattiva) -> None:
        import json

        api.post("/ricerca/avanzata").respond(200, json=carica("ricerca_avanzata"))
        nuova = api.post("/ricerca-asincrona/nuova-ricerca").respond(202, text=TOKEN)
        api.put("/ricerca-asincrona/conferma-ricerca").respond(200, json=stato(1))
        client.start_export(anno=1990, numero=241, mode=ExportMode.MULTIVIGENTE)
        corpo = json.loads(nuova.calls.last.request.content)
        assert corpo["formato"] == "JSON"
        assert corpo["richiestaExport"] == "M"
        assert corpo["tipoRicerca"] == "A"
        assert corpo["parametriRicerca"]["annoProvvedimento"] == 1990

    def test_conteggio_preventivo(self, api, client: Normattiva) -> None:
        conteggio = api.post("/ricerca/avanzata").respond(200, json=carica("ricerca_avanzata"))
        api.post("/ricerca-asincrona/nuova-ricerca").respond(202, text=TOKEN)
        api.put("/ricerca-asincrona/conferma-ricerca").respond(200, json=stato(1))
        client.start_export(anno=1990, numero=241)
        assert conteggio.call_count == 1

    def test_export_troppo_grande_rifiutato(self, api, client: Normattiva) -> None:
        risultati = carica("ricerca_avanzata")
        risultati["numeroAttiTrovati"] = 5000
        api.post("/ricerca/avanzata").respond(200, json=risultati)
        nuova = api.post("/ricerca-asincrona/nuova-ricerca").respond(202, text=TOKEN)
        with pytest.raises(TooManyResultsError) as errore:
            client.start_export(anno=1990)
        assert errore.value.totale == 5000
        assert nuova.call_count == 0

    def test_limite_disattivabile(self, api, client: Normattiva) -> None:
        conteggio = api.post("/ricerca/avanzata").respond(200, json=carica("ricerca_avanzata"))
        api.post("/ricerca-asincrona/nuova-ricerca").respond(202, text=TOKEN)
        api.put("/ricerca-asincrona/conferma-ricerca").respond(200, json=stato(1))
        client.start_export(anno=1990, massimo_atti=None)
        assert conteggio.call_count == 0

    def test_conteggio_irraggiungibile_spiega_la_via_d_uscita(
        self, api, client: Normattiva
    ) -> None:
        api.post("/ricerca/avanzata").mock(side_effect=httpx.ConnectError("giù"))
        with pytest.raises(ConnectionError, match="massimo_atti=None"):
            client.start_export(anno=1990, numero=241)

    def test_senza_conteggio_l_export_parte_lo_stesso(self, api, client: Normattiva) -> None:
        api.post("/ricerca/avanzata").mock(side_effect=httpx.ConnectError("giù"))
        api.post("/ricerca-asincrona/nuova-ricerca").respond(202, text=TOKEN)
        api.put("/ricerca-asincrona/conferma-ricerca").respond(200, json=stato(1))
        assert client.start_export(anno=1990, massimo_atti=None).token == TOKEN

    def test_criterio_sconosciuto_rifiutato(self, api, client: Normattiva) -> None:
        conteggio = api.post("/ricerca/avanzata").respond(200, json=carica("ricerca_avanzata"))
        with pytest.raises(TypeError, match="denomiazione"):
            client.start_export(denomiazione="LEGGE", anno=1990)
        assert conteggio.call_count == 0

    def test_senza_criteri_e_il_conteggio_a_fermare_l_export(self, api, client: Normattiva) -> None:
        """Esportare tutto il corpus è caro per il servizio: lo ferma il conteggio."""
        risultati = carica("ricerca_avanzata")
        risultati["numeroAttiTrovati"] = 205070
        api.post("/ricerca/avanzata").respond(200, json=risultati)
        nuova = api.post("/ricerca-asincrona/nuova-ricerca").respond(202, text=TOKEN)
        with pytest.raises(TooManyResultsError):
            client.start_export()
        assert nuova.call_count == 0


class TestAttesa:
    def test_percorre_gli_stati(self, api, esportazione: Export) -> None:
        controllo = api.get(STATO).mock(
            side_effect=[
                httpx.Response(200, json=stato(1)),
                httpx.Response(200, json=stato(2, percentuale=50.0)),
                httpx.Response(
                    303, json=stato(3, percentuale=100.0), headers={"x-ipzs-location": "http://qui"}
                ),
            ]
        )
        assert esportazione.wait() is ExportStatus.COMPLETED
        assert controllo.call_count == 3

    def test_avanzamento_esposto(self, api, esportazione: Export) -> None:
        api.get(STATO).respond(200, json=stato(2, percentuale=42.0))
        esportazione.refresh()
        assert esportazione.progress.percent == 42.0

    def test_attende_fra_un_controllo_e_l_altro(
        self, api, esportazione: Export, orologio: Orologio
    ) -> None:
        api.get(STATO).mock(
            side_effect=[httpx.Response(200, json=stato(1)), httpx.Response(303, json=stato(3))]
        )
        esportazione.wait()
        assert orologio.attese == [4.0]

    def test_fallimento(self, api, esportazione: Export) -> None:
        api.get(STATO).respond(200, json=stato(4, descrizioneErrore="niente da fare"))
        with pytest.raises(ExportFailedError, match="niente da fare"):
            esportazione.wait()

    def test_sovraccarico(self, api, esportazione: Export) -> None:
        api.get(STATO).respond(
            200, json=stato(5, descrizioneStato="usa la collezione Leggi"), headers={}
        )
        with pytest.raises(OverloadedError) as errore:
            esportazione.wait()
        assert "Leggi" in str(errore.value)

    def test_ritardo_dichiarato_allunga_l_attesa(
        self, api, esportazione: Export, orologio: Orologio
    ) -> None:
        api.get(STATO).mock(
            side_effect=[httpx.Response(200, json=stato(6))] * 3
            + [httpx.Response(303, json=stato(3))]
        )
        assert esportazione.wait(timeout=10.0) is ExportStatus.COMPLETED

    def test_scadenza_superata(self, api, esportazione: Export) -> None:
        api.get(STATO).respond(200, json=stato(2))
        with pytest.raises(ExportFailedError, match="secondi"):
            esportazione.wait(timeout=10.0)

    def test_stato_conclusivo(self) -> None:
        assert ExportStatus.COMPLETED.done
        assert not ExportStatus.PROCESSING.done


class TestScarico:
    def test_segue_la_posizione_indicata(self, api, esportazione: Export) -> None:
        api.get(STATO).respond(303, json=stato(3), headers={"x-ipzs-location": f"{BASE}/altrove"})
        altrove = api.get("/altrove").respond(200, content=ARCHIVIO)
        esportazione.wait()
        esportazione.download()
        assert altrove.call_count == 1

    def test_ripiega_sul_percorso_per_token(self, api, esportazione: Export) -> None:
        scarico = api.get(SCARICO).respond(200, content=ARCHIVIO)
        assert len(esportazione.download().atti) == 1
        assert scarico.call_count == 1

    def test_corpus_letto(self, api, esportazione: Export) -> None:
        api.get(SCARICO).respond(200, content=ARCHIVIO)
        corpus = esportazione.download()
        assert str(corpus.atti[0].urn) == "urn:nir:stato:legge:1990-08-07;241"

    def test_salva_su_disco(self, api, esportazione: Export, tmp_path) -> None:
        api.get(SCARICO).respond(200, content=ARCHIVIO)
        percorso = esportazione.save(tmp_path / "export.zip")
        assert percorso.read_bytes() == ARCHIVIO

    def test_formato_non_json_non_si_legge_in_modelli(self, api, client: Normattiva) -> None:
        api.post("/ricerca/avanzata").respond(200, json=carica("ricerca_avanzata"))
        api.post("/ricerca-asincrona/nuova-ricerca").respond(202, text=TOKEN)
        api.put("/ricerca-asincrona/conferma-ricerca").respond(200, json=stato(1))
        esportazione = client.start_export(anno=1990, numero=241, format=Format.AKN)
        with pytest.raises(ValueError, match=r"save\(\)"):
            esportazione.download()

    def test_formato_non_json_si_salva(self, api, client: Normattiva, tmp_path) -> None:
        api.post("/ricerca/avanzata").respond(200, json=carica("ricerca_avanzata"))
        api.post("/ricerca-asincrona/nuova-ricerca").respond(202, text=TOKEN)
        api.put("/ricerca-asincrona/conferma-ricerca").respond(200, json=stato(1))
        api.get(SCARICO).respond(200, content=b"PK\x03\x04finto")
        esportazione = client.start_export(anno=1990, numero=241, format=Format.AKN)
        assert esportazione.save(tmp_path / "akn.zip").exists()


class TestRipresa:
    def test_da_token(self, api, client: Normattiva) -> None:
        api.get(STATO).respond(200, json=stato(2, percentuale=30.0))
        esportazione = client.export_from_token(TOKEN)
        assert esportazione.token == TOKEN
        assert esportazione.status is ExportStatus.PROCESSING
        assert esportazione.progress.percent == 30.0

    def test_ripresa_e_scarico(self, api, client: Normattiva) -> None:
        api.get(STATO).respond(303, json=stato(3), headers={"x-ipzs-location": f"{BASE}/qui"})
        api.get("/qui").respond(200, content=ARCHIVIO)
        assert len(client.export_from_token(TOKEN).download().atti) == 1


class TestCorpus:
    def test_da_zip_senza_rete(self, tmp_path) -> None:
        percorso = tmp_path / "corpus.zip"
        percorso.write_bytes(ARCHIVIO)
        corpus = Corpus.from_zip(percorso)
        assert len(corpus) == 1
        assert corpus.atti[0].estremi.numero == "241"

    def test_giro_completo_su_disco(self, tmp_path) -> None:
        primo = Corpus.from_data(ARCHIVIO)
        percorso = primo.save(tmp_path / "salvato.zip")
        assert Corpus.from_zip(percorso).atti[0].urn == primo.atti[0].urn

    def test_archivio_vuoto_lo_dice(self) -> None:
        with pytest.raises(UnexpectedResponseError, match="vuoto"):
            Corpus.from_data(b"")

    def test_iterabile(self) -> None:
        assert [a.estremi.numero for a in Corpus.from_data(ARCHIVIO)] == ["241"]

    def test_attribuzione(self) -> None:
        assert "CC BY 4.0" in Corpus.from_data(ARCHIVIO).attribuzione


class TestAvanzamentoDettagliato:
    """Una percentuale sola non dice se l'esportazione è ferma o solo lenta."""

    @pytest.fixture
    def trasporto(self) -> Trasporto:
        return Trasporto(base_url=BASE, requests_per_second=0, sleep=lambda _: None)

    def test_conta_gli_atti_quando_il_servizio_li_conta(self, api, trasporto) -> None:
        api.get(STATO).respond(
            200, json={"stato": 2, "percentuale": 12.0, "attiElaborati": 36, "totAtti": 300}
        )
        esportazione = Export(TOKEN, trasporto)
        esportazione.refresh()
        assert esportazione.progress == Progress(percent=12.0, processed=36, total=300)
        assert str(esportazione.progress) == "36/300 atti"

    def test_ripiega_sulla_percentuale_quando_non_li_conta(self, api, trasporto) -> None:
        api.get(STATO).respond(200, json={"stato": 2, "percentuale": 42.0})
        esportazione = Export(TOKEN, trasporto)
        esportazione.refresh()
        assert str(esportazione.progress) == "42%"

    def test_e_dice_di_non_sapere_quando_non_sa(self, api, trasporto) -> None:
        api.get(STATO).respond(200, json={"stato": 2})
        esportazione = Export(TOKEN, trasporto)
        esportazione.refresh()
        assert str(esportazione.progress) == "sconosciuto"
