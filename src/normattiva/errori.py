"""Gerarchia delle eccezioni della libreria.

Tutte derivano da `NormattivaError`. Quelle causate da una richiesta errata derivano
anche da `ValueError`, così chi convalida input dell'utente può intercettarle tutte
insieme senza sapere quale strato le ha sollevate.
"""

from __future__ import annotations

from datetime import date
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from normattiva.modelli import DettaglioAtto, FinestraVigenza


class RuleCode(IntEnum):
    """Codici applicativi con cui il servizio segnala un errore nella richiesta.

    Questi codici descrivono la richiesta, non lo stato del servizio: la stessa
    richiesta riceverà sempre lo stesso codice, quindi non viene mai ritentata.
    Un codice fuori da questo elenco non dà la stessa garanzia: può indicare anche
    un guasto transitorio, e in quel caso il retry segue lo stato HTTP come per
    ogni altra risposta.
    """

    ERRORE_GENERICO = 1000
    FORMATO_NON_VALIDO = 1003
    INPUT_NON_VALIDO = 1005
    FORMATO_RICHIESTA_NON_VALIDO = 1006
    COLLEZIONE_INESISTENTE = 1200
    TOKEN_INESISTENTE = 1204
    INTERVALLO_OLTRE_12_MESI = 1501
    TROPPI_ATTI = 1502
    DATE_INVERTITE = 1503


TRANSIENT_CODES = frozenset({RuleCode.ERRORE_GENERICO})
"""Codici che indicano un guasto del servizio, non un errore nella richiesta.

Il 1000 arriva con un `500` e il messaggio «riprovare più tardi»: il servizio lo
restituisce anche per un URN perfettamente valido quando è in avaria. Trattarlo
come una regola violata spingerebbe chi lo riceve a correggere una richiesta già
corretta.
"""


class NormattivaError(Exception):
    """Classe base di tutti gli errori sollevati da questa libreria."""


class InvalidArgumentError(NormattivaError, ValueError):
    """Un argomento passato alla libreria non è valido: non serve interrogare il servizio."""


class InvalidUrnError(NormattivaError, ValueError):
    """L'URN non rispetta la grammatica NIR che Normattiva accetta."""

    def __init__(self, testo: object, motivo: str | None = None) -> None:
        self.testo = testo
        self.motivo = motivo
        messaggio = f"URN non valido: {testo!r}"
        if motivo:
            messaggio = f"{messaggio} ({motivo})"
        super().__init__(messaggio)


class ConnectionError(NormattivaError):
    """Impossibile raggiungere il servizio, oppure la connessione si è interrotta."""


class UnexpectedResponseError(NormattivaError):
    """La risposta non è nel formato che questa libreria sa interpretare."""


class RequestBlockedError(NormattivaError):
    """Lo strato di protezione davanti all'API ha respinto la richiesta per la sua forma."""


class RuleViolationError(NormattivaError, ValueError):
    """La richiesta viola una regola documentata del servizio.

    Descrive sempre la richiesta, mai un problema del servizio: se il codice non
    è fra quelli documentati, o arriva con un `5xx`, la libreria solleva
    un'eccezione diversa.
    """

    def __init__(self, codice: int, messaggio: str | None = None) -> None:
        self.codice = codice
        try:
            self.regola: RuleCode | None = RuleCode(codice)
        except ValueError:
            self.regola = None
        etichetta = (
            self.regola.name.lower().replace("_", " ") if self.regola else "regola sconosciuta"
        )
        super().__init__(messaggio or f"[{codice}] {etichetta}")


class NotFoundError(NormattivaError):
    """Nessun atto corrisponde alle coordinate richieste."""


class AmbiguityError(NormattivaError):
    """L'URN corrisponde a più di un atto pubblicato.

    I candidati sono inclusi nella stessa risposta in cui è emersa l'ambiguità,
    quindi leggerli non costa una richiesta in più. Non portano un
    identificatore: si distinguono per le coordinate di Gazzetta, cioè data,
    numero e codice redazionale.
    """

    def __init__(self, candidati: tuple[DettaglioAtto, ...]) -> None:
        self.candidati = candidati
        super().__init__(
            f"l'URN corrisponde a {len(candidati)} atti distinti: scegliere quale usare"
        )


class NotYetInForceError(NormattivaError):
    """L'articolo non esisteva ancora alla data richiesta."""

    def __init__(self, vigente_dal: date | None = None) -> None:
        self.vigente_dal = vigente_dal
        quando = f" (in vigore dal {vigente_dal.isoformat()})" if vigente_dal else ""
        super().__init__(f"l'articolo non era ancora in vigore alla data richiesta{quando}")


class ValidityMismatchError(NormattivaError):
    """Il servizio ha risposto con una versione che non copre la data richiesta."""

    def __init__(self, richiesta: date, finestra: FinestraVigenza) -> None:
        self.richiesta = richiesta
        self.finestra = finestra
        super().__init__(
            f"richiesta la vigenza al {richiesta.isoformat()} ma la risposta copre {finestra}"
        )


class VersionNotFoundError(NotFoundError):
    """Nessuna versione di questo atto copre la data richiesta."""

    def __init__(self, giorno: date) -> None:
        self.giorno = giorno
        super().__init__(f"nessuna versione copre il {giorno.isoformat()}")


class TruncationError(NormattivaError):
    """Il percorso interattivo ha restituito un articolo probabilmente troncato.

    `ultimo_comma` è l'etichetta dell'ultimo comma ricevuto, non il numero di
    commi arrivati: il sospetto di troncamento nasce dall'etichetta, che cade
    esattamente su un multiplo di cento.
    """

    def __init__(self, ultimo_comma: int) -> None:
        self.ultimo_comma = ultimo_comma
        super().__init__(
            f"l'articolo si ferma al comma {ultimo_comma} e potrebbe essere troncato: "
            "usare l'esportazione per il testo integrale"
        )


class TooManyResultsError(NormattivaError):
    """L'operazione supererebbe il limite di risultati consentito dal chiamante."""

    def __init__(self, totale: int | None, massimo: int) -> None:
        self.totale = totale
        self.massimo = massimo
        quanti = f"{totale} risultati superano" if totale is not None else "i risultati superano"
        super().__init__(
            f"{quanti} il massimo di {massimo}: "
            "restringere la richiesta oppure alzare il limite esplicitamente"
        )


class ExportFailedError(NormattivaError):
    """Il servizio ha dichiarato fallita l'esportazione."""

    def __init__(self, descrizione: str | None = None) -> None:
        self.descrizione = descrizione
        super().__init__(descrizione or "esportazione fallita")


class OverloadedError(NormattivaError):
    """Il servizio è sovraccarico e ha rifiutato temporaneamente la richiesta.

    `descrizione` contiene il messaggio del servizio, se presente; è testo
    informativo, non un URL né un'indicazione operativa.
    """

    def __init__(self, descrizione: str | None = None) -> None:
        self.descrizione = descrizione
        messaggio = "il servizio è sovraccarico"
        if descrizione:
            messaggio = f"{messaggio}: {descrizione}"
        super().__init__(messaggio)


__all__ = [
    "AmbiguityError",
    "ConnectionError",
    "ExportFailedError",
    "InvalidArgumentError",
    "InvalidUrnError",
    "NormattivaError",
    "NotFoundError",
    "NotYetInForceError",
    "OverloadedError",
    "RequestBlockedError",
    "RuleCode",
    "RuleViolationError",
    "TooManyResultsError",
    "TruncationError",
    "UnexpectedResponseError",
    "ValidityMismatchError",
    "VersionNotFoundError",
]
