"""Trasforma i modelli in output: righe per il terminale, strutture per il JSON.

Ogni cosa che i comandi producono ha due forme: `mostra_*` la scrive per chi ha
un terminale davanti, `dati_*` la riduce alle strutture che `json.dumps` sa
scrivere. Le due non si chiamano fra loro: così un cambiamento
nell'allineamento di una colonna non cambia anche la forma del JSON, che resta
stabile per gli script che ci costruiscono sopra.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from datetime import date

    from normattiva.codici import AttoNoto
    from normattiva.modelli import (
        AttoTrovato,
        Collection,
        DettaglioAtto,
        EsitoRicerca,
        EstremiAtto,
        Faccetta,
        FinestraVigenza,
        PubblicazioneGazzetta,
        Tipologica,
    )
    from normattiva.urn import Urn

_FORTE = "\x1b[1m"
_TENUE = "\x1b[2m"
_FINE = "\x1b[0m"

ORDINE = "{:>4}  "
"""Il numero d'ordine davanti a ogni atto, negli elenchi."""

RIENTRO = " " * len(ORDINE.format(0))
"""Il rientro che allinea le righe seguenti sotto la prima."""


@dataclass(frozen=True, slots=True)
class Stile:
    """Le capacità del terminale di destinazione: colori e larghezza."""

    colori: bool = False
    larghezza: int = 80

    def forte(self, testo: str) -> str:
        """Il testo in grassetto, se i colori sono attivi."""
        return f"{_FORTE}{testo}{_FINE}" if self.colori else testo

    def tenue(self, testo: str) -> str:
        """Il testo smorzato, per etichette, note a piè di pagina e contorno."""
        return f"{_TENUE}{testo}{_FINE}" if self.colori else testo


def _giorno(quando: date | None) -> str | None:
    return quando.isoformat() if quando else None


def _urn_di(estremi: EstremiAtto, richiesto: Urn | None) -> Urn | None:
    """L'URN da mostrare: quello richiesto se c'è, altrimenti quello degli estremi.

    Quello richiesto è più ricco, perché porta l'articolo e la vigenza che gli
    estremi da soli non conoscono. Per i tipi di atto la cui forma URN non è
    verificata non esiste né l'uno né l'altro, e il risultato è `None` invece
    di un identificatore inventato.
    """
    if richiesto is not None:
        return richiesto
    return estremi.urn if estremi.ha_urn else None


def scheda(stile: Stile, coppie: Sequence[tuple[str, str | None]]) -> str:
    """Un blocco «etichetta valore» incolonnato, senza le etichette vuote."""
    presenti = [(etichetta, valore) for etichetta, valore in coppie if valore]
    if not presenti:
        return ""
    larghezza = max(len(etichetta) for etichetta, _ in presenti)
    return "\n".join(
        f"{stile.tenue(etichetta.ljust(larghezza))}  {valore}" for etichetta, valore in presenti
    )


def tabella(stile: Stile, intestazione: Sequence[str], righe: Sequence[Sequence[str]]) -> str:
    """Colonne allineate sul contenuto più lungo, con l'intestazione smorzata."""
    if not righe:
        return ""
    larghezze = [
        max(len(str(riga[colonna])) for riga in [intestazione, *righe])
        for colonna in range(len(intestazione))
    ]

    def _riga(celle: Sequence[str]) -> str:
        return "  ".join(
            str(cella).ljust(larghezza) for cella, larghezza in zip(celle, larghezze, strict=True)
        ).rstrip()

    return "\n".join([stile.tenue(_riga(intestazione)), *(_riga(riga) for riga in righe)])


def a_capo(stile: Stile, testo: str, rientro: str = RIENTRO) -> str:
    """Il testo mandato a capo alla larghezza del terminale, tutto rientrato."""
    return textwrap.fill(
        testo,
        width=stile.larghezza,
        initial_indent=rientro,
        subsequent_indent=rientro,
        # Un URN o un «416-bis» spezzati a metà non si copiano più: meglio una
        # riga che sporge di una parola che una parola che non esiste.
        break_long_words=False,
        break_on_hyphens=False,
    )


def prosa(stile: Stile, testo: str) -> str:
    """Il testo mandato a capo un capoverso per volta, senza rientri.

    Le righe inviate dal servizio sono capoversi, non righe da rispettare: se
    il terminale le tagliasse a metà parola sarebbero meno leggibili di così.
    """
    return "\n".join(
        textwrap.fill(riga, width=stile.larghezza, break_long_words=False, break_on_hyphens=False)
        if riga.strip()
        else ""
        for riga in testo.splitlines()
    )


def blocchi(*pezzi: str) -> str:
    """Unisce i pezzi non vuoti con una riga bianca fra l'uno e l'altro."""
    return "\n\n".join(pezzo for pezzo in pezzi if pezzo)


def quanti(numero: int, singolare: str, plurale: str) -> str:
    """«1 atto», «2 atti», «0 atti»: in italiano l'uno non regge il plurale."""
    return f"{numero} {singolare if numero == 1 else plurale}"


def fonte(stile: Stile, attribuzione: str) -> str:
    """La riga di attribuzione che la licenza dei dati obbliga a portare."""
    return a_capo(stile, attribuzione, rientro="")


# --- il testo di un atto ------------------------------------------------------


def mostra_atto(stile: Stile, atto: DettaglioAtto, *, richiesto: Urn | None = None) -> str:
    """Il testo di un atto per il terminale: intestazione, coordinate, testo, note.

    Il titolo apre perché è il nome per esteso dell'atto; la citazione sta fra
    le coordinate, insieme alle altre cose che si copiano. Il testo viene
    mandato a capo alla larghezza del terminale: è l'output per chi legge, e
    chi vuole le righe originali del servizio usa il JSON.
    """
    urn = _urn_di(atto.atto, richiesto)
    testa = [stile.forte(atto.titolo or atto.atto.citazione)]
    if atto.sottotitolo:
        testa.append(a_capo(stile, atto.sottotitolo, rientro=""))
    coordinate = scheda(
        stile,
        [
            ("Citazione", atto.atto.citazione),
            ("Articolo", urn.articolo if urn else None),
            ("Gazzetta", str(atto.gazzetta)),
            ("Vigenza", str(atto.finestra) if atto.finestra else None),
            ("URN", str(urn) if urn else None),
            ("Permalink", urn.permalink if urn else None),
        ],
    )
    note = ""
    if atto.note_aggiornamento:
        note = f"{stile.forte('Note di aggiornamento')}\n{prosa(stile, atto.note_aggiornamento)}"
    return blocchi(
        "\n".join(testa),
        coordinate,
        prosa(stile, atto.preambolo or ""),
        prosa(stile, atto.testo),
        note,
        stile.tenue(fonte(stile, atto.attribuzione)),
    )


def dati_atto(atto: DettaglioAtto, *, richiesto: Urn | None = None) -> dict[str, Any]:
    """Un atto come struttura per il JSON: le stesse informazioni, senza impaginazione."""
    urn = _urn_di(atto.atto, richiesto)
    return {
        "citazione": atto.atto.citazione,
        "titolo": atto.titolo,
        "sottotitolo": atto.sottotitolo,
        "urn": str(urn) if urn else None,
        "permalink": urn.permalink if urn else None,
        "estremi": dati_estremi(atto.atto),
        "gazzetta": dati_gazzetta(atto.gazzetta),
        "vigenza": dati_finestra(atto.finestra),
        "preambolo": atto.preambolo,
        "testo": atto.testo,
        "commi": [{"numero": comma.numero, "testo": comma.testo} for comma in atto.commi],
        "note_aggiornamento": atto.note_aggiornamento,
        "possibile_troncamento": atto.possibile_troncamento,
        "fonte": atto.attribuzione,
    }


def dati_estremi(estremi: EstremiAtto) -> dict[str, Any]:
    """Il tipo, la data e il numero di un provvedimento."""
    return {
        "denominazione": estremi.denominazione,
        "data": _giorno(estremi.data),
        "numero": estremi.numero,
        "citazione": estremi.citazione,
    }


def dati_gazzetta(gazzetta: PubblicazioneGazzetta) -> dict[str, Any]:
    """Dove e quando l'atto è comparso in Gazzetta Ufficiale."""
    return {
        "data": _giorno(gazzetta.data),
        "numero": gazzetta.numero,
        "codice_redazionale": gazzetta.codice_redazionale,
        "supplemento": gazzetta.supplemento,
        "numero_supplemento": gazzetta.numero_supplemento,
    }


def dati_finestra(finestra: FinestraVigenza | None) -> dict[str, Any] | None:
    """Il tratto di tempo in cui una versione è stata in vigore."""
    if finestra is None:
        return None
    return {"inizio": _giorno(finestra.inizio), "fine": _giorno(finestra.fine)}


# --- i risultati di una ricerca ----------------------------------------------


def mostra_trovati(stile: Stile, trovati: Sequence[AttoTrovato], *, da: int = 1) -> str:
    """Un atto per voce: numero d'ordine, citazione, titolo, identificatore."""
    voci = []
    for posizione, trovato in enumerate(trovati, start=da):
        righe = [ORDINE.format(posizione) + stile.forte(trovato.estremi.citazione)]
        if trovato.titolo:
            righe.append(a_capo(stile, trovato.titolo))
        if trovato.estremi.ha_urn:
            righe.append(stile.tenue(f"{RIENTRO}{trovato.estremi.urn}"))
        voci.append("\n".join(righe))
    return "\n\n".join(voci)


def mostra_esito(stile: Stile, esito: EsitoRicerca, *, da: int = 1, faccette: bool = False) -> str:
    """Il conto dei risultati, la pagina, gli atti e, a richiesta, le faccette.

    Args:
        stile: il terminale su cui si scrive.
        esito: la pagina di risultati da rendere.
        da: il numero d'ordine del primo atto, che dipende da quanti se ne sono
            chiesti per pagina e quindi lo sa solo chi ha fatto la richiesta.
        faccette: se mostrare anche i valori con cui restringere.
    """
    trovati = quanti(esito.totale, "atto trovato", "atti trovati")
    dove = f", pagina {esito.pagina} di {esito.pagine}" if esito.pagine > 1 else ""
    return blocchi(
        stile.forte(trovati + dove),
        mostra_trovati(stile, esito.atti, da=da),
        mostra_faccette(stile, esito) if faccette else "",
    )


def mostra_faccette(stile: Stile, esito: EsitoRicerca) -> str:
    """Le tre faccette con cui restringere, ciascuna con il suo nome di opzione."""
    gruppi = [
        ("--tipo", esito.faccette.per_tipo),
        ("--anno", esito.faccette.per_anno),
        ("--emettitore", esito.faccette.per_emettitore),
    ]
    pezzi = []
    for opzione, voci in gruppi:
        if not voci:
            continue
        righe = [
            [voce.codice, str(voce.conteggio), _descrizione(voce)]
            for voce in sorted(voci, key=lambda v: -v.conteggio)
        ]
        intestazione = ["codice", "atti", "descrizione" if any(r[2] for r in righe) else ""]
        pezzi.append(f"{stile.forte(opzione)}\n{tabella(stile, intestazione, righe)}")
    return "\n\n".join(pezzi)


def _descrizione(faccetta: Faccetta) -> str:
    """La descrizione della faccetta, vuota quando ripete il codice.

    Le faccette per anno portano l'anno due volte, e una colonna che ripete
    quella accanto non aiuta a scegliere.
    """
    descrizione = faccetta.descrizione or ""
    return "" if descrizione == faccetta.codice else descrizione


def dati_trovato(trovato: AttoTrovato) -> dict[str, Any]:
    """Un atto come esce da una ricerca, con le evidenziazioni se ci sono."""
    return {
        "citazione": trovato.estremi.citazione,
        "titolo": trovato.titolo,
        "descrizione": trovato.descrizione,
        "urn": str(trovato.urn) if trovato.estremi.ha_urn else None,
        "estremi": dati_estremi(trovato.estremi),
        "gazzetta": dati_gazzetta(trovato.gazzetta),
        "ultima_modifica": _giorno(trovato.ultima_modifica),
        "atti_modificanti": list(trovato.atti_modificanti),
        "evidenziazioni": [
            {"articolo": voce.articolo, "frammenti": list(voce.frammenti)}
            for voce in trovato.evidenziazioni
        ],
    }


def dati_esito(esito: EsitoRicerca, attribuzione: str) -> dict[str, Any]:
    """Una pagina di risultati, con il totale e le faccette per restringere."""
    return {
        "totale": esito.totale,
        "pagina": esito.pagina,
        "pagine": esito.pagine,
        "atti": [dati_trovato(trovato) for trovato in esito.atti],
        "faccette": {
            "per_tipo": [dati_faccetta(v) for v in esito.faccette.per_tipo],
            "per_anno": [dati_faccetta(v) for v in esito.faccette.per_anno],
            "per_emettitore": [dati_faccetta(v) for v in esito.faccette.per_emettitore],
        },
        "fonte": attribuzione,
    }


def dati_faccetta(faccetta: Faccetta) -> dict[str, Any]:
    """Un valore con cui restringere, e quanti atti ci ricadono."""
    return {
        "codice": faccetta.codice,
        "conteggio": faccetta.conteggio,
        "descrizione": faccetta.descrizione,
    }


# --- la storia di un articolo -------------------------------------------------


def mostra_versioni(stile: Stile, versioni: Sequence[DettaglioAtto]) -> str:
    """Una riga per versione: quando è entrata in vigore e fino a quando."""
    righe = []
    for posizione, versione in enumerate(versioni, start=1):
        finestra = str(versione.finestra) if versione.finestra else "senza finestra dichiarata"
        marchio = " (in vigore)" if versione.finestra and versione.finestra.aperta else ""
        righe.append(ORDINE.format(posizione) + finestra + stile.tenue(marchio))
    return "\n".join(righe)


def dati_versione(versione: DettaglioAtto, urn: Urn) -> dict[str, Any]:
    """Una versione, con l'URN da cui rileggerla per intero."""
    inizio = versione.finestra.inizio if versione.finestra else None
    return {
        "urn": str(urn.con_vigenza(inizio)) if inizio else str(urn),
        "vigenza": dati_finestra(versione.finestra),
        "note_aggiornamento": versione.note_aggiornamento,
        "possibile_troncamento": versione.possibile_troncamento,
    }


# --- identificatori e dizionari ----------------------------------------------


def mostra_urn(stile: Stile, urn: Urn) -> str:
    """Un URN smontato nelle sue parti, con il permalink da aprire."""
    return blocchi(
        stile.forte(str(urn)),
        scheda(
            stile,
            [
                ("Autorità", urn.autorita),
                ("Denominazione", urn.denominazione),
                ("Anno", str(urn.anno)),
                ("Data", _giorno(urn.data)),
                ("Numero", urn.numero),
                ("Allegato", urn.allegato),
                ("Articolo", urn.articolo),
                ("Comma", urn.comma),
                ("Versione", _versione(urn)),
                ("Permalink", urn.permalink),
            ],
        ),
    )


def _versione(urn: Urn) -> str | None:
    if urn.versione is None:
        return None
    return urn.versione if isinstance(urn.versione, str) else urn.versione.isoformat()


def dati_urn(urn: Urn) -> dict[str, Any]:
    """Le parti di un URN, come le legge la grammatica NIR."""
    return {
        "urn": str(urn),
        "autorita": urn.autorita,
        "denominazione": urn.denominazione,
        "anno": urn.anno,
        "data": _giorno(urn.data),
        "numero": urn.numero,
        "allegato": urn.allegato,
        "articolo": urn.articolo,
        "comma": urn.comma,
        "versione": _versione(urn),
        "permalink": urn.permalink,
    }


def mostra_codici(stile: Stile, noti: Iterable[tuple[str, AttoNoto]]) -> str:
    """Gli atti che si possono chiamare per nome, con l'URN a cui rispondono."""
    righe = [[nome, atto.nome, str(atto.base), atto.allegato_articoli or ""] for nome, atto in noti]
    return tabella(stile, ["nome", "atto", "urn", "allegato"], righe)


def mostra_tipologiche(stile: Stile, voci: Sequence[Tipologica]) -> str:
    """Un dizionario del servizio: il codice da passare e che cosa significa."""
    return tabella(stile, ["codice", "descrizione"], [[v.codice, v.descrizione] for v in voci])


def dati_tipologica(voce: Tipologica) -> dict[str, Any]:
    """Una voce di dizionario."""
    return {"codice": voce.codice, "descrizione": voce.descrizione}


def mostra_collezioni(stile: Stile, voci: Sequence[Collection]) -> str:
    """Gli archivi già confezionati, con il numero di atti di ciascuno.

    La colonna «formato» porta il nome che il campo ha nel servizio, ma i suoi
    valori sono modalità di vigenza. Senza la nota sotto la tabella, lo si
    scoprirebbe solo passando `--formato O` e vedendolo rifiutato.
    """
    righe = [[v.name, v.format, str(v.total_atti), v.description or ""] for v in voci]
    return blocchi(
        tabella(stile, ["nome", "formato", "atti", "descrizione"], righe),
        stile.tenue(
            "Il «formato» dichiarato qui è la modalità di vigenza, e si sceglie con "
            "--modalita. Il formato del file, JSON o PDF o altro, si sceglie con --formato."
        ),
    )


def dati_collezione(collezione: Collection) -> dict[str, Any]:
    """Un archivio già confezionato."""
    return {
        "nome": collezione.name,
        "formato": collezione.format,
        "numero_atti": collezione.total_atti,
        "descrizione": collezione.description,
        "creata_il": _giorno(collezione.created_at),
    }
