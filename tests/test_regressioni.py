"""Un test per ogni difetto trovato, perché nessuno possa tornare.

Ogni classe qui sotto porta il nome del difetto e la sua data. Non sono prove di
comportamento nuovo: sono la memoria di comportamenti che una volta erano
sbagliati, e che senza queste righe potrebbero tornare a esserlo senza che
nessuno se ne accorga.
"""

from __future__ import annotations

import io
import json
import re
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from itertools import pairwise

import httpx
import pytest
import respx

from normattiva import Corpus, InvalidUrnError, Normattiva, Urn, _wire
from normattiva._http import Limitatore, Risposta, Trasporto
from normattiva._wire import _dati, _intero, _testo, solleva_errore
from normattiva.client import (
    PAGINE_MASSIME,
    PASSI_MASSIMI,
    _campi_avanzati,
    _coordinate,
    _corpo_export,
)
from normattiva.errori import (
    ConnectionError,
    InvalidArgumentError,
    OverloadedError,
    RuleViolationError,
    TooManyResultsError,
    UnexpectedResponseError,
    VersionNotFoundError,
)
from normattiva.esporta import Export, ExportStatus, _stato_da
from normattiva.modelli import (
    AttoStorico,
    AttoTrovato,
    EsitoRicerca,
    EstremiAtto,
    ExportMode,
    Format,
    PubblicazioneGazzetta,
    VersioneAtto,
)
from normattiva.testo import estrai, normalize_accents
from tests.dati import FIXTURES, carica, html_di

BASE = "https://esempio.invalid/api"
URN = "atto/dettaglio-atto-urn"
TOKEN = "un-token"


@pytest.fixture
def api():
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        yield router


class Orologio:
    def __init__(self) -> None:
        self.adesso = 0.0

    def tempo(self) -> float:
        return self.adesso

    def attendi(self, quanto: float) -> None:
        self.adesso += quanto


@pytest.fixture
def orologio() -> Orologio:
    return Orologio()


@pytest.fixture
def client(orologio: Orologio) -> Normattiva:
    with Normattiva(
        base_url=BASE,
        requests_per_second=0,
        sleep=orologio.attendi,
        clock=orologio.tempo,
    ) as normattiva:
        yield normattiva


class TestElementiVuotiSbilanciavanoLaPila:
    """Un `<img>` dentro le note faceva sparire tutto il corpo dell'articolo."""

    def test_un_elemento_vuoto_non_apre_un_contenitore(self) -> None:
        contenuto = estrai(
            '<div class="art_aggiornamento-akn"><img src="x">Nota.</div>'
            "<p>Testo dell'articolo.</p>"
        )
        assert "Testo dell'articolo." in contenuto.corpo
        assert contenuto.note == "Nota."

    @pytest.mark.parametrize("vuoto", ["img", "hr", "input", "meta", "col", "wbr"])
    def test_nessun_elemento_vuoto_sposta_il_testo(self, vuoto: str) -> None:
        contenuto = estrai(
            f'<div class="art_aggiornamento-akn"><{vuoto}>Nota</div><div>Corpo</div>'
        )
        assert contenuto.corpo == "Corpo"

    def test_un_tag_di_chiusura_spaiato_non_chiude_altro(self) -> None:
        contenuto = estrai('</span><div class="art_aggiornamento-akn">Nota</div><div>Corpo</div>')
        assert contenuto.corpo == "Corpo"
        assert contenuto.note == "Nota"

    def test_un_paragrafo_non_chiuso_chiude_il_precedente(self) -> None:
        contenuto = estrai('<p class="art_aggiornamento-akn">Nota<p>Corpo')
        assert contenuto.corpo == "Corpo"
        assert contenuto.note == "Nota"


class TestLeParoleSiIncollavanoFraBlocchi:
    """Due paragrafi diventavano una parola sola."""

    def test_due_paragrafi_restano_due_righe(self) -> None:
        assert estrai("<p>Primo.</p><p>Secondo.</p>").corpo == "Primo.\nSecondo."

    def test_le_celle_di_una_tabella_non_si_fondono(self) -> None:
        assert "unodue" not in estrai("<table><tr><td>uno</td><td>due</td></tr></table>").corpo

    def test_gli_elementi_inline_restano_attaccati(self) -> None:
        """Fra `<span>` non va messo nulla: è il comportamento di ogni browser."""
        assert estrai("<span>venti</span><span>due</span>").corpo == "ventidue"


class TestTroncamentiAccentatiPerSbaglio:
    """`po'` diventava `pò`, che in italiano non esiste."""

    @pytest.mark.parametrize(
        "intatto",
        ["un po' di tempo", "va' via", "fa' presto", "sta' fermo", "di' pure", "se' medesimo"],
    )
    def test_i_troncamenti_restano_intatti(self, intatto: str) -> None:
        assert normalize_accents(intatto) == intatto

    @pytest.mark.parametrize(
        ("grezzo", "atteso"),
        [("attivita'", "attività"), ("e' vietato", "è vietato"), ("perche'", "perché")],
    )
    def test_gli_accenti_veri_si_normalizzano_ancora(self, grezzo: str, atteso: str) -> None:
        assert normalize_accents(grezzo) == atteso


class TestQuadreMangiate:
    """`strip("[]")` toglieva la quadra di chiusura da «Art. 5 [1]»."""

    def test_una_quadra_interna_resta(self) -> None:
        assert _testo("Art. 5 [1]") == "Art. 5 [1]"

    def test_una_coppia_esterna_viene_tolta(self) -> None:
        assert _testo("[  Nuove norme \r ]") == "Nuove norme"

    def test_il_titolo_reale_e_ripulito(self) -> None:
        atto = carica("ricerca_avanzata")["listaAtti"][0]
        assert _testo(atto["titoloAtto"]).startswith("Nuove norme")


class TestNodiAssentiNellExport:
    """Un atto senza allegati faceva fallire la lettura di tutto l'archivio."""

    def test_un_ramo_assente_non_e_una_risposta_malformata(self) -> None:
        assert _dati({"articolato": {"elementi": []}}, "annessi", "elementi") is None

    def test_un_ramo_nullo_nemmeno(self) -> None:
        assert _dati({"annessi": None}, "annessi", "elementi") is None

    def test_un_ramo_del_tipo_sbagliato_lo_e(self) -> None:
        with pytest.raises(UnexpectedResponseError):
            _dati({"annessi": "niente"}, "annessi", "elementi")


class TestCodiciDiErroreIlleggibili:
    """Un `code` non numerico diventava «numero non interpretabile», perdendo il messaggio."""

    def test_il_messaggio_del_servizio_sopravvive(self) -> None:
        with pytest.raises(UnexpectedResponseError, match="parametro non valido"):
            solleva_errore(400, b'{"code":"E1005","message":"parametro non valido"}', None)

    def test_un_numero_decimale_resta_un_numero(self) -> None:
        assert _intero("12.0") == 12
        assert _intero(12.0) == 12


class TestUrnCostruitiMale:
    """L'URN nasceva invalido e il difetto emergeva come 404 del servizio."""

    def test_un_articolo_numerico_non_fa_esplodere_nulla(self) -> None:
        assert str(Urn.legge(1990, 241, articolo=5)).endswith("~art5")

    def test_un_numero_assente_non_finisce_nell_urn(self) -> None:
        assert str(Urn.legge(2000, None)) == "urn:nir:stato:legge:2000"
        assert str(Urn.legge(2000, "")) == "urn:nir:stato:legge:2000"

    def test_un_datetime_diventa_una_data(self) -> None:
        urn = Urn.legge(1990, 241).con_vigenza(datetime(2005, 1, 1, 12, 30))
        assert str(urn).endswith("!vig=2005-01-01")
        assert Urn.parse(str(urn)) == urn


class TestDenominazioniIndovinate:
    """La forma URN veniva dedotta, e sbagliava su dodici tipi di atto su trenta."""

    def test_le_denominazioni_verificate_funzionano(self) -> None:
        assert EstremiAtto("LEGGE", date(1990, 8, 7), "241").urn.denominazione == "legge"

    def test_quelle_non_verificate_lo_dicono(self) -> None:
        with pytest.raises(InvalidUrnError, match="non è verificata"):
            assert EstremiAtto("DECRETO DEL DUCE", date(1942, 12, 14), "1485").urn

    def test_l_errore_indica_la_via_alternativa(self) -> None:
        with pytest.raises(InvalidUrnError, match="esportazione"):
            assert EstremiAtto("REGOLAMENTO", date(1867, 2, 18), "3539").urn


class TestAttesaCheNonScadeva:
    """Un servizio fermo su «confermata con ritardo» teneva `wait` in ciclo per sempre."""

    def _esportazione(self, client: Normattiva, orologio: Orologio) -> Export:
        return Export(TOKEN, client._trasporto, sleep=orologio.attendi, clock=orologio.tempo)

    def test_la_proroga_si_concede_una_volta_sola(
        self, api, client: Normattiva, orologio: Orologio
    ) -> None:
        api.get(f"/ricerca-asincrona/check-status/{TOKEN}").respond(200, json={"stato": 6})
        with pytest.raises(Exception, match="secondi"):
            self._esportazione(client, orologio).wait(timeout=10.0)
        assert orologio.adesso < 100, "l'attesa non deve superare di molto la scadenza"

    def test_una_lavorazione_normale_scade_puntuale(
        self, api, client: Normattiva, orologio: Orologio
    ) -> None:
        api.get(f"/ricerca-asincrona/check-status/{TOKEN}").respond(200, json={"stato": 2})
        with pytest.raises(Exception, match="secondi"):
            self._esportazione(client, orologio).wait(timeout=10.0)


class TestSuccessoDedottoDalSilenzio:
    """Una risposta senza `stato` veniva letta come esportazione completata."""

    def _stato(self, client: Normattiva, orologio: Orologio) -> ExportStatus:
        return Export(
            TOKEN, client._trasporto, sleep=orologio.attendi, clock=orologio.tempo
        ).refresh()

    @pytest.mark.parametrize(
        "risposta",
        [
            httpx.Response(202, content=b""),
            httpx.Response(200, json={}),
            httpx.Response(200, json={"stato": None}),
        ],
    )
    def test_senza_stato_la_lavorazione_continua(
        self, api, client: Normattiva, orologio: Orologio, risposta: httpx.Response
    ) -> None:
        api.get(f"/ricerca-asincrona/check-status/{TOKEN}").mock(return_value=risposta)
        assert self._stato(client, orologio) is ExportStatus.PROCESSING

    def test_lo_stato_come_stringa_viene_capito(
        self, api, client: Normattiva, orologio: Orologio
    ) -> None:
        api.get(f"/ricerca-asincrona/check-status/{TOKEN}").respond(200, json={"stato": "2"})
        assert self._stato(client, orologio) is ExportStatus.PROCESSING

    def test_il_303_resta_il_segnale_di_fine(
        self, api, client: Normattiva, orologio: Orologio
    ) -> None:
        api.get(f"/ricerca-asincrona/check-status/{TOKEN}").respond(303, content=b"")
        assert self._stato(client, orologio) is ExportStatus.COMPLETED


class TestCronologiaFuoriDiUno:
    """Chiedere esattamente PASSI_MASSIMI versioni produceva l'errore invece del risultato."""

    def _sempre_chiusa(self, api) -> None:
        modello = carica("urn_vigenza_finestra")
        modello["data"]["atto"]["articoloDataInizioVigenza"] = "19900902"
        modello["data"]["atto"]["articoloDataFineVigenza"] = "19920610"
        api.post(f"/{URN}").respond(200, json=modello)

    def test_il_limite_dell_utente_vince_sempre(self, api, client: Normattiva) -> None:
        self._sempre_chiusa(api)
        versioni = list(
            client.cronologia("urn:nir:stato:legge:1990;241~art1", massimo=PASSI_MASSIMI)
        )
        assert len(versioni) == PASSI_MASSIMI

    def test_senza_limite_la_catena_infinita_viene_denunciata(
        self, api, client: Normattiva
    ) -> None:
        self._sempre_chiusa(api)
        with pytest.raises(UnexpectedResponseError, match="non si chiude"):
            list(client.cronologia("urn:nir:stato:legge:1990;241~art1"))


class TestPaginazioneSenzaFine:
    """Un servizio che si dimenticava la pagina faceva rileggere la prima all'infinito."""

    def test_il_totale_dichiarato_ferma_il_ciclo(self, api, client: Normattiva) -> None:
        pagina = carica("ricerca_semplice")
        pagina["numeroAttiTrovati"] = 10
        pagina["numeroPagine"] = 999
        pagina.pop("paginaCorrente", None)
        rotta = api.post("/ricerca/semplice").respond(200, json=pagina)
        atti = list(client.ricerca_completa("divorzio"))
        assert len(atti) == 10
        assert rotta.call_count == 2

    def test_una_pagina_vuota_ferma_il_ciclo(self, api, client: Normattiva) -> None:
        vuota = {"listaAtti": [], "numeroAttiTrovati": 500, "numeroPagine": 999}
        api.post("/ricerca/semplice").respond(200, json=vuota)
        assert list(client.ricerca_completa("divorzio")) == []

    def test_esiste_comunque_un_tetto_di_pagine(self) -> None:
        assert PAGINE_MASSIME > 0

    @pytest.mark.parametrize("massimo", [0, -1])
    def test_un_limite_non_positivo_da_un_iteratore_vuoto(
        self, api, client: Normattiva, massimo: int
    ) -> None:
        rotta = api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        assert list(client.ricerca_completa("divorzio", massimo=massimo)) == []
        assert rotta.call_count == 0


class TestTrasportoSenzaTentativi:
    """Con zero tentativi il sincrono esplodeva con UnboundLocalError, l'asincrono no."""

    def test_nessun_tentativo_da_un_errore_del_dominio(self, api) -> None:
        api.get("/prova").respond(200, json={})
        with Trasporto(base_url=BASE, requests_per_second=0) as trasporto:
            trasporto.retries = -1
            with pytest.raises(UnexpectedResponseError):
                trasporto.get("/prova")


class TestVersioneOriginaleIgnorata:
    """`alla_data` non trovava nulla prima della prima modifica."""

    def test_l_archivio_reale_risponde_prima_della_prima_modifica(self) -> None:
        atto = Corpus.from_zip(FIXTURES / "export_multivigente.zip").atti[0]
        prima_modifica = atto.versioni[1].vigente_dal
        assert prima_modifica is not None
        fra_pubblicazione_e_modifica = atto.pubblicato_il + timedelta(days=1)
        assert fra_pubblicazione_e_modifica < prima_modifica
        assert atto.alla_data(fra_pubblicazione_e_modifica).originale

    def test_prima_che_l_atto_esistesse_non_c_e_nulla(self) -> None:
        atto = Corpus.from_zip(FIXTURES / "export_multivigente.zip").atti[0]
        with pytest.raises(VersionNotFoundError):
            atto.alla_data(atto.pubblicato_il - timedelta(days=1))


class TestNoteERegressioniDiEstrazione:
    """Le fixture vere devono continuare a dare gli stessi pezzi."""

    def test_articolo_con_commi(self) -> None:
        contenuto = estrai(html_di("urn_articolo_con_commi"))
        assert contenuto.corpo.startswith("Art. 2")
        assert len(contenuto.commi) > 10
        assert contenuto.note is None

    def test_articolo_con_note(self) -> None:
        contenuto = estrai(html_di("urn_articolo_con_aggiornamento"))
        assert contenuto.note is not None
        assert "AGGIORNAMENTO" in contenuto.note
        assert "AGGIORNAMENTO" not in contenuto.corpo

    def test_atto_intero_col_preambolo(self) -> None:
        contenuto = estrai(html_di("urn_atto_intero"))
        assert contenuto.preambolo is not None
        assert "La Camera dei deputati" in contenuto.preambolo
        assert "La Camera dei deputati" not in contenuto.corpo


class TestLaVigenzaLettaDaUnNomeDiFile:
    """L'archivio dell'export data le versioni solo nel nome dei file.

    Nessun campo del documento porta la data di vigenza: la porta il nome, nella
    forma `..._VIGENZA_2005-01-01_V3.json`. Prima un nome che non la dichiarava
    veniva letto come «versione originale», e allora tutte le versioni
    diventavano l'originale: `alla_data` rispondeva il testo di partenza per
    qualunque data, con sicurezza e senza sollevare niente.
    """

    @staticmethod
    def _archivio_rinominato(da: str, a: str) -> bytes:
        vecchio = zipfile.ZipFile(io.BytesIO((FIXTURES / "export_multivigente.zip").read_bytes()))
        fuori = io.BytesIO()
        with zipfile.ZipFile(fuori, "w") as nuovo:
            for nome in vecchio.namelist():
                nuovo.writestr(nome.replace(da, a), vecchio.read(nome))
        return fuori.getvalue()

    def test_una_convenzione_cambiata_non_passa_in_silenzio(self) -> None:
        with pytest.raises(UnexpectedResponseError, match="non dichiara la versione"):
            Corpus.from_data(self._archivio_rinominato("VIGENZA_", "VIG_"))

    def test_la_convenzione_intatta_continua_a_datare_le_versioni(self) -> None:
        atto = Corpus.from_data(self._archivio_rinominato("VIGENZA_", "VIGENZA_")).atti[0]
        assert [v.vigente_dal for v in atto.versioni][1:] == [
            date(1990, 12, 20),
            date(1991, 1, 23),
            date(2026, 4, 21),
        ]

    def test_due_originali_sono_uno_stato_impossibile(self) -> None:
        """Anche se i nomi passassero, un atto con due originali non è un atto."""
        with pytest.raises(InvalidArgumentError, match="originale"):
            AttoStorico(
                urn=Urn.legge(1990, 241),
                estremi=EstremiAtto("LEGGE", date(1990, 8, 7), "241"),
                versioni=(VersioneAtto(vigente_dal=None), VersioneAtto(vigente_dal=None)),
            )


class TestIlSupplementoButtatoVia:
    """La ricerca porta il supplemento di Gazzetta, e prima veniva scartato.

    Per una legge di bilancio il supplemento è come la si trova in Gazzetta: la
    risposta dichiara `tipoSupplemento` e `numeroSupplemento`, e il lettore della
    ricerca costruiva la `PubblicazioneGazzetta` senza guardarli, mentre quello
    del dettaglio li leggeva. Stesso modello, due lettori, uno cieco.
    """

    def test_la_ricerca_conserva_il_supplemento(self) -> None:
        nodo = dict(carica("ricerca_semplice")["listaAtti"][0])
        nodo["tipoSupplemento"] = "SO"
        nodo["numeroSupplemento"] = "42"
        atto = _wire.leggi_ricerca({"listaAtti": [nodo], "numeroAttiTrovati": 1}).atti[0]
        assert atto.gazzetta.supplemento == "SO"
        assert atto.gazzetta.numero_supplemento == 42
        assert atto.gazzetta.in_supplemento
        assert "suppl. SO n. 42" in str(atto.gazzetta)

    def test_nessun_supplemento_resta_nessun_supplemento(self) -> None:
        nodo = dict(carica("ricerca_semplice")["listaAtti"][0])
        nodo["tipoSupplemento"] = "NO"
        nodo["numeroSupplemento"] = "0"
        atto = _wire.leggi_ricerca({"listaAtti": [nodo], "numeroAttiTrovati": 1}).atti[0]
        assert atto.gazzetta.supplemento is None
        assert not atto.gazzetta.in_supplemento
        assert "suppl." not in str(atto.gazzetta)


class TestIlNumeroDiGazzettaInventato:
    """Zero non è un numero di Gazzetta: è un numero che non c'era."""

    def test_un_riferimento_senza_numero_non_ne_inventa_uno(self) -> None:
        gazzetta = PubblicazioneGazzetta(data=date(2005, 1, 1))
        assert gazzetta.numero is None
        assert str(gazzetta) == "G.U. del 2005-01-01"

    def test_gli_atti_aggiornanti_dell_export_non_hanno_numero(self) -> None:
        atto = Corpus.from_zip(FIXTURES / "export_multivigente.zip").atti[0]
        riferimenti = [r for a in atto.aggiornamenti for r in a.riferimenti]
        assert riferimenti
        assert all(r.gazzetta.numero is None for r in riferimenti)


class TestUnGuastoScambiatoPerUnaRegola:
    """Un `5xx` parla del servizio, non della richiesta.

    Il servizio risponde `500` con `code: 1000` e «riprovare più tardi» anche a
    un URN perfettamente valido, quando è in avaria. Prima diventava
    `RuleViolationError`, cioè «la tua richiesta viola una regola»: chi lo
    riceveva andava a correggere una richiesta che era già giusta.
    """

    def test_il_codice_passeggero_viene_ritentato(self) -> None:
        with respx.mock(base_url=BASE) as api:
            rotta = api.get("/prova").mock(
                side_effect=[
                    httpx.Response(500, json={"code": "1000", "message": "riprovare più tardi"}),
                    httpx.Response(200, json={"ok": True}),
                ]
            )
            trasporto = Trasporto(base_url=BASE, sleep=lambda _: None)
            assert trasporto.get("/prova").json() == {"ok": True}
            assert rotta.call_count == 2

    def test_e_alla_fine_e_un_guasto_non_una_regola(self) -> None:
        with pytest.raises(ConnectionError):
            solleva_errore(500, b'{"code":"1000","message":"riprovare"}')

    def test_una_regola_vera_resta_una_regola(self) -> None:
        with pytest.raises(RuleViolationError):
            solleva_errore(400, b'{"code":"1501","message":"oltre dodici mesi"}')


class TestIlSovraccaricoRaccontatoMale:
    """`OverloadedError` prometteva una collezione e consegnava un percorso.

    L'attributo si chiamava `collezione_equivalente` e riceveva l'intestazione
    `x-ipzs-location`, cioè un percorso di scarico. Chi lo leggeva otteneva una
    stringa che non era né una collezione né un rimedio.
    """

    def test_porta_la_descrizione_del_servizio_e_non_una_posizione(self) -> None:
        risposta = Risposta(
            status=200,
            contenuto=b'{"stato": 5, "descrizioneStato": "troppe richieste in coda"}',
        )
        with pytest.raises(OverloadedError) as errore:
            _stato_da(risposta, "collections/download/collection-asincrona/abc123")
        assert errore.value.descrizione == "troppe richieste in coda"
        assert "abc123" not in str(errore.value)


class TestIlContoDeiRisultatiSgrammaticato:
    def test_senza_totale_la_frase_sta_in_piedi(self) -> None:
        assert str(TooManyResultsError(None, 5)).startswith("i risultati superano il massimo di 5")

    def test_col_totale_dice_quanti_erano(self) -> None:
        assert str(TooManyResultsError(9000, 100)).startswith("9000 risultati superano")


class TestUnEsitoVuotoSuMigliaiaDiRisultati:
    """`len()` contava la pagina, e una pagina vuota rendeva falso l'intero esito.

    Un esito con cinquemila atti trovati e la pagina corrente vuota era `False`
    in un `if`: la trappola era pronta e silenziosa. Adesso `EsitoRicerca` non
    ha `__len__`, e chi vuole un numero deve dire quale.
    """

    def test_non_si_puo_piu_chiedere_una_lunghezza_ambigua(self) -> None:
        esito = EsitoRicerca(atti=(), totale=5000, pagina=3, pagine=250)
        with pytest.raises(TypeError):
            len(esito)  # type: ignore[arg-type]
        assert esito.totale == 5000
        assert list(esito) == []


class TestLaSuperficieSiRaggiungeDavvero:
    """Ogni nome pubblico deve essere raggiungibile da `import normattiva`."""

    def test_i_codici_sono_raggiungibili_dal_pacchetto(self) -> None:
        import normattiva

        assert normattiva.codici.CODICE_CIVILE.nome == "Codice civile"

    def test_nessun_sottomodulo_esporta_nomi_che_il_pacchetto_nasconde(self) -> None:
        """Quello che un sottomodulo dichiara pubblico si deve poter importare.

        I codici fanno eccezione per scelta: stanno dietro il loro spazio di nomi
        (`codici.CODICE_CIVILE`), che è più leggibile di una dozzina di costanti
        sparse in cima al pacchetto. Ma lo spazio di nomi deve esserci.
        """
        import normattiva
        from normattiva import esporta, modelli, urn

        for modulo in (modelli, esporta, urn):
            mancanti = [n for n in modulo.__all__ if not hasattr(normattiva, n)]
            assert mancanti == [], f"{modulo.__name__} espone nomi irraggiungibili: {mancanti}"
        assert all(hasattr(normattiva.codici, n) for n in normattiva.codici.__all__)


class TestLUrnSiPuoChiedereInAnticipo:
    """Dodici tipi di atto su trenta non hanno una forma URN verificata.

    Scorrendo dei risultati di ricerca l'unico modo di saperlo era `try/except`
    su ogni elemento: adesso `ha_urn` lo dice senza sollevare.
    """

    def test_un_tipo_noto_lo_dichiara(self) -> None:
        estremi = EstremiAtto("LEGGE", date(1990, 8, 7), "241")
        assert estremi.ha_urn
        assert str(estremi.urn) == "urn:nir:stato:legge:1990-08-07;241"

    def test_un_tipo_storico_lo_nega_prima_di_esplodere(self) -> None:
        estremi = EstremiAtto("DECRETO DEL DUCE", date(1938, 1, 1), "1")
        assert not estremi.ha_urn
        with pytest.raises(InvalidUrnError):
            _ = estremi.urn

    def test_la_citazione_funziona_anche_dove_l_urn_non_si_sa(self) -> None:
        """Abbreviare è una convenzione editoriale, comporre un URN è un fatto verificato."""
        estremi = EstremiAtto("REGIO DECRETO-LEGGE", date(1935, 1, 13), "1")
        assert not estremi.ha_urn
        assert estremi.citazione == "R.D.L. 13 gennaio 1935, n. 1"


class TestIFiltriDellExportCheNonFiltravano:
    """L'esportazione chiama tre campi in modo diverso dalla ricerca.

    `pubblicazione` e `vigente_al` finivano dentro `parametriRicerca` coi nomi
    della ricerca interattiva: il servizio non protesta, li ignora e basta. Due
    filtri su undici erano decorativi, e il conteggio preventivo, che passa
    dalla ricerca dove i nomi sono giusti, restituiva un numero che l'export
    poi non rispettava.

    Verificato il 2026-08-24 esportando la legge 241/1990 con una finestra di
    pubblicazione nel 1800: col nome della ricerca l'atto torna lo stesso, col
    nome dell'esportazione l'archivio è vuoto. Idem per la vigenza.
    """

    @staticmethod
    def _parametri(**criteri) -> dict:
        coordinate = _coordinate(
            criteri.get("denominazione"),
            criteri.get("anno"),
            criteri.get("numero"),
            None,
            None,
            None,
            None,
            criteri.get("vigente_al"),
            None,
            None,
            criteri.get("pubblicazione"),
        )
        return _corpo_export(coordinate, Format.JSON, ExportMode.VIGENTE, {})["parametriRicerca"]

    def test_la_pubblicazione_usa_i_nomi_dell_export(self) -> None:
        parametri = self._parametri(pubblicazione=(date(1990, 1, 1), date(1990, 12, 31)))
        assert "dataInizioPubblicazione" in parametri
        assert "dataFinePubblicazione" in parametri
        assert "dataInizioPubProvvedimento" not in parametri

    def test_la_vigenza_usa_il_nome_dell_export(self) -> None:
        parametri = self._parametri(vigente_al=date(2005, 1, 1))
        assert parametri["dataVigenza"] == "2005-01-01"
        assert "vigenza" not in parametri

    def test_la_ricerca_interattiva_tiene_i_suoi(self) -> None:
        """Gli stessi criteri, mandati alla ricerca, devono avere i nomi di lei."""
        coordinate = _coordinate(
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            date(2005, 1, 1),
            None,
            None,
            (date(1990, 1, 1), date(1990, 12, 31)),
        )
        campi = _campi_avanzati(coordinate)
        assert campi["vigenza"] == "2005-01-01"
        assert "dataInizioPubProvvedimento" in campi
        assert "dataVigenza" not in campi

    def test_i_campi_comuni_non_cambiano_nome(self) -> None:
        parametri = self._parametri(denominazione="LEGGE", anno=1990, numero=241)
        assert parametri["denominazioneAtto"] == "LEGGE"
        assert parametri["annoProvvedimento"] == 1990
        assert parametri["numeroProvvedimento"] == 241


class TestGliAttiSenzaFormaUrnEranoIlleggibili:
    """Trovarli e non poterli leggere era un vicolo cieco.

    Dodici tipi su trenta non hanno una forma NIR verificata. Il servizio però
    li rende da `atto/dettaglio-atto` con codice redazionale e data di Gazzetta,
    che ogni risultato di ricerca porta già: era un endpoint della specifica che
    non avvolgevamo.
    """

    @staticmethod
    def _trovato(denominazione: str, codice: str | None = "038U0001") -> AttoTrovato:
        return AttoTrovato(
            estremi=EstremiAtto(denominazione, date(1938, 1, 1), "1"),
            gazzetta=PubblicazioneGazzetta(date(1938, 1, 1), codice_redazionale=codice),
            titolo="",
        )

    def test_un_atto_senza_urn_passa_dalle_coordinate_di_gazzetta(self) -> None:
        with respx.mock(base_url=BASE, assert_all_called=False) as api:
            rotta = api.post("/atto/dettaglio-atto").respond(200, json=carica("urn_atto_intero"))
            per_urn = api.post(f"/{URN}").respond(500, json={"error": "non deve arrivarci"})
            with Normattiva(base_url=BASE, requests_per_second=0) as client:
                assert client.dettaglio(self._trovato("DECRETO DEL DUCE")).testo
            assert not per_urn.called, "non deve provare a comporre un URN che non conosce"
            inviato = json.loads(rotta.calls.last.request.content)
            assert inviato == {"codiceRedazionale": "038U0001", "dataGU": "1938-01-01"}

    def test_un_atto_con_urn_continua_a_passare_dall_urn(self) -> None:
        with respx.mock(base_url=BASE) as api:
            rotta = api.post(f"/{URN}").respond(200, json=carica("urn_atto_intero"))
            with Normattiva(base_url=BASE, requests_per_second=0) as client:
                assert client.dettaglio(self._trovato("LEGGE")).testo
            assert "urn" in json.loads(rotta.calls.last.request.content)

    def test_senza_codice_redazionale_lo_dice_invece_di_provarci(self) -> None:
        with (
            Normattiva(base_url=BASE, requests_per_second=0) as client,
            pytest.raises(InvalidArgumentError, match="codice redazionale"),
        ):
            client.dettaglio(self._trovato("DECRETO DEL DUCE", codice=None))

    def test_una_vigenza_su_quella_strada_non_viene_ingoiata(self) -> None:
        """Il servizio accetta `dataVigenza` e la ignora: accettarla noi sarebbe peggio."""
        with (
            Normattiva(base_url=BASE, requests_per_second=0) as client,
            pytest.raises(InvalidArgumentError, match="richiede un URN"),
        ):
            client.dettaglio(self._trovato("DECRETO DEL DUCE"), vigenza=date(1940, 1, 1))


class TestUnCampoCheNonAvevoMaiVisto:
    """`ultimiAttiModificanti` era letto senza aver mai osservato un valore vero.

    Il codice lo spezzava sugli spazi presumendo un elenco. Osservato dal vivo il
    2026-08-24 nel flusso degli atti aggiornati, è davvero un elenco: di codici
    redazionali, non di titoli né di URN. Questa prova fissa quella forma: se il
    servizio passasse alla prosa, la tupla si riempirebbe di parole sciolte e
    nessuno se ne accorgerebbe.
    """

    CODICE = re.compile(r"\A\d{2}[A-Z]\d{5}\Z")

    def _atto(self, valore: object) -> AttoTrovato:
        nodo = dict(carica("ricerca_semplice")["listaAtti"][0])
        nodo["ultimiAttiModificanti"] = valore
        return _wire.leggi_ricerca({"listaAtti": [nodo], "numeroAttiTrovati": 1}).atti[0]

    def test_un_codice_solo(self) -> None:
        assert self._atto("26G00129").atti_modificanti == ("26G00129",)

    def test_piu_codici_spaziati(self) -> None:
        atto = self._atto("26G00129 25G00212")
        assert atto.atti_modificanti == ("26G00129", "25G00212")
        assert all(self.CODICE.match(c) for c in atto.atti_modificanti)

    def test_assente_resta_vuoto(self) -> None:
        assert self._atto(None).atti_modificanti == ()


class TestIlLimitatoreReggeIThread:
    """Il README promette un client condivisibile fra thread: va provato, non detto."""

    def test_sedici_thread_non_superano_il_limite(self) -> None:
        limitatore = Limitatore(20.0)
        istanti: list[float] = []
        serratura = threading.Lock()

        def turno(_: int) -> None:
            limitatore.attendi_turno()
            with serratura:
                istanti.append(time.monotonic())

        with ThreadPoolExecutor(max_workers=16) as piscina:
            list(piscina.map(turno, range(32)))

        istanti.sort()
        salti = [dopo - prima for prima, dopo in pairwise(istanti)]
        assert min(salti) >= 0.045, f"due richieste a {min(salti) * 1000:.0f} ms di distanza"
