import json
from datetime import date

import httpx
import pytest
import respx

from normattiva import AsyncNormattiva, Urn
from normattiva._http import LimitatoreAsync, TrasportoAsync
from normattiva.errori import (
    AmbiguityError,
    ConnectionError,
    ExportFailedError,
    RequestBlockedError,
    RuleCode,
    RuleViolationError,
    TooManyResultsError,
    TruncationError,
    UnexpectedResponseError,
    ValidityMismatchError,
)
from normattiva.esporta import AsyncExport, ExportStatus
from tests.dati import FIXTURES, carica

BASE = "https://esempio.invalid/api"
URN = "atto/dettaglio-atto-urn"
TOKEN = "un-token"
STATO = f"/ricerca-asincrona/check-status/{TOKEN}"
SCARICO = f"/collections/download/collection-asincrona/{TOKEN}"
ARCHIVIO = (FIXTURES / "export_multivigente.zip").read_bytes()

pytestmark = pytest.mark.anyio


class Orologio:
    def __init__(self) -> None:
        self.adesso = 0.0
        self.attese: list[float] = []

    def tempo(self) -> float:
        return self.adesso

    async def attendi(self, quanto: float) -> None:
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
async def client(orologio: Orologio):
    async with AsyncNormattiva(
        base_url=BASE,
        requests_per_second=0,
        sleep=orologio.attendi,
        clock=orologio.tempo,
    ) as normattiva:
        yield normattiva


def corpo_di(rotta) -> dict:
    return json.loads(rotta.calls.last.request.content)


def stato(codice: int, **oltre) -> dict:
    return {"stato": codice, "percentuale": 0.0, **oltre}


class TestDettaglio:
    async def test_testo_recuperato(self, api, client: AsyncNormattiva) -> None:
        api.post(f"/{URN}").respond(200, json=carica("urn_vigenza_finestra"))
        atto = await client.dettaglio("urn:nir:stato:legge:1970-12-01;898~art5")
        assert atto.atto.numero == "898"
        assert atto.testo

    async def test_vigenza_nell_urn(self, api, client: AsyncNormattiva) -> None:
        rotta = api.post(f"/{URN}").respond(200, json=carica("urn_vigenza_finestra"))
        await client.dettaglio(Urn.legge(1970, 898, articolo="5"), vigenza=date(2005, 1, 1))
        assert corpo_di(rotta)["urn"].endswith("!vig=2005-01-01")

    async def test_vigenza_incoerente(self, api, client: AsyncNormattiva) -> None:
        api.post(f"/{URN}").respond(200, json=carica("urn_vigenza_finestra"))
        with pytest.raises(ValidityMismatchError):
            await client.dettaglio(
                "urn:nir:stato:legge:1970-12-01;898~art5", vigenza=date(1980, 1, 1)
            )

    async def test_ambiguita(self, api, client: AsyncNormattiva) -> None:
        api.post(f"/{URN}").respond(200, json=carica("urn_ambiguo"))
        with pytest.raises(AmbiguityError):
            await client.dettaglio("urn:nir:stato:legge:2001-12-28;448~art2")

    async def test_troncamento_sollevabile(self, api, client: AsyncNormattiva) -> None:
        api.post(f"/{URN}").respond(200, json=carica("urn_troncato_100_commi"))
        with pytest.raises(TruncationError):
            await client.dettaglio("urn:nir:stato:legge:2016-12-11;232~art1", se_troncato="solleva")

    async def test_urn_non_valido_non_tocca_la_rete(self, api, client: AsyncNormattiva) -> None:
        rotta = api.post(f"/{URN}").respond(200, json={})
        with pytest.raises(ValueError, match="URN non valido"):
            await client.dettaglio("legge 241/1990")
        assert rotta.call_count == 0


class TestRitentativi:
    async def test_ritenta_il_500(self, api, client: AsyncNormattiva) -> None:
        rotta = api.post(f"/{URN}").mock(
            side_effect=[
                httpx.Response(500),
                httpx.Response(200, json=carica("urn_vigenza_finestra")),
            ]
        )
        await client.dettaglio("urn:nir:stato:legge:1970-12-01;898~art5")
        assert rotta.call_count == 2

    async def test_non_ritenta_il_waf(self, api, client: AsyncNormattiva) -> None:
        rotta = api.post(f"/{URN}").respond(409, json={"supportId": "1"})
        with pytest.raises(RequestBlockedError):
            await client.dettaglio("urn:nir:stato:legge:1970-12-01;898~art5")
        assert rotta.call_count == 1

    async def test_attende_senza_bloccare(
        self, api, client: AsyncNormattiva, orologio: Orologio
    ) -> None:
        api.post(f"/{URN}").mock(
            side_effect=[
                httpx.Response(500),
                httpx.Response(200, json=carica("urn_vigenza_finestra")),
            ]
        )
        await client.dettaglio("urn:nir:stato:legge:1970-12-01;898~art5")
        assert len(orologio.attese) == 1


class TestRicerca:
    async def test_esito(self, api, client: AsyncNormattiva) -> None:
        api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        esito = await client.ricerca("divorzio")
        assert esito.totale == 87

    async def test_avanzata(self, api, client: AsyncNormattiva) -> None:
        rotta = api.post("/ricerca/avanzata").respond(200, json=carica("ricerca_avanzata"))
        await client.ricerca_avanzata(anno=1990, numero=241)
        assert corpo_di(rotta)["annoProvvedimento"] == 1990

    async def test_completa_scorre_le_pagine(self, api, client: AsyncNormattiva) -> None:
        pagina = carica("ricerca_semplice")
        pagina["numeroAttiTrovati"] = 10
        pagina["numeroPagine"] = 2
        api.post("/ricerca/semplice").mock(
            side_effect=[
                httpx.Response(200, json={**pagina, "paginaCorrente": 1}),
                httpx.Response(200, json={**pagina, "paginaCorrente": 2}),
            ]
        )
        atti = [atto async for atto in client.ricerca_completa("divorzio")]
        assert len(atti) == 10

    async def test_il_limite_prende_i_primi(self, api, client: AsyncNormattiva) -> None:
        api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        atti = [atto async for atto in client.ricerca_completa("divorzio", massimo=3)]
        assert len(atti) == 3

    async def test_aggiornati_spezza_l_intervallo(self, api, client: AsyncNormattiva) -> None:
        rotta = api.post("/ricerca/aggiornati").respond(200, json=carica("ricerca_aggiornati"))
        [a async for a in client.atti_aggiornati(date(2020, 1, 1), date(2023, 1, 1))]
        assert rotta.call_count == 4

    async def test_aggiornati_date_invertite(self, api, client: AsyncNormattiva) -> None:
        rotta = api.post("/ricerca/aggiornati").respond(200, json={})
        with pytest.raises(RuleViolationError) as errore:
            [a async for a in client.atti_aggiornati(date(2026, 8, 20), date(2026, 8, 1))]
        assert errore.value.regola is RuleCode.DATE_INVERTITE
        assert rotta.call_count == 0


class TestCronologia:
    async def test_percorre_le_finestre(self, api, client: AsyncNormattiva) -> None:
        modello = carica("urn_vigenza_finestra")

        def con(inizio: str, fine: str) -> httpx.Response:
            copia = json.loads(json.dumps(modello))
            copia["data"]["atto"]["articoloDataInizioVigenza"] = inizio
            copia["data"]["atto"]["articoloDataFineVigenza"] = fine
            return httpx.Response(200, json=copia)

        api.post(f"/{URN}").mock(
            side_effect=[con("19900902", "19920610"), con("19920611", "99999999")]
        )
        versioni = [v async for v in client.cronologia("urn:nir:stato:legge:1990-08-07;241~art19")]
        assert len(versioni) == 2


class TestTipologiche:
    async def test_cache(self, api, client: AsyncNormattiva) -> None:
        rotta = api.get("/tipologiche/denominazione-atto").respond(
            200, json=carica("tipologiche_denominazione_atto")
        )
        await client.denominazioni()
        await client.denominazioni()
        assert rotta.call_count == 1

    async def test_ricarica(self, api, client: AsyncNormattiva) -> None:
        rotta = api.get("/tipologiche/denominazione-atto").respond(
            200, json=carica("tipologiche_denominazione_atto")
        )
        await client.denominazioni()
        await client.denominazioni(reload=True)
        assert rotta.call_count == 2


class TestEsportazione:
    @pytest.fixture
    async def esportazione(self, api, client: AsyncNormattiva):
        api.post("/ricerca/avanzata").respond(200, json=carica("ricerca_avanzata"))
        api.post("/ricerca-asincrona/nuova-ricerca").respond(202, text=TOKEN)
        api.put("/ricerca-asincrona/conferma-ricerca").respond(200, json=stato(1))
        return await client.start_export(anno=1990, numero=241)

    async def test_avvio(self, esportazione) -> None:
        assert esportazione.token == TOKEN

    async def test_attesa_fino_al_completamento(self, api, esportazione) -> None:
        api.get(STATO).mock(
            side_effect=[
                httpx.Response(200, json=stato(1)),
                httpx.Response(303, json=stato(3), headers={"x-ipzs-location": f"{BASE}/qui"}),
            ]
        )
        assert await esportazione.wait() is ExportStatus.COMPLETED

    async def test_scarico(self, api, esportazione) -> None:
        api.get(SCARICO).respond(200, content=ARCHIVIO)
        corpus = await esportazione.download()
        assert len(corpus.atti) == 1

    async def test_salva(self, api, esportazione, tmp_path) -> None:
        api.get(SCARICO).respond(200, content=ARCHIVIO)
        percorso = await esportazione.save(tmp_path / "export.zip")
        assert percorso.read_bytes() == ARCHIVIO

    async def test_conteggio_preventivo(self, api, client: AsyncNormattiva) -> None:
        risultati = carica("ricerca_avanzata")
        risultati["numeroAttiTrovati"] = 5000
        api.post("/ricerca/avanzata").respond(200, json=risultati)
        nuova = api.post("/ricerca-asincrona/nuova-ricerca").respond(202, text=TOKEN)
        with pytest.raises(TooManyResultsError):
            await client.start_export(anno=1990)
        assert nuova.call_count == 0

    async def test_ripresa_da_token(self, api, client: AsyncNormattiva) -> None:
        api.get(STATO).respond(200, json=stato(2, percentuale=30.0))
        esportazione = await client.export_from_token(TOKEN)
        assert esportazione.progress.percent == 30.0


class TestCollezioni:
    async def test_scarica(self, api, client: AsyncNormattiva) -> None:
        api.get("/collections/download/collection-preconfezionata").respond(200, content=ARCHIVIO)
        corpus = await client.download_collection("Leggi di delegazione europea")
        assert len(corpus.atti) == 1


class TestCicloDiVita:
    async def test_chiusura(self, orologio: Orologio) -> None:
        client = AsyncNormattiva(base_url=BASE, requests_per_second=0)
        await client.close()
        assert client.closed

    async def test_client_http_iniettabile(self) -> None:
        mio = httpx.AsyncClient()
        async with AsyncNormattiva(base_url=BASE, http_client=mio):
            pass
        assert not mio.is_closed
        await mio.aclose()


class TestIlGemelloAsincronoRegge:
    """I punti dove due implementazioni gemelle divergono in silenzio.

    Le firme dei due client si rispecchiano, e lo verifica `test_copertura_e2e`,
    ma finora l'autolimitazione, il ritentativo esaurito e la scadenza
    dell'attesa erano provati solo sul gemello sincrono: sono esattamente il
    genere di logica che si copia una volta e poi si corregge da una parte sola.
    """

    async def test_il_limitatore_distanzia_le_richieste(self, orologio: Orologio) -> None:
        limitatore = LimitatoreAsync(2.0, sleep=orologio.attendi, clock=orologio.tempo)
        await limitatore.attendi_turno()
        await limitatore.attendi_turno()
        assert orologio.attese == [0.5], "la seconda richiesta non ha aspettato il suo turno"

    async def test_il_limitatore_spento_non_aspetta(self, orologio: Orologio) -> None:
        limitatore = LimitatoreAsync(0, sleep=orologio.attendi, clock=orologio.tempo)
        await limitatore.attendi_turno()
        await limitatore.attendi_turno()
        assert orologio.attese == []

    async def test_il_limitatore_non_aspetta_se_il_tempo_e_gia_passato(
        self, orologio: Orologio
    ) -> None:
        limitatore = LimitatoreAsync(2.0, sleep=orologio.attendi, clock=orologio.tempo)
        await limitatore.attendi_turno()
        orologio.adesso += 10
        await limitatore.attendi_turno()
        assert orologio.attese == []

    async def test_un_errore_di_rete_persistente_diventa_connessione(
        self, api, client: AsyncNormattiva
    ) -> None:
        rotta = api.post(f"/{URN}").mock(side_effect=httpx.ConnectError("giù"))
        with pytest.raises(ConnectionError):
            await client.dettaglio(Urn.legge(1990, 241))
        assert rotta.call_count == 3

    async def test_un_cinquecento_persistente_emerge_dopo_i_tentativi(
        self, api, client: AsyncNormattiva
    ) -> None:
        rotta = api.post(f"/{URN}").respond(500, json={"error": "rotto"})
        with pytest.raises(UnexpectedResponseError):
            await client.dettaglio(Urn.legge(1990, 241))
        assert rotta.call_count == 3

    async def test_l_attesa_scade(self, api, esportazione_lenta) -> None:
        api.get(STATO).respond(200, json=stato(2))
        with pytest.raises(ExportFailedError, match="non si è conclusa"):
            await esportazione_lenta.wait(timeout=10.0)

    async def test_il_ritardo_dichiarato_vale_una_proroga_sola(
        self, api, esportazione_lenta
    ) -> None:
        """Rinnovare la proroga a ogni giro vorrebbe dire non scadere mai."""
        api.get(STATO).respond(200, json=stato(6))
        with pytest.raises(ExportFailedError):
            await esportazione_lenta.wait(timeout=10.0)

    @pytest.fixture
    async def esportazione_lenta(self, orologio: Orologio):
        return AsyncExport(
            TOKEN,
            TrasportoAsync(base_url=BASE, requests_per_second=0, sleep=orologio.attendi),
            sleep=orologio.attendi,
            clock=orologio.tempo,
        )
