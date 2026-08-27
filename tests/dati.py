"""Le risposte reali registrate, a disposizione dei test."""

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"


def carica(nome: str) -> Any:
    """Legge una risposta registrata."""
    return json.loads((FIXTURES / f"{nome}.json").read_text(encoding="utf-8"))


def atto_di(nome: str) -> dict[str, Any]:
    """Il nodo `atto` di una risposta registrata di dettaglio-atto-urn."""
    return carica(nome)["data"]["atto"]


def html_di(nome: str) -> str:
    """L'`articoloHtml` di una risposta registrata di dettaglio-atto-urn."""
    return atto_di(nome)["articoloHtml"]
