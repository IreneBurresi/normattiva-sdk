"""Gli obblighi della licenza sono verificabili, quindi vanno verificati.

L'avviso legale di Normattiva non chiede una riga di cortesia: chiede tre
menzioni precise. Una riga di attribuzione è però il genere di testo che qualcuno
accorcia perché «è troppo lunga», e la libreria smette di essere conforme senza
che niente si rompa. Qui si rompe.

Fonte: avviso legale del portale dati.normattiva.it, letto il 2026-08-24.

    La riproduzione dei testi forniti nel formato elettronico è consentita
    purché venga menzionata la fonte, il carattere non autentico e gratuito.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

import normattiva
from normattiva import ATTRIBUZIONE, Corpus, DettaglioAtto, EstremiAtto, PubblicazioneGazzetta
from tests.dati import FIXTURES

RADICE = Path(__file__).resolve().parent.parent

MENZIONI_DOVUTE = {
    "la fonte": r"normattiva\.it",
    "il carattere non autentico": r"non autentic",
    "il carattere gratuito": r"gratuit",
}
"""Le tre menzioni che l'avviso legale impone, con come si riconoscono."""


class TestLAttribuzione:
    @pytest.mark.parametrize(("obbligo", "spia"), MENZIONI_DOVUTE.items())
    def test_porta_ogni_menzione_dovuta(self, obbligo: str, spia: str) -> None:
        assert re.search(spia, ATTRIBUZIONE, re.I), (
            f"l'attribuzione non menziona {obbligo}, che l'avviso legale di "
            "Normattiva impone a chi riproduce i testi"
        )

    def test_nomina_la_licenza(self) -> None:
        """CC BY 4.0 dal 1° gennaio 2026, finita la fase sperimentale con la clausola NC."""
        assert "CC BY 4.0" in ATTRIBUZIONE

    def test_dice_qual_e_il_testo_che_prevale(self) -> None:
        assert "Gazzetta Ufficiale" in ATTRIBUZIONE

    def test_sta_in_una_riga_di_referto(self) -> None:
        """Se cresce troppo nessuno la ricopia, e allora tanto vale non averla."""
        assert len(ATTRIBUZIONE) < 320


class TestOgniModelloLaEspone:
    """Chi riceve i dati deve poter prendere l'attribuzione da dove sono i dati."""

    def test_il_dettaglio(self) -> None:
        atto = DettaglioAtto(
            estremi=EstremiAtto("LEGGE", date(1990, 8, 7), "241"),
            gazzetta=PubblicazioneGazzetta(date(1990, 8, 18)),
            titolo="",
            sottotitolo=None,
            testo_html="",
            finestra=None,
        )
        assert atto.attribuzione == ATTRIBUZIONE

    def test_il_corpus_e_gli_atti_che_contiene(self) -> None:
        corpus = Corpus.from_zip(FIXTURES / "export_multivigente.zip")
        assert corpus.attribuzione == ATTRIBUZIONE
        assert corpus.atti[0].attribuzione == ATTRIBUZIONE

    def test_e_raggiungibile_dal_pacchetto(self) -> None:
        assert normattiva.ATTRIBUZIONE == ATTRIBUZIONE


class TestLaDocumentazioneLoDice:
    """Non basta che la libreria sia conforme: deve dirlo a chi la usa.

    Chi costruisce qualcosa su questi dati eredita gli stessi obblighi, e se la
    documentazione non glieli spiega non ha modo di saperlo.
    """

    @staticmethod
    def _testo(*percorsi: str) -> str:
        """Le pagine appiattite: una frase spezzata su due righe è la stessa frase."""
        unito = "\n".join((RADICE / p).read_text(encoding="utf-8") for p in percorsi)
        return " ".join(re.sub(r"^\s*>\s?", "", unito, flags=re.M).split())

    VETRINA = ("docs/index.md", "docs/progetto/licenza.md", "README.md")

    @pytest.mark.parametrize(
        ("cosa", "spia"),
        [
            ("che è un progetto non ufficiale", r"non ufficiale"),
            ("che non è affiliato con IPZS", r"non\s+(è\s+)?affiliat"),
            ("che il codice è gratuito e MIT", r"\bMIT\b"),
            ("da dove vengono i dati", r"normattiva\.it"),
            ("con che licenza", r"CC BY 4\.0"),
            ("che il testo non è ufficiale", r"non (ha carattere di ufficialità|autentic)"),
            ("che prevale la Gazzetta", r"Gazzetta Ufficiale"),
        ],
    )
    def test_la_copertina_e_la_pagina_di_licenza_lo_dicono(self, cosa: str, spia: str) -> None:
        assert re.search(spia, self._testo(*self.VETRINA), re.I), f"manca: {cosa}"

    def test_il_disclaimer_sta_anche_nel_piede_di_ogni_pagina(self) -> None:
        """Chi arriva da una ricerca atterra su una pagina interna, non in copertina."""
        configurazione = (RADICE / "mkdocs.yml").read_text(encoding="utf-8")
        piede = re.search(r"^copyright: *>?\n((?:  .*\n)+)", configurazione, re.M)
        assert piede, "mkdocs.yml non dichiara un piede"
        testo = piede.group(1)
        for spia in (r"non ufficiale", r"CC BY 4\.0", r"Gazzetta"):
            assert re.search(spia, testo, re.I), f"il piede non menziona {spia}"


class TestLaDocumentazioneNonLaAccorcia:
    """Una copia dell'attribuzione nella prosa invecchia da sola.

    La riga vive nel codice, ma la documentazione la mostra per far vedere
    com'è fatta. Quelle copie non sono legate a niente: quando la costante
    cambia restano indietro senza che nulla si rompa, e chi legge la
    documentazione impara una formula non più conforme. È già successo.
    """

    @staticmethod
    def _appiattito(testo: str) -> str:
        """Il testo senza i segni di commento, di citazione e gli a capo."""
        return " ".join(re.sub(r"^\s*(#|>)\s?", "", testo, flags=re.M).split())

    SCRITTE = tuple(
        p.relative_to(RADICE)
        for p in [*sorted((RADICE / "docs").rglob("*.md")), RADICE / "README.md"]
        if "Fonte: Normattiva" in p.read_text(encoding="utf-8")
    )

    def test_qualcuno_la_mostra(self) -> None:
        """Se nessuna pagina la mostra, la prova sotto non verifica più niente."""
        assert self.SCRITTE, "nessuna pagina mostra l'attribuzione"

    @pytest.mark.parametrize("pagina", SCRITTE, ids=str)
    def test_ogni_copia_dice_quello_che_dice_la_costante(self, pagina: Path) -> None:
        testo = (RADICE / pagina).read_text(encoding="utf-8")
        assert self._appiattito(ATTRIBUZIONE) in self._appiattito(testo), (
            f"{pagina} mostra un'attribuzione diversa da normattiva.ATTRIBUZIONE"
        )
