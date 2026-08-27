"""Conversione dell'HTML servito da Normattiva in testo utilizzabile da un programma.

Il markup è generato da Akoma Ntoso e i suoi nomi di classe sono stabili: per
questo è affidabile separare il testo dell'articolo dalle note redazionali di
aggiornamento accodate in fondo e dalla formula introduttiva in testa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

NOTE = "art_aggiornamento-akn"
PREAMBOLO = frozenset(
    {
        "preamble-before-title-akn",
        "preamble-title-akn",
        "preamble-end-akn",
        "formula-introduttiva",
    }
)
COMMA = "art-comma-div-akn"
NUMERO_COMMA = "comma-num-akn"
TESTO_COMMA = "art_text_in_comma"

VUOTI = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
"""Elementi HTML senza tag di chiusura: metterli sulla pila la lascerebbe sbilanciata."""

BLOCCHI = frozenset(
    {
        "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt",
        "h1", "h2", "h3", "h4", "h5", "h6", "hr", "li", "ol", "p", "section",
        "table", "td", "th", "tr", "ul",
    }
)  # fmt: skip
"""Elementi che terminano una riga: senza un a capo le parole di blocchi adiacenti
si incollerebbero."""

CHIUSURA_IMPLICITA = {
    "p": {"p"},
    "li": {"li"},
    "td": {"td", "th"},
    "th": {"td", "th"},
    "tr": {"tr"},
}
"""Tag che aprendosi chiudono il precedente: `<p>uno<p>due` sono due paragrafi
consecutivi, non annidati."""

_SPAZI = re.compile(r"[^\S\n]+")
_RIGHE_VUOTE = re.compile(r"\n\s*\n+")
_NUMERO = re.compile(r"\d+(?:[-.]?[a-z]+)?", re.I)

_TRONCAMENTI = frozenset(
    {
        "a", "be", "ca", "co", "da", "de", "di", "fa", "li",
        "mo", "ne", "pe", "po", "se", "sta", "su", "to", "va",
    }
)  # fmt: skip
"""Parole in cui l'apostrofo finale indica troncamento, non accento: `po'`, `va'`,
`de' Medici`.

Alcune sono ambigue anche per un lettore umano: `ne'` può stare per «nei» o per
«né», `se'` per «sei» o per «sé». In questi casi la libreria lascia il testo
com'è invece di indovinare: in un testo di legge una parola sbagliata è peggio
di una grafia antica lasciata intatta.
"""

_ACCENTI = {"a": "à", "e": "è", "i": "ì", "o": "ò", "u": "ù"}
_USCITE_ACUTE = ("ch",)
"""Terminazioni per cui la `e'` finale vale `é` e non `è`: perché, poiché, benché."""

_VOCALE_APOSTROFO = re.compile(r"([a-z]*)([aeiou])'(?![a-zA-Z])", re.I)


def _ripulisci(pezzi: list[str]) -> str:
    testo = _SPAZI.sub(" ", "".join(pezzi))
    testo = _RIGHE_VUOTE.sub("\n", testo)
    return "\n".join(riga.strip() for riga in testo.split("\n") if riga.strip())


@dataclass(frozen=True, slots=True)
class Comma:
    """Un comma numerato di un articolo."""

    numero: str
    testo: str


@dataclass(frozen=True, slots=True)
class Contenuto:
    """L'HTML di un articolo, smontato nelle sue parti."""

    corpo: str
    commi: tuple[Comma, ...]
    note: str | None = None
    preambolo: str | None = None


class _Estrattore(HTMLParser):
    """Traccia l'annidamento dei tag per attribuire ogni frammento di testo al suo contenitore.

    La pila conserva il nome del tag oltre alle sue classi, perché un tag di
    chiusura spaiato non deve chiudere il contenitore sbagliato: quando succede,
    il testo dell'articolo finisce fra le note redazionali e sparisce dal corpo.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._pila: list[tuple[str, frozenset[str]]] = []
        self._corpo: list[str] = []
        self._note: list[str] = []
        self._preambolo: list[str] = []
        self._commi: list[tuple[list[str], list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in VUOTI:
            if tag in BLOCCHI:
                self._deposito().append("\n")
            return
        self._chiudi_implicito(tag)
        classi = frozenset((dict(attrs).get("class") or "").split())
        self._pila.append((tag, classi))
        if COMMA in classi:
            self._commi.append(([], []))

    def _chiudi_implicito(self, tag: str) -> None:
        chiude = CHIUSURA_IMPLICITA.get(tag)
        if chiude and any(aperto in chiude for aperto, _ in self._pila):
            self.handle_endtag(next(a for a, _ in reversed(self._pila) if a in chiude))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in VUOTI:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in VUOTI:
            return
        for quanti, (aperto, _) in enumerate(reversed(self._pila), start=1):
            if aperto == tag:
                del self._pila[len(self._pila) - quanti :]
                break
        if tag in BLOCCHI:
            self._deposito().append("\n")

    def handle_data(self, data: str) -> None:
        self._deposito().append(data)
        self._deposito_comma(data)

    def _attive(self) -> frozenset[str]:
        if not self._pila:
            return frozenset()
        return frozenset().union(*(classi for _, classi in self._pila))

    def _deposito(self) -> list[str]:
        attive = self._attive()
        if NOTE in attive:
            return self._note
        if attive & PREAMBOLO:
            return self._preambolo
        return self._corpo

    def _deposito_comma(self, data: str) -> None:
        attive = self._attive()
        if NOTE in attive or COMMA not in attive or not self._commi:
            return
        numero, testo = self._commi[-1]
        if NUMERO_COMMA in attive:
            numero.append(data)
        elif TESTO_COMMA in attive:
            testo.append(data)

    @property
    def contenuto(self) -> Contenuto:
        commi = []
        for grezzo_numero, grezzo_testo in self._commi:
            trovato = _NUMERO.search("".join(grezzo_numero))
            if trovato is None:
                continue
            commi.append(Comma(trovato.group(), _ripulisci(grezzo_testo)))
        return Contenuto(
            corpo=_ripulisci(self._corpo),
            commi=tuple(commi),
            note=_ripulisci(self._note) or None,
            preambolo=_ripulisci(self._preambolo) or None,
        )


def estrai(html: str) -> Contenuto:
    """Fa il parsing di un `articoloHtml` e lo separa in testo, commi e note."""
    estrattore = _Estrattore()
    estrattore.feed(html)
    estrattore.close()
    return estrattore.contenuto


def _accenta(pezzi: re.Match[str]) -> str:
    prefisso, vocale = pezzi.group(1), pezzi.group(2)
    minuscolo = (prefisso + vocale).lower()
    if minuscolo in _TRONCAMENTI:
        return pezzi.group(0)
    acuta = vocale.lower() == "e" and prefisso.lower().endswith(_USCITE_ACUTE)
    accentata = "é" if acuta else _ACCENTI[vocale.lower()]
    if vocale.isupper():
        accentata = accentata.upper()
    return f"{prefisso}{accentata}"


def normalize_accents(testo: str) -> str:
    """Riscrive `attivita'` come `attività`, cioè con la grafia italiana corretta.

    L'esportazione conserva le vocali accentate come vocale più apostrofo,
    quindi una ricerca sulla grafia corretta non trova nulla. Le elisioni
    (`dell'articolo`) e i troncamenti (`po'`, `va'`, `de' Medici`) restano
    intatti.

    Sul percorso interattivo non serve: lì gli accenti arrivano come entità
    HTML e sono già scritti correttamente.
    """
    return _VOCALE_APOSTROFO.sub(_accenta, testo)


__all__ = ["Comma", "Contenuto", "estrai", "normalize_accents"]
