"""Le astrazioni della libreria reggono ancora?

Le impronte guardano la forma delle risposte; qui si guarda il comportamento:
che i codici rispondano dal loro allegato, che le trappole note siano ancora
trappole, che la finestra di vigenza copra la data richiesta. Se una di queste
cade, la libreria racconta qualcosa che non è più vero.
"""

from datetime import date

import pytest

from normattiva import Normattiva, codici
from normattiva.errori import AmbiguityError, NotFoundError
from normattiva.modelli import Format

pytestmark = [pytest.mark.rete, pytest.mark.timeout(600)]

AMBIGUI = {"Testo unico dell'edilizia"}


class TestAttiNoti:
    @pytest.mark.parametrize("atto", codici.tutti(), ids=lambda a: a.nome)
    def test_l_articolo_risponde(self, client: Normattiva, atto) -> None:
        articolo = "3" if atto is codici.COSTITUZIONE else "1"
        if atto.nome in AMBIGUI:
            with pytest.raises(AmbiguityError) as ambiguita:
                client.dettaglio(atto.articolo(articolo))
            assert len(ambiguita.value.candidati) >= 2
            return
        assert client.dettaglio(atto.articolo(articolo)).testo

    def test_il_codice_civile_passa_dall_allegato(self, client: Normattiva) -> None:
        assert client.dettaglio(codici.CODICE_CIVILE.articolo("2043")).testo

    def test_senza_allegato_il_codice_civile_non_risponde(self, client: Normattiva) -> None:
        diretto = codici.CODICE_CIVILE.urn.con_articolo("2043")
        with pytest.raises(NotFoundError):
            client.dettaglio(diretto)

    def test_anche_l_atto_inesistente_e_un_atto_non_trovato(self, client: Normattiva) -> None:
        """Il servizio ha due modi di dire «non c'è», e devono arrivare uguali.

        Per un articolo che non esiste manda un 404 con `code` nullo; per un
        atto che non esiste manda un 404 con `code` uguale allo stato. Chi
        cattura `NotFoundError` non ha modo di sapere quale dei due
        riceverà, e non deve averne bisogno.
        """
        with pytest.raises(NotFoundError):
            client.dettaglio("urn:nir:stato:legge:1990-08-07;9999")


class TestTrappole:
    def test_il_troncamento_e_ancora_presente(self, client: Normattiva) -> None:
        atto = client.dettaglio("urn:nir:stato:legge:2016-12-11;232~art1")
        assert atto.possibile_troncamento
        assert atto.ultimo_comma_numerato == 100

    def test_l_ambiguita_e_ancora_presente(self, client: Normattiva) -> None:
        with pytest.raises(AmbiguityError) as errore:
            client.dettaglio("urn:nir:stato:legge:2001-12-28;448~art2")
        assert len(errore.value.candidati) >= 2

    def test_la_finestra_copre_la_data_richiesta(self, client: Normattiva) -> None:
        atto = client.dettaglio("urn:nir:stato:legge:1970-12-01;898~art5", vigenza=date(2005, 1, 1))
        assert atto.finestra is not None
        assert atto.finestra.contiene(date(2005, 1, 1))


class TestDizionari:
    def test_denominazioni(self, client: Normattiva) -> None:
        assert any(v.codice == "PLE" for v in client.denominazioni())

    def test_formati(self, client: Normattiva) -> None:
        codici_formati = {v.codice for v in client.export_formats()}
        assert {f.value for f in Format} <= codici_formati

    def test_classi(self, client: Normattiva) -> None:
        assert len(client.classi_provvedimento()) == 3


class TestRicerca:
    def test_semplice(self, client: Normattiva) -> None:
        esito = client.ricerca("divorzio", per_pagina=5)
        assert esito.totale > 0
        assert len(esito.atti) <= 5

    def test_avanzata_trova_la_241(self, client: Normattiva, nonostante_i_guasti) -> None:
        esito = nonostante_i_guasti(
            client.ricerca_avanzata, denominazione="LEGGE", anno=1990, numero=241
        )
        assert esito.atti[0].gazzetta.codice_redazionale == "090G0294"
