"""Il taccuino invecchia come la documentazione, e va guardato allo stesso modo.

Un notebook si legge senza eseguirlo, quindi le uscite salvate dentro sono
un'affermazione su cosa succede a eseguirlo. Qui si controlla che quelle
affermazioni siano ancora sostenibili: che il codice compili, che nessuna cella
si sia fermata su un errore, e che l'attribuzione che la licenza richiede sia
rimasta in fondo.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from normattiva.modelli import ATTRIBUZIONE

RADICE = Path(__file__).resolve().parent.parent
TACCUINO = RADICE / "esempi" / "normattiva-in-pratica.ipynb"


@pytest.fixture(scope="module")
def quaderno() -> dict[str, Any]:
    return json.loads(TACCUINO.read_text(encoding="utf-8"))


def sorgente(cella: dict[str, Any]) -> str:
    """La sorgente di una cella, che il formato salva come lista di righe."""
    grezza = cella["source"]
    return grezza if isinstance(grezza, str) else "".join(grezza)


def celle(quaderno: dict[str, Any], tipo: str) -> list[tuple[int, dict[str, Any]]]:
    return [(n, c) for n, c in enumerate(quaderno["cells"]) if c["cell_type"] == tipo]


def uscite(quaderno: dict[str, Any]) -> list[dict[str, Any]]:
    return [u for _, c in celle(quaderno, "code") for u in c.get("outputs", [])]


class TestIlTaccuino:
    def test_esiste_ed_e_un_notebook(self, quaderno: dict[str, Any]) -> None:
        assert quaderno["nbformat"] == 4
        assert quaderno["cells"]

    def test_ha_codice_e_prosa(self, quaderno: dict[str, Any]) -> None:
        """Un taccuino di solo codice è uno script, uno di sola prosa è una pagina."""
        assert len(celle(quaderno, "code")) >= 10
        assert len(celle(quaderno, "markdown")) >= 10

    def test_ogni_cella_di_codice_compila(self, quaderno: dict[str, Any]) -> None:
        for numero, cella in celle(quaderno, "code"):
            codice = sorgente(cella)
            try:
                ast.parse(codice)
            except SyntaxError as errore:
                pytest.fail(f"la cella {numero} non compila: {errore.msg}")

    def test_le_uscite_sono_salvate(self, quaderno: dict[str, Any]) -> None:
        """Senza uscite il taccuino non racconta niente a chi non lo esegue."""
        assert len(uscite(quaderno)) >= 10

    def test_nessuna_cella_si_e_fermata_su_un_errore(self, quaderno: dict[str, Any]) -> None:
        rotte = [
            f"{u.get('ename')}: {u.get('evalue')}"
            for u in uscite(quaderno)
            if u["output_type"] == "error"
        ]
        assert rotte == [], f"il taccuino porta uscite di errore: {rotte}"

    def test_c_e_anche_un_grafico(self, quaderno: dict[str, Any]) -> None:
        assert any("image/png" in u.get("data", {}) for u in uscite(quaderno))


class TestQuelloCheLaLicenzaChiede:
    def test_l_attribuzione_compare_per_intero(self, quaderno: dict[str, Any]) -> None:
        intero = TACCUINO.read_text(encoding="utf-8")
        pezzi = json.dumps(ATTRIBUZIONE, ensure_ascii=False)[1:-1]
        assert pezzi in intero, (
            "il taccuino non mostra più l'attribuzione di normattiva.ATTRIBUZIONE"
        )

    def test_dichiara_di_non_essere_ufficiale(self, quaderno: dict[str, Any]) -> None:
        prosa = " ".join(sorgente(c) for _, c in celle(quaderno, "markdown"))
        assert "non ufficiale" in prosa.lower()
        assert "CC BY 4.0" in prosa

    def test_il_lettore_sa_da_quando_sono_i_dati(self, quaderno: dict[str, Any]) -> None:
        """Le uscite salvate sono una fotografia: senza la data non si sa di quando."""
        prosa = " ".join(sorgente(c) for _, c in celle(quaderno, "markdown"))
        assert "2026" in prosa
