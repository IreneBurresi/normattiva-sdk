"""L'interfaccia a riga di comando della libreria.

Un comando per capacità: `testo` legge un atto, `cerca` lo trova, `cronologia`
ne elenca le versioni, `esporta` ne scarica l'archivio. Ogni comando produce
output leggibile, oppure JSON con `--json`, e restituisce un codice di uscita
che indica la famiglia del problema: richiesta sbagliata, atto non trovato,
guasto del servizio.

Questo modulo non aggiunge capacità alla libreria: traduce argomenti in
chiamate e modelli in righe di output, e delega ogni decisione alla libreria.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import textwrap
from dataclasses import replace
from datetime import date
from enum import IntEnum
from itertools import islice
from typing import TYPE_CHECKING, Any, NoReturn

from normattiva import __version__ as _versione_libreria
from normattiva import _output, codici
from normattiva.client import Normattiva
from normattiva.errori import (
    AmbiguityError,
    ConnectionError,
    ExportFailedError,
    InvalidArgumentError,
    NormattivaError,
    NotFoundError,
    NotYetInForceError,
    OverloadedError,
    RequestBlockedError,
    UnexpectedResponseError,
    VersionNotFoundError,
)
from normattiva.esporta import TIMEOUT
from normattiva.modelli import (
    ATTRIBUZIONE,
    AttoTrovato,
    ClasseProvvedimento,
    EsitoRicerca,
    ExportMode,
    Format,
    Sort,
)
from normattiva.urn import Urn

if TYPE_CHECKING:
    from collections.abc import Sequence

    from normattiva.client import Intervallo, Vigenza
    from normattiva.codici import AttoNoto

PROGRAMMA = "normattiva"
USER_AGENT = "normattiva-sdk-cli (+https://github.com/ireneburresi/normattiva-sdk)"
"""Lo User-Agent della CLI. Distingue il traffico del terminale da quello di uno
script: un'informazione che a IPZS non costa niente avere e a noi niente dare."""
LARGHEZZA_MASSIMA = 100


class Uscita(IntEnum):
    """I codici di uscita del programma.

    Sono divisi per famiglia di causa, non per eccezione: uno script che usa il
    comando deve poter distinguere una richiesta sbagliata, un atto inesistente
    e un guasto del servizio senza conoscere la gerarchia delle eccezioni.
    """

    OK = 0
    ERRORE = 1
    USO = 2
    NON_TROVATO = 3
    RICHIESTA = 4
    SERVIZIO = 5
    INTERROTTO = 130
    LETTURA_INTERROTTA = 141


_FAMIGLIE: tuple[tuple[type[NormattivaError], Uscita], ...] = (
    (NotFoundError, Uscita.NON_TROVATO),
    (VersionNotFoundError, Uscita.NON_TROVATO),
    (NotYetInForceError, Uscita.NON_TROVATO),
    (ConnectionError, Uscita.SERVIZIO),
    (RequestBlockedError, Uscita.SERVIZIO),
    (UnexpectedResponseError, Uscita.SERVIZIO),
    (OverloadedError, Uscita.SERVIZIO),
    (ExportFailedError, Uscita.SERVIZIO),
)
"""Le eccezioni che non riguardano la richiesta, con la famiglia di uscita corrispondente.

Tutte le altre discendono da `NormattivaError` per una richiesta sbagliata, e
finiscono in `Uscita.RICHIESTA` senza bisogno di comparire qui.
"""


class _UsoSbagliato(Exception):
    """Gli argomenti sono validi uno per uno ma si contraddicono fra loro.

    argparse copre quello che si può dichiarare nel parser; questo copre il
    resto, e viene reso con lo stesso codice di uscita.
    """


class _Aiuto(argparse.HelpFormatter):
    """Manda a capo la prosa, ma lascia intatti i blocchi già impaginati.

    argparse passa descrizione ed epilogo per lo stesso metodo, quindi l'unico
    modo di distinguerli è il contenuto: un testo con righe rientrate è già
    impaginato da chi l'ha scritto, e riempirlo lo rovinerebbe.
    """

    def _fill_text(self, text: str, width: int, indent: str) -> str:
        if any(riga.startswith(("  ", "\t")) for riga in text.splitlines()):
            return textwrap.indent(text, indent)
        return super()._fill_text(text, width, indent)


# --- output -------------------------------------------------------------------


def _stampa(testo: str) -> None:
    if testo:
        print(testo)


def _scrivi(dati: object) -> None:
    print(json.dumps(dati, ensure_ascii=False, indent=2))


def _avviso(messaggio: str) -> None:
    print(f"{PROGRAMMA}: {messaggio}", file=sys.stderr)


def _a_colori(scelta: str) -> bool:
    """Se colorare: su richiesta esplicita, oppure se c'è un terminale che guarda."""
    if scelta == "sempre":
        return True
    if scelta == "mai":
        return False
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _stile(argomenti: argparse.Namespace) -> _output.Stile:
    larghezza = min(shutil.get_terminal_size((80, 24)).columns, LARGHEZZA_MASSIMA)
    return _output.Stile(colori=_a_colori(argomenti.colore), larghezza=larghezza)


def _registro(verboso: bool) -> None:
    """Attiva su stderr il logging della libreria: retry, attese, stati HTTP."""
    if not verboso:
        return
    gestore = logging.StreamHandler(sys.stderr)
    gestore.setFormatter(logging.Formatter(f"{PROGRAMMA}: %(message)s"))
    registro = logging.getLogger("normattiva")
    registro.setLevel(logging.DEBUG)
    registro.addHandler(gestore)


def _dimensione(byte: int) -> str:
    """La dimensione di un archivio, in kB o MB secondo la grandezza."""
    if byte < 1_048_576:
        return f"{byte / 1024:.0f} kB"
    return f"{byte / 1_048_576:.1f} MB"


def _cliente(argomenti: argparse.Namespace) -> Normattiva:
    """Il client usato dai comandi, con lo User-Agent della CLI."""
    return Normattiva(timeout=argomenti.timeout, user_agent=USER_AGENT)


# --- conversioni degli argomenti ---------------------------------------------


def _data(grezza: str) -> date:
    """Una data in forma `AAAA-MM-GG`, l'unica che il servizio accetta."""
    try:
        return date.fromisoformat(grezza)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{grezza!r} non è una data: serve la forma AAAA-MM-GG, per esempio 1990-08-07"
        ) from None


def _vigenza(grezza: str) -> Vigenza:
    """Una data, oppure la parola `originale` per la prima pubblicazione."""
    return "originale" if grezza == "originale" else _data(grezza)


def _positivo(grezzo: str) -> int:
    """Un intero maggiore di zero: pagine e tetti partono da 1."""
    numero = int(grezzo) if grezzo.lstrip("+-").isdigit() else 0
    if numero < 1:
        raise argparse.ArgumentTypeError(f"{grezzo!r} non è un numero maggiore di zero")
    return numero


def _classe(grezza: str) -> ClasseProvvedimento:
    """Una classe di provvedimento indicata per nome, senza distinzione di maiuscole."""
    try:
        return ClasseProvvedimento[grezza.upper()]
    except KeyError:
        ammesse = ", ".join(c.name.lower() for c in ClasseProvvedimento)
        raise argparse.ArgumentTypeError(f"{grezza!r} non è una classe: {ammesse}") from None


def _formato(grezzo: str) -> Format:
    """Un formato di esportazione, senza distinzione di maiuscole."""
    try:
        return Format(grezzo.upper())
    except ValueError:
        ammessi = ", ".join(f.value for f in Format)
        raise argparse.ArgumentTypeError(f"{grezzo!r} non è un format: {ammessi}") from None


_ORDINE_CLI = {"recente": Sort.NEWEST, "vecchio": Sort.OLDEST}
"""Come si chiedono i due ordinamenti dal terminale, che parla italiano."""


def _modalita(grezza: str) -> ExportMode:
    """Una modalità di esportazione, senza distinzione di maiuscole."""
    try:
        return ExportMode(grezza.lower())
    except ValueError:
        ammesse = ", ".join(m.value for m in ExportMode)
        raise argparse.ArgumentTypeError(f"{grezza!r} non è una modalità: {ammesse}") from None


def _intervallo(dal: date | None, al: date | None) -> Intervallo | None:
    return None if dal is None and al is None else (dal, al)


def _noti() -> dict[str, AttoNoto]:
    """Gli atti notissimi, indicizzati per il nome con cui la CLI li accetta.

    Il nome è quello della costante, in minuscolo e con i trattini:
    `CODICE_CIVILE` diventa `codice-civile`. La tabella deriva dal modulo
    `codici` invece di essere scritta a mano, così un atto aggiunto lì è
    subito disponibile anche qui.
    """
    return {
        nome.lower().replace("_", "-"): oggetto
        for nome in codici.__all__
        if isinstance(oggetto := getattr(codici, nome), codici.AttoNoto)
    }


def _risolvi_atto(testo: str, articolo: str | None) -> Urn:
    """L'URN dell'atto richiesto, da un URN o dal nome di un atto notissimo.

    Quando si passa per il nome, l'articolo viene composto tenendo conto
    dell'allegato che risponde per quel codice, che è la parte difficile da
    indovinare a mano.

    Raises:
        InvalidArgumentError: l'atto indicato non è un URN né un nome noto.
        InvalidUrnError: è un URN, ma malformato.
    """
    noti = _noti()
    grezzo = testo.strip()
    chiave = grezzo.lower().replace("_", "-").replace(" ", "-")
    if chiave in noti:
        noto = noti[chiave]
        return noto.articolo(articolo) if articolo else noto.urn
    if not chiave.startswith("urn:"):
        raise InvalidArgumentError(
            f"{testo!r} non è un URN e non è uno degli atti che questo comando "
            f"conosce per nome ({', '.join(sorted(noti))}): "
            f"vedere «{PROGRAMMA} codici»"
        )
    urn = Urn.parse(grezzo)
    return urn.con_articolo(articolo) if articolo else urn


def _coordinate(argomenti: argparse.Namespace) -> dict[str, Any]:
    """I criteri di ricerca per coordinate, nella forma che il client si aspetta."""
    return {
        "denominazione": argomenti.denominazione,
        "anno": argomenti.anno,
        "numero": argomenti.numero,
        "giorno": argomenti.giorno,
        "mese": argomenti.mese,
        "titolo": argomenti.titolo,
        "testo": argomenti.testo,
        "vigente_al": argomenti.vigente_al,
        "classe": argomenti.classe,
        "emanazione": _intervallo(argomenti.emanazione_dal, argomenti.emanazione_al),
        "pubblicazione": _intervallo(argomenti.pubblicazione_dal, argomenti.pubblicazione_al),
    }


def _faccette(argomenti: argparse.Namespace) -> dict[str, Any]:
    return {
        "sort": _ORDINE_CLI[argomenti.ordine],
        "tipo": argomenti.tipo,
        "emettitore": argomenti.emettitore,
    }


# --- comandi ------------------------------------------------------------------


def _esegui_testo(argomenti: argparse.Namespace) -> Uscita:
    if argomenti.gazzetta and argomenti.atto:
        raise _UsoSbagliato("o l'atto o --gazzetta, non tutti e due")
    if not argomenti.gazzetta and not argomenti.atto:
        raise _UsoSbagliato("serve un URN, il nome di un atto notissimo, oppure --gazzetta")
    if argomenti.gazzetta and argomenti.data is None:
        raise _UsoSbagliato("--gazzetta ha bisogno di --data, la data di pubblicazione")
    richiesto = None if argomenti.gazzetta else _risolvi_atto(argomenti.atto, argomenti.articolo)
    with _cliente(argomenti) as cliente:
        if richiesto is None:
            atto = cliente.dettaglio_da_gazzetta(
                argomenti.gazzetta, argomenti.data, se_troncato=argomenti.se_troncato
            )
        else:
            atto = cliente.dettaglio(
                richiesto, vigenza=argomenti.vigenza, se_troncato=argomenti.se_troncato
            )
    if argomenti.json:
        _scrivi(_output.dati_atto(atto, richiesto=richiesto))
        return Uscita.OK
    _stampa(_output.mostra_atto(_stile(argomenti), atto, richiesto=richiesto))
    if atto.possibile_troncamento:
        _avviso(
            f"il testo si ferma al comma {atto.ultimo_comma_numerato}, esatto su un multiplo "
            "di cento: potrebbe essere tagliato, e l'esportazione non taglia"
        )
    return Uscita.OK


def _esegui_cerca(argomenti: argparse.Namespace) -> Uscita:
    parole = " ".join(argomenti.parole)
    with _cliente(argomenti) as cliente:
        if argomenti.massimo is not None:
            trovati = list(
                cliente.ricerca_completa(
                    parole,
                    massimo=argomenti.massimo,
                    per_pagina=argomenti.per_pagina,
                    anno=argomenti.anno,
                    **_faccette(argomenti),
                )
            )
            return _rendi_trovati(argomenti, trovati)
        esito = cliente.ricerca(
            parole,
            pagina=argomenti.pagina,
            per_pagina=argomenti.per_pagina,
            anno=argomenti.anno,
            **_faccette(argomenti),
        )
    return _rendi_esito(argomenti, esito)


def _esegui_cerca_avanzata(argomenti: argparse.Namespace) -> Uscita:
    with _cliente(argomenti) as cliente:
        esito = cliente.ricerca_avanzata(
            pagina=argomenti.pagina,
            per_pagina=argomenti.per_pagina,
            **_coordinate(argomenti),
            **_faccette(argomenti),
        )
    return _rendi_esito(argomenti, esito)


def _esegui_cronologia(argomenti: argparse.Namespace) -> Uscita:
    urn = _risolvi_atto(argomenti.atto, argomenti.articolo)
    with _cliente(argomenti) as cliente:
        versioni = list(cliente.cronologia(urn, massimo=argomenti.massimo))
    if argomenti.json:
        _scrivi(
            {
                "urn": str(urn),
                "versioni": [_output.dati_versione(v, urn) for v in versioni],
                "fonte": ATTRIBUZIONE,
            }
        )
        return Uscita.OK
    stile = _stile(argomenti)
    _stampa(
        _output.blocchi(
            stile.forte(f"{_output.quanti(len(versioni), 'versione', 'versioni')} di {urn}"),
            _output.mostra_versioni(stile, versioni),
            stile.tenue(_output.fonte(stile, ATTRIBUZIONE)),
        )
    )
    return Uscita.OK


def _esegui_aggiornati(argomenti: argparse.Namespace) -> Uscita:
    with _cliente(argomenti) as cliente:
        flusso = cliente.atti_aggiornati(argomenti.dal, argomenti.al)
        trovati = list(islice(flusso, argomenti.massimo) if argomenti.massimo else flusso)
    return _rendi_trovati(argomenti, trovati)


def _rendi_esito(argomenti: argparse.Namespace, esito: EsitoRicerca) -> Uscita:
    """L'output comune alle due ricerche, che producono la stessa pagina di risultati."""
    if argomenti.json:
        _scrivi(_output.dati_esito(esito, ATTRIBUZIONE))
        return Uscita.OK
    stile = _stile(argomenti)
    da = (esito.pagina - 1) * argomenti.per_pagina + 1
    _stampa(
        _output.blocchi(
            _output.mostra_esito(stile, esito, da=da, faccette=argomenti.faccette),
            stile.tenue(_output.fonte(stile, ATTRIBUZIONE)),
        )
    )
    return Uscita.OK


def _rendi_trovati(argomenti: argparse.Namespace, trovati: Sequence[AttoTrovato]) -> Uscita:
    """L'output comune ai comandi che producono un elenco di atti senza paginazione."""
    if argomenti.json:
        _scrivi({"atti": [_output.dati_trovato(t) for t in trovati], "fonte": ATTRIBUZIONE})
        return Uscita.OK
    stile = _stile(argomenti)
    _stampa(
        _output.blocchi(
            stile.forte(_output.quanti(len(trovati), "atto", "atti")),
            _output.mostra_trovati(stile, trovati),
            stile.tenue(_output.fonte(stile, ATTRIBUZIONE)),
        )
    )
    return Uscita.OK


def _esegui_esporta(argomenti: argparse.Namespace) -> Uscita:
    coordinate = _coordinate(argomenti)
    if argomenti.token and any(valore is not None for valore in coordinate.values()):
        raise _UsoSbagliato(
            "--token riprende un'esportazione già avviata: i criteri sono già stati fissati"
        )
    with _cliente(argomenti) as cliente:
        if argomenti.token:
            esportazione = cliente.export_from_token(argomenti.token, format=argomenti.formato)
        else:
            esportazione = cliente.start_export(
                format=argomenti.formato,
                mode=argomenti.modalita,
                massimo_atti=None if argomenti.senza_conteggio else argomenti.massimo_atti,
                escludi_testo=argomenti.escludi_testo,
                escludi_titolo=argomenti.escludi_titolo,
                **coordinate,
            )
            _avviso(f"esportazione avviata, token {esportazione.token}")
        _avviso(f"in attesa dell'archivio, al più {argomenti.scadenza:.0f} secondi")
        esportazione.wait(timeout=argomenti.scadenza)
        percorso = esportazione.save(argomenti.archivio)
    dimensione = percorso.stat().st_size
    if argomenti.json:
        _scrivi(
            {
                "token": esportazione.token,
                "formato": str(esportazione.format),
                "archivio": str(percorso),
                "byte": dimensione,
                "fonte": ATTRIBUZIONE,
            }
        )
        return Uscita.OK
    stile = _stile(argomenti)
    _stampa(
        _output.scheda(
            stile,
            [
                ("Archivio", str(percorso)),
                ("Format", str(esportazione.format)),
                ("Dimensione", _dimensione(dimensione)),
                ("Token", esportazione.token),
            ],
        )
    )
    return Uscita.OK


def _esegui_collezioni(argomenti: argparse.Namespace) -> Uscita:
    with _cliente(argomenti) as cliente:
        voci = cliente.collections()
    if argomenti.json:
        _scrivi({"collezioni": [_output.dati_collezione(v) for v in voci]})
        return Uscita.OK
    _stampa(_output.mostra_collezioni(_stile(argomenti), voci))
    return Uscita.OK


def _esegui_scarica_collezione(argomenti: argparse.Namespace) -> Uscita:
    with _cliente(argomenti) as cliente:
        percorso = cliente.save_collection(
            argomenti.nome,
            argomenti.archivio,
            format=argomenti.formato,
            mode=argomenti.modalita,
        )
    dimensione = percorso.stat().st_size
    if argomenti.json:
        _scrivi({"archivio": str(percorso), "byte": dimensione, "fonte": ATTRIBUZIONE})
        return Uscita.OK
    stile = _stile(argomenti)
    _stampa(
        _output.scheda(
            stile,
            [("Archivio", str(percorso)), ("Dimensione", _dimensione(dimensione))],
        )
    )
    return Uscita.OK


def _esegui_dizionario(argomenti: argparse.Namespace) -> Uscita:
    with _cliente(argomenti) as cliente:
        voci = {
            "denominazioni": cliente.denominazioni,
            "classi": cliente.classi_provvedimento,
            "formati": cliente.export_formats,
        }[argomenti.quale]()
    if argomenti.json:
        _scrivi({argomenti.quale: [_output.dati_tipologica(v) for v in voci]})
        return Uscita.OK
    _stampa(_output.mostra_tipologiche(_stile(argomenti), voci))
    return Uscita.OK


def _esegui_urn(argomenti: argparse.Namespace) -> Uscita:
    urn = _risolvi_atto(argomenti.atto, argomenti.articolo)
    if argomenti.comma:
        urn = replace(urn, comma=argomenti.comma)
    if argomenti.vigenza:
        urn = urn.con_vigenza(argomenti.vigenza)
    if argomenti.json:
        _scrivi(_output.dati_urn(urn))
        return Uscita.OK
    _stampa(_output.mostra_urn(_stile(argomenti), urn))
    return Uscita.OK


def _esegui_codici(argomenti: argparse.Namespace) -> Uscita:
    noti = sorted(_noti().items())
    if argomenti.json:
        _scrivi(
            {
                "codici": [
                    {
                        "nome": nome,
                        "atto": noto.nome,
                        "urn": str(noto.base),
                        "allegato_articoli": noto.allegato_articoli,
                    }
                    for nome, noto in noti
                ]
            }
        )
        return Uscita.OK
    _stampa(_output.mostra_codici(_stile(argomenti), noti))
    return Uscita.OK


# --- il parser ----------------------------------------------------------------


def _genitori() -> tuple[argparse.ArgumentParser, argparse.ArgumentParser]:
    """Le opzioni condivise: come scrivere l'output, come parlare col servizio."""
    uscita = argparse.ArgumentParser(add_help=False)
    uscita.add_argument("--json", action="store_true", help="scrive JSON invece che testo")
    uscita.add_argument(
        "--colore",
        choices=("auto", "sempre", "mai"),
        default="auto",
        help="quando colorare l'output (predefinito: auto, cioè solo su un terminale)",
    )
    rete = argparse.ArgumentParser(add_help=False)
    rete.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        metavar="SECONDI",
        help="quanto attendere ogni singola risposta (predefinito: 30)",
    )
    rete.add_argument(
        "--verboso",
        action="store_true",
        help="scrive su stderr retry, attese e stati HTTP",
    )
    return uscita, rete


def _aggiungi_criteri(sotto: argparse.ArgumentParser) -> None:
    """I criteri per coordinate, uguali per la ricerca avanzata e per l'esportazione."""
    gruppo = sotto.add_argument_group("criteri")
    gruppo.add_argument("--denominazione", help="il tipo di atto, per esempio «LEGGE»")
    gruppo.add_argument("--anno", type=int, help="anno di emanazione")
    gruppo.add_argument("--numero", help="numero del provvedimento")
    gruppo.add_argument("--giorno", type=int, help="giorno di emanazione")
    gruppo.add_argument("--mese", type=int, help="mese di emanazione")
    gruppo.add_argument("--titolo", help="parole da cercare nel titolo")
    gruppo.add_argument("--testo", help="parole da cercare nel testo")
    gruppo.add_argument(
        "--vigente-al", type=_data, metavar="DATA", help="solo gli atti in vigore quel giorno"
    )
    gruppo.add_argument(
        "--classe",
        type=_classe,
        choices=list(ClasseProvvedimento),
        metavar="{senza_aggiornamenti,aggiornato,abrogato}",
        help="la classe redazionale dell'atto",
    )
    gruppo.add_argument(
        "--emanazione-dal", type=_data, metavar="DATA", help="emanati da questo giorno in poi"
    )
    gruppo.add_argument(
        "--emanazione-al", type=_data, metavar="DATA", help="emanati fino a questo giorno"
    )
    gruppo.add_argument(
        "--pubblicazione-dal",
        type=_data,
        metavar="DATA",
        help="pubblicati in Gazzetta da questo giorno in poi",
    )
    gruppo.add_argument(
        "--pubblicazione-al",
        type=_data,
        metavar="DATA",
        help="pubblicati in Gazzetta fino a questo giorno",
    )


def _aggiungi_pagina(sotto: argparse.ArgumentParser) -> None:
    """Le opzioni comuni ai comandi che producono una pagina di risultati."""
    sotto.add_argument("--pagina", type=_positivo, default=1, help="quale pagina (predefinito: 1)")
    sotto.add_argument(
        "--per-pagina", type=_positivo, default=20, help="quanti per pagina (predefinito: 20)"
    )
    sotto.add_argument(
        "--ordine",
        choices=list(_ORDINE_CLI),
        default="recente",
        help="dal più recente o dal più vecchio (predefinito: recente)",
    )
    sotto.add_argument("--tipo", help="codice della faccetta per tipo di atto")
    sotto.add_argument("--emettitore", help="codice della faccetta per amministrazione emanante")
    sotto.add_argument(
        "--faccette", action="store_true", help="mostra i valori con cui restringere la ricerca"
    )


def parser() -> argparse.ArgumentParser:
    """Costruisce il parser completo, con tutti i comandi già dentro."""
    uscita, rete = _genitori()
    principale = argparse.ArgumentParser(
        prog=PROGRAMMA,
        description=(
            "Interroga Normattiva, il portale della legge vigente, dalla riga di comando. "
            "Programma non ufficiale: i dati sono di IPZS in licenza CC BY 4.0, il testo "
            "non è autentico e l'unico ufficiale resta quello della Gazzetta Ufficiale a "
            "mezzo stampa."
        ),
        formatter_class=_Aiuto,
    )
    principale.add_argument(
        "--versione",
        "--version",
        action="version",
        version=f"{PROGRAMMA}-sdk {_versione_libreria}",
        help="stampa la versione della libreria e termina",
    )
    comandi = principale.add_subparsers(title="comandi", metavar="COMANDO", required=True)

    testo = comandi.add_parser(
        "testo",
        parents=[uscita, rete],
        help="legge il testo di un atto o di un suo articolo",
        description="Legge il testo di un atto, o di un suo articolo, a una data qualsiasi.",
        epilog=(
            "esempi:\n"
            "  normattiva testo codice-civile --articolo 2043\n"
            "  normattiva testo urn:nir:stato:legge:1990-08-07;241 --articolo 19 "
            "--vigenza 2000-01-01\n"
            "  normattiva testo --gazzetta 017U1234 --data 1917-05-20\n"
        ),
        formatter_class=_Aiuto,
    )
    testo.add_argument(
        "atto",
        nargs="?",
        help="un URN, oppure il nome di un atto notissimo come «codice-penale»",
    )
    testo.add_argument("--articolo", help="il numero dell'articolo, per esempio 416bis")
    testo.add_argument(
        "--vigenza",
        type=_vigenza,
        metavar="DATA",
        help="il giorno a cui leggere il testo, oppure «originale»",
    )
    testo.add_argument(
        "--gazzetta",
        metavar="CODICE",
        help="il codice redazionale, per gli atti che non hanno una forma URN verificata",
    )
    testo.add_argument(
        "--data", type=_data, help="la data di pubblicazione in Gazzetta, insieme a --gazzetta"
    )
    testo.add_argument(
        "--se-troncato",
        choices=("segnala", "solleva"),
        default="segnala",
        help="che fare se il testo sembra tagliato (predefinito: segnala)",
    )
    testo.set_defaults(esegui=_esegui_testo)

    cerca = comandi.add_parser(
        "cerca",
        parents=[uscita, rete],
        help="cerca nel testo pieno del corpus",
        description=(
            "Cerca fra le parole di tutti gli atti. Il servizio le combina in AND: non c'è "
            "modo di chiedere un OR. Senza --massimo costa una richiesta sola e mostra una "
            "pagina; con --massimo scorre le pagine finché quel numero di atti è raggiunto."
        ),
        epilog=(
            "esempi:\n"
            "  normattiva cerca procedimento amministrativo\n"
            "  normattiva cerca trasparenza --anno 1990 --faccette\n"
            "  normattiva cerca appalti --massimo 200 --json\n"
        ),
        formatter_class=_Aiuto,
    )
    cerca.add_argument("parole", nargs="+", help="le parole da cercare")
    cerca.add_argument("--anno", type=int, help="faccetta per anno di provvedimento")
    cerca.add_argument(
        "--massimo",
        type=_positivo,
        metavar="N",
        help="scorre le pagine fino a N atti, invece di mostrarne una sola",
    )
    _aggiungi_pagina(cerca)
    cerca.set_defaults(esegui=_esegui_cerca)

    avanzata = comandi.add_parser(
        "cerca-avanzata",
        parents=[uscita, rete],
        help="cerca per coordinate invece che per parole",
        description=(
            "Cerca per tipo, anno, numero e date. Senza nessun criterio il servizio "
            "risponde con l'intero corpus: è una richiesta ammessa."
        ),
        epilog=(
            "esempi:\n"
            "  normattiva cerca-avanzata --denominazione LEGGE --anno 1990 --numero 241\n"
            "  normattiva cerca-avanzata --titolo privacy --vigente-al 2020-01-01\n"
        ),
        formatter_class=_Aiuto,
    )
    _aggiungi_criteri(avanzata)
    _aggiungi_pagina(avanzata)
    avanzata.set_defaults(esegui=_esegui_cerca_avanzata)

    cronologia = comandi.add_parser(
        "cronologia",
        parents=[uscita, rete],
        help="percorre tutte le versioni di un articolo",
        description=(
            "Elenca le versioni di un articolo, dall'originale a quella in vigore, con la "
            "finestra di vigenza di ciascuna. Costa una richiesta per versione."
        ),
        epilog=(
            "esempi:\n"
            "  normattiva cronologia urn:nir:stato:legge:1990-08-07;241 --articolo 19\n"
            "  normattiva cronologia codice-civile --articolo 2043\n"
        ),
        formatter_class=_Aiuto,
    )
    cronologia.add_argument("atto", help="un URN, oppure il nome di un atto notissimo")
    cronologia.add_argument("--articolo", help="il numero dell'articolo")
    cronologia.add_argument(
        "--massimo", type=_positivo, metavar="N", help="si ferma dopo N versioni"
    )
    cronologia.set_defaults(esegui=_esegui_cronologia)

    aggiornati = comandi.add_parser(
        "aggiornati",
        parents=[uscita, rete],
        help="elenca gli atti modificati fra due date",
        description=(
            "Elenca gli atti toccati da una modifica nella finestra indicata. Include solo "
            "le modifiche: un atto pubblicato nella finestra ma mai modificato dopo non "
            "compare."
        ),
        epilog="esempi:\n  normattiva aggiornati --dal 2026-01-01 --al 2026-03-31\n",
        formatter_class=_Aiuto,
    )
    aggiornati.add_argument(
        "--dal", type=_data, required=True, metavar="DATA", help="primo giorno, compreso"
    )
    aggiornati.add_argument(
        "--al", type=_data, required=True, metavar="DATA", help="ultimo giorno, compreso"
    )
    aggiornati.add_argument("--massimo", type=_positivo, metavar="N", help="si ferma dopo N atti")
    aggiornati.set_defaults(esegui=_esegui_aggiornati)

    esporta = comandi.add_parser(
        "esporta",
        parents=[uscita, rete],
        help="scarica l'archivio degli atti che i criteri trovano",
        description=(
            "Chiede al servizio un archivio con gli atti che i criteri trovano, attende che "
            "sia pronto e lo scrive su disco. Un'esportazione costa minuti di lavoro al "
            "servizio, quindi gli atti vengono contati prima: oltre --massimo-atti "
            "l'esportazione non parte."
        ),
        epilog=(
            "esempi:\n"
            "  normattiva esporta --denominazione LEGGE --anno 1990 --numero 241 "
            "--archivio 241.zip\n"
            "  normattiva esporta --token 3f2a... --archivio ripreso.zip\n"
        ),
        formatter_class=_Aiuto,
    )
    _aggiungi_criteri(esporta)
    esporta.add_argument(
        "--archivio", required=True, metavar="FILE", help="dove scrivere l'archivio"
    )
    esporta.add_argument(
        "--formato",
        type=_formato,
        choices=list(Format),
        default=Format.JSON,
        help="in che formato produrlo (predefinito: JSON)",
    )
    esporta.add_argument(
        "--modalita",
        type=_modalita,
        choices=list(ExportMode),
        default=ExportMode.MULTIVIGENTE,
        help="quante versioni includere (predefinito: multivigente)",
    )
    tetto = esporta.add_mutually_exclusive_group()
    tetto.add_argument(
        "--massimo-atti",
        type=_positivo,
        default=100,
        metavar="N",
        help="il tetto oltre il quale non parte (predefinito: 100)",
    )
    tetto.add_argument(
        "--senza-conteggio",
        action="store_true",
        help="parte senza contare prima quanti atti verrebbero presi",
    )
    esporta.add_argument(
        "--escludi-testo", metavar="PAROLA", help="toglie gli atti che la contengono"
    )
    esporta.add_argument(
        "--escludi-titolo", metavar="PAROLA", help="toglie gli atti il cui titolo la contiene"
    )
    esporta.add_argument(
        "--token", help="riprende un'esportazione già avviata invece di chiederne una nuova"
    )
    esporta.add_argument(
        "--scadenza",
        type=float,
        default=TIMEOUT,
        metavar="SECONDI",
        help=f"quanto attendere l'archivio (predefinito: {TIMEOUT:.0f})",
    )
    esporta.set_defaults(esegui=_esegui_esporta)

    collezioni = comandi.add_parser(
        "collezioni",
        parents=[uscita, rete],
        help="elenca gli archivi già confezionati dal servizio",
        description="Elenca gli archivi che il servizio tiene già pronti per lo scaricamento.",
        formatter_class=_Aiuto,
    )
    collezioni.set_defaults(esegui=_esegui_collezioni)

    scarica = comandi.add_parser(
        "scarica-collezione",
        parents=[uscita, rete],
        help="scarica uno degli archivi già confezionati",
        description="Scarica su disco un archivio già pronto, senza attendere un'esportazione.",
        epilog=("esempi:\n  normattiva scarica-collezione Codici --archivio codici.zip\n"),
        formatter_class=_Aiuto,
    )
    scarica.add_argument("nome", help="il nome della collezione, come lo elenca «collezioni»")
    scarica.add_argument(
        "--archivio", required=True, metavar="FILE", help="dove scrivere l'archivio"
    )
    scarica.add_argument(
        "--formato",
        type=_formato,
        choices=list(Format),
        default=Format.JSON,
        help="in che formato scaricarlo (predefinito: JSON)",
    )
    scarica.add_argument(
        "--modalita",
        type=_modalita,
        choices=list(ExportMode),
        default=ExportMode.VIGENTE,
        help="quante versioni includere (predefinito: vigente)",
    )
    scarica.set_defaults(esegui=_esegui_scarica_collezione)

    dizionario = comandi.add_parser(
        "dizionario",
        parents=[uscita, rete],
        help="elenca i codici che il servizio accetta",
        description=(
            "Mostra uno dei dizionari del servizio: sono i valori che «--denominazione», "
            "«--classe» e «--formato» accettano."
        ),
        formatter_class=_Aiuto,
    )
    dizionario.add_argument(
        "quale",
        choices=("denominazioni", "classi", "formati"),
        help="quale dizionario mostrare",
    )
    dizionario.set_defaults(esegui=_esegui_dizionario)

    identificatore = comandi.add_parser(
        "urn",
        parents=[uscita],
        help="smonta o compone un identificatore, senza toccare la rete",
        description=(
            "Convalida un URN e ne mostra le parti, oppure ne compone uno a partire dal nome "
            "di un atto notissimo. Non interroga il servizio: un URN malformato viene "
            "segnalato subito, senza toccare la rete."
        ),
        epilog=(
            "esempi:\n"
            "  normattiva urn urn:nir:stato:legge:1990-08-07;241~art19\n"
            "  normattiva urn codice-penale --articolo 416bis --vigenza 2010-01-01\n"
        ),
        formatter_class=_Aiuto,
    )
    identificatore.add_argument("atto", help="un URN, oppure il nome di un atto notissimo")
    identificatore.add_argument("--articolo", help="il numero dell'articolo da attaccare")
    identificatore.add_argument("--comma", help="il numero del comma da attaccare")
    identificatore.add_argument(
        "--vigenza", type=_vigenza, metavar="DATA", help="la versione da attaccare"
    )
    identificatore.set_defaults(esegui=_esegui_urn)

    noti = comandi.add_parser(
        "codici",
        parents=[uscita],
        help="elenca gli atti che si possono chiamare per nome",
        description=(
            "Elenca gli atti notissimi con l'URN a cui rispondono. Sono i nomi che «testo», "
            "«cronologia» e «urn» accettano al posto di un URN."
        ),
        formatter_class=_Aiuto,
    )
    noti.set_defaults(esegui=_esegui_codici)

    return principale


# --- l'ingresso ---------------------------------------------------------------


def _spiega(errore: NormattivaError) -> None:
    """Scrive l'errore su stderr, insieme ai dettagli utili che l'eccezione trasporta."""
    _avviso(str(errore))
    if isinstance(errore, AmbiguityError):
        for posizione, candidato in enumerate(errore.candidati, start=1):
            coordinate = candidato.gazzetta
            _avviso(
                f"  {posizione}. {coordinate} "
                f"(codice redazionale {coordinate.codice_redazionale or 'ignoto'})"
            )
        _avviso(f"scegliere con «{PROGRAMMA} testo --gazzetta CODICE --data DATA»")


def _famiglia(errore: NormattivaError) -> Uscita:
    for tipo, uscita in _FAMIGLIE:
        if isinstance(errore, tipo):
            return uscita
    return Uscita.RICHIESTA


def _zittisci_uscita() -> None:
    """Reindirizza stdout su /dev/null, così l'interprete non riprova a svuotarlo.

    Senza questo, un comando in una pipe il cui lettore smette di leggere
    (`| head`) stamperebbe un errore sopra il prompt senza che l'utente abbia
    sbagliato niente.
    """
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, sys.stdout.fileno())


def main(argv: Sequence[str] | None = None) -> int:
    """Esegue un comando e restituisce il codice di uscita del programma.

    Args:
        argv: gli argomenti senza il nome del programma. Con `None` vengono
            letti da `sys.argv`.

    Returns:
        Uno dei valori di `Uscita`.
    """
    argomenti = parser().parse_args(argv)
    _registro(getattr(argomenti, "verboso", False))
    try:
        return argomenti.esegui(argomenti)
    except _UsoSbagliato as errore:
        _avviso(str(errore))
        return Uscita.USO
    except NormattivaError as errore:
        _spiega(errore)
        return _famiglia(errore)
    except KeyboardInterrupt:
        _avviso("interrotto")
        return Uscita.INTERROTTO
    except BrokenPipeError:
        _zittisci_uscita()
        return Uscita.LETTURA_INTERROTTA
    except OSError as errore:
        # I comandi che scrivono un archivio possono trovare un percorso che non
        # c'è o un disco pieno. È l'unico modo di fallire che non riguarda né la
        # richiesta né il servizio, e una traccia di stack non lo spiegherebbe.
        _avviso(str(errore))
        return Uscita.ERRORE


def _da_terminale() -> NoReturn:
    sys.exit(main())


if __name__ == "__main__":
    _da_terminale()
