"""Atti di uso comune, con l'allegato attraverso cui i loro articoli sono indirizzabili.

Gli articoli dei codici furono approvati come allegato a un decreto e non sono
indirizzabili sotto il decreto stesso; quale sia l'allegato cambia da codice a
codice. Ogni corrispondenza in questo modulo è stata verificata contro il
servizio il 2026-08-24.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from normattiva.urn import Urn


@dataclass(frozen=True, slots=True)
class AttoNoto:
    """Un atto noto, richiamabile per nome invece che per URN."""

    nome: str
    base: Urn
    allegato_articoli: str | None = None

    @property
    def urn(self) -> Urn:
        """L'URN dell'atto nel suo insieme."""
        return self.base

    def articolo(self, numero: str | int) -> Urn:
        """Compone l'URN di un articolo, passando per l'allegato che lo contiene.

        Args:
            numero: il numero dell'articolo, con l'eventuale ordinale attaccato
                (`416bis`, non `416-bis`).

        Examples:
            >>> from normattiva.codici import CODICE_CIVILE
            >>> str(CODICE_CIVILE.articolo(2043))
            'urn:nir:stato:regio.decreto:1942-03-16;262:2~art2043'
        """
        return replace(self.base, allegato=self.allegato_articoli, articolo=str(numero))


COSTITUZIONE = AttoNoto(
    "Costituzione",
    Urn(denominazione="costituzione", anno=1947, data=date(1947, 12, 27)),
)
CODICE_CIVILE = AttoNoto(
    "Codice civile",
    Urn.regio_decreto(1942, 262, data=date(1942, 3, 16)),
    allegato_articoli="2",
)
CODICE_PENALE = AttoNoto(
    "Codice penale",
    Urn.regio_decreto(1930, 1398, data=date(1930, 10, 19)),
    allegato_articoli="1",
)
CODICE_PROCEDURA_CIVILE = AttoNoto(
    "Codice di procedura civile",
    Urn.regio_decreto(1940, 1443, data=date(1940, 10, 28)),
    allegato_articoli="1",
)
CODICE_PROCEDURA_PENALE = AttoNoto(
    "Codice di procedura penale",
    Urn.dpr(1988, 447, data=date(1988, 9, 22)),
)
CODICE_AMMINISTRAZIONE_DIGITALE = AttoNoto(
    "Codice dell'amministrazione digitale",
    Urn.decreto_legislativo(2005, 82, data=date(2005, 3, 7)),
)
CODICE_PRIVACY = AttoNoto(
    "Codice in materia di protezione dei dati personali",
    Urn.decreto_legislativo(2003, 196, data=date(2003, 6, 30)),
)
CODICE_DELLA_STRADA = AttoNoto(
    "Codice della strada",
    Urn.decreto_legislativo(1992, 285, data=date(1992, 4, 30)),
)
CODICE_DEL_CONSUMO = AttoNoto(
    "Codice del consumo",
    Urn.decreto_legislativo(2005, 206, data=date(2005, 9, 6)),
)
TUIR = AttoNoto(
    "Testo unico delle imposte sui redditi",
    Urn.dpr(1986, 917, data=date(1986, 12, 22)),
)
TESTO_UNICO_EDILIZIA = AttoNoto(
    "Testo unico dell'edilizia",
    Urn.dpr(2001, 380, data=date(2001, 6, 6)),
)
STATUTO_DEI_LAVORATORI = AttoNoto(
    "Statuto dei lavoratori",
    Urn.legge(1970, 300, data=date(1970, 5, 20)),
)

_TUTTI = (
    COSTITUZIONE,
    CODICE_CIVILE,
    CODICE_PENALE,
    CODICE_PROCEDURA_CIVILE,
    CODICE_PROCEDURA_PENALE,
    CODICE_AMMINISTRAZIONE_DIGITALE,
    CODICE_PRIVACY,
    CODICE_DELLA_STRADA,
    CODICE_DEL_CONSUMO,
    TUIR,
    TESTO_UNICO_EDILIZIA,
    STATUTO_DEI_LAVORATORI,
)


def tutti() -> tuple[AttoNoto, ...]:
    """Restituisce tutti gli atti noti definiti in questo modulo."""
    return _TUTTI


__all__ = [
    "CODICE_AMMINISTRAZIONE_DIGITALE",
    "CODICE_CIVILE",
    "CODICE_DELLA_STRADA",
    "CODICE_DEL_CONSUMO",
    "CODICE_PENALE",
    "CODICE_PRIVACY",
    "CODICE_PROCEDURA_CIVILE",
    "CODICE_PROCEDURA_PENALE",
    "COSTITUZIONE",
    "STATUTO_DEI_LAVORATORI",
    "TESTO_UNICO_EDILIZIA",
    "TUIR",
    "AttoNoto",
    "tutti",
]
