"""L'impronta di una risposta: la sua forma, senza i suoi valori.

I valori cambiano di continuo e legittimamente: un atto viene modificato, un
conteggio sale. La forma no: se un campo sparisce o cambia tipo, il contratto
si è spostato sotto i piedi di chi lo usa. È questo che il monitoraggio guarda.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field

NULLO = "null"
PROFONDITA = 12


def _tipo(valore: object) -> str:
    if valore is None:
        return NULLO
    if isinstance(valore, bool):
        return "bool"
    if isinstance(valore, int):
        return "int"
    if isinstance(valore, float):
        return "float"
    if isinstance(valore, str):
        return "str"
    if isinstance(valore, Mapping):
        return "oggetto"
    if isinstance(valore, Sequence):
        return "lista"
    return type(valore).__name__


def _cammini(valore: object, radice: str = "", profondita: int = 0) -> Iterator[tuple[str, str]]:
    yield radice or ".", _tipo(valore)
    if profondita >= PROFONDITA:
        return
    if isinstance(valore, Mapping):
        for chiave, dentro in valore.items():
            yield from _cammini(dentro, f"{radice}.{chiave}", profondita + 1)
    elif isinstance(valore, Sequence) and not isinstance(valore, str | bytes):
        for elemento in valore:
            yield from _cammini(elemento, f"{radice}[]", profondita + 1)


def impronta_json(valore: object) -> dict[str, list[str]]:
    """Ogni cammino della risposta, con i tipi osservati lungo quel cammino."""
    trovati: dict[str, set[str]] = {}
    for cammino, tipo in _cammini(valore):
        trovati.setdefault(cammino, set()).add(tipo)
    return {cammino: sorted(tipi) for cammino, tipi in sorted(trovati.items())}


def impronta_zip(dati: bytes) -> dict[str, list[str]]:
    """La forma di un archivio: com'è fatto dentro, non cosa contiene."""
    archivio = zipfile.ZipFile(io.BytesIO(dati))
    nomi = archivio.namelist()
    forma: dict[str, set[str]] = {
        "@archivio": {"zip"},
        "@estensioni": {n.rsplit(".", 1)[-1].lower() for n in nomi if "." in n},
    }
    primo = next((n for n in nomi if n.lower().endswith(".json")), None)
    if primo is not None:
        for cammino, tipi in impronta_json(json.loads(archivio.read(primo))).items():
            forma[f"@contenuto{cammino}"] = set(tipi)
    return {cammino: sorted(tipi) for cammino, tipi in sorted(forma.items())}


UUID = re.compile(r"\A[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z", re.I)


def impronta_testo(dati: bytes) -> dict[str, list[str]]:
    """La forma di una risposta di solo testo.

    Non la sua lunghezza: il corpo del blocco WAF porta un identificativo di
    supporto diverso a ogni richiesta, e un'impronta che ci inciampa segnala
    uno scostamento ogni giorno senza che nulla sia cambiato.
    """
    testo = dati.decode("utf-8", "replace").strip()
    if not testo:
        return {"@testo": ["vuoto"]}
    return {"@testo": ["identificativo" if UUID.match(testo) else "presente"]}


@dataclass(frozen=True, slots=True)
class Deriva:
    """Uno scostamento fra l'impronta registrata e quella odierna."""

    cammino: str
    genere: str
    prima: list[str] = field(default_factory=list)
    clock: list[str] = field(default_factory=list)

    @property
    def rompe(self) -> bool:
        """Se questo scostamento rompe chi legge la risposta."""
        return self.genere in ("campo sparito", "tipo cambiato")

    def __str__(self) -> str:
        if self.genere == "campo sparito":
            return f"{self.cammino}: sparito (era {'|'.join(self.prima)})"
        if self.genere == "campo nuovo":
            return f"{self.cammino}: nuovo ({'|'.join(self.clock)})"
        return f"{self.cammino}: era {'|'.join(self.prima)}, adesso {'|'.join(self.clock)}"


def confronta(
    registrata: Mapping[str, Sequence[str]], odierna: Mapping[str, Sequence[str]]
) -> list[Deriva]:
    """Cosa è cambiato fra due impronte.

    Un campo che compare è una notizia, non un guasto: la libreria continua a
    funzionare. Un campo che sparisce o cambia tipo rompe chi lo leggeva, e un
    tipo che diventa anche nullo non rompe nessuno che già lo trattasse così.
    """
    derive = []
    for cammino, prima in registrata.items():
        if cammino not in odierna:
            derive.append(Deriva(cammino, "campo sparito", list(prima)))
            continue
        adesso = odierna[cammino]
        nuovi = {t for t in adesso if t != NULLO} - set(prima)
        if nuovi:
            derive.append(Deriva(cammino, "tipo cambiato", list(prima), list(adesso)))
    for cammino, adesso in odierna.items():
        if cammino not in registrata:
            derive.append(Deriva(cammino, "campo nuovo", [], list(adesso)))
    return derive
