from datetime import date

import pytest

from normattiva import Urn, codici
from normattiva.codici import AttoNoto


class TestAllegatoRisolto:
    def test_codice_civile_passa_dall_allegato_2(self) -> None:
        urn = codici.CODICE_CIVILE.articolo("2043")
        assert str(urn) == "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2043"

    def test_codice_penale_passa_dall_allegato_1(self) -> None:
        assert codici.CODICE_PENALE.articolo("575").allegato == "1"

    def test_procedura_civile_passa_dall_allegato_1(self) -> None:
        assert codici.CODICE_PROCEDURA_CIVILE.articolo("99").allegato == "1"

    def test_procedura_penale_risponde_diretto(self) -> None:
        assert codici.CODICE_PROCEDURA_PENALE.articolo("1").allegato is None

    @pytest.mark.parametrize(
        "atto",
        [
            codici.COSTITUZIONE,
            codici.CODICE_AMMINISTRAZIONE_DIGITALE,
            codici.CODICE_PRIVACY,
            codici.CODICE_DELLA_STRADA,
            codici.CODICE_DEL_CONSUMO,
            codici.TUIR,
            codici.TESTO_UNICO_EDILIZIA,
            codici.STATUTO_DEI_LAVORATORI,
        ],
    )
    def test_atti_senza_allegato(self, atto: AttoNoto) -> None:
        assert atto.articolo("1").allegato is None


class TestComposizione:
    def test_urn_dell_atto_intero_non_ha_allegato(self) -> None:
        assert codici.CODICE_CIVILE.urn.allegato is None
        assert codici.CODICE_CIVILE.urn.articolo is None

    def test_costituzione_senza_numero(self) -> None:
        assert codici.COSTITUZIONE.urn.numero is None

    def test_articolo_accetta_ordinali_contratti(self) -> None:
        assert codici.CODICE_PENALE.articolo("416bis").articolo == "416bis"

    def test_articolo_accetta_interi(self) -> None:
        assert codici.CODICE_CIVILE.articolo(2043) == codici.CODICE_CIVILE.articolo("2043")

    def test_data_di_emanazione_presente(self) -> None:
        assert codici.CODICE_CIVILE.urn.data == date(1942, 3, 16)

    def test_nome_leggibile(self) -> None:
        assert codici.CODICE_CIVILE.nome == "Codice civile"

    def test_permalink_disponibile(self) -> None:
        assert codici.COSTITUZIONE.urn.permalink.startswith("https://www.normattiva.it/uri-res/")


class TestRegistro:
    def test_tutti_elenca_gli_atti_noti(self) -> None:
        assert codici.CODICE_CIVILE in codici.tutti()

    def test_ogni_atto_noto_e_esposto_come_costante(self) -> None:
        esposti = {getattr(codici, nome) for nome in codici.__all__ if nome.isupper()}
        assert set(codici.tutti()) == esposti

    def test_nomi_distinti(self) -> None:
        nomi = [atto.nome for atto in codici.tutti()]
        assert len(nomi) == len(set(nomi))

    def test_immutabile(self) -> None:
        with pytest.raises(AttributeError):
            codici.CODICE_CIVILE.nome = "altro"  # type: ignore[misc]


class TestAttoNoto:
    def test_articolo_su_atto_costruito_a_mano(self) -> None:
        atto = AttoNoto("Prova", Urn.legge(1990, 241), allegato_articoli=None)
        assert str(atto.articolo("5")) == "urn:nir:stato:legge:1990;241~art5"

    def test_allegato_applicato(self) -> None:
        atto = AttoNoto("Prova", Urn.legge(1990, 241), allegato_articoli="3")
        assert atto.articolo("5").allegato == "3"
