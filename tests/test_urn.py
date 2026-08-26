from datetime import date

import pytest

from normattiva import InvalidUrnError, Urn


class TestParse:
    def test_atto_intero_con_data_completa(self) -> None:
        urn = Urn.parse("urn:nir:stato:legge:1990-08-07;241")
        assert urn.denominazione == "legge"
        assert urn.data == date(1990, 8, 7)
        assert urn.anno == 1990
        assert urn.numero == "241"
        assert urn.articolo is None

    def test_solo_anno(self) -> None:
        urn = Urn.parse("urn:nir:stato:legge:1990;241")
        assert urn.anno == 1990
        assert urn.data is None
        assert urn.numero == "241"

    def test_articolo(self) -> None:
        urn = Urn.parse("urn:nir:stato:legge:1970-12-01;898~art5")
        assert urn.articolo == "5"

    def test_articolo_con_ordinale_contratto(self) -> None:
        assert Urn.parse("urn:nir:stato:legge:1990-08-07;241~art10bis").articolo == "10bis"

    def test_articolo_con_numerazione_estesa(self) -> None:
        assert Urn.parse("urn:nir:stato:legge:1990-08-07;241~art71.1").articolo == "71.1"

    def test_allegato(self) -> None:
        urn = Urn.parse("urn:nir:stato:regio.decreto:1942-03-16;262:2~art2043")
        assert urn.allegato == "2"
        assert urn.articolo == "2043"
        assert urn.numero == "262"

    def test_costituzione_senza_numero(self) -> None:
        urn = Urn.parse("urn:nir:stato:costituzione:1947-12-27")
        assert urn.numero is None
        assert urn.data == date(1947, 12, 27)

    def test_vigenza_esplicita(self) -> None:
        urn = Urn.parse("urn:nir:stato:legge:1970-12-01;898~art5!vig=2005-01-01")
        assert urn.versione == date(2005, 1, 1)

    def test_versione_originale(self) -> None:
        assert (
            Urn.parse("urn:nir:stato:legge:1990-08-07;241~art1@originale").versione == "originale"
        )

    def test_comma_conservato_come_citazione(self) -> None:
        urn = Urn.parse("urn:nir:stato:legge:2007-12-24;244~art2-com428")
        assert urn.articolo == "2"
        assert urn.comma == "428"

    def test_comma_con_lettera(self) -> None:
        urn = Urn.parse("urn:nir:stato:costituzione:1947-12-27~art117-com2-letr")
        assert urn.comma == "2-letr"

    def test_case_insensitive(self) -> None:
        urn = Urn.parse("URN:NIR:STATO:LEGGE:1970-12-01;898~ART5")
        assert urn.denominazione == "legge"
        assert urn.autorita == "stato"
        assert urn.articolo == "5"

    def test_zero_iniziale_normalizzato(self) -> None:
        assert Urn.parse("urn:nir:stato:legge:1990-08-07;241~art01").articolo == "1"

    def test_accetta_istanza_urn(self) -> None:
        urn = Urn.legge(1990, 241)
        assert Urn.parse(urn) is urn


class TestParseRifiuti:
    @pytest.mark.parametrize(
        "testo",
        [
            "",
            "   ",
            "legge 241/1990",
            "urn:nir:stato:legge",
            "urn:altro:stato:legge:1990;241",
            "urn:nir:stato:legge:xxxx;241",
            "urn:nir:stato:legge:1990-13-45;241",
            "urn:nir:stato:legge:1990-08-07;241~art5-bis",
            "urn:nir:stato:legge:1990-08-07;241~artXIV",
            "urn:nir:stato:legge:1990-08-07;241~art",
            "urn:nir:stato:legge:1990-08-07;241!vig=NONSENSE",
            "urn:nir:stato:legge:1990-08-07;241!pippo=2005-01-01",
            "urn:nir:stato:legge:1990-08-07;241@vigente",
        ],
    )
    def test_solleva(self, testo: str) -> None:
        with pytest.raises(InvalidUrnError):
            Urn.parse(testo)

    def test_e_anche_value_error(self) -> None:
        with pytest.raises(ValueError, match="URN non valido"):
            Urn.parse("non un urn")

    def test_messaggio_riporta_il_testo(self) -> None:
        with pytest.raises(InvalidUrnError, match="pippo"):
            Urn.parse("pippo")


class TestRicomposizione:
    @pytest.mark.parametrize(
        "testo",
        [
            "urn:nir:stato:legge:1990-08-07;241",
            "urn:nir:stato:legge:1990;241",
            "urn:nir:stato:legge:1970-12-01;898~art5",
            "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2043",
            "urn:nir:stato:costituzione:1947-12-27",
            "urn:nir:stato:costituzione:1947-12-27~art117-com2-letr",
            "urn:nir:stato:legge:1970-12-01;898~art5!vig=2005-01-01",
            "urn:nir:stato:legge:1990-08-07;241~art1@originale",
            "urn:nir:stato:legge:1990-08-07;241~art10bis",
        ],
    )
    def test_round_trip(self, testo: str) -> None:
        assert str(Urn.parse(testo)) == testo

    def test_normalizza_il_caso(self) -> None:
        assert str(Urn.parse("URN:NIR:STATO:LEGGE:1990;241")) == "urn:nir:stato:legge:1990;241"


class TestCostruttori:
    def test_legge(self) -> None:
        assert str(Urn.legge(1990, 241)) == "urn:nir:stato:legge:1990;241"

    def test_legge_con_articolo(self) -> None:
        assert str(Urn.legge(1990, 241, articolo="5")) == "urn:nir:stato:legge:1990;241~art5"

    def test_numero_intero_o_stringa(self) -> None:
        assert Urn.legge(1990, 241) == Urn.legge(1990, "241")

    def test_decreto_legislativo(self) -> None:
        atteso = "urn:nir:stato:decreto.legislativo:2005;82"
        assert str(Urn.decreto_legislativo(2005, 82)) == atteso

    def test_decreto_legge(self) -> None:
        assert str(Urn.decreto_legge(2008, 180)) == "urn:nir:stato:decreto.legge:2008;180"

    def test_dpr(self) -> None:
        assert (
            str(Urn.dpr(2001, 380))
            == "urn:nir:stato:decreto.del.presidente.della.repubblica:2001;380"
        )

    def test_regio_decreto(self) -> None:
        assert str(Urn.regio_decreto(1942, 262)) == "urn:nir:stato:regio.decreto:1942;262"

    def test_data_completa_opzionale(self) -> None:
        urn = Urn.legge(1990, 241, data=date(1990, 8, 7))
        assert str(urn) == "urn:nir:stato:legge:1990-08-07;241"

    def test_data_incoerente_con_anno(self) -> None:
        with pytest.raises(InvalidUrnError):
            Urn.legge(1990, 241, data=date(1991, 8, 7))


class TestDerivazione:
    def test_con_articolo(self) -> None:
        urn = Urn.legge(1990, 241).con_articolo("5")
        assert urn.articolo == "5"

    def test_con_articolo_non_muta_originale(self) -> None:
        base = Urn.legge(1990, 241)
        base.con_articolo("5")
        assert base.articolo is None

    def test_con_vigenza_data(self) -> None:
        urn = Urn.legge(1990, 241, articolo="5").con_vigenza(date(2005, 1, 1))
        assert urn.versione == date(2005, 1, 1)
        assert str(urn).endswith("!vig=2005-01-01")

    def test_con_vigenza_originale(self) -> None:
        assert Urn.legge(1990, 241).con_vigenza("originale").versione == "originale"

    def test_con_vigenza_rifiuta_valore_ignoto(self) -> None:
        with pytest.raises(InvalidUrnError):
            Urn.legge(1990, 241).con_vigenza("vigente")

    def test_senza_comma(self) -> None:
        urn = Urn.parse("urn:nir:stato:legge:2007-12-24;244~art2-com428")
        assert urn.senza_comma.comma is None
        assert str(urn.senza_comma) == "urn:nir:stato:legge:2007-12-24;244~art2"

    def test_senza_comma_e_idempotente(self) -> None:
        urn = Urn.legge(1990, 241, articolo="5")
        assert urn.senza_comma == urn

    def test_permalink(self) -> None:
        urn = Urn.legge(1990, 241)
        assert (
            urn.permalink == "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1990;241"
        )


class TestIdentita:
    def test_hashable(self) -> None:
        assert len({Urn.legge(1990, 241), Urn.legge(1990, 241)}) == 1

    def test_immutabile(self) -> None:
        with pytest.raises(AttributeError):
            Urn.legge(1990, 241).articolo = "5"  # type: ignore[misc]

    def test_repr_utile(self) -> None:
        assert "241" in repr(Urn.legge(1990, 241))
