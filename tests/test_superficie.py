"""La superficie pubblica è un impegno: questi test la trattano come tale."""

import dataclasses
import inspect
import re
from pathlib import Path

import pytest

import normattiva
from normattiva import AsyncNormattiva, Normattiva
from normattiva.esporta import AsyncExport, Corpus, Export

_README_GREZZO = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")


def appiattisci(testo: str) -> str:
    """Il testo senza gli a capo e senza i segni di citazione.

    Una frase che nel sorgente sta su due righe, magari dentro un `>`, è la
    stessa frase per chi legge: cercarla senza appiattire vorrebbe dire piegare
    la prosa alla forma dell'espressione regolare.
    """
    return " ".join(re.sub(r"^\s*>\s?", "", testo, flags=re.M).split())


README = appiattisci(_README_GREZZO)

SOLO_SINCRONI = {"chiudi", "esportazione"}
PRIVATI = re.compile(r"^_")


def metodi(cosa: type) -> set[str]:
    return {
        nome
        for nome, _ in inspect.getmembers(cosa, callable)
        if not PRIVATI.match(nome) and nome in vars(cosa)
    }


class TestEsportazioni:
    def test_tutto_cio_che_e_in_all_esiste(self) -> None:
        assert all(hasattr(normattiva, nome) for nome in normattiva.__all__)

    def test_all_e_ordinato(self) -> None:
        """L'ordine è quello che ruff impone da solo: costanti, tipi, funzioni.

        Non è il `sorted()` di Python, che mescolerebbe `ATTRIBUZIONE` e
        `Aggiornamento` secondo il codice ASCII. Riscriverlo qui a mano vorrebbe
        dire litigare a ogni salvataggio con il formattatore.
        """

        def per_famiglia(nome: str) -> tuple[int, str]:
            return (0 if nome.isupper() else 1 if nome[0].isupper() else 2, nome)

        assert list(normattiva.__all__) == sorted(normattiva.__all__, key=per_famiglia)

    def test_all_non_ripete_nessun_nome(self) -> None:
        assert len(normattiva.__all__) == len(set(normattiva.__all__))

    def test_niente_nomi_privati(self) -> None:
        assert not [n for n in normattiva.__all__ if n.startswith("_") and n != "__version__"]


class TestSpecchioAsincrono:
    def test_stessi_metodi(self) -> None:
        assert metodi(Normattiva) - SOLO_SINCRONI <= metodi(AsyncNormattiva) | SOLO_SINCRONI

    @pytest.mark.parametrize(
        "nome",
        [
            "dettaglio",
            "cronologia",
            "ricerca",
            "ricerca_avanzata",
            "ricerca_completa",
            "atti_aggiornati",
            "denominazioni",
            "start_export",
            "download_collection",
        ],
    )
    def test_stessa_firma(self, nome: str) -> None:
        sincrono = inspect.signature(getattr(Normattiva, nome))
        asincrono = inspect.signature(getattr(AsyncNormattiva, nome))
        assert list(sincrono.parameters) == list(asincrono.parameters)

    def test_esportazione_rispecchiata(self) -> None:
        assert metodi(Export) == metodi(AsyncExport)


class TestDocstring:
    @pytest.mark.parametrize("cosa", [Normattiva, AsyncNormattiva, Export, Corpus])
    def test_ogni_metodo_pubblico_e_documentato(self, cosa: type) -> None:
        senza = [nome for nome in metodi(cosa) if not (getattr(cosa, nome).__doc__ or "").strip()]
        assert senza == []

    def test_la_classe_e_documentata(self) -> None:
        assert (Normattiva.__doc__ or "").strip()


class TestReadme:
    @pytest.mark.parametrize(
        "citato",
        [
            "Normattiva",
            "AsyncNormattiva",
            "Urn",
            "Corpus",
            "codici",
        ],
    )
    def test_i_nomi_citati_esistono(self, citato: str) -> None:
        assert citato in README
        assert hasattr(normattiva, citato) or citato == "codici"

    @pytest.mark.parametrize(
        ("cosa", "attributo"),
        [
            (Normattiva, "dettaglio"),
            (Normattiva, "ricerca"),
            (Normattiva, "ricerca_completa"),
            (Normattiva, "cronologia"),
            (Normattiva, "start_export"),
            (Normattiva, "export_from_token"),
            (Export, "wait"),
            (Export, "download"),
            (Corpus, "from_zip"),
            (Corpus, "save"),
        ],
    )
    def test_i_metodi_mostrati_esistono(self, cosa: type, attributo: str) -> None:
        assert f"{attributo}(" in README
        assert hasattr(cosa, attributo)

    @pytest.mark.parametrize(
        "proprieta",
        ["testo", "commi", "note_aggiornamento", "finestra", "permalink", "attribuzione"],
    )
    def test_le_proprieta_mostrate_esistono(self, proprieta: str) -> None:
        campi = {c.name for c in dataclasses.fields(normattiva.DettaglioAtto)}
        assert f".{proprieta}" in README
        assert proprieta in campi or hasattr(normattiva.DettaglioAtto, proprieta)

    def test_i_costruttori_di_urn_mostrati_esistono(self) -> None:
        for costruttore in ("legge", "decreto_legislativo"):
            assert f"Urn.{costruttore}(" in README
            assert hasattr(normattiva.Urn, costruttore)

    def test_l_avvertenza_di_non_ufficialita_e_presente(self) -> None:
        """L'avviso legale chiede il carattere non autentico, comunque lo si scriva."""
        assert re.search(r"non (è )?autentic|non ha carattere di ufficialità", README, re.I)
        assert "Gazzetta Ufficiale" in README

    def test_la_non_ufficialita_del_progetto_e_dichiarata(self) -> None:
        """Diversa dalla precedente: quella riguarda il testo, questa il progetto."""
        assert "non ufficiale" in README.lower()
        assert re.search(r"non\s+(è\s+)?affiliat", README, re.I)

    def test_la_licenza_dei_dati_e_dichiarata(self) -> None:
        assert "CC BY 4.0" in README
