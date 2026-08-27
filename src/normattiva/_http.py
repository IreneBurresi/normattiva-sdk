"""Lo strato HTTP verso il servizio: retry, rate limit e gestione dei guasti.

L'API non è sempre deterministica: la stessa lettura può rispondere 200 una
volta e 400 quella successiva. Ogni chiamata di questa libreria è una lettura,
e ripeterla è sicuro, quindi un 400 viene ritentato qui. Un 409 no: è lo strato
di protezione che rifiuta la forma della richiesta, e la rifiuterebbe anche al
tentativo successivo.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import threading
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any

import httpx

from normattiva import _wire
from normattiva.errori import ConnectionError, UnexpectedResponseError

PRODUZIONE = "https://api.normattiva.it/t/normattiva.api/bff-opendata/v1/api/v1"
USER_AGENT = "normattiva-sdk (+https://github.com/ireneburresi/normattiva-sdk)"
RITENTABILI = frozenset({400, 500, 502, 503, 504})

logger = logging.getLogger("normattiva")


@dataclass(frozen=True, slots=True)
class PoliticaRitentativi:
    """La politica dei retry: quali stati ritentare e quanto attendere fra i tentativi."""

    base: float = 0.5
    jitter: float = 0.3
    tetto: float = 8.0

    def ritentabile(self, stato: int) -> bool:
        """True se uno stato fallito va ritentato."""
        return stato in RITENTABILI

    def attesa(self, tentativo: int) -> float:
        """Il backoff prima del tentativo numero `tentativo`, contando da zero."""
        return min(self.base * 2**tentativo, self.tetto) + random.uniform(0, self.jitter)


class LimitatoreAsync:
    """Applica il rate limit distanziando le richieste, senza bloccare il ciclo di eventi."""

    def __init__(
        self,
        al_secondo: float,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._intervallo = 1 / al_secondo if al_secondo > 0 else 0.0
        self._sleep = sleep
        self._clock = clock
        self._ultima: float | None = None
        self._serratura = asyncio.Lock()

    async def attendi_turno(self) -> None:
        """Attende che sia passato abbastanza tempo dalla richiesta precedente."""
        if not self._intervallo:
            return
        async with self._serratura:
            if self._ultima is not None:
                mancante = self._ultima + self._intervallo - self._clock()
                if mancante > 0:
                    await self._sleep(mancante)
            self._ultima = self._clock()


class Limitatore:
    """Applica il rate limit distanziando le richieste, anche fra thread diversi."""

    def __init__(
        self,
        al_secondo: float,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._intervallo = 1 / al_secondo if al_secondo > 0 else 0.0
        self._sleep = sleep
        self._clock = clock
        self._ultima: float | None = None
        self._serratura = threading.Lock()

    def attendi_turno(self) -> None:
        """Blocca finché non è passato abbastanza tempo dalla richiesta precedente."""
        if not self._intervallo:
            return
        with self._serratura:
            if self._ultima is not None:
                mancante = self._ultima + self._intervallo - self._clock()
                if mancante > 0:
                    self._sleep(mancante)
            self._ultima = self._clock()


@dataclass(frozen=True, slots=True)
class Risposta:
    """Una risposta HTTP grezza: stato, corpo e intestazioni, prima di ogni parsing."""

    status: int
    contenuto: bytes
    intestazioni: Mapping[str, str] = field(default_factory=dict)

    @property
    def testo(self) -> str:
        """Il corpo decodificato come testo."""
        return self.contenuto.decode("utf-8", "replace").strip()

    def json(self) -> Any:
        """Il corpo come JSON."""
        try:
            return json.loads(self.contenuto)
        except (json.JSONDecodeError, UnicodeDecodeError) as errore:
            raise UnexpectedResponseError("il servizio non ha risposto in JSON") from errore


def _query(parametri: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not parametri:
        return None
    return {chiave: valore for chiave, valore in parametri.items() if valore is not None}


class Trasporto:
    """Il canale HTTP sincrono verso il servizio, con retry e rate limit."""

    def __init__(
        self,
        *,
        base_url: str = PRODUZIONE,
        user_agent: str | None = None,
        timeout: float = 30.0,
        retries: int = 2,
        requests_per_second: float = 2.0,
        http_client: httpx.Client | None = None,
        politica: PoliticaRitentativi | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.retries = max(0, retries)
        self.politica = politica or PoliticaRitentativi()
        self._sleep = sleep
        self._limitatore = Limitatore(requests_per_second, sleep=sleep, clock=clock)
        self._nostro = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout, follow_redirects=False)
        self._intestazioni = {
            "User-Agent": user_agent or USER_AGENT,
            "Accept": "application/json",
        }

    @property
    def closed(self) -> bool:
        """Se questo trasporto è stato chiuso."""
        return self._client.is_closed

    def close(self) -> None:
        """Rilascia il pool di connessioni sottostante, se è nostro da rilasciare."""
        if self._nostro:
            self._client.close()

    def __enter__(self) -> Trasporto:
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        errore: BaseException | None,
        traccia: TracebackType | None,
    ) -> None:
        self.close()

    def _indirizzo(self, percorso: str) -> str:
        return (
            percorso if percorso.startswith("http") else f"{self.base_url}/{percorso.lstrip('/')}"
        )

    def richiesta(
        self,
        metodo: str,
        percorso: str,
        *,
        corpo: Any = None,
        parametri: Mapping[str, Any] | None = None,
        attesi: Sequence[int] = (200,),
        segui_redirect: bool = False,
    ) -> Risposta:
        """Esegue una richiesta HTTP, con retry sugli errori ritentabili."""
        indirizzo = self._indirizzo(percorso)
        intestazioni = dict(self._intestazioni)
        if corpo is not None:
            intestazioni["Content-Type"] = "application/json"
        ultimo_errore: Exception | None = None
        ultima_risposta: httpx.Response | None = None

        for tentativo in range(1 + self.retries):
            if tentativo:
                pausa = self.politica.attesa(tentativo - 1)
                logger.debug("nuovo tentativo fra %.2fs su %s %s", pausa, metodo, indirizzo)
                self._sleep(pausa)
            self._limitatore.attendi_turno()
            try:
                risposta = self._client.request(
                    metodo,
                    indirizzo,
                    json=corpo,
                    params=_query(parametri),
                    headers=intestazioni,
                    follow_redirects=segui_redirect,
                )
            except httpx.HTTPError as errore:
                ultimo_errore = errore
                logger.debug("errore di trasporto su %s %s: %s", metodo, indirizzo, errore)
                continue

            if risposta.status_code in attesi:
                return Risposta(
                    status=risposta.status_code,
                    contenuto=risposta.content,
                    intestazioni=dict(risposta.headers),
                )
            regola = _wire.regola_nota(risposta.content)
            if regola is not None or not self.politica.ritentabile(risposta.status_code):
                _wire.solleva_errore(
                    risposta.status_code, risposta.content, risposta.headers.get("content-type")
                )
            logger.debug("il servizio ha risposto %s su %s", risposta.status_code, indirizzo)
            ultimo_errore = None
            ultima_risposta = risposta

        if ultimo_errore is not None:
            raise ConnectionError(f"il servizio non risponde: {ultimo_errore}") from ultimo_errore
        if ultima_risposta is not None:
            _wire.solleva_errore(
                ultima_risposta.status_code,
                ultima_risposta.content,
                ultima_risposta.headers.get("content-type"),
            )
        raise UnexpectedResponseError("richiesta fallita senza una causa riconoscibile")

    def get(
        self,
        percorso: str,
        *,
        parametri: Mapping[str, Any] | None = None,
        attesi: Sequence[int] = (200,),
        segui_redirect: bool = False,
    ) -> Risposta:
        """Esegue una GET."""
        return self.richiesta(
            "GET", percorso, parametri=parametri, attesi=attesi, segui_redirect=segui_redirect
        )

    def post(self, percorso: str, corpo: Any, *, attesi: Sequence[int] = (200,)) -> Risposta:
        """Esegue una POST con corpo JSON."""
        return self.richiesta("POST", percorso, corpo=corpo, attesi=attesi)

    def put(self, percorso: str, corpo: Any, *, attesi: Sequence[int] = (200,)) -> Risposta:
        """Esegue una PUT con corpo JSON."""
        return self.richiesta("PUT", percorso, corpo=corpo, attesi=attesi)


class TrasportoAsync:
    """La variante asincrona di `Trasporto`, con lo stesso comportamento."""

    def __init__(
        self,
        *,
        base_url: str = PRODUZIONE,
        user_agent: str | None = None,
        timeout: float = 30.0,
        retries: int = 2,
        requests_per_second: float = 2.0,
        http_client: httpx.AsyncClient | None = None,
        politica: PoliticaRitentativi | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.retries = max(0, retries)
        self.politica = politica or PoliticaRitentativi()
        self._sleep = sleep
        self._limitatore = LimitatoreAsync(requests_per_second, sleep=sleep, clock=clock)
        self._nostro = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)
        self._intestazioni = {
            "User-Agent": user_agent or USER_AGENT,
            "Accept": "application/json",
        }

    @property
    def closed(self) -> bool:
        """Se questo trasporto è stato chiuso."""
        return self._client.is_closed

    async def close(self) -> None:
        """Rilascia il pool di connessioni sottostante, se è nostro da rilasciare."""
        if self._nostro:
            await self._client.aclose()

    async def __aenter__(self) -> TrasportoAsync:
        return self

    async def __aexit__(
        self,
        tipo: type[BaseException] | None,
        errore: BaseException | None,
        traccia: TracebackType | None,
    ) -> None:
        await self.close()

    def _indirizzo(self, percorso: str) -> str:
        if percorso.startswith("http"):
            return percorso
        return f"{self.base_url}/{percorso.lstrip('/')}"

    async def richiesta(
        self,
        metodo: str,
        percorso: str,
        *,
        corpo: Any = None,
        parametri: Mapping[str, Any] | None = None,
        attesi: Sequence[int] = (200,),
        segui_redirect: bool = False,
    ) -> Risposta:
        """Esegue una richiesta HTTP, con retry sugli errori ritentabili."""
        indirizzo = self._indirizzo(percorso)
        intestazioni = dict(self._intestazioni)
        if corpo is not None:
            intestazioni["Content-Type"] = "application/json"
        ultimo_errore: Exception | None = None
        ultima_risposta: httpx.Response | None = None

        for tentativo in range(1 + self.retries):
            if tentativo:
                pausa = self.politica.attesa(tentativo - 1)
                logger.debug("nuovo tentativo fra %.2fs su %s %s", pausa, metodo, indirizzo)
                await self._sleep(pausa)
            await self._limitatore.attendi_turno()
            try:
                risposta = await self._client.request(
                    metodo,
                    indirizzo,
                    json=corpo,
                    params=_query(parametri),
                    headers=intestazioni,
                    follow_redirects=segui_redirect,
                )
            except httpx.HTTPError as errore:
                ultimo_errore = errore
                logger.debug("errore di trasporto su %s %s: %s", metodo, indirizzo, errore)
                continue

            if risposta.status_code in attesi:
                return Risposta(
                    status=risposta.status_code,
                    contenuto=risposta.content,
                    intestazioni=dict(risposta.headers),
                )
            regola = _wire.regola_nota(risposta.content)
            if regola is not None or not self.politica.ritentabile(risposta.status_code):
                _wire.solleva_errore(
                    risposta.status_code, risposta.content, risposta.headers.get("content-type")
                )
            logger.debug("il servizio ha risposto %s su %s", risposta.status_code, indirizzo)
            ultimo_errore = None
            ultima_risposta = risposta

        if ultimo_errore is not None:
            raise ConnectionError(f"il servizio non risponde: {ultimo_errore}") from ultimo_errore
        if ultima_risposta is not None:
            _wire.solleva_errore(
                ultima_risposta.status_code,
                ultima_risposta.content,
                ultima_risposta.headers.get("content-type"),
            )
        raise UnexpectedResponseError("richiesta fallita senza una causa riconoscibile")

    async def get(
        self,
        percorso: str,
        *,
        parametri: Mapping[str, Any] | None = None,
        attesi: Sequence[int] = (200,),
        segui_redirect: bool = False,
    ) -> Risposta:
        """Esegue una GET."""
        return await self.richiesta(
            "GET", percorso, parametri=parametri, attesi=attesi, segui_redirect=segui_redirect
        )

    async def post(self, percorso: str, corpo: Any, *, attesi: Sequence[int] = (200,)) -> Risposta:
        """Esegue una POST con corpo JSON."""
        return await self.richiesta("POST", percorso, corpo=corpo, attesi=attesi)

    async def put(self, percorso: str, corpo: Any, *, attesi: Sequence[int] = (200,)) -> Risposta:
        """Esegue una PUT con corpo JSON."""
        return await self.richiesta("PUT", percorso, corpo=corpo, attesi=attesi)
