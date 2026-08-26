"""Come i modelli vengono scritti: allineamenti, capoversi, colonne.

Sono promesse piccole ma visibili a chiunque usi la riga di comando, e sono il
genere di cosa che si rompe riordinando un `if`. Qui vengono guardate una per
una, senza passare dai comandi, perché il difetto sia dove il test lo indica.
"""

from __future__ import annotations

from datetime import date

import pytest

from normattiva import _output, _wire
from normattiva.modelli import Collection, Faccetta, FinestraVigenza
from tests.dati import carica

PIATTO = _output.Stile(colori=False, larghezza=40)
COLORATO = _output.Stile(colori=True, larghezza=40)


def dettaglio(nome: str):
    return _wire.leggi_dettaglio(carica(nome))


class TestLoStile:
    def test_senza_colori_non_aggiunge_niente(self) -> None:
        assert PIATTO.forte("ciao") == "ciao"
        assert PIATTO.tenue("ciao") == "ciao"

    def test_con_i_colori_avvolge_e_richiude(self) -> None:
        """Una sequenza aperta e mai chiusa colora tutto quello che viene dopo."""
        for reso in (COLORATO.forte("ciao"), COLORATO.tenue("ciao")):
            assert "ciao" in reso
            assert reso.endswith("\x1b[0m")


class TestLaScheda:
    def test_le_etichette_sono_incolonnate(self) -> None:
        reso = _output.scheda(PIATTO, [("Anno", "1990"), ("Denominazione", "legge")])
        assert [riga.index("1990") for riga in reso.splitlines()[:1]] == [
            reso.splitlines()[1].index("legge")
        ]

    def test_i_valori_assenti_spariscono_con_la_loro_etichetta(self) -> None:
        reso = _output.scheda(PIATTO, [("Anno", "1990"), ("Numero", None), ("Comma", "")])
        assert "Numero" not in reso
        assert "Comma" not in reso

    def test_una_scheda_senza_niente_non_e_una_riga_vuota(self) -> None:
        """Una stringa vuota sparisce da `blocchi`; una riga bianca no."""
        assert _output.scheda(PIATTO, [("Anno", None)]) == ""


class TestLaTabella:
    def test_le_colonne_seguono_la_cella_piu_lunga(self) -> None:
        reso = _output.tabella(PIATTO, ["a", "b"], [["lunghissimo", "x"], ["c", "y"]])
        prima, seconda, terza = reso.splitlines()
        assert prima.index("b") == seconda.index("x") == terza.index("y")

    def test_niente_righe_niente_tabella(self) -> None:
        assert _output.tabella(PIATTO, ["a"], []) == ""

    def test_non_lascia_spazi_in_coda(self) -> None:
        reso = _output.tabella(PIATTO, ["a", "b"], [["c", "d"]])
        assert not any(riga.endswith(" ") for riga in reso.splitlines())


class TestLaProsa:
    def test_i_capoversi_vanno_a_capo_alla_larghezza_chiesta(self) -> None:
        reso = _output.prosa(PIATTO, "parola " * 30)
        assert max(len(riga) for riga in reso.splitlines()) <= PIATTO.larghezza

    def test_le_righe_bianche_restano_bianche(self) -> None:
        assert _output.prosa(PIATTO, "uno\n\ndue") == "uno\n\ndue"

    def test_le_parole_troppo_lunghe_sporgono_invece_di_spezzarsi(self) -> None:
        """Un URN spezzato a metà riga non si copia più: meglio una riga che sporge."""
        lungo = "urn:nir:stato:decreto.del.presidente.della.repubblica:1988-09-22;447"
        assert lungo in _output.prosa(_output.Stile(larghezza=10), lungo)

    def test_gli_ordinali_col_trattino_restano_interi(self) -> None:
        assert "416-bis" in _output.prosa(_output.Stile(larghezza=8), "articolo 416-bis")


class TestIBlocchi:
    def test_i_pezzi_vuoti_non_lasciano_righe_bianche(self) -> None:
        assert _output.blocchi("uno", "", "due") == "uno\n\ndue"


class TestL_Atto:
    def test_le_note_di_aggiornamento_hanno_un_titolo(self) -> None:
        atto = dettaglio("urn_articolo_con_aggiornamento")
        assert atto.note_aggiornamento, "la fixture non porta più note: prova a vuoto"
        assert "Note di aggiornamento" in _output.mostra_atto(PIATTO, atto)

    def test_senza_note_non_c_e_il_titolo(self) -> None:
        atto = dettaglio("urn_atto_intero")
        assert atto.note_aggiornamento is None
        assert "Note di aggiornamento" not in _output.mostra_atto(PIATTO, atto)

    def test_l_urn_chiesto_ha_la_precedenza_su_quello_dell_atto(self) -> None:
        """Quello chiesto porta l'articolo e la vigenza; quello dell'atto no."""
        from normattiva import Urn

        chiesto = Urn.parse("urn:nir:stato:regio.decreto:1942-03-16;262:2~art2043")
        reso = _output.mostra_atto(PIATTO, dettaglio("urn_atto_intero"), richiesto=chiesto)
        assert "~art2043" in reso

    def test_in_json_il_testo_e_quello_del_servizio(self) -> None:
        atto = dettaglio("urn_articolo_con_commi")
        assert _output.dati_atto(atto)["testo"] == atto.testo


class TestLeFinestre:
    def test_una_finestra_che_non_c_e_resta_niente(self) -> None:
        assert _output.dati_finestra(None) is None

    def test_una_finestra_aperta_non_inventa_una_fine(self) -> None:
        reso = _output.dati_finestra(FinestraVigenza(date(1990, 1, 1)))
        assert reso == {"inizio": "1990-01-01", "fine": None}


class TestLeFaccette:
    def test_la_descrizione_che_ripete_il_codice_sparisce(self) -> None:
        assert _output._descrizione(Faccetta("2024", 3, "2024")) == ""
        assert _output._descrizione(Faccetta("PLE", 3, "LEGGE")) == "LEGGE"

    def test_un_gruppo_vuoto_non_lascia_un_titolo_orfano(self) -> None:
        esito = _wire.leggi_ricerca({"listaAtti": [], "numeroAttiTrovati": 0})
        assert _output.mostra_faccette(PIATTO, esito) == ""

    def test_le_piu_numerose_vengono_prima(self) -> None:
        esito = _wire.leggi_ricerca(carica("ricerca_semplice"))
        if not esito.faccette.per_tipo:
            pytest.skip("la risposta registrata non porta faccette per tipo")
        reso = _output.mostra_faccette(PIATTO, esito)
        attesi = sorted(esito.faccette.per_tipo, key=lambda v: -v.conteggio)
        posizioni = [reso.index(voce.codice) for voce in attesi]
        assert posizioni == sorted(posizioni)


class TestLeCollezioni:
    def test_il_formato_dichiarato_viene_spiegato(self) -> None:
        reso = _output.mostra_collezioni(PIATTO, [Collection("Codici", "V", 40, "VIGENTE")])
        assert "--modalita" in reso

    def test_in_json_ci_sono_tutti_i_campi(self) -> None:
        reso = _output.dati_collezione(Collection("Codici", "V", 40, "VIGENTE", date(2026, 1, 1)))
        assert reso == {
            "nome": "Codici",
            "formato": "V",
            "numero_atti": 40,
            "descrizione": "VIGENTE",
            "creata_il": "2026-01-01",
        }
