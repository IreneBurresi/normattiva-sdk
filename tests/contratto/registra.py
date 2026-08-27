"""Rigenera il dataset di riferimento interrogando il servizio.

    uv run python -m tests.contratto.registra
    uv run python -m tests.contratto.registra urn_ambiguo ricerca_semplice

Si esegue a mano, quando si vuole accettare come nuova normalità quel che il
monitoraggio ha segnalato. Le risposte vengono salvate ridotte: i testi sono
troncati, la struttura resta intera, ed è la struttura che ci interessa.
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any

from tests.contratto import interroga as rete
from tests.contratto.campioni import TUTTI, Campione

TESTO_MASSIMO = 60
ELEMENTI_MASSIMI = 3
MARCATURA_MASSIMA = 3000
"""Oltre questa soglia l'HTML ripete se stesso: la struttura è già tutta all'inizio."""


class _Riduttore(HTMLParser):
    """Riemette l'HTML accorciando il testo e lasciando intatti i tag."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.pezzi: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        marcatori = "".join(f' {k}="{v}"' for k, v in attrs if v is not None)
        self.pezzi.append(f"<{tag}{marcatori}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.pezzi.append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        self.pezzi.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        ripulito = data.strip()
        self.pezzi.append(f" {ripulito[:TESTO_MASSIMO]}" if ripulito else " ")

    def handle_entityref(self, name: str) -> None:
        self.pezzi.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.pezzi.append(f"&#{name};")


def _riduci_html(html: str) -> str:
    riduttore = _Riduttore()
    riduttore.feed(html)
    riduttore.close()
    ridotto = "".join(riduttore.pezzi)
    if len(ridotto) <= MARCATURA_MASSIMA:
        return ridotto
    return f"{ridotto[:MARCATURA_MASSIMA]}…[{len(ridotto) - MARCATURA_MASSIMA} caratteri omessi]"


def riduci(valore: Any) -> Any:
    """Accorcia i valori conservando ogni chiave e ogni tipo."""
    if isinstance(valore, dict):
        return {chiave: riduci(dentro) for chiave, dentro in valore.items()}
    if isinstance(valore, list):
        return [riduci(elemento) for elemento in valore[:ELEMENTI_MASSIMI]]
    if isinstance(valore, str):
        if "<" in valore and ">" in valore:
            return _riduci_html(valore)
        return valore if len(valore) <= TESTO_MASSIMO else valore[:TESTO_MASSIMO] + "…"
    return valore


def _salva_risposta(campione: Campione, esito: rete.Esito) -> None:
    destinazione = rete.RISPOSTE / f"{campione.nome}.json"
    if campione.forma == "zip" and esito.status == 200:
        archivio = zipfile.ZipFile(io.BytesIO(esito.contenuto))
        dentro = {
            "@nomi": archivio.namelist()[:ELEMENTI_MASSIMI],
            "@totale": len(archivio.namelist()),
        }
        primo = next((n for n in archivio.namelist() if n.lower().endswith(".json")), None)
        if primo is not None:
            dentro["@primo"] = riduci(json.loads(archivio.read(primo)))
        corpo: Any = dentro
    else:
        try:
            corpo = riduci(esito.json)
        except (json.JSONDecodeError, UnicodeDecodeError):
            corpo = esito.contenuto.decode("utf-8", "replace")[:400]
    destinazione.write_text(
        json.dumps(
            {
                "stato": esito.status,
                "tipo_contenuto": esito.tipo_contenuto,
                "corpo": corpo,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )


def registra(scelti: list[str] | None = None) -> int:
    """Interroga i campioni e riscrive il dataset."""
    catalogo = [c for c in TUTTI if not scelti or c.nome in scelti]
    if not catalogo:
        print("nessun campione corrisponde", file=sys.stderr)
        return 1

    rete.DATASET.mkdir(parents=True, exist_ok=True)
    rete.RISPOSTE.mkdir(parents=True, exist_ok=True)
    impronte = rete.impronte_registrate() if rete.IMPRONTE.exists() else {}
    indisponibili = []

    with rete.nuovo_client() as client:
        for campione in catalogo:
            try:
                esito = rete.interroga(campione, client)
            except rete.Indisponibile as guasto:
                indisponibili.append(campione.nome)
                print(f"  !! {campione.nome}: {guasto}", file=sys.stderr)
                continue
            impronte[campione.nome] = rete.impronta_di(campione, esito)
            _salva_risposta(campione, esito)
            print(f"  ok {campione.nome:<38} {esito.status}  {len(esito.contenuto):>8} B")

    rete.IMPRONTE.write_text(
        json.dumps(
            {
                "registrato": datetime.now(UTC).date().isoformat(),
                "campioni": dict(sorted(impronte.items())),
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\n{len(catalogo) - len(indisponibili)}/{len(catalogo)} registrati in {rete.DATASET}")
    if indisponibili:
        print(f"indisponibili: {', '.join(indisponibili)}", file=sys.stderr)
    return 1 if len(indisponibili) == len(catalogo) else 0


if __name__ == "__main__":
    raise SystemExit(registra(sys.argv[1:]))
