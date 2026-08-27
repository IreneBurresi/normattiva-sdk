import pytest

from normattiva.testo import estrai, normalize_accents
from tests.dati import html_di


class TestEstrazioneSuArticoloConCommi:
    @pytest.fixture
    def contenuto(self):
        return estrai(html_di("urn_articolo_con_commi"))

    def test_corpo_non_e_html(self, contenuto) -> None:
        assert "<div" not in contenuto.corpo
        assert "class=" not in contenuto.corpo

    def test_entita_html_risolte(self, contenuto) -> None:
        assert "&agrave;" not in contenuto.corpo
        assert "&egrave;" not in contenuto.corpo

    def test_corpo_apre_con_il_numero_di_articolo(self, contenuto) -> None:
        assert contenuto.corpo.startswith("Art. 2")

    def test_rubrica_presente_nel_corpo(self, contenuto) -> None:
        assert "Conclusione del procedimento" in contenuto.corpo

    def test_commi_numerati(self, contenuto) -> None:
        assert [c.numero for c in contenuto.commi][:4] == ["1", "2", "3", "4"]

    def test_testo_del_comma_senza_numero(self, contenuto) -> None:
        primo = contenuto.commi[0]
        assert primo.testo
        assert not primo.testo.startswith("1.")

    def test_niente_note_di_aggiornamento(self, contenuto) -> None:
        assert contenuto.note is None

    def test_niente_preambolo_su_articolo_singolo(self, contenuto) -> None:
        assert contenuto.preambolo is None


class TestSeparazioneNoteDiAggiornamento:
    @pytest.fixture
    def contenuto(self):
        return estrai(html_di("urn_articolo_con_aggiornamento"))

    def test_note_estratte(self, contenuto) -> None:
        assert contenuto.note is not None
        assert "AGGIORNAMENTO" in contenuto.note

    def test_note_fuori_dal_corpo(self, contenuto) -> None:
        assert "AGGIORNAMENTO" not in contenuto.corpo

    def test_corpo_resta_sostanzioso(self, contenuto) -> None:
        assert len(contenuto.corpo) > 500

    def test_commi_non_contaminati_dalle_note(self, contenuto) -> None:
        assert all("AGGIORNAMENTO" not in c.testo for c in contenuto.commi)


class TestPreamboloSeparato:
    @pytest.fixture
    def contenuto(self):
        return estrai(html_di("urn_atto_intero"))

    def test_formula_di_promulgazione_isolata(self, contenuto) -> None:
        assert contenuto.preambolo is not None
        assert "La Camera dei deputati" in contenuto.preambolo

    def test_formula_non_incollata_al_corpo(self, contenuto) -> None:
        assert "La Camera dei deputati" not in contenuto.corpo


class TestArticoloDaAllegato:
    def test_testo_estratto_anche_senza_marcatura_di_commi(self) -> None:
        contenuto = estrai(html_di("urn_articolo_allegato"))
        assert "416" in contenuto.corpo
        assert contenuto.note is not None


class TestConteggioCommi:
    def test_articolo_troncato_si_ferma_al_comma_cento(self) -> None:
        commi = estrai(html_di("urn_troncato_100_commi")).commi
        assert commi[-1].numero == "100"

    def test_ordinali_dei_commi_conservati(self) -> None:
        numeri = {c.numero for c in estrai(html_di("urn_troncato_100_commi")).commi}
        assert "85-bis" in numeri

    def test_articolo_normale_ne_ha_pochi(self) -> None:
        assert len(estrai(html_di("urn_articolo_con_commi")).commi) < 20


class TestCasiLimite:
    def test_html_vuoto(self) -> None:
        contenuto = estrai("")
        assert contenuto.corpo == ""
        assert contenuto.commi == ()
        assert contenuto.note is None

    def test_testo_senza_marcatura(self) -> None:
        assert estrai("<div>ciao</div>").corpo == "ciao"

    def test_br_diventa_a_capo(self) -> None:
        assert estrai("<div>uno<br>due</div>").corpo == "uno\ndue"

    def test_spazi_collassati(self) -> None:
        assert estrai("<div>   uno     due   </div>").corpo == "uno due"

    def test_righe_vuote_rimosse(self) -> None:
        assert estrai("<div>uno<br><br><br>due</div>").corpo == "uno\ndue"


class TestNormalizzaAccenti:
    @pytest.mark.parametrize(
        ("grezzo", "atteso"),
        [
            ("attivita'", "attività"),
            ("responsabilita'", "responsabilità"),
            ("puo'", "può"),
            ("e' vietato", "è vietato"),
            ("cosi'", "così"),
            ("piu'", "più"),
            ("perche'", "perché"),
            ("poiche'", "poiché"),
            ("nonche'", "nonché"),
            ("affinche'", "affinché"),
            ("liberta' e attivita'", "libertà e attività"),
        ],
    )
    def test_converte(self, grezzo: str, atteso: str) -> None:
        assert normalize_accents(grezzo) == atteso

    @pytest.mark.parametrize(
        "invariato",
        [
            "dell'articolo",
            "l'attivita",
            "un'altra",
            "de' Medici",
            "ne' casi previsti",
            "a' sensi di legge",
            "",
            "nessun apostrofo",
        ],
    )
    def test_lascia_stare(self, invariato: str) -> None:
        assert normalize_accents(invariato) == invariato

    def test_maiuscole(self) -> None:
        assert normalize_accents("ATTIVITA'") == "ATTIVITÀ"

    def test_idempotente(self) -> None:
        una_volta = normalize_accents("attivita' e liberta'")
        assert normalize_accents(una_volta) == una_volta
