from datetime import date

import pytest

from normattiva.errori import VersionNotFoundError
from normattiva.modelli import (
    AttoStorico,
    ClasseProvvedimento,
    DettaglioAtto,
    EstremiAtto,
    ExportMode,
    FinestraVigenza,
    Format,
    PubblicazioneGazzetta,
    VersioneAtto,
)
from tests.dati import html_di

L241 = EstremiAtto(denominazione="LEGGE", data=date(1990, 8, 7), numero="241", codice_tipo="PLE")
GU = PubblicazioneGazzetta(data=date(1990, 8, 18), numero=192, codice_redazionale="090G0294")


def dettaglio(nome: str, **oltre) -> DettaglioAtto:
    parametri = {
        "atto": L241,
        "gazzetta": GU,
        "titolo": "LEGGE 7 agosto 1990, n. 241",
        "sottotitolo": None,
        "testo_html": html_di(nome),
        "finestra": FinestraVigenza(date(2021, 6, 1), None),
    }
    return DettaglioAtto(**{**parametri, **oltre})


class TestFinestraVigenza:
    def test_contiene_estremi_inclusi(self) -> None:
        finestra = FinestraVigenza(date(2020, 1, 1), date(2020, 12, 31))
        assert finestra.contiene(date(2020, 1, 1))
        assert finestra.contiene(date(2020, 12, 31))
        assert finestra.contiene(date(2020, 6, 15))

    def test_non_contiene_fuori(self) -> None:
        finestra = FinestraVigenza(date(2020, 1, 1), date(2020, 12, 31))
        assert not finestra.contiene(date(2019, 12, 31))
        assert not finestra.contiene(date(2021, 1, 1))

    def test_finestra_aperta(self) -> None:
        finestra = FinestraVigenza(date(2020, 1, 1), None)
        assert finestra.aperta
        assert finestra.contiene(date(2999, 1, 1))

    def test_finestra_chiusa(self) -> None:
        assert not FinestraVigenza(date(2020, 1, 1), date(2020, 12, 31)).aperta

    def test_fine_prima_dell_inizio_rifiutata(self) -> None:
        with pytest.raises(ValueError, match="inizio"):
            FinestraVigenza(date(2020, 12, 31), date(2020, 1, 1))

    def test_leggibile(self) -> None:
        assert "2020-01-01" in str(FinestraVigenza(date(2020, 1, 1), None))

    def test_immutabile(self) -> None:
        with pytest.raises(AttributeError):
            FinestraVigenza(date(2020, 1, 1), None).inizio = date(2021, 1, 1)  # type: ignore[misc]


class TestEstremiAtto:
    def test_urn_derivato(self) -> None:
        assert str(L241.urn) == "urn:nir:stato:legge:1990-08-07;241"

    @pytest.mark.parametrize(
        ("denominazione", "atteso"),
        [
            ("LEGGE", "legge"),
            ("DECRETO-LEGGE", "decreto.legge"),
            ("DECRETO LEGISLATIVO", "decreto.legislativo"),
            ("REGIO DECRETO", "regio.decreto"),
            (
                "DECRETO DEL PRESIDENTE DELLA REPUBBLICA",
                "decreto.del.presidente.della.repubblica",
            ),
            ("COSTITUZIONE", "costituzione"),
        ],
    )
    def test_denominazione_tradotta_in_urn(self, denominazione: str, atteso: str) -> None:
        estremi = EstremiAtto(denominazione=denominazione, data=date(1990, 8, 7), numero="1")
        assert estremi.urn.denominazione == atteso

    @pytest.mark.parametrize(
        ("denominazione", "numero", "atteso"),
        [
            ("LEGGE", "241", "L. 7 agosto 1990, n. 241"),
            ("DECRETO-LEGGE", "180", "D.L. 7 agosto 1990, n. 180"),
            ("DECRETO LEGISLATIVO", "82", "D.Lgs. 7 agosto 1990, n. 82"),
            (
                "DECRETO DEL PRESIDENTE DELLA REPUBBLICA",
                "380",
                "D.P.R. 7 agosto 1990, n. 380",
            ),
            ("REGIO DECRETO", "262", "R.D. 7 agosto 1990, n. 262"),
            ("LEGGE COSTITUZIONALE", "3", "L. cost. 7 agosto 1990, n. 3"),
            ("ORDINANZA", "9", "Ordinanza 7 agosto 1990, n. 9"),
        ],
    )
    def test_citazione_forense(self, denominazione: str, numero: str, atteso: str) -> None:
        estremi = EstremiAtto(denominazione=denominazione, data=date(1990, 8, 7), numero=numero)
        assert estremi.citazione == atteso

    def test_citazione_senza_numero(self) -> None:
        estremi = EstremiAtto(denominazione="COSTITUZIONE", data=date(1947, 12, 27), numero=None)
        assert estremi.citazione == "Cost. 27 dicembre 1947"

    def test_mesi_in_italiano(self) -> None:
        estremi = EstremiAtto(denominazione="LEGGE", data=date(1990, 1, 5), numero="1")
        assert "5 gennaio 1990" in estremi.citazione


class TestPubblicazioneGazzetta:
    def test_campi(self) -> None:
        assert GU.codice_redazionale == "090G0294"

    def test_senza_codice_redazionale(self) -> None:
        assert PubblicazioneGazzetta(date(1990, 8, 18), 192, None).codice_redazionale is None

    def test_leggibile(self) -> None:
        assert "192" in str(GU)


class TestDettaglioAtto:
    def test_testo_piano(self) -> None:
        atto = dettaglio("urn_articolo_con_commi")
        assert "<div" not in atto.testo
        assert atto.testo.startswith("Art. 2")

    def test_commi_strutturati(self) -> None:
        commi = dettaglio("urn_articolo_con_commi").commi
        assert commi[0].numero == "1"
        assert commi[0].testo

    def test_note_di_aggiornamento_separate(self) -> None:
        atto = dettaglio("urn_articolo_con_aggiornamento")
        assert atto.note_aggiornamento is not None
        assert "AGGIORNAMENTO" not in atto.testo

    def test_senza_note_e_none(self) -> None:
        assert dettaglio("urn_articolo_con_commi").note_aggiornamento is None

    def test_preambolo_separato(self) -> None:
        assert dettaglio("urn_atto_intero").preambolo is not None

    def test_commi_presenti_contati(self) -> None:
        assert dettaglio("urn_articolo_con_commi").commi_presenti == len(
            dettaglio("urn_articolo_con_commi").commi
        )

    def test_troncamento_sospetto_quando_l_ultimo_comma_e_cento(self) -> None:
        assert dettaglio("urn_troncato_100_commi").possibile_troncamento

    def test_nessun_sospetto_su_articolo_breve(self) -> None:
        assert not dettaglio("urn_articolo_con_commi").possibile_troncamento

    def test_nessun_sospetto_senza_commi(self) -> None:
        atto = dettaglio("urn_articolo_allegato")
        assert atto.commi_presenti is None
        assert not atto.possibile_troncamento

    def test_permalink(self) -> None:
        assert dettaglio("urn_articolo_con_commi").permalink.startswith(
            "https://www.normattiva.it/uri-res/N2Ls?"
        )

    def test_attribuzione_cita_la_fonte_e_la_licenza(self) -> None:
        attribuzione = dettaglio("urn_articolo_con_commi").attribuzione
        assert "Normattiva" in attribuzione
        assert "CC BY 4.0" in attribuzione

    def test_urn_esposto(self) -> None:
        assert dettaglio("urn_articolo_con_commi").urn == L241.urn

    def test_immutabile(self) -> None:
        with pytest.raises(AttributeError):
            dettaglio("urn_articolo_con_commi").titolo = "altro"  # type: ignore[misc]


class TestEnumerazioni:
    def test_formato_dal_valore(self) -> None:
        assert Format("AKN") is Format.AKN

    def test_formato_come_stringa(self) -> None:
        assert str(Format.JSON) == "JSON"
        assert f"{Format.JSON}" == "JSON"

    def test_formato_ignoto(self) -> None:
        with pytest.raises(ValueError, match="DOCX"):
            Format("DOCX")

    def test_modalita_export_per_esteso(self) -> None:
        assert ExportMode("multivigente") is ExportMode.MULTIVIGENTE

    def test_classe_provvedimento(self) -> None:
        assert ClasseProvvedimento(3) is ClasseProvvedimento.ABROGATO
        assert ClasseProvvedimento.AGGIORNATO == 2


class TestAttoStorico:
    @pytest.fixture
    def atto(self) -> AttoStorico:
        return AttoStorico(
            urn=L241.urn,
            estremi=L241,
            gazzetta=GU,
            versioni=(
                VersioneAtto(vigente_dal=None),
                VersioneAtto(vigente_dal=date(1995, 1, 1)),
                VersioneAtto(vigente_dal=date(2005, 1, 1)),
            ),
        )

    def test_prima_della_prima_modifica_vale_l_originale(self, atto: AttoStorico) -> None:
        assert atto.alla_data(date(1992, 1, 1)).originale

    def test_il_giorno_della_pubblicazione_vale_l_originale(self, atto: AttoStorico) -> None:
        assert atto.alla_data(GU.data).originale

    def test_fra_due_modifiche_vale_la_precedente(self, atto: AttoStorico) -> None:
        assert atto.alla_data(date(1997, 6, 30)).vigente_dal == date(1995, 1, 1)

    def test_il_giorno_stesso_di_una_modifica_vale_la_nuova(self, atto: AttoStorico) -> None:
        assert atto.alla_data(date(2005, 1, 1)).vigente_dal == date(2005, 1, 1)

    def test_dopo_l_ultima_modifica_vale_l_ultima(self, atto: AttoStorico) -> None:
        assert atto.alla_data(date(2026, 1, 1)).vigente_dal == date(2005, 1, 1)

    def test_prima_che_l_atto_esistesse_non_c_e_versione(self, atto: AttoStorico) -> None:
        with pytest.raises(VersionNotFoundError):
            atto.alla_data(date(1950, 1, 1))

    def test_un_atto_mai_modificato_vale_sempre(self) -> None:
        mai = AttoStorico(
            urn=L241.urn,
            estremi=L241,
            gazzetta=GU,
            versioni=(VersioneAtto(vigente_dal=None),),
        )
        assert mai.alla_data(date(2026, 1, 1)).originale
        assert mai.vigente is mai.originale

    def test_senza_gazzetta_vale_la_data_di_emanazione(self) -> None:
        senza = AttoStorico(urn=L241.urn, estremi=L241, versioni=(VersioneAtto(vigente_dal=None),))
        assert senza.pubblicato_il == L241.data
        assert senza.alla_data(L241.data).originale

    def test_un_atto_senza_versioni_non_ne_ha_nessuna(self) -> None:
        vuoto = AttoStorico(urn=L241.urn, estremi=L241, versioni=())
        assert vuoto.originale is None
        assert vuoto.vigente is None
        with pytest.raises(VersionNotFoundError):
            vuoto.alla_data(date(2000, 1, 1))
