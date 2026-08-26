"""Export asincrona: atti interi, con tutta la loro storia.

Un'esportazione impiega circa un minuto, quindi non è un metodo bloccante che
restituisce un atto: è un oggetto con uno stato, che si può interrogare,
mettere da parte e riprendere dal suo token anche dopo che il processo che
l'attendeva è terminato.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from normattiva import _wire
from normattiva._http import Risposta, Trasporto, TrasportoAsync
from normattiva.errori import (
    ExportFailedError,
    InvalidArgumentError,
    OverloadedError,
)
from normattiva.modelli import ATTRIBUZIONE, AttoStorico, Format

ATTESA_FRA_CONTROLLI = 4.0
TIMEOUT = 600.0
POSIZIONE = "x-ipzs-location"

logger = logging.getLogger("normattiva")


class ExportStatus(IntEnum):
    """Stato di avanzamento di un'esportazione."""

    TO_CONFIRM = 0
    WAITING = 1
    PROCESSING = 2
    COMPLETED = 3
    FAILED = 4
    OVERLOADED = 5
    CONFIRMED_WITH_DELAY = 6

    @property
    def done(self) -> bool:
        """Indica se lo stato è terminale: interrogare di nuovo il servizio non lo cambierà."""
        return self in (
            ExportStatus.COMPLETED,
            ExportStatus.FAILED,
            ExportStatus.OVERLOADED,
        )


@dataclass(frozen=True, slots=True)
class Corpus:
    """Gli atti contenuti in un archivio esportato, insieme all'archivio stesso."""

    atti: tuple[AttoStorico, ...]
    archive: bytes = b""

    @classmethod
    def from_zip(cls, path: str | Path) -> Corpus:
        """Riapre un'esportazione salvata in precedenza, senza accedere alla rete.

        Args:
            path: il file ZIP scritto in precedenza da `save`.

        Returns:
            Gli atti che l'archivio contiene, e l'archivio stesso.

        Raises:
            UnexpectedResponseError: l'archivio non è leggibile, o non segue la
                convenzione di nomi da cui si legge la data di vigenza.
        """
        dati = Path(path).read_bytes()
        return cls(atti=_wire.leggi_corpus(dati), archive=dati)

    @classmethod
    def from_data(cls, dati: bytes) -> Corpus:
        """Legge un archivio già presente in memoria."""
        return cls(atti=_wire.leggi_corpus(dati), archive=dati)

    def save(self, path: str | Path) -> Path:
        """Scrive l'archivio su disco, per riaprirlo senza una nuova esportazione."""
        destinazione = Path(path)
        destinazione.write_bytes(self.archive)
        return destinazione

    def __len__(self) -> int:
        return len(self.atti)

    def __iter__(self) -> Iterator[AttoStorico]:
        return iter(self.atti)

    @property
    def attribuzione(self) -> str:
        """La riga di attribuzione richiesta dalla licenza."""
        return ATTRIBUZIONE


def _numero(grezzo: object) -> int | None:
    """Converte lo stato in intero, anche quando il servizio lo serializza come stringa."""
    if isinstance(grezzo, bool) or grezzo is None:
        return None
    try:
        return int(str(grezzo).strip())
    except ValueError:
        return None


def _descrizione(grezza: object) -> str | None:
    """Il messaggio del servizio, se presente."""
    return str(grezza).strip() or None if grezza is not None else None


def _verifica_leggibile(format: Format, alternativa: str) -> None:
    """Rifiuta i formati che la libreria non sa interpretare.

    Solo il JSON viene convertito in modelli. Gli altri formati si scaricano
    come file, ed è meglio segnalarlo subito che restituire un archivio non
    interpretabile.
    """
    if format is not Format.JSON:
        raise InvalidArgumentError(
            f"il format {format} non viene letto in modelli: usare {alternativa} "
            "per scaricarlo come file"
        )


@dataclass(frozen=True, slots=True)
class Progress:
    """L'avanzamento che il servizio dichiara per un'esportazione.

    La percentuale da sola non dice se il lavoro sta procedendo: `processed` e
    `total` sì, e sono l'unico modo per capire se un'esportazione lunga è
    ferma o solo lenta. Il servizio non li invia sempre.
    """

    percent: float | None = None
    processed: int | None = None
    total: int | None = None

    def __str__(self) -> str:
        if self.total:
            return f"{self.processed or 0}/{self.total} atti"
        return f"{self.percent:.0f}%" if self.percent is not None else "sconosciuto"


def _avanzamento_da(corpo: dict[str, object]) -> Progress:
    percentuale = corpo.get("percentuale")
    return Progress(
        percent=float(percentuale) if isinstance(percentuale, int | float) else None,
        processed=_numero(corpo.get("attiElaborati")),
        total=_numero(corpo.get("totAtti")),
    )


def _stato_da(
    risposta: Risposta, posizione: str | None
) -> tuple[ExportStatus, str | None, Progress]:
    """Legge una risposta di stato e solleva per i due stati che concludono l'attesa con errore.

    Una risposta che non dichiara lo stato non dichiara nemmeno di essere
    conclusa: viene trattata come lavorazione in corso. Dedurne il successo
    porterebbe a scaricare un archivio che non esiste.
    """
    if risposta.status == 303:
        posizione = risposta.intestazioni.get(POSIZIONE) or posizione
    corpo = risposta.json() if risposta.contenuto else {}
    if not isinstance(corpo, dict):
        corpo = {}
    grezzo = _numero(corpo.get("stato"))
    if grezzo is not None and grezzo in {s.value for s in ExportStatus}:
        stato = ExportStatus(grezzo)
    elif risposta.status == 303:
        stato = ExportStatus.COMPLETED
    else:
        stato = ExportStatus.PROCESSING
    if stato is ExportStatus.FAILED:
        raise ExportFailedError(_descrizione(corpo.get("descrizioneErrore")))
    if stato is ExportStatus.OVERLOADED:
        raise OverloadedError(_descrizione(corpo.get("descrizioneStato")))
    return stato, posizione, _avanzamento_da(corpo)


class Export:
    """Un'esportazione, dalla richiesta all'archivio prodotto."""

    def __init__(
        self,
        token: str,
        trasporto: Trasporto,
        *,
        format: Format = Format.JSON,
        stato: ExportStatus = ExportStatus.TO_CONFIRM,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._token = token
        self._formato = format
        self._trasporto = trasporto
        self._stato = stato
        self._avanzamento = Progress()
        self._posizione: str | None = None
        self._sleep = sleep
        self._clock = clock

    @classmethod
    def from_token(
        cls, token: str, trasporto: Trasporto, *, format: Format = Format.JSON
    ) -> Export:
        """Riprende un'esportazione già avviata, a partire dal suo token."""
        esportazione = cls(token, trasporto, format=format, stato=ExportStatus.WAITING)
        esportazione.refresh()
        return esportazione

    @property
    def token(self) -> str:
        """Il token con cui riprendere questa esportazione da un altro processo."""
        return self._token

    @property
    def format(self) -> Format:
        """Il format in cui è stato richiesto l'archivio."""
        return self._formato

    @property
    def status(self) -> ExportStatus:
        """L'ultimo stato dichiarato dal servizio."""
        return self._stato

    @property
    def progress(self) -> Progress:
        """L'ultimo avanzamento dichiarato dal servizio, quando lo dichiara."""
        return self._avanzamento

    def refresh(self) -> ExportStatus:
        """Interroga il servizio una volta sullo stato dell'esportazione."""
        risposta = self._trasporto.get(
            f"ricerca-asincrona/check-status/{self._token}", attesi=(200, 202, 303)
        )
        stato, posizione, avanzamento = _stato_da(risposta, self._posizione)
        self._stato, self._posizione, self._avanzamento = stato, posizione, avanzamento
        return stato

    def wait(self, *, timeout: float = TIMEOUT) -> ExportStatus:
        """Interroga il servizio finché l'archivio è pronto, o finché la scadenza è superata.

        Se il servizio dichiara un possibile ritardo, la scadenza viene
        prorogata una sola volta: prorogarla a ogni dichiarazione toglierebbe
        ogni limite all'attesa.

        Args:
            timeout: quanti secondi attendere prima di rinunciare.

        Returns:
            Lo stato in cui l'esportazione si è conclusa.

        Raises:
            ExportFailedError: il servizio l'ha dichiarata fallita,
                oppure l'attesa ha superato `timeout`.
            OverloadedError: il servizio non è in grado di completarla adesso.
        """
        limite = self._clock() + timeout
        prorogato = False
        while True:
            stato = self.refresh()
            if stato.done:
                return stato
            if stato is ExportStatus.CONFIRMED_WITH_DELAY and not prorogato:
                limite = self._clock() + timeout
                prorogato = True
            if self._clock() >= limite:
                raise ExportFailedError(
                    f"l'esportazione non si è conclusa entro {timeout:.0f} secondi"
                )
            logger.debug(
                "esportazione %s: stato %s, %s", self._token, stato.name, self._avanzamento
            )
            self._sleep(ATTESA_FRA_CONTROLLI)

    def _scarica(self) -> bytes:
        percorso = self._posizione or f"collections/download/collection-asincrona/{self._token}"
        return self._trasporto.get(percorso, segui_redirect=True).contenuto

    def download(self) -> Corpus:
        """Scarica l'archivio e legge gli atti che contiene.

        Solo il format JSON viene convertito in modelli; gli altri formati si
        scaricano come file con `save`, perché la libreria non li interpreta.

        Returns:
            Gli atti che l'archivio contiene, e l'archivio stesso.

        Raises:
            InvalidArgumentError: il format non è JSON; usare `save`.
            UnexpectedResponseError: l'archivio non è leggibile, o i nomi dei file
                non dichiarano più la vigenza.
        """
        _verifica_leggibile(self._formato, "save()")
        return Corpus.from_data(self._scarica())

    def save(self, path: str | Path) -> Path:
        """Scarica l'archivio e lo scrive su disco, in qualunque format."""
        destinazione = Path(path)
        destinazione.write_bytes(self._scarica())
        return destinazione


class AsyncExport:
    """La variante asincrona di `Export`."""

    def __init__(
        self,
        token: str,
        trasporto: TrasportoAsync,
        *,
        format: Format = Format.JSON,
        stato: ExportStatus = ExportStatus.TO_CONFIRM,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._token = token
        self._formato = format
        self._trasporto = trasporto
        self._stato = stato
        self._avanzamento = Progress()
        self._posizione: str | None = None
        self._sleep = sleep
        self._clock = clock

    @classmethod
    async def from_token(
        cls, token: str, trasporto: TrasportoAsync, *, format: Format = Format.JSON
    ) -> AsyncExport:
        """Riprende un'esportazione già avviata, a partire dal suo token."""
        esportazione = cls(token, trasporto, format=format, stato=ExportStatus.WAITING)
        await esportazione.refresh()
        return esportazione

    @property
    def token(self) -> str:
        """Il token con cui riprendere questa esportazione da un altro processo."""
        return self._token

    @property
    def format(self) -> Format:
        """Il format in cui è stato richiesto l'archivio."""
        return self._formato

    @property
    def status(self) -> ExportStatus:
        """L'ultimo stato dichiarato dal servizio."""
        return self._stato

    @property
    def progress(self) -> Progress:
        """L'ultimo avanzamento dichiarato dal servizio, quando lo dichiara."""
        return self._avanzamento

    async def refresh(self) -> ExportStatus:
        """Interroga il servizio una volta sullo stato dell'esportazione."""
        risposta = await self._trasporto.get(
            f"ricerca-asincrona/check-status/{self._token}", attesi=(200, 202, 303)
        )
        stato, posizione, avanzamento = _stato_da(risposta, self._posizione)
        self._stato, self._posizione, self._avanzamento = stato, posizione, avanzamento
        return stato

    async def wait(self, *, timeout: float = TIMEOUT) -> ExportStatus:
        """Interroga il servizio finché l'archivio è pronto, o finché la scadenza è superata.

        Se il servizio dichiara un possibile ritardo, la scadenza viene
        prorogata una sola volta: prorogarla a ogni dichiarazione toglierebbe
        ogni limite all'attesa.

        Args:
            timeout: quanti secondi attendere prima di rinunciare.

        Returns:
            Lo stato in cui l'esportazione si è conclusa.

        Raises:
            ExportFailedError: il servizio l'ha dichiarata fallita,
                oppure l'attesa ha superato `timeout`.
            OverloadedError: il servizio non è in grado di completarla adesso.
        """
        limite = self._clock() + timeout
        prorogato = False
        while True:
            stato = await self.refresh()
            if stato.done:
                return stato
            if stato is ExportStatus.CONFIRMED_WITH_DELAY and not prorogato:
                limite = self._clock() + timeout
                prorogato = True
            if self._clock() >= limite:
                raise ExportFailedError(
                    f"l'esportazione non si è conclusa entro {timeout:.0f} secondi"
                )
            logger.debug(
                "esportazione %s: stato %s, %s", self._token, stato.name, self._avanzamento
            )
            await self._sleep(ATTESA_FRA_CONTROLLI)

    async def _scarica(self) -> bytes:
        percorso = self._posizione or f"collections/download/collection-asincrona/{self._token}"
        risposta = await self._trasporto.get(percorso, segui_redirect=True)
        return risposta.contenuto

    async def download(self) -> Corpus:
        """Scarica l'archivio e legge gli atti che contiene.

        Solo il format JSON viene convertito in modelli; gli altri formati si
        scaricano come file con `save`, perché la libreria non li interpreta.

        Returns:
            Gli atti che l'archivio contiene, e l'archivio stesso.

        Raises:
            InvalidArgumentError: il format non è JSON; usare `save`.
            UnexpectedResponseError: l'archivio non è leggibile, o i nomi dei file
                non dichiarano più la vigenza.
        """
        _verifica_leggibile(self._formato, "save()")
        return Corpus.from_data(await self._scarica())

    async def save(self, path: str | Path) -> Path:
        """Scarica l'archivio e lo scrive su disco, in qualunque format."""
        destinazione = Path(path)
        destinazione.write_bytes(await self._scarica())
        return destinazione


__all__ = [
    "AsyncExport",
    "Corpus",
    "Export",
    "ExportStatus",
    "Progress",
]
