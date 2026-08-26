"""Il monitoraggio è codice come un altro: se `confronta` sbaglia, tace per sempre."""

import io
import json
import zipfile

import pytest

from tests.contratto.campioni import TUTTI
from tests.contratto.impronta import confronta, impronta_json, impronta_testo, impronta_zip


class TestImprontaJson:
    def test_tipi_delle_foglie(self) -> None:
        forma = impronta_json({"a": 1, "b": "x", "c": True, "d": None, "e": 1.5})
        assert forma[".a"] == ["int"]
        assert forma[".b"] == ["str"]
        assert forma[".c"] == ["bool"]
        assert forma[".d"] == ["null"]
        assert forma[".e"] == ["float"]

    def test_annidamento(self) -> None:
        forma = impronta_json({"a": {"b": {"c": 1}}})
        assert forma[".a.b.c"] == ["int"]

    def test_le_liste_collassano_in_un_cammino(self) -> None:
        forma = impronta_json({"atti": [{"n": 1}, {"n": 2}, {"n": 3}]})
        assert forma[".atti[].n"] == ["int"]

    def test_la_lista_unisce_i_tipi_visti(self) -> None:
        forma = impronta_json({"x": [1, "due"]})
        assert forma[".x[]"] == ["int", "str"]

    def test_un_campo_nullo_in_un_elemento_non_nasconde_gli_altri(self) -> None:
        forma = impronta_json({"atti": [{"n": None}, {"n": 2}]})
        assert forma[".atti[].n"] == ["int", "null"]

    def test_lista_vuota(self) -> None:
        assert impronta_json({"x": []})[".x"] == ["lista"]

    def test_i_valori_non_contano(self) -> None:
        assert impronta_json({"n": 1}) == impronta_json({"n": 99999})

    def test_la_ricorsione_ha_un_fondo(self) -> None:
        profondo: dict = {}
        corrente = profondo
        for _ in range(50):
            corrente["giu"] = {}
            corrente = corrente["giu"]
        assert impronta_json(profondo)


class TestImprontaZip:
    def test_forma_dell_archivio(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archivio:
            archivio.writestr("ATTO/uno.json", json.dumps({"metadati": {"urn": "x"}}))
        forma = impronta_zip(buffer.getvalue())
        assert forma["@archivio"] == ["zip"]
        assert forma["@estensioni"] == ["json"]
        assert forma["@contenuto.metadati.urn"] == ["str"]

    def test_archivio_senza_json(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archivio:
            archivio.writestr("atto.xml", "<akn/>")
        assert impronta_zip(buffer.getvalue())["@estensioni"] == ["xml"]


class TestImprontaTesto:
    def test_corpo_vuoto(self) -> None:
        assert impronta_testo(b"")["@testo"] == ["vuoto"]

    def test_corpo_presente(self) -> None:
        assert impronta_testo(b"un-token")["@testo"] == ["presente"]


class TestConfronto:
    def test_nessuna_deriva(self) -> None:
        forma = impronta_json({"a": 1})
        assert confronta(forma, forma) == []

    def test_campo_sparito_rompe(self) -> None:
        derive = confronta(impronta_json({"a": 1, "b": 2}), impronta_json({"a": 1}))
        assert [d.cammino for d in derive] == [".b"]
        assert derive[0].rompe

    def test_tipo_cambiato_rompe(self) -> None:
        derive = confronta(impronta_json({"a": 1}), impronta_json({"a": "uno"}))
        assert derive[0].rompe
        assert derive[0].genere == "tipo cambiato"

    def test_campo_nuovo_non_rompe(self) -> None:
        derive = confronta(impronta_json({"a": 1}), impronta_json({"a": 1, "b": 2}))
        assert [d.cammino for d in derive] == [".b"]
        assert not derive[0].rompe

    def test_un_campo_che_diventa_nullo_non_rompe(self) -> None:
        registrata = {".a": ["str"]}
        assert confronta(registrata, {".a": ["null", "str"]}) == []

    def test_un_campo_solo_nullo_non_rompe(self) -> None:
        """Un valore assente in questa risposta non dice che il campo sia sparito."""
        assert confronta({".a": ["str"]}, {".a": ["null"]}) == []

    def test_lo_stato_cambiato_rompe(self) -> None:
        derive = confronta({"@stato": ["200"]}, {"@stato": ["500"]})
        assert derive[0].rompe

    def test_derive_leggibili(self) -> None:
        derive = confronta(impronta_json({"a": 1, "b": 2}), impronta_json({"a": "uno", "c": 3}))
        testi = sorted(str(d) for d in derive)
        assert testi == [
            ".a: era int, adesso str",
            ".b: sparito (era int)",
            ".c: nuovo (int)",
        ]


class TestCatalogo:
    def test_nomi_distinti(self) -> None:
        nomi = [c.nome for c in TUTTI]
        assert len(nomi) == len(set(nomi))

    def test_ogni_campione_dice_perche_esiste(self) -> None:
        senza = [c.nome for c in TUTTI if len(c.perche.strip()) < 20]
        assert senza == []

    def test_ogni_campione_ha_un_metodo_http(self) -> None:
        assert all(c.metodo in ("GET", "POST", "PUT") for c in TUTTI)

    def test_i_corpi_sono_serializzabili(self) -> None:
        for campione in TUTTI:
            json.dumps(campione.corpo)

    @pytest.mark.parametrize(
        "endpoint",
        [
            "tipologiche/denominazione-atto",
            "tipologiche/classe-provvedimento",
            "tipologiche/estensioni",
            "ricerca/predefinita",
            "ricerca/semplice",
            "ricerca/avanzata",
            "ricerca/aggiornati",
            "atto/dettaglio-atto-urn",
            "atto/dettaglio-atto",
            "collections/collection-predefinite",
            "collections/download/collection-preconfezionata",
        ],
    )
    def test_ogni_endpoint_sincrono_e_coperto(self, endpoint: str) -> None:
        assert any(c.percorso == endpoint for c in TUTTI), f"nessun campione per {endpoint}"

    def test_il_dataset_registrato_copre_il_catalogo(self) -> None:
        from tests.contratto.interroga import impronte_registrate

        registrati = set(impronte_registrate())
        mancanti = {c.nome for c in TUTTI} - registrati
        assert not mancanti, f"campioni mai registrati: {', '.join(sorted(mancanti))}"
