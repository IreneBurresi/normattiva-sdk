from datetime import date

import pytest

from normattiva import _wire
from normattiva.errori import (
    AmbiguityError,
    NotFoundError,
    NotYetInForceError,
    RequestBlockedError,
    RuleCode,
    RuleViolationError,
    UnexpectedResponseError,
)
from tests.dati import FIXTURES, carica


class TestLeggiData:
    @pytest.mark.parametrize(
        ("grezza", "attesa"),
        [
            ("19900807", date(1990, 8, 7)),
            ("1990-08-07", date(1990, 8, 7)),
            ("07/08/1990", date(1990, 8, 7)),
            ("1990-08-07T00:00:00Z", date(1990, 8, 7)),
            ("1990-08-07T00:00:00+00:00", date(1990, 8, 7)),
        ],
    )
    def test_forme_ammesse(self, grezza: str, attesa: date) -> None:
        assert _wire.leggi_data(grezza) == attesa

    @pytest.mark.parametrize("vuota", [None, "", "  ", "99999999", "0"])
    def test_assenze(self, vuota: str | None) -> None:
        assert _wire.leggi_data(vuota) is None

    def test_data_incomprensibile(self) -> None:
        with pytest.raises(UnexpectedResponseError):
            _wire.leggi_data("non una data")

    def test_data_impossibile(self) -> None:
        with pytest.raises(UnexpectedResponseError):
            _wire.leggi_data("19901345")


class TestLeggiFinestra:
    def test_finestra_chiusa(self) -> None:
        finestra = _wire.leggi_finestra("19870312", "20230227")
        assert finestra.inizio == date(1987, 3, 12)
        assert finestra.fine == date(2023, 2, 27)

    def test_finestra_aperta(self) -> None:
        assert _wire.leggi_finestra("20150614", "99999999").aperta

    def test_articolo_non_ancora_vigente(self) -> None:
        with pytest.raises(NotYetInForceError) as errore:
            _wire.leggi_finestra("0", "19820928")
        assert errore.value.vigente_dal == date(1982, 9, 29)

    def test_inizio_non_dichiarato_su_finestra_aperta(self) -> None:
        assert _wire.leggi_finestra("0", "99999999") is None


class TestLeggiDettaglio:
    def test_estremi(self) -> None:
        atto = _wire.leggi_dettaglio(carica("urn_vigenza_finestra"))
        assert atto.estremi.denominazione == "LEGGE"
        assert atto.estremi.data == date(1970, 12, 1)
        assert atto.estremi.numero == "898"
        assert atto.estremi.codice_tipo == "PLE"

    def test_gazzetta(self) -> None:
        atto = _wire.leggi_dettaglio(carica("urn_vigenza_finestra"))
        assert atto.gazzetta.data == date(1970, 12, 3)
        assert atto.gazzetta.numero == 306
        assert atto.gazzetta.codice_redazionale is None

    def test_finestra(self) -> None:
        atto = _wire.leggi_dettaglio(carica("urn_vigenza_finestra"))
        assert atto.finestra.contiene(date(2005, 1, 1))

    def test_titolo_e_sottotitolo_ripuliti(self) -> None:
        atto = _wire.leggi_dettaglio(carica("urn_articolo_allegato"))
        assert not atto.titolo.endswith("\n")
        assert atto.sottotitolo is not None
        assert "\r" not in atto.sottotitolo

    def test_testo_disponibile(self) -> None:
        assert _wire.leggi_dettaglio(carica("urn_vigenza_finestra")).testo

    def test_ambiguita(self) -> None:
        with pytest.raises(AmbiguityError) as errore:
            _wire.leggi_dettaglio(carica("urn_ambiguo"))
        assert len(errore.value.candidati) == 2

    def test_candidato_senza_inizio_dichiarato_non_fa_fallire(self) -> None:
        with pytest.raises(AmbiguityError) as errore:
            _wire.leggi_dettaglio(carica("urn_ambiguo"))
        assert any(c.finestra is None for c in errore.value.candidati)

    def test_candidati_distinguibili_dalla_gazzetta(self) -> None:
        with pytest.raises(AmbiguityError) as errore:
            _wire.leggi_dettaglio(carica("urn_ambiguo"))
        gazzette = {c.gazzetta.data for c in errore.value.candidati}
        assert len(gazzette) == 2

    def test_articolo_non_ancora_vigente(self) -> None:
        with pytest.raises(NotYetInForceError):
            _wire.leggi_dettaglio(carica("urn_non_ancora_vigente"))

    def test_envelope_senza_atto(self) -> None:
        with pytest.raises(NotFoundError):
            _wire.leggi_dettaglio({"data": {"atto": None, "lista": None}, "success": True})

    def test_envelope_malformato(self) -> None:
        with pytest.raises(UnexpectedResponseError):
            _wire.leggi_dettaglio({"qualcosa": "altro"})


class TestLeggiRicerca:
    def test_totale_e_pagine(self) -> None:
        esito = _wire.leggi_ricerca(carica("ricerca_semplice"))
        assert esito.totale == 87
        assert esito.pagine == 18
        assert esito.pagina == 1

    def test_numero_elementi_dichiarato_dal_server_ignorato(self) -> None:
        esito = _wire.leggi_ricerca(carica("ricerca_semplice"))
        assert len(esito.atti) == 5

    def test_atto_trovato(self) -> None:
        atto = _wire.leggi_ricerca(carica("ricerca_avanzata")).atti[0]
        assert atto.estremi.numero == "241"
        assert atto.estremi.data == date(1990, 8, 7)
        assert atto.gazzetta.codice_redazionale == "090G0294"
        assert str(atto.urn) == "urn:nir:stato:legge:1990-08-07;241"

    def test_titolo_ripulito(self) -> None:
        atto = _wire.leggi_ricerca(carica("ricerca_avanzata")).atti[0]
        assert not atto.titolo.startswith("[")
        assert "\r" not in atto.titolo

    def test_faccette(self) -> None:
        faccette = _wire.leggi_ricerca(carica("ricerca_avanzata")).faccette
        assert faccette.per_tipo[0].codice == "PLE"
        assert faccette.per_tipo[0].conteggio == 1
        assert faccette.per_anno[0].codice == "1990"

    def test_aggiornati_porta_la_data_di_modifica(self) -> None:
        atti = _wire.leggi_ricerca(carica("ricerca_aggiornati")).atti
        assert any(a.ultima_modifica is not None for a in atti)

    def test_atti_modificanti_divisi(self) -> None:
        atti = _wire.leggi_ricerca(carica("ricerca_aggiornati")).atti
        modificanti = [a.atti_modificanti for a in atti if a.atti_modificanti]
        assert modificanti
        assert all(" " not in codice for codici in modificanti for codice in codici)

    def test_risposta_vuota(self) -> None:
        esito = _wire.leggi_ricerca({"listaAtti": [], "numeroAttiTrovati": 0})
        assert esito.totale == 0
        assert esito.atti == ()


class TestLeggiTipologiche:
    def test_denominazioni(self) -> None:
        voci = _wire.leggi_denominazioni(carica("tipologiche_denominazione_atto"))
        codici = {v.codice: v.descrizione for v in voci}
        assert codici["PLE"] == "LEGGE"
        assert len(voci) == 30

    def test_classi_provvedimento(self) -> None:
        voci = _wire.leggi_classi(carica("tipologiche_classe_provvedimento"))
        assert {v.codice for v in voci} == {"1", "2", "3"}
        assert "abrogato" in {v.codice: v.descrizione for v in voci}["3"]

    def test_estensioni(self) -> None:
        voci = _wire.leggi_estensioni(carica("tipologiche_estensioni"))
        assert "AKN" in {v.codice for v in voci}
        assert len(voci) == 8


class TestErrori:
    def test_waf_bloccante(self) -> None:
        contenuto = (FIXTURES / "errore_409_waf.html").read_bytes()
        with pytest.raises(RequestBlockedError):
            _wire.solleva_errore(409, contenuto, "text/html")

    def test_regola_di_business_riconosciuta(self) -> None:
        with pytest.raises(RuleViolationError) as errore:
            _wire.solleva_errore(
                400,
                b'{"message":"periodo troppo lungo","code":"1501"}',
                "application/json",
            )
        assert errore.value.regola is RuleCode.INTERVALLO_OLTRE_12_MESI
        assert errore.value.codice == 1501

    def test_codice_ignoto_degrada(self) -> None:
        with pytest.raises(RuleViolationError) as errore:
            _wire.solleva_errore(400, b'{"message":"boh","code":"9999"}', "application/json")
        assert errore.value.regola is None
        assert errore.value.codice == 9999

    def test_404_di_business(self) -> None:
        contenuto = (FIXTURES / "errore_404_business.json").read_bytes()
        with pytest.raises(NotFoundError):
            _wire.solleva_errore(404, contenuto, "application/json")

    def test_404_che_ripete_lo_stato_e_un_atto_che_non_c_e(self) -> None:
        """Il `code` di questo 404 è lo stato HTTP, non una regola di business.

        È la forma che il servizio rende per un atto inesistente, ed è diversa
        da quella dell'articolo inesistente, che porta `code` nullo. Chiamarla
        regola violata manderebbe a correggere una richiesta scritta bene.
        """
        contenuto = (FIXTURES / "errore_404_atto_assente.json").read_bytes()
        with pytest.raises(NotFoundError):
            _wire.solleva_errore(404, contenuto, "application/json")

    def test_un_codice_che_ripete_lo_stato_non_e_una_regola(self) -> None:
        with pytest.raises(UnexpectedResponseError):
            _wire.solleva_errore(400, b'{"message":"boh","code":"400"}', "application/json")

    def test_404_non_espone_i_parametri_interni(self) -> None:
        contenuto = (FIXTURES / "errore_404_business.json").read_bytes()
        with pytest.raises(NotFoundError) as errore:
            _wire.solleva_errore(404, contenuto, "application/json")
        assert "codiceRedazionale" not in str(errore.value)

    def test_500_spring(self) -> None:
        contenuto = (FIXTURES / "errore_500_spring.json").read_bytes()
        with pytest.raises(UnexpectedResponseError):
            _wire.solleva_errore(500, contenuto, "application/json")

    def test_corpo_illeggibile(self) -> None:
        with pytest.raises(UnexpectedResponseError):
            _wire.solleva_errore(500, b"<html>errore</html>", "text/html")


class TestLeggiCorpus:
    @pytest.fixture
    def atti(self):
        return _wire.leggi_corpus((FIXTURES / "export_multivigente.zip").read_bytes())

    def test_un_solo_atto(self, atti) -> None:
        assert len(atti) == 1

    def test_urn_ed_estremi(self, atti) -> None:
        atto = atti[0]
        assert str(atto.urn) == "urn:nir:stato:legge:1990-08-07;241"
        assert atto.estremi.numero == "241"
        assert atto.eli is not None

    def test_versioni_ordinate(self, atti) -> None:
        versioni = atti[0].versioni
        assert versioni[0].originale
        date_vigenza = [v.vigente_dal for v in versioni if v.vigente_dal]
        assert date_vigenza == sorted(date_vigenza)

    def test_articolato_ad_albero(self, atti) -> None:
        prima = atti[0].versioni[0]
        assert prima.articolato
        assert prima.articolato[0].tipo is None
        assert prima.articolato[0].figli

    def test_articoli_raggiungibili(self, atti) -> None:
        articoli = list(atti[0].versioni[-1].articoli())
        assert [a.numero for a in articoli][:3] == ["1", "2", "2 bis"]

    def test_finestre_per_articolo(self, atti) -> None:
        articoli = list(atti[0].versioni[-1].articoli())
        assert articoli[0].finestre
        assert articoli[0].finestre[0].aperta

    def test_alla_data(self, atti) -> None:
        versione = atti[0].alla_data(date(1990, 12, 25))
        assert versione.vigente_dal == date(1990, 12, 20)

    def test_non_abrogato(self, atti) -> None:
        assert atti[0].abrogato is False

    def test_aggiornamenti_letti(self, atti) -> None:
        assert atti[0].aggiornamenti
        assert atti[0].aggiornamenti[0].data.year > 1990

    def test_archivio_non_zip(self) -> None:
        with pytest.raises(UnexpectedResponseError):
            _wire.leggi_corpus(b"non uno zip")
