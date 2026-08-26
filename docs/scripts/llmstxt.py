"""Aggiustamenti all'HTML prima che diventi Markdown per `llms.txt`.

Il plugin converte l'HTML costruito, non il sorgente: è il motivo per cui nel
Markdown c'è anche il riferimento generato dalle docstring. Restano però un
paio di cose che la conversione perde da sola, e che si rimettono a posto qui.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - solo per i tipi
    from bs4 import BeautifulSoup


def preprocess(soup: BeautifulSoup, output: str) -> None:
    """Rende convertibili i diagrammi e toglie i segni di ancoraggio.

    Args:
        soup: l'HTML della pagina, già ripulito dal plugin.
        output: il file che si sta scrivendo (`llms.txt`, la pagina, o il
            documento completo).
    """
    _diagrammi_taggati(soup)
    _via_le_ancore(soup)


def _diagrammi_taggati(soup: BeautifulSoup) -> None:
    """Mermaid scrive `<pre class="mermaid">`, che diventa un blocco senza lingua.

    Un blocco senza lingua, in Markdown, è testo qualunque: chi legge non sa
    che quelle righe sono un diagramma, e nessun visualizzatore le disegna.
    Qui il blocco viene riscritto nella forma che markdownify sa etichettare.
    """
    for blocco in soup.find_all("pre", class_="mermaid"):
        codice = soup.new_tag("code")
        codice.string = blocco.get_text()
        blocco.clear()
        # la lingua va dichiarata sul `pre`: il convertitore la cerca lì e sul
        # genitore, non sul `code` che sta dentro
        blocco.attrs = {"class": ["language-mermaid"]}
        blocco.append(codice)


def _via_le_ancore(soup: BeautifulSoup) -> None:
    """I permalink «¶» accanto ai titoli non vogliono dire niente fuori dal sito."""
    for ancora in soup.select("a.headerlink"):
        ancora.decompose()
