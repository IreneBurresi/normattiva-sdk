"""Come il monitoraggio parla col servizio.

Non passa dal client della libreria di proposito: alcune richieste del catalogo
sono malformate apposta, e il client non le manderebbe mai. Qui si osserva
l'API com'è, non come la libreria la addomestica.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from normattiva import __version__
from tests.contratto import impronta as forme
from tests.contratto.campioni import Campione

PRODUZIONE = "https://api.normattiva.it/t/normattiva.api/bff-opendata/v1/api/v1"
USER_AGENT = (
    f"normattiva-sdk/{__version__} monitoraggio-contratto "
    "(+https://github.com/ireneburresi/normattiva-sdk)"
)
PAUSA = 1.5
DATASET = Path(__file__).parent / "dataset"
RISPOSTE = DATASET / "risposte"
IMPRONTE = DATASET / "impronte.json"


class Indisponibile(RuntimeError):
    """Il servizio non ha risposto affatto: un guasto, non un cambio di contratto."""


@dataclass(frozen=True, slots=True)
class Esito:
    """Quel che è tornato, prima di qualsiasi interpretazione."""

    stato: int
    contenuto: bytes
    tipo_contenuto: str

    @property
    def json(self) -> object:
        return json.loads(self.contenuto)


def nuovo_client(timeout: float = 60.0) -> httpx.Client:
    """Un client HTTP nudo, con l'identificazione che il servizio merita."""
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=timeout,
        follow_redirects=False,
    )


def interroga(
    campione: Campione, client: httpx.Client, *, base_url: str = PRODUZIONE, retries: int = 2
) -> Esito:
    """Esegue un campione, ritentando quel tanto che basta a non gridare al lupo."""
    indirizzo = f"{base_url}/{campione.percorso.lstrip('/')}"
    intestazioni = dict(campione.intestazioni)
    ultimo: Exception | None = None
    for tentativo in range(1 + retries):
        if tentativo:
            time.sleep(PAUSA * 2**tentativo)
        time.sleep(PAUSA)
        try:
            risposta = client.request(
                campione.metodo,
                indirizzo,
                json=campione.corpo,
                params=campione.parametri,
                headers=intestazioni,
            )
        except httpx.HTTPError as errore:
            ultimo = errore
            continue
        return Esito(
            stato=risposta.status_code,
            contenuto=risposta.content,
            tipo_contenuto=risposta.headers.get("content-type", ""),
        )
    raise Indisponibile(f"{campione.nome}: {ultimo}") from ultimo


def impronta_di(campione: Campione, esito: Esito) -> dict[str, list[str]]:
    """La forma di una risposta, stato e tipo di contenuto compresi."""
    if campione.forma == "zip" and esito.status == 200:
        corpo = forme.impronta_zip(esito.contenuto)
    elif campione.forma == "testo" or not esito.contenuto:
        corpo = forme.impronta_testo(esito.contenuto)
    else:
        try:
            corpo = forme.impronta_json(esito.json)
        except (json.JSONDecodeError, UnicodeDecodeError):
            corpo = forme.impronta_testo(esito.contenuto)
    return {
        "@stato": [str(esito.status)],
        "@tipo-contenuto": [esito.tipo_contenuto.split(";")[0].strip() or "assente"],
        **corpo,
    }


def impronte_registrate() -> dict[str, dict[str, list[str]]]:
    """Il dataset di riferimento, come sta su disco."""
    return json.loads(IMPRONTE.read_text(encoding="utf-8"))["campioni"]
