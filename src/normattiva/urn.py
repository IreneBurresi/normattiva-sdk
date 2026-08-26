"""L'identificatore NIR con cui Normattiva indirizza atti e articoli."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Literal

from normattiva.errori import InvalidUrnError

PERMALINK = "https://www.normattiva.it/uri-res/N2Ls?"

LEGGE = "legge"
DECRETO_LEGGE = "decreto.legge"
DECRETO_LEGISLATIVO = "decreto.legislativo"
DPR = "decreto.del.presidente.della.repubblica"
REGIO_DECRETO = "regio.decreto"
COSTITUZIONE = "costituzione"

_GRAMMATICA = re.compile(
    r"""^urn:nir:
        (?P<autorita>[a-z0-9.]+):
        (?P<denominazione>[a-z0-9.]+):
        (?P<data>\d{4}(?:-\d{2}-\d{2})?)
        (?:;(?P<numero>[^:~!@]+))?
        (?::(?P<allegato>\d+))?
        (?:~art(?P<articolo>\d+(?:\.\d+)?[a-z]*)(?:-com(?P<comma>[^!@]+))?)?
        (?:@(?P<originale>originale)|!vig=(?P<vigenza>\d{4}-\d{2}-\d{2}))?
        $""",
    re.VERBOSE,
)
_ARTICOLO = re.compile(r"(\d+)(?:\.(\d+))?([a-z]*)")


def _normalizza_articolo(grezzo: str) -> str:
    pezzi = _ARTICOLO.fullmatch(grezzo)
    if pezzi is None:
        raise InvalidUrnError(grezzo, "numero di articolo non riconosciuto")
    principale, estensione, ordinale = pezzi.groups()
    numero = str(int(principale))
    if estensione is not None:
        numero = f"{numero}.{int(estensione)}"
    return f"{numero}{ordinale}"


def _leggi_data(grezza: str) -> date:
    try:
        return date.fromisoformat(grezza)
    except ValueError as errore:
        raise InvalidUrnError(grezza, "data inesistente") from errore


@dataclass(frozen=True, slots=True)
class Urn:
    """Un identificatore NIR, scomposto nelle sue parti.

    Il suffisso di versione fa parte dell'identificatore perché i rimandi
    dentro il testo restituito lo includono. Vale lo stesso per il comma, che
    però il servizio rifiuta in ingresso: `senza_comma` restituisce
    l'identificatore che si può davvero usare in una richiesta.

    `numero`, `allegato` e `articolo` accettano anche interi e li conservano
    come stringhe: `numero=300` e `numero="300"` costruiscono lo stesso URN.
    L'articolo viene inoltre normalizzato (`"5-bis"` non è ammesso, `"5bis"`
    sì).
    """

    denominazione: str
    anno: int
    data: date | None = None
    numero: str | None = None
    autorita: str = "stato"
    allegato: str | None = None
    articolo: str | None = None
    comma: str | None = None
    versione: date | Literal["originale"] | None = None

    def __post_init__(self) -> None:
        if isinstance(self.versione, datetime):
            object.__setattr__(self, "versione", self.versione.date())
        if self.data is not None and isinstance(self.data, datetime):
            object.__setattr__(self, "data", self.data.date())
        if self.data is not None and self.data.year != self.anno:
            raise InvalidUrnError(str(self.data), f"la data non appartiene all'anno {self.anno}")
        if self.comma is not None and self.articolo is None:
            raise InvalidUrnError(self.comma, "un comma richiede un articolo")
        if self.versione not in (None, "originale") and not isinstance(self.versione, date):
            raise InvalidUrnError(self.versione, "la versione è una data oppure 'originale'")
        if self.articolo is not None:
            object.__setattr__(self, "articolo", _normalizza_articolo(str(self.articolo).lower()))
        numero = None if self.numero is None else str(self.numero).strip()
        object.__setattr__(self, "numero", numero or None)
        if self.allegato is not None:
            object.__setattr__(self, "allegato", str(self.allegato).strip() or None)

    @classmethod
    def parse(cls, testo: str | Urn) -> Urn:
        """Costruisce un `Urn` dalla sua forma testuale.

        Args:
            testo: la forma testuale, oppure un `Urn` già letto, che viene
                restituito com'è.

        Returns:
            L'identificatore scomposto nelle sue parti.

        Examples:
            >>> from normattiva import Urn
            >>> Urn.parse("urn:nir:stato:legge:1990-08-07;241~art5").articolo
            '5'

        Raises:
            InvalidUrnError: il testo non rispetta la grammatica NIR, o porta
                una data che non esiste.
        """
        if isinstance(testo, Urn):
            return testo
        pezzi = _GRAMMATICA.match(str(testo).strip().lower())
        if pezzi is None:
            raise InvalidUrnError(testo)
        grezza = pezzi["data"]
        data = _leggi_data(grezza) if len(grezza) > 4 else None
        vigenza = pezzi["vigenza"]
        versione: date | Literal["originale"] | None = None
        if vigenza:
            versione = _leggi_data(vigenza)
        elif pezzi["originale"]:
            versione = "originale"
        return cls(
            denominazione=pezzi["denominazione"],
            anno=data.year if data else int(grezza),
            data=data,
            numero=pezzi["numero"],
            autorita=pezzi["autorita"],
            allegato=pezzi["allegato"],
            articolo=pezzi["articolo"],
            comma=pezzi["comma"],
            versione=versione,
        )

    @classmethod
    def _di_tipo(
        cls,
        denominazione: str,
        anno: int,
        numero: int | str | None,
        *,
        articolo: int | str | None = None,
        data: date | None = None,
    ) -> Urn:
        return cls(
            denominazione=denominazione,
            anno=anno,
            data=data,
            numero=None if numero is None else str(numero),
            articolo=None if articolo is None else str(articolo),
        )

    @classmethod
    def legge(
        cls,
        anno: int,
        numero: int | str,
        *,
        articolo: int | str | None = None,
        data: date | None = None,
    ) -> Urn:
        """Costruisce l'URN di una legge.

        Args:
            anno: anno di emanazione.
            numero: numero della legge, come intero o come stringa.
            articolo: l'articolo da indirizzare, se ne serve uno solo.
            data: la data esatta di emanazione. Rende l'URN più preciso e
                disambigua fra due atti con lo stesso numero nello stesso anno.

        Examples:
            >>> from normattiva import Urn
            >>> str(Urn.legge(1990, 241, articolo=5))
            'urn:nir:stato:legge:1990;241~art5'
        """
        return cls._di_tipo(LEGGE, anno, numero, articolo=articolo, data=data)

    @classmethod
    def decreto_legge(
        cls,
        anno: int,
        numero: int | str,
        *,
        articolo: int | str | None = None,
        data: date | None = None,
    ) -> Urn:
        """Costruisce l'URN di un decreto-legge."""
        return cls._di_tipo(DECRETO_LEGGE, anno, numero, articolo=articolo, data=data)

    @classmethod
    def decreto_legislativo(
        cls,
        anno: int,
        numero: int | str,
        *,
        articolo: int | str | None = None,
        data: date | None = None,
    ) -> Urn:
        """Costruisce l'URN di un decreto legislativo."""
        return cls._di_tipo(DECRETO_LEGISLATIVO, anno, numero, articolo=articolo, data=data)

    @classmethod
    def dpr(
        cls,
        anno: int,
        numero: int | str,
        *,
        articolo: int | str | None = None,
        data: date | None = None,
    ) -> Urn:
        """Costruisce l'URN di un decreto del Presidente della Repubblica."""
        return cls._di_tipo(DPR, anno, numero, articolo=articolo, data=data)

    @classmethod
    def regio_decreto(
        cls,
        anno: int,
        numero: int | str,
        *,
        articolo: int | str | None = None,
        data: date | None = None,
    ) -> Urn:
        """Costruisce l'URN di un regio decreto."""
        return cls._di_tipo(REGIO_DECRETO, anno, numero, articolo=articolo, data=data)

    def con_articolo(self, articolo: int | str) -> Urn:
        """Costruisce lo stesso atto, indirizzato a uno dei suoi articoli."""
        return replace(self, articolo=str(articolo), comma=None)

    def con_vigenza(self, vigenza: date | Literal["originale"]) -> Urn:
        """Restituisce lo stesso URN con la data di vigenza indicata."""
        return replace(self, versione=vigenza)

    @property
    def senza_comma(self) -> Urn:
        """Lo stesso URN senza il comma, che il servizio rifiuta in ingresso."""
        return self if self.comma is None else replace(self, comma=None)

    @property
    def permalink(self) -> str:
        """Il link pubblico di Normattiva, per verificare sulla fonte."""
        return f"{PERMALINK}{self}"

    def __str__(self) -> str:
        estremi = self.data.isoformat() if self.data else str(self.anno)
        parti = [f"urn:nir:{self.autorita}:{self.denominazione}:{estremi}"]
        if self.numero is not None:
            parti.append(f";{self.numero}")
        if self.allegato is not None:
            parti.append(f":{self.allegato}")
        if self.articolo is not None:
            parti.append(f"~art{self.articolo}")
            if self.comma is not None:
                parti.append(f"-com{self.comma}")
        if self.versione == "originale":
            parti.append("@originale")
        elif isinstance(self.versione, date):
            parti.append(f"!vig={self.versione.isoformat()}")
        return "".join(parti)


__all__ = ["Urn"]
"""Le costanti di denominazione qui sopra sono di supporto alle classmethod e non fanno
parte dell'API pubblica: un URN di legge si costruisce con `Urn.legge`, non concatenando
`LEGGE` a mano."""
