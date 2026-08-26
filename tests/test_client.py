import json
from datetime import date

import httpx
import pytest
import respx

from normattiva import Normattiva, Urn, codici
from normattiva.client import PASSI_MASSIMI
from normattiva.errori import (
    AmbiguityError,
    RuleCode,
    RuleViolationError,
    TruncationError,
    UnexpectedResponseError,
    ValidityMismatchError,
)
from normattiva.modelli import ClasseProvvedimento, Format
from tests.dati import FIXTURES, carica

BASE = "https://esempio.invalid/api"
URN = "atto/dettaglio-atto-urn"


@pytest.fixture
def api():
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        yield router


@pytest.fixture
def client() -> Normattiva:
    with Normattiva(base_url=BASE, requests_per_second=0) as normattiva:
        yield normattiva


def corpo_di(rotta) -> dict:
    return json.loads(rotta.calls.last.request.content)


class TestDettaglio:
    def test_urn_inviato(self, api, client: Normattiva) -> None:
        rotta = api.post(f"/{URN}").respond(200, json=carica("urn_vigenza_finestra"))
        client.dettaglio("urn:nir:stato:legge:1970-12-01;898~art5")
        assert corpo_di(rotta)["urn"] == "urn:nir:stato:legge:1970-12-01;898~art5"

    def test_accetta_un_oggetto_urn(self, api, client: Normattiva) -> None:
        rotta = api.post(f"/{URN}").respond(200, json=carica("urn_vigenza_finestra"))
        client.dettaglio(Urn.legge(1970, 898, articolo="5"))
        assert corpo_di(rotta)["urn"] == "urn:nir:stato:legge:1970;898~art5"

    def test_accetta_un_atto_noto(self, api, client: Normattiva) -> None:
        rotta = api.post(f"/{URN}").respond(200, json=carica("urn_articolo_allegato"))
        client.dettaglio(codici.CODICE_PENALE.articolo("416bis"))
        assert ":1~art416bis" in corpo_di(rotta)["urn"]

    def test_vigenza_aggiunta_all_urn(self, api, client: Normattiva) -> None:
        rotta = api.post(f"/{URN}").respond(200, json=carica("urn_vigenza_finestra"))
        client.dettaglio("urn:nir:stato:legge:1970-12-01;898~art5", vigenza=date(2005, 1, 1))
        assert corpo_di(rotta)["urn"].endswith("!vig=2005-01-01")

    def test_vigenza_originale(self, api, client: Normattiva) -> None:
        rotta = api.post(f"/{URN}").respond(200, json=carica("urn_vigenza_finestra"))
        client.dettaglio("urn:nir:stato:legge:1970-12-01;898~art5", vigenza="originale")
        assert corpo_di(rotta)["urn"].endswith("@originale")

    def test_comma_tolto_dall_urn(self, api, client: Normattiva) -> None:
        rotta = api.post(f"/{URN}").respond(200, json=carica("urn_vigenza_finestra"))
        client.dettaglio("urn:nir:stato:legge:2007-12-24;244~art2-com428")
        assert "-com" not in corpo_di(rotta)["urn"]

    def test_vigenza_in_conflitto_con_l_urn(self, client: Normattiva) -> None:
        with pytest.raises(ValueError, match="vigenza"):
            client.dettaglio(
                "urn:nir:stato:legge:1970-12-01;898~art5!vig=2010-01-01",
                vigenza=date(2005, 1, 1),
            )

    def test_vigenza_ripetuta_uguale_va_bene(self, api, client: Normattiva) -> None:
        api.post(f"/{URN}").respond(200, json=carica("urn_vigenza_finestra"))
        client.dettaglio(
            "urn:nir:stato:legge:1970-12-01;898!vig=2005-01-01", vigenza=date(2005, 1, 1)
        )

    def test_modello_restituito(self, api, client: Normattiva) -> None:
        api.post(f"/{URN}").respond(200, json=carica("urn_vigenza_finestra"))
        atto = client.dettaglio("urn:nir:stato:legge:1970-12-01;898~art5")
        assert atto.atto.numero == "898"
        assert atto.testo

    def test_ambiguita_propagata(self, api, client: Normattiva) -> None:
        api.post(f"/{URN}").respond(200, json=carica("urn_ambiguo"))
        with pytest.raises(AmbiguityError):
            client.dettaglio("urn:nir:stato:legge:2001-12-28;448~art2")

    def test_urn_non_valido_non_tocca_la_rete(self, api, client: Normattiva) -> None:
        rotta = api.post(f"/{URN}").respond(200, json={})
        with pytest.raises(ValueError, match="URN non valido"):
            client.dettaglio("legge 241 del 1990")
        assert rotta.call_count == 0


class TestVerificaDellaVigenza:
    def test_finestra_incoerente_rifiutata(self, api, client: Normattiva) -> None:
        api.post(f"/{URN}").respond(200, json=carica("urn_vigenza_finestra"))
        with pytest.raises(ValidityMismatchError) as errore:
            client.dettaglio("urn:nir:stato:legge:1970-12-01;898~art5", vigenza=date(1980, 1, 1))
        assert errore.value.richiesta == date(1980, 1, 1)

    def test_finestra_coerente_accettata(self, api, client: Normattiva) -> None:
        api.post(f"/{URN}").respond(200, json=carica("urn_vigenza_finestra"))
        atto = client.dettaglio("urn:nir:stato:legge:1970-12-01;898~art5", vigenza=date(2005, 1, 1))
        assert atto.finestra is not None

    def test_senza_vigenza_nessuna_verifica(self, api, client: Normattiva) -> None:
        api.post(f"/{URN}").respond(200, json=carica("urn_vigenza_finestra"))
        assert client.dettaglio("urn:nir:stato:legge:1970-12-01;898~art5")


class TestTroncamento:
    def test_dichiarato_per_impostazione(self, api, client: Normattiva) -> None:
        api.post(f"/{URN}").respond(200, json=carica("urn_troncato_100_commi"))
        atto = client.dettaglio("urn:nir:stato:legge:2016-12-11;232~art1")
        assert atto.possibile_troncamento

    def test_sollevato_su_richiesta(self, api, client: Normattiva) -> None:
        api.post(f"/{URN}").respond(200, json=carica("urn_troncato_100_commi"))
        with pytest.raises(TruncationError):
            client.dettaglio("urn:nir:stato:legge:2016-12-11;232~art1", se_troncato="solleva")

    def test_articolo_integro_non_solleva(self, api, client: Normattiva) -> None:
        api.post(f"/{URN}").respond(200, json=carica("urn_articolo_con_commi"))
        assert client.dettaglio("urn:nir:stato:legge:1990-08-07;241~art2", se_troncato="solleva")

    def test_valore_ignoto_rifiutato(self, client: Normattiva) -> None:
        with pytest.raises(ValueError, match="se_troncato"):
            client.dettaglio("urn:nir:stato:legge:1990;241", se_troncato="ignora")


class TestCronologia:
    def _finestre(self, *periodi: tuple[str, str]) -> list[httpx.Response]:
        modello = carica("urn_vigenza_finestra")
        risposte = []
        for inizio, fine in periodi:
            copia = json.loads(json.dumps(modello))
            copia["data"]["atto"]["articoloDataInizioVigenza"] = inizio
            copia["data"]["atto"]["articoloDataFineVigenza"] = fine
            risposte.append(httpx.Response(200, json=copia))
        return risposte

    def test_percorre_le_finestre(self, api, client: Normattiva) -> None:
        rotta = api.post(f"/{URN}").mock(
            side_effect=self._finestre(
                ("19900902", "19920610"), ("19920611", "19931231"), ("19940101", "99999999")
            )
        )
        versioni = list(client.cronologia("urn:nir:stato:legge:1990-08-07;241~art19"))
        assert len(versioni) == 3
        assert rotta.call_count == 3

    def test_parte_dall_originale(self, api, client: Normattiva) -> None:
        rotta = api.post(f"/{URN}").mock(side_effect=self._finestre(("19900902", "99999999")))
        list(client.cronologia("urn:nir:stato:legge:1990-08-07;241~art19"))
        assert corpo_di(rotta)["urn"].endswith("@originale")

    def test_chiede_il_giorno_dopo_la_chiusura(self, api, client: Normattiva) -> None:
        rotta = api.post(f"/{URN}").mock(
            side_effect=self._finestre(("19900902", "19920610"), ("19920611", "99999999"))
        )
        list(client.cronologia("urn:nir:stato:legge:1990-08-07;241~art19"))
        assert corpo_di(rotta)["urn"].endswith("!vig=1992-06-11")

    def test_si_ferma_sulla_finestra_aperta(self, api, client: Normattiva) -> None:
        api.post(f"/{URN}").mock(side_effect=self._finestre(("19900902", "99999999")))
        assert len(list(client.cronologia("urn:nir:stato:legge:1990-08-07;241~art19"))) == 1

    def test_il_limite_prende_le_prime_versioni(self, api, client: Normattiva) -> None:
        rotta = api.post(f"/{URN}").mock(
            side_effect=self._finestre(*[("19900902", "19920610")] * 5)
        )
        versioni = list(client.cronologia("urn:nir:stato:legge:1990-08-07;241~art19", massimo=3))
        assert len(versioni) == 3
        assert rotta.call_count == 3

    def test_una_catena_che_non_si_chiude_viene_denunciata(self, api, client: Normattiva) -> None:
        api.post(f"/{URN}").mock(
            side_effect=self._finestre(*[("19900902", "19920610")] * (PASSI_MASSIMI + 1))
        )
        with pytest.raises(UnexpectedResponseError, match="non si chiude"):
            list(client.cronologia("urn:nir:stato:legge:1990-08-07;241~art19"))

    def test_e_pigra(self, api, client: Normattiva) -> None:
        rotta = api.post(f"/{URN}").mock(side_effect=self._finestre(("19900902", "99999999")))
        client.cronologia("urn:nir:stato:legge:1990-08-07;241~art19")
        assert rotta.call_count == 0


class TestRicerca:
    def test_paginazione_sempre_inviata(self, api, client: Normattiva) -> None:
        rotta = api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        client.ricerca("divorzio")
        assert corpo_di(rotta)["paginazione"] == {
            "paginaCorrente": 1,
            "numeroElementiPerPagina": 20,
        }

    def test_testo_e_ordine(self, api, client: Normattiva) -> None:
        """`sort` è pubblico in inglese, ma al servizio arriva la parola che lui conosce."""
        rotta = api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        client.ricerca("divorzio", sort="oldest")
        assert corpo_di(rotta)["testoRicerca"] == "divorzio"
        assert corpo_di(rotta)["orderType"] == "vecchio"

    def test_faccette_come_filtri(self, api, client: Normattiva) -> None:
        rotta = api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        client.ricerca("trasparenza", tipo="PLE", anno=2016)
        assert corpo_di(rotta)["filtriMap"] == {
            "codice_tipo_provvedimento": "PLE",
            "anno_provvedimento": "2016",
        }

    def test_esito(self, api, client: Normattiva) -> None:
        api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        esito = client.ricerca("divorzio")
        assert esito.totale == 87
        assert len(esito.atti) == 5

    def test_testo_vuoto_non_tocca_la_rete(self, api, client: Normattiva) -> None:
        rotta = api.post("/ricerca/semplice").respond(200, json={})
        with pytest.raises(ValueError, match="testo"):
            client.ricerca("   ")
        assert rotta.call_count == 0


class TestRicercaAvanzata:
    def test_coordinate(self, api, client: Normattiva) -> None:
        rotta = api.post("/ricerca/avanzata").respond(200, json=carica("ricerca_avanzata"))
        client.ricerca_avanzata(denominazione="LEGGE", anno=1990, numero=241)
        corpo = corpo_di(rotta)
        assert corpo["denominazioneAtto"] == "LEGGE"
        assert corpo["annoProvvedimento"] == 1990
        assert corpo["numeroProvvedimento"] == 241

    def test_campi_vuoti_omessi(self, api, client: Normattiva) -> None:
        rotta = api.post("/ricerca/avanzata").respond(200, json=carica("ricerca_avanzata"))
        client.ricerca_avanzata(anno=1990)
        assert "titoloRicerca" not in corpo_di(rotta)

    def test_vigenza_formattata(self, api, client: Normattiva) -> None:
        rotta = api.post("/ricerca/avanzata").respond(200, json=carica("ricerca_avanzata"))
        client.ricerca_avanzata(anno=1990, vigente_al=date(2020, 1, 1))
        assert corpo_di(rotta)["vigenza"] == "2020-01-01"

    def test_classe_come_enum(self, api, client: Normattiva) -> None:
        rotta = api.post("/ricerca/avanzata").respond(200, json=carica("ricerca_avanzata"))
        client.ricerca_avanzata(anno=1990, classe=ClasseProvvedimento.ABROGATO)
        assert corpo_di(rotta)["classeProvvedimento"] == "3"

    def test_senza_criteri_chiede_tutto_il_corpus(self, api, client: Normattiva) -> None:
        """Il servizio accetta la domanda e risponde con tutto: non la rifiutiamo noi."""
        rotta = api.post("/ricerca/avanzata").respond(200, json=carica("ricerca_avanzata"))
        client.ricerca_avanzata()
        assert rotta.call_count == 1
        assert "denominazioneAtto" not in corpo_di(rotta)

    def test_un_anno_fuori_copertura_lo_decide_il_servizio(self, api, client: Normattiva) -> None:
        """Normattiva parte dal 1861 e agli anni prima risponde «zero atti», non con un errore."""
        rotta = api.post("/ricerca/avanzata").respond(
            200, json={"listaAtti": [], "numeroAttiTrovati": 0}
        )
        assert client.ricerca_avanzata(anno=1800).totale == 0
        assert rotta.call_count == 1


class TestRicercaCompleta:
    def test_scorre_le_pagine(self, api, client: Normattiva) -> None:
        pagina = carica("ricerca_semplice")
        pagina["numeroAttiTrovati"] = 10
        pagina["numeroPagine"] = 2
        rotta = api.post("/ricerca/semplice").mock(
            side_effect=[
                httpx.Response(200, json={**pagina, "paginaCorrente": 1}),
                httpx.Response(200, json={**pagina, "paginaCorrente": 2}),
            ]
        )
        atti = list(client.ricerca_completa("divorzio"))
        assert len(atti) == 10
        assert rotta.call_count == 2

    def test_il_limite_prende_i_primi(self, api, client: Normattiva) -> None:
        rotta = api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        atti = list(client.ricerca_completa("divorzio", massimo=3))
        assert len(atti) == 3
        assert rotta.call_count == 1, "una pagina sola per tre risultati"

    def test_non_chiede_una_pagina_piu_grande_del_limite(self, api, client: Normattiva) -> None:
        rotta = api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        list(client.ricerca_completa("divorzio", massimo=2, per_pagina=50))
        assert corpo_di(rotta)["paginazione"]["numeroElementiPerPagina"] == 2

    def test_e_pigra(self, api, client: Normattiva) -> None:
        rotta = api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        client.ricerca_completa("divorzio")
        assert rotta.call_count == 0

    def test_per_impostazione_scorre_tutto(self, api, client: Normattiva) -> None:
        pagina = carica("ricerca_semplice")
        pagina["numeroAttiTrovati"] = 5
        pagina["numeroPagine"] = 1
        rotta = api.post("/ricerca/semplice").respond(200, json=pagina)
        assert len(list(client.ricerca_completa("divorzio"))) == 5
        assert rotta.call_count == 1

    def test_il_totale_conta_piu_del_numero_di_pagine(self, api, client: Normattiva) -> None:
        """Un `numeroPagine` sbagliato tronca in silenzio; il totale no."""
        pagina = carica("ricerca_semplice")
        pagina["numeroAttiTrovati"] = 15
        pagina["numeroPagine"] = 1
        api.post("/ricerca/semplice").respond(200, json=pagina)
        assert len(list(client.ricerca_completa("divorzio"))) == 15


class TestAttiAggiornati:
    def test_intervallo_inviato(self, api, client: Normattiva) -> None:
        rotta = api.post("/ricerca/aggiornati").respond(200, json=carica("ricerca_aggiornati"))
        list(client.atti_aggiornati(date(2026, 8, 1), date(2026, 8, 20)))
        corpo = corpo_di(rotta)
        assert corpo["dataInizioAggiornamento"].startswith("2026-08-01")
        assert corpo["dataFineAggiornamento"].startswith("2026-08-20")

    def test_date_invertite_bloccate_in_locale(self, api, client: Normattiva) -> None:
        rotta = api.post("/ricerca/aggiornati").respond(200, json={})
        with pytest.raises(RuleViolationError) as errore:
            list(client.atti_aggiornati(date(2026, 8, 20), date(2026, 8, 1)))
        assert errore.value.regola is RuleCode.DATE_INVERTITE
        assert rotta.call_count == 0

    def test_intervallo_lungo_spezzato(self, api, client: Normattiva) -> None:
        rotta = api.post("/ricerca/aggiornati").respond(200, json=carica("ricerca_aggiornati"))
        list(client.atti_aggiornati(date(2020, 1, 1), date(2023, 1, 1)))
        assert rotta.call_count == 4

    def test_finestre_non_si_sovrappongono(self, api, client: Normattiva) -> None:
        rotta = api.post("/ricerca/aggiornati").respond(200, json=carica("ricerca_aggiornati"))
        list(client.atti_aggiornati(date(2020, 1, 1), date(2022, 6, 1)))
        inizi = [json.loads(c.request.content)["dataInizioAggiornamento"] for c in rotta.calls]
        assert len(set(inizi)) == len(inizi)


class TestTipologiche:
    def test_denominazioni(self, api, client: Normattiva) -> None:
        api.get("/tipologiche/denominazione-atto").respond(
            200, json=carica("tipologiche_denominazione_atto")
        )
        assert any(v.codice == "PLE" for v in client.denominazioni())

    def test_cache_per_istanza(self, api, client: Normattiva) -> None:
        rotta = api.get("/tipologiche/denominazione-atto").respond(
            200, json=carica("tipologiche_denominazione_atto")
        )
        client.denominazioni()
        client.denominazioni()
        assert rotta.call_count == 1

    def test_ricarica_forzata(self, api, client: Normattiva) -> None:
        rotta = api.get("/tipologiche/denominazione-atto").respond(
            200, json=carica("tipologiche_denominazione_atto")
        )
        client.denominazioni()
        client.denominazioni(reload=True)
        assert rotta.call_count == 2

    def test_classi(self, api, client: Normattiva) -> None:
        api.get("/tipologiche/classe-provvedimento").respond(
            200, json=carica("tipologiche_classe_provvedimento")
        )
        assert len(client.classi_provvedimento()) == 3

    def test_formati(self, api, client: Normattiva) -> None:
        api.get("/tipologiche/estensioni").respond(200, json=carica("tipologiche_estensioni"))
        assert len(client.export_formats()) == 8


class TestCollezioni:
    def test_catalogo(self, api, client: Normattiva) -> None:
        api.get("/collections/collection-predefinite").respond(
            200,
            json=[
                {
                    "nomeCollezione": "Regi decreti",
                    "formatoCollezione": "JSON",
                    "numeroAtti": 91346,
                }
            ],
        )
        collezioni = client.collections()
        assert collezioni[0].name == "Regi decreti"
        assert collezioni[0].total_atti == 91346

    def test_scarica(self, api, client: Normattiva) -> None:
        rotta = api.get("/collections/download/collection-preconfezionata").respond(
            200, content=(FIXTURES / "export_multivigente.zip").read_bytes()
        )
        corpus = client.download_collection("Leggi di delegazione europea")
        assert len(corpus.atti) == 1
        assert rotta.calls.last.request.url.path.endswith("collection-preconfezionata")
        parametri = rotta.calls.last.request.url.params
        assert parametri["nome"] == "Leggi di delegazione europea"
        assert parametri["formato"] == "JSON"
        assert parametri["formatoRichiesta"] == "V"


class TestFormatiDelleCollezioni:
    def test_un_formato_che_non_sappiamo_leggere_lo_dice_subito(
        self, api, client: Normattiva
    ) -> None:
        rotta = api.get("/collections/download/collection-preconfezionata").respond(200)
        with pytest.raises(ValueError, match="save_collection"):
            client.download_collection("Regi decreti", format=Format.AKN)
        assert rotta.call_count == 0, "non si scarica un archivio che non sapremmo leggere"

    def test_ogni_formato_si_salva_su_disco(self, api, client: Normattiva, tmp_path) -> None:
        api.get("/collections/download/collection-preconfezionata").respond(200, content=b"<akn/>")
        percorso = client.save_collection("Regi decreti", tmp_path / "regi.zip", format=Format.AKN)
        assert percorso.read_bytes() == b"<akn/>"


class TestCicloDiVita:
    def test_context_manager(self) -> None:
        with Normattiva(base_url=BASE) as client:
            pass
        assert client.closed

    def test_client_http_iniettabile(self) -> None:
        mio = httpx.Client()
        with Normattiva(base_url=BASE, http_client=mio):
            pass
        assert not mio.is_closed
        mio.close()

    def test_base_url_predefinito(self) -> None:
        with Normattiva() as client:
            assert "api.normattiva.it" in client.base_url
