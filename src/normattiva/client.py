"""Il client sincrono e asincrono verso l'API open data di Normattiva."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import date, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any, Literal

import httpx

from normattiva import _wire
from normattiva._http import PRODUZIONE, Trasporto, TrasportoAsync
from normattiva.errori import (
    ConnectionError,
    InvalidArgumentError,
    NormattivaError,
    RuleCode,
    RuleViolationError,
    TooManyResultsError,
    TruncationError,
    UnexpectedResponseError,
    ValidityMismatchError,
)
from normattiva.esporta import AsyncExport, Corpus, Export, _verifica_leggibile
from normattiva.modelli import (
    AttoTrovato,
    ClasseProvvedimento,
    Collection,
    DettaglioAtto,
    EsitoRicerca,
    ExportMode,
    Format,
    RicercaPredefinita,
    Sort,
    Tipologica,
)
from normattiva.urn import Urn

PASSI_MASSIMI = 500
"""Numero massimo di versioni che `cronologia` percorre: oltre, la catena è considerata rotta."""

PAGINE_MASSIME = 2000
"""Numero massimo di pagine che `ricerca_completa` scorre, a protezione da paginazioni infinite."""

SeTroncato = Literal["segnala", "solleva"]
Vigenza = date | Literal["originale"] | None
Intervallo = tuple[date | None, date | None]

_ORDINE_WIRE = {
    Sort.NEWEST: "recente",
    Sort.OLDEST: "vecchio",
}
"""Come il servizio chiama i due ordinamenti. Il wire non esce da qui."""

_LETTERA_MODALITA = {
    ExportMode.ORIGINALE: "O",
    ExportMode.VIGENTE: "V",
    ExportMode.MULTIVIGENTE: "M",
}


def _urn_con_vigenza(urn: Urn | str, vigenza: Vigenza) -> Urn:
    letto = Urn.parse(urn).senza_comma
    if vigenza is None:
        return letto
    if letto.versione is not None and letto.versione != vigenza:
        raise InvalidArgumentError(
            f"la vigenza è indicata due volte, {letto.versione} nell'URN e {vigenza} nel "
            "parametro: indicarla una volta sola"
        )
    return letto.con_vigenza(vigenza)


def _paginazione(pagina: int, per_pagina: int) -> dict[str, int]:
    if pagina < 1 or per_pagina < 1:
        raise InvalidArgumentError("pagina e per_pagina partono da 1")
    return {"paginaCorrente": pagina, "numeroElementiPerPagina": per_pagina}


def _filtri(tipo: str | None, anno: int | None, emettitore: str | None) -> dict[str, str]:
    scelti = {
        "codice_tipo_provvedimento": tipo,
        "anno_provvedimento": str(anno) if anno is not None else None,
        "descrizione_emettitore": emettitore,
    }
    return {chiave: valore for chiave, valore in scelti.items() if valore is not None}


def _senza_vuoti(campi: dict[str, Any]) -> dict[str, Any]:
    return {chiave: valore for chiave, valore in campi.items() if valore is not None}


def _coordinate(
    denominazione: str | None,
    anno: int | None,
    numero: int | str | None,
    giorno: int | None,
    mese: int | None,
    titolo: str | None,
    testo: str | None,
    vigente_al: date | None,
    classe: ClasseProvvedimento | int | None,
    emanazione: Intervallo | None,
    pubblicazione: Intervallo | None,
) -> dict[str, Any]:
    """Raccoglie in un dizionario i criteri di una ricerca avanzata.

    La ricerca avanzata e l'esportazione accettano gli stessi criteri e li
    dichiarano entrambe per esteso nella firma; questa raccolta serve solo
    all'esportazione, che deve passare i criteri al conteggio preventivo.
    """
    return _senza_vuoti(
        {
            "denominazione": denominazione,
            "anno": anno,
            "numero": numero,
            "giorno": giorno,
            "mese": mese,
            "titolo": titolo,
            "testo": testo,
            "vigente_al": vigente_al,
            "classe": classe,
            "emanazione": emanazione,
            "pubblicazione": pubblicazione,
        }
    )


_NOMI_EXPORT = {
    "vigenza": "dataVigenza",
    "dataInizioPubProvvedimento": "dataInizioPubblicazione",
    "dataFinePubProvvedimento": "dataFinePubblicazione",
}
"""Tre campi che l'esportazione chiama con un nome diverso rispetto alla ricerca.

La distinzione è sostanziale: mandare all'esportazione il nome usato dalla
ricerca non produce un errore, produce un filtro che non filtra. Verificato il
2026-08-24 esportando la legge 241/1990 con una finestra di pubblicazione
impossibile: col nome della ricerca l'atto viene restituito comunque, col nome
dell'esportazione l'archivio è vuoto.
"""


def _campi_avanzati(coordinate: dict[str, Any], *, per_export: bool = False) -> dict[str, Any]:
    """Traduce le coordinate nei campi che il servizio legge.

    Senza coordinate il servizio risponde con l'intero corpus: è una richiesta
    ammessa, e la libreria non la rifiuta. Per l'esportazione, che è costosa per
    il servizio, il limite è il conteggio preventivo.

    I due schemi non usano gli stessi nomi per tutti i campi: `per_export` sceglie
    quelli dell'esportazione, che ignora in silenzio gli altri.
    """
    dal_emanazione, al_emanazione = coordinate.get("emanazione") or (None, None)
    dal_pubblicazione, al_pubblicazione = coordinate.get("pubblicazione") or (None, None)
    numero = coordinate.get("numero")
    classe = coordinate.get("classe")
    vigente_al = coordinate.get("vigente_al")
    campi = _senza_vuoti(
        {
            "denominazioneAtto": coordinate.get("denominazione"),
            "annoProvvedimento": coordinate.get("anno"),
            "numeroProvvedimento": int(numero) if numero is not None else None,
            "giornoProvvedimento": coordinate.get("giorno"),
            "meseProvvedimento": coordinate.get("mese"),
            "titoloRicerca": coordinate.get("titolo"),
            "testoRicerca": coordinate.get("testo"),
            "vigenza": vigente_al.isoformat() if vigente_al else None,
            "classeProvvedimento": str(int(classe)) if classe is not None else None,
            "dataInizioEmanazione": _istante(dal_emanazione),
            "dataFineEmanazione": _istante(al_emanazione),
            "dataInizioPubProvvedimento": _istante(dal_pubblicazione),
            "dataFinePubProvvedimento": _istante(al_pubblicazione),
        }
    )
    if per_export:
        campi = {_NOMI_EXPORT.get(nome, nome): valore for nome, valore in campi.items()}
    return campi


def _istante(giorno: date | None) -> str | None:
    return f"{giorno.isoformat()}T00:00:00Z" if giorno else None


def _intervalli(dal: date, al: date) -> Iterator[tuple[date, date]]:
    inizio = dal
    while inizio <= al:
        fine = min(_avanti_di_un_anno(inizio), al)
        yield inizio, fine
        inizio = fine + timedelta(days=1)


def _avanti_di_un_anno(giorno: date) -> date:
    try:
        return giorno.replace(year=giorno.year + 1) - timedelta(days=1)
    except ValueError:
        return giorno.replace(year=giorno.year + 1, day=giorno.day - 1) - timedelta(days=1)


def _corpo_ricerca(
    testo: str,
    *,
    pagina: int,
    per_pagina: int,
    sort: Sort | str,
    tipo: str | None,
    anno: int | None,
    emettitore: str | None,
) -> dict[str, Any]:
    if not testo.strip():
        raise InvalidArgumentError("il testo da cercare non può essere vuoto")
    corpo: dict[str, Any] = {
        "testoRicerca": testo.strip(),
        "orderType": _ORDINE_WIRE[Sort(sort)],
        "paginazione": _paginazione(pagina, per_pagina),
    }
    filtri = _filtri(tipo, anno, emettitore)
    if filtri:
        corpo["filtriMap"] = filtri
    return corpo


def _corpo_avanzata(
    coordinate: dict[str, Any],
    sort: Sort | str,
    pagina: int,
    per_pagina: int,
    tipo: str | None,
    emettitore: str | None,
) -> dict[str, Any]:
    corpo = _campi_avanzati(coordinate)
    corpo["orderType"] = _ORDINE_WIRE[Sort(sort)]
    corpo["paginazione"] = _paginazione(pagina, per_pagina)
    filtri = _filtri(tipo, None, emettitore)
    if filtri:
        corpo["filtriMap"] = filtri
    return corpo


def _corpo_export(
    coordinate: dict[str, Any],
    format: Format | str,
    mode: ExportMode | str,
    esclusioni: dict[str, Any],
) -> dict[str, Any]:
    return {
        "formato": str(Format(format)),
        "tipoRicerca": "A",
        "richiestaExport": _LETTERA_MODALITA[ExportMode(mode)],
        "modalita": "C",
        "parametriRicerca": {
            **_campi_avanzati(coordinate, per_export=True),
            **_senza_vuoti(esclusioni),
            "limitaAnniVigenza": False,
        },
    }


def _corpo_gazzetta(codice_redazionale: str, giorno: date) -> dict[str, Any]:
    if not codice_redazionale.strip():
        raise InvalidArgumentError("il codice redazionale non può essere vuoto")
    return {"codiceRedazionale": codice_redazionale.strip(), "dataGU": giorno.isoformat()}


def _coordinate_di_gazzetta(trovato: AttoTrovato) -> tuple[str, date]:
    codice = trovato.gazzetta.codice_redazionale
    if codice is None:
        raise InvalidArgumentError(
            f"«{trovato.estremi.denominazione}» non ha una forma URN verificata e il "
            "risultato non include un codice redazionale: impossibile richiederne il testo"
        )
    return codice, trovato.gazzetta.data


def _parametri_collezione(
    name: str, format: Format | str, mode: ExportMode | str
) -> dict[str, str]:
    return {
        "nome": name,
        "formato": str(Format(format)),
        "formatoRichiesta": _LETTERA_MODALITA[ExportMode(mode)],
    }


def _verifica_senza_vigenza(trovato: AttoTrovato, vigenza: Vigenza) -> None:
    """Rifiuta una vigenza per gli atti raggiungibili solo dalle coordinate di Gazzetta.

    Quel percorso non supporta le date: `dataVigenza` esiste nello schema di
    `dettaglio-atto` ma non ha effetto (verificato il 2026-08-24, la finestra
    restituita è la stessa con e senza). Accettare il parametro e ignorarlo
    restituirebbe il testo di oggi presentandolo come storico.
    """
    if vigenza is not None:
        raise InvalidArgumentError(
            f"«{trovato.estremi.denominazione}» è raggiungibile solo dalle coordinate di "
            "Gazzetta, che restituiscono sempre il testo vigente: "
            "una vigenza a una data richiede un URN"
        )


def _verifica_se_troncato(se_troncato: str) -> None:
    if se_troncato not in ("segnala", "solleva"):
        raise InvalidArgumentError("se_troncato accetta 'segnala' oppure 'solleva'")


def _controlla_dettaglio(atto: DettaglioAtto, vigenza: Vigenza, se_troncato: str) -> DettaglioAtto:
    if isinstance(vigenza, date) and atto.finestra and not atto.finestra.contiene(vigenza):
        raise ValidityMismatchError(vigenza, atto.finestra)
    if se_troncato == "solleva" and atto.possibile_troncamento:
        raise TruncationError(atto.ultimo_comma_numerato or 0)
    return atto


def _verifica_intervallo(dal: date, al: date) -> None:
    if al < dal:
        raise RuleViolationError(RuleCode.DATE_INVERTITE, f"la fine {al} precede l'inizio {dal}")


def _conteggio_non_riuscito(errore: NormattivaError) -> NormattivaError:
    """Riscrive l'errore del conteggio preventivo, indicando come procedere senza.

    Il conteggio si appoggia alla ricerca sincrona, che può fallire anche quando
    l'esportazione funziona: senza questa riscrittura, chi chiama leggerebbe «il
    servizio non risponde» senza sapere a quale delle due chiamate si riferisce.
    """
    return type(errore)(
        f"il conteggio preventivo dell'esportazione non è riuscito: {errore}. "
        "Con massimo_atti=None l'esportazione parte senza conteggio."
    )


def _corpo_aggiornati(inizio: date, fine: date) -> dict[str, Any]:
    return {
        "dataInizioAggiornamento": _istante(inizio),
        "dataFineAggiornamento": _istante(fine),
    }


class Normattiva:
    """Il client sincrono verso il servizio open data di Normattiva.

    Tiene il pool di connessioni HTTP, l'autolimitazione delle richieste e la
    politica dei tentativi, ed espone un metodo per ogni endpoint dell'API. Va
    costruito una volta e riusato: l'autolimitazione conta le richieste di un
    client, quindi con un client per chiamata non limita più niente.

    I metodi che costano una richiesta restituiscono un modello; quelli che
    possono costarne molte sono iteratori, e il nome lo indica.

    Ogni metodo che tocca la rete può sollevare `ConnectionError` se il
    servizio non è raggiungibile, `UnexpectedResponseError` se la risposta non ha
    la forma che la libreria sa leggere, e `RequestBlockedError` se lo strato
    di protezione respinge la forma della richiesta. Le sezioni `Raises` dei
    singoli metodi elencano solo le eccezioni specifiche di ciascuno.

    Args:
        user_agent: come il client si presenta al servizio. Il predefinito
            nomina la libreria e il suo repository; indicare il proprio
            servizio e un recapito è una cortesia verso chi riceve il traffico.
        timeout: quanti secondi attendere una singola risposta. Le esportazioni
            lente vogliono un valore più alto.
        retries: quanti tentativi in tutto per ogni richiesta, il primo
            compreso. Con `1` non si ritenta; valori più bassi valgono `1`.
        requests_per_second: il tetto che il client si impone. Il servizio non
            pubblica quote: due al secondo è una scelta prudente di questa
            libreria, non un limite imposto da Normattiva. Con `0` non limita.
        base_url: la radice dell'API. Si cambia per puntare a un doppio del
            servizio nei test.
        http_client: un client `httpx` già configurato, per metriche, tracing o
            intestazioni aggiuntive. Un client passato da fuori non viene
            chiuso da `close`.
        sleep: la funzione che attende fra un tentativo e l'altro; nei test la
            si sostituisce per non attendere davvero.
        clock: la sorgente di tempo dell'autolimitazione, sostituibile per lo
            stesso motivo.

    Examples:
        >>> with Normattiva() as normattiva:  # doctest: +SKIP
        ...     atto = normattiva.dettaglio("urn:nir:stato:legge:1990-08-07;241~art2")
    """

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        timeout: float = 30.0,
        retries: int = 3,
        requests_per_second: float = 2.0,
        base_url: str = PRODUZIONE,
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._trasporto = Trasporto(
            base_url=base_url,
            user_agent=user_agent,
            timeout=timeout,
            retries=retries,
            requests_per_second=requests_per_second,
            http_client=http_client,
            sleep=sleep,
            clock=clock,
        )
        self._sleep = sleep
        self._clock = clock
        self._dizionari: dict[str, tuple[Tipologica, ...]] = {}

    @property
    def base_url(self) -> str:
        """L'indirizzo base del servizio a cui questo client si rivolge."""
        return self._trasporto.base_url

    @property
    def closed(self) -> bool:
        """Se questo client è stato chiuso."""
        return self._trasporto.closed

    def close(self) -> None:
        """Rilascia il pool di connessioni, se è stato creato da questo client.

        Un client HTTP passato dall'esterno resta aperto: chiuderlo spetta a chi
        lo ha creato.
        """
        self._trasporto.close()

    def __enter__(self) -> Normattiva:
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        errore: BaseException | None,
        traccia: TracebackType | None,
    ) -> None:
        self.close()

    def dettaglio(
        self,
        atto: Urn | str | AttoTrovato,
        *,
        vigenza: Vigenza = None,
        se_troncato: SeTroncato = "segnala",
    ) -> DettaglioAtto:
        """Legge il testo di un atto o di un suo articolo.

        `atto` è un URN, oppure un `AttoTrovato` uscito da una ricerca. Per i
        dodici tipi di atto su trenta la cui forma URN non è verificata la
        libreria passa dalle coordinate di Gazzetta, che il servizio accetta
        allo stesso modo. Quel percorso però non supporta le date: chiedere una
        `vigenza` per un atto raggiungibile solo così solleva un errore, il
        parametro non viene ignorato in silenzio.

        Senza `vigenza` il servizio restituisce il testo vigente oggi, e nella
        risposta nulla dichiara a quale data corrisponde: indicarla è l'unico
        modo di saperlo. Quando si indica una data, la finestra restituita
        viene verificata contro di essa.

        Con `se_troncato="solleva"` un articolo che sembra tagliato solleva
        `TruncationError` invece di limitarsi a segnalarlo in una
        proprietà.

        Args:
            atto: un URN, la sua forma testuale, oppure un `AttoTrovato`
                uscito da una ricerca. Il comma viene rimosso automaticamente,
                perché il servizio lo rifiuta in ingresso.
            vigenza: il giorno a cui leggere il testo, `"originale"` per la
                prima pubblicazione, `None` per il testo di oggi.
            se_troncato: `"segnala"` registra il sospetto nella proprietà
                `possibile_troncamento`, `"solleva"` lo trasforma in eccezione.

        Returns:
            Il testo richiesto, con la finestra di vigenza in cui è valido.

        Examples:
            Il testo dell'articolo 19 della legge 241 com'era nel 2000, con la
            finestra in cui quel testo è stato in vigore::

                atto = normattiva.dettaglio(
                    "urn:nir:stato:legge:1990-08-07;241~art19",
                    vigenza=date(2000, 1, 1),
                )
                print(atto.finestra)  # 1994-01-01 → 2005-03-07

        Raises:
            NotFoundError: nessun atto risponde a quelle coordinate.
            AmbiguityError: l'URN corrisponde a più atti pubblicati; i
                candidati sono elencati nell'eccezione.
            NotYetInForceError: l'articolo non esisteva alla data
                richiesta.
            ValidityMismatchError: il servizio ha risposto con una versione che
                non copre la data richiesta.
            TruncationError: solo con `se_troncato="solleva"`, e solo se
                il testo sembra tagliato.
            InvalidUrnError: l'URN è malformato, oppure la forma URN di quel
                tipo di atto non è verificata.
            InvalidArgumentError: la vigenza è indicata due volte, oppure è
                chiesta per un atto raggiungibile solo dalle coordinate di
                Gazzetta.
        """
        _verifica_se_troncato(se_troncato)
        if isinstance(atto, AttoTrovato) and not atto.ha_urn:
            _verifica_senza_vigenza(atto, vigenza)
            codice, giorno = _coordinate_di_gazzetta(atto)
            return self.dettaglio_da_gazzetta(codice, giorno, se_troncato=se_troncato)
        urn = atto.urn if isinstance(atto, AttoTrovato) else atto
        risposta = self._trasporto.post(
            "atto/dettaglio-atto-urn", {"urn": str(_urn_con_vigenza(urn, vigenza))}
        )
        return _controlla_dettaglio(_wire.leggi_dettaglio(risposta.json()), vigenza, se_troncato)

    def dettaglio_da_gazzetta(
        self,
        codice_redazionale: str,
        data: date,
        *,
        se_troncato: SeTroncato = "segnala",
    ) -> DettaglioAtto:
        """Legge un atto a partire dalle sue coordinate di Gazzetta.

        È il percorso per gli atti la cui forma URN non è verificata: il codice
        redazionale e la data di Gazzetta arrivano da una ricerca, e il servizio
        risponde anche per un decreto-legge luogotenenziale del 1917. Questo
        percorso però non supporta la multivigenza: restituisce sempre il testo
        vigente oggi, e per una data serve un URN.

        Args:
            codice_redazionale: l'identificativo di Gazzetta dell'atto, come
                arriva da `AttoTrovato.gazzetta.codice_redazionale`.
            data: la data di pubblicazione in Gazzetta.
            se_troncato: come per `dettaglio`.

        Returns:
            Il testo dell'atto, sempre nella versione vigente oggi.

        Raises:
            NotFoundError: nessun atto per quelle coordinate di Gazzetta.
            InvalidArgumentError: il codice redazionale è vuoto.
        """
        _verifica_se_troncato(se_troncato)
        risposta = self._trasporto.post(
            "atto/dettaglio-atto", _corpo_gazzetta(codice_redazionale, data)
        )
        return _controlla_dettaglio(_wire.leggi_dettaglio(risposta.json()), None, se_troncato)

    def cronologia(self, urn: Urn | str, *, massimo: int | None = None) -> Iterator[DettaglioAtto]:
        """Percorre tutte le versioni di un articolo, dall'originale a quella in vigore.

        Costa una richiesta per versione: le finestre di vigenza sono contigue,
        quindi ogni versione viene chiesta al giorno successivo alla fine della
        precedente. Con `massimo` l'iterazione si ferma dopo quel numero di
        versioni; senza, arriva all'ultima. Senza `massimo` la catena si ferma
        comunque dopo cinquecento passi: nessun articolo italiano ha
        cinquecento versioni, quindi una catena così lunga indica finestre non
        contigue.

        Args:
            urn: l'articolo di cui percorrere le versioni.
            massimo: quante versioni al più produrre. Senza, si arriva in fondo.

        Yields:
            Una versione per volta, dalla più vecchia alla più recente.

        Raises:
            UnexpectedResponseError: la catena non si chiude entro cinquecento
                passi, cioè le finestre di vigenza non sono contigue.
        """
        base = Urn.parse(urn).senza_comma
        prossima: Vigenza = "originale"
        prodotte = 0
        while massimo is None or prodotte < massimo:
            if massimo is None and prodotte >= PASSI_MASSIMI:
                raise UnexpectedResponseError(
                    f"la catena delle versioni non si chiude dopo {PASSI_MASSIMI} passi: "
                    "le finestre di vigenza non sono contigue"
                )
            atto = self.dettaglio(base.con_vigenza(prossima))
            yield atto
            prodotte += 1
            chiusura = atto.finestra.fine if atto.finestra else None
            if chiusura is None:
                return
            prossima = chiusura + timedelta(days=1)

    def ricerca(
        self,
        testo: str,
        *,
        pagina: int = 1,
        per_pagina: int = 20,
        sort: Sort | str = Sort.NEWEST,
        tipo: str | None = None,
        anno: int | None = None,
        emettitore: str | None = None,
    ) -> EsitoRicerca:
        """Cerca nel testo pieno del corpus.

        Le parole vengono combinate in AND dal servizio; non c'è modo di
        chiedere un OR. `tipo`, `anno` ed `emettitore` sono le faccette che la
        risposta stessa propone, non le coordinate dell'atto: per quelle c'è
        `ricerca_avanzata`.

        Args:
            testo: le parole da cercare, combinate in AND dal servizio.
            pagina: quale pagina di risultati, a partire da 1.
            per_pagina: quanti risultati per pagina.
            sort: `"newest"` dal più recente, `"oldest"` dal più vecchio.
            tipo: codice della faccetta per tipo di atto, come `"PLE"`.
            anno: faccetta per anno di provvedimento.
            emettitore: faccetta per amministrazione emanante.

        Returns:
            Una pagina di risultati, con il totale e le faccette per restringere.
        """
        corpo = _corpo_ricerca(
            testo,
            pagina=pagina,
            per_pagina=per_pagina,
            sort=sort,
            tipo=tipo,
            anno=anno,
            emettitore=emettitore,
        )
        return _wire.leggi_ricerca(self._trasporto.post("ricerca/semplice", corpo).json())

    def ricerca_avanzata(
        self,
        *,
        denominazione: str | None = None,
        anno: int | None = None,
        numero: int | str | None = None,
        giorno: int | None = None,
        mese: int | None = None,
        titolo: str | None = None,
        testo: str | None = None,
        vigente_al: date | None = None,
        classe: ClasseProvvedimento | int | None = None,
        emanazione: Intervallo | None = None,
        pubblicazione: Intervallo | None = None,
        sort: Sort | str = Sort.NEWEST,
        tipo: str | None = None,
        emettitore: str | None = None,
        pagina: int = 1,
        per_pagina: int = 20,
    ) -> EsitoRicerca:
        """Cerca per coordinate invece che per parole.

        Senza nessuna coordinata il servizio risponde con l'intero corpus: è
        una richiesta ammessa, e la libreria non la rifiuta.

        Args:
            denominazione: il tipo di atto come lo scrive il dizionario, per
                esempio `"LEGGE"` o `"DECRETO LEGISLATIVO"`.
            anno: anno di emanazione.
            numero: numero del provvedimento.
            giorno: giorno di emanazione.
            mese: mese di emanazione.
            titolo: parole da cercare nel titolo.
            testo: parole da cercare nel testo.
            vigente_al: tiene solo gli atti in vigore in quel giorno.
            classe: la classe redazionale dell'atto (senza aggiornamenti,
                aggiornato, abrogato).
            emanazione: intervallo di emanazione, come coppia `(dal, al)`. Un
                estremo può essere `None` per lasciare la finestra aperta.
            pubblicazione: intervallo di pubblicazione in Gazzetta, come sopra.
            sort: `"newest"` dal più recente, `"oldest"` dal più vecchio.
            tipo: faccetta per tipo di atto.
            emettitore: faccetta per amministrazione emanante.
            pagina: quale pagina di risultati, a partire da 1.
            per_pagina: quanti risultati per pagina.

        Returns:
            Una pagina di risultati, nella stessa forma che rende `ricerca`.
        """
        corpo = _corpo_avanzata(
            _coordinate(
                denominazione,
                anno,
                numero,
                giorno,
                mese,
                titolo,
                testo,
                vigente_al,
                classe,
                emanazione,
                pubblicazione,
            ),
            sort,
            pagina,
            per_pagina,
            tipo,
            emettitore,
        )
        return _wire.leggi_ricerca(self._trasporto.post("ricerca/avanzata", corpo).json())

    def ricerca_completa(
        self,
        testo: str,
        *,
        massimo: int | None = None,
        per_pagina: int = 50,
        sort: Sort | str = Sort.NEWEST,
        tipo: str | None = None,
        anno: int | None = None,
        emettitore: str | None = None,
    ) -> Iterator[AttoTrovato]:
        """Scorre tutti gli atti che una ricerca trova, una pagina per volta.

        L'iteratore è pigro: ogni pagina viene chiesta solo quando serve,
        quindi consumare dieci risultati costa una richiesta sola. Con
        `massimo` ci si ferma dopo quel numero di atti; per sapere quanti ce
        n'erano in tutto basta una `ricerca` e il suo `totale`.

        Quel `totale` è anche la condizione di uscita: il numero di pagina
        restituito dal servizio non è affidabile, e usarlo come condizione
        potrebbe rileggere la prima pagina all'infinito.

        Args:
            testo: le parole da cercare.
            massimo: quanti atti al più produrre. Senza, si arriva in fondo.
            per_pagina: quanti risultati chiedere per richiesta.
            sort: `"newest"` dal più recente, `"oldest"` dal più vecchio.
            tipo: faccetta per tipo di atto.
            anno: faccetta per anno di provvedimento.
            emettitore: faccetta per amministrazione emanante.

        Yields:
            Un atto per volta, nell'ordine in cui il servizio li rende.
        """
        if massimo is not None and massimo <= 0:
            return
        prodotti = 0
        pagina = 1
        dichiarati: int | None = None
        quanti_per_pagina = per_pagina if massimo is None else min(per_pagina, massimo)
        while True:
            esito = self.ricerca(
                testo,
                pagina=pagina,
                per_pagina=quanti_per_pagina,
                sort=sort,
                tipo=tipo,
                anno=anno,
                emettitore=emettitore,
            )
            if dichiarati is None:
                dichiarati = esito.totale
            for atto in esito.atti:
                yield atto
                prodotti += 1
                if massimo is not None and prodotti >= massimo:
                    return
            if not esito.atti or prodotti >= dichiarati or pagina >= PAGINE_MASSIME:
                return
            pagina += 1

    def atti_aggiornati(self, dal: date, al: date) -> Iterator[AttoTrovato]:
        """Elenca gli atti modificati fra due date.

        Il flusso contiene solo le modifiche: un atto pubblicato dentro la
        finestra ma mai modificato dopo non compare. Le finestre più lunghe di
        un anno vengono spezzate, perché il servizio le rifiuta.

        Args:
            dal: primo giorno della finestra, compreso.
            al: ultimo giorno della finestra, compreso.

        Yields:
            Un atto modificato per volta, finestra dopo finestra.

        Raises:
            RuleViolationError: `al` precede `dal`. Sollevata prima di toccare
                la rete, col codice `RuleCode.DATE_INVERTITE`.
        """
        _verifica_intervallo(dal, al)
        for inizio, fine in _intervalli(dal, al):
            corpo = _corpo_aggiornati(inizio, fine)
            esito = _wire.leggi_ricerca(self._trasporto.post("ricerca/aggiornati", corpo).json())
            yield from esito.atti

    def _dizionario(
        self,
        chiave: str,
        percorso: str,
        lettore: Callable[[Any], tuple[Tipologica, ...]],
        reload: bool,
    ) -> tuple[Tipologica, ...]:
        if reload or chiave not in self._dizionari:
            self._dizionari[chiave] = lettore(self._trasporto.get(percorso).json())
        return self._dizionari[chiave]

    def denominazioni(self, *, reload: bool = False) -> tuple[Tipologica, ...]:
        """Elenca i tipi di atto che il corpus contiene, e tiene il risultato in memoria."""
        return self._dizionario(
            "denominazioni", "tipologiche/denominazione-atto", _wire.leggi_denominazioni, reload
        )

    def classi_provvedimento(self, *, reload: bool = False) -> tuple[Tipologica, ...]:
        """Elenca le classi redazionali a cui un atto può appartenere."""
        return self._dizionario(
            "classi", "tipologiche/classe-provvedimento", _wire.leggi_classi, reload
        )

    def export_formats(self, *, reload: bool = False) -> tuple[Tipologica, ...]:
        """Elenca i formati in cui si può chiedere un'esportazione."""
        return self._dizionario(
            "estensioni", "tipologiche/estensioni", _wire.leggi_estensioni, reload
        )

    def ricerche_predefinite(self) -> tuple[RicercaPredefinita, ...]:
        """Elenca le ricerche predefinite che il servizio propone."""
        return _wire.leggi_ricerche_predefinite(self._trasporto.get("ricerca/predefinita").json())

    def collections(self) -> tuple[Collection, ...]:
        """Elenca gli archivi già confezionati che il servizio mette a disposizione."""
        return _wire.leggi_collezioni(
            self._trasporto.get("collections/collection-predefinite").json()
        )

    def _archivio_collezione(
        self, name: str, format: Format | str, mode: ExportMode | str
    ) -> bytes:
        risposta = self._trasporto.get(
            "collections/download/collection-preconfezionata",
            parametri=_parametri_collezione(name, format, mode),
            segui_redirect=True,
        )
        return risposta.contenuto

    def download_collection(
        self,
        name: str,
        *,
        format: Format | str = Format.JSON,
        mode: ExportMode | str = ExportMode.VIGENTE,
    ) -> Corpus:
        """Scarica un archivio già confezionato e legge gli atti che contiene.

        Raises:
            InvalidArgumentError: il formato chiesto non viene letto in
                modelli; usare `save_collection` per averlo come file.
        """
        _verifica_leggibile(Format(format), "save_collection()")
        return Corpus.from_data(self._archivio_collezione(name, format, mode))

    def save_collection(
        self,
        name: str,
        path: str | Path,
        *,
        format: Format | str = Format.JSON,
        mode: ExportMode | str = ExportMode.VIGENTE,
    ) -> Path:
        """Scarica su disco un archivio già confezionato, in qualunque formato sia."""
        destinazione = Path(path)
        destinazione.write_bytes(self._archivio_collezione(name, format, mode))
        return destinazione

    def start_export(
        self,
        *,
        format: Format | str = Format.JSON,
        mode: ExportMode | str = ExportMode.MULTIVIGENTE,
        massimo_atti: int | None = 100,
        escludi_testo: str | None = None,
        escludi_titolo: str | None = None,
        denominazione: str | None = None,
        anno: int | None = None,
        numero: int | str | None = None,
        giorno: int | None = None,
        mese: int | None = None,
        titolo: str | None = None,
        testo: str | None = None,
        vigente_al: date | None = None,
        classe: ClasseProvvedimento | int | None = None,
        emanazione: Intervallo | None = None,
        pubblicazione: Intervallo | None = None,
    ) -> Export:
        """Chiede l'esportazione completa degli atti che una ricerca trova.

        Le coordinate sono le stesse di `ricerca_avanzata`. Prima di avviare
        l'esportazione gli atti vengono contati con una ricerca sincrona,
        perché un'esportazione costa minuti di lavoro al servizio e, una volta
        partita, non si annulla. Con `massimo_atti=None` si parte senza
        conteggio.

        `escludi_testo` ed `escludi_titolo` escludono dal risultato gli atti
        che contengono quelle parole, e sono l'unico filtro che l'esportazione
        supporta e la ricerca no: il conteggio preventivo non ne tiene conto,
        quindi può contare più atti di quanti ne arriveranno.

        Args:
            format: in che formato produrre l'archivio. Solo `JSON` viene poi
                letto in modelli.
            mode: quante versioni includere nell'archivio.
            massimo_atti: il tetto oltre il quale l'esportazione non parte.
                `None` la avvia senza conteggio preventivo.
            escludi_testo: esclude gli atti che contengono questa parola.
            escludi_titolo: esclude gli atti il cui titolo la contiene.
            denominazione: come in `ricerca_avanzata`, e così tutti i criteri
                che seguono.
            anno: anno di emanazione.
            numero: numero del provvedimento.
            giorno: giorno di emanazione.
            mese: mese di emanazione.
            titolo: parole da cercare nel titolo.
            testo: parole da cercare nel testo.
            vigente_al: tiene solo gli atti in vigore in quel giorno.
            classe: la classe redazionale dell'atto (senza aggiornamenti,
                aggiornato, abrogato).
            emanazione: intervallo di emanazione, come coppia `(dal, al)`.
            pubblicazione: intervallo di pubblicazione in Gazzetta.

        Returns:
            L'esportazione appena avviata, da attendere e poi scaricare.

        Raises:
            TooManyResultsError: i criteri selezionano più atti di
                `massimo_atti`. L'esportazione non viene avviata.
            ConnectionError: il conteggio preventivo non è riuscito. Il
                messaggio indica come procedere senza.
        """
        coordinate = _coordinate(
            denominazione,
            anno,
            numero,
            giorno,
            mese,
            titolo,
            testo,
            vigente_al,
            classe,
            emanazione,
            pubblicazione,
        )
        corpo = _corpo_export(
            coordinate,
            format,
            mode,
            {"testoNot": escludi_testo, "titoloNot": escludi_titolo},
        )
        if massimo_atti is not None:
            try:
                quanti = self.ricerca_avanzata(**coordinate, per_pagina=1).totale
            except (ConnectionError, UnexpectedResponseError) as errore:
                raise _conteggio_non_riuscito(errore) from errore
            if quanti > massimo_atti:
                raise TooManyResultsError(quanti, massimo_atti)
        risposta = self._trasporto.post("ricerca-asincrona/nuova-ricerca", corpo, attesi=(200, 202))
        token = risposta.testo
        self._trasporto.put(
            "ricerca-asincrona/conferma-ricerca", {"token": token}, attesi=(200, 202, 204)
        )
        return Export(
            token,
            self._trasporto,
            format=Format(format),
            sleep=self._sleep,
            clock=self._clock,
        )

    def export_from_token(self, token: str, *, format: Format | str = Format.JSON) -> Export:
        """Riprende un'esportazione già in corso, dal suo token."""
        return Export.from_token(token, self._trasporto, format=Format(format))


class AsyncNormattiva:
    """La variante asincrona del client.

    Ogni metodo rispecchia il suo gemello su `Normattiva`, firma compresa;
    quelli che iterano restituiscono iteratori asincroni. Anche gli argomenti
    del costruttore sono gli stessi, con `http_client` che qui vuole un
    `httpx.AsyncClient` e `sleep` che passa da `asyncio.sleep`.

    Le corutine che condividono un client condividono anche la sua
    autolimitazione, e quindi si mettono in fila da sole.

    Ogni metodo che tocca la rete può sollevare `ConnectionError` se il
    servizio non è raggiungibile, `UnexpectedResponseError` se la risposta non ha
    la forma che la libreria sa leggere, e `RequestBlockedError` se lo strato
    di protezione respinge la forma della richiesta. Le sezioni `Raises` dei
    singoli metodi elencano solo le eccezioni specifiche di ciascuno.
    """

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        timeout: float = 30.0,
        retries: int = 3,
        requests_per_second: float = 2.0,
        base_url: str = PRODUZIONE,
        http_client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._trasporto = TrasportoAsync(
            base_url=base_url,
            user_agent=user_agent,
            timeout=timeout,
            retries=retries,
            requests_per_second=requests_per_second,
            http_client=http_client,
            sleep=sleep,
            clock=clock,
        )
        self._sleep = sleep
        self._clock = clock
        self._dizionari: dict[str, tuple[Tipologica, ...]] = {}

    @property
    def base_url(self) -> str:
        """L'indirizzo base del servizio a cui questo client si rivolge."""
        return self._trasporto.base_url

    @property
    def closed(self) -> bool:
        """Se questo client è stato chiuso."""
        return self._trasporto.closed

    async def close(self) -> None:
        """Rilascia il pool di connessioni, se è stato creato da questo client.

        Un client HTTP passato dall'esterno resta aperto: chiuderlo spetta a chi
        lo ha creato.
        """
        await self._trasporto.close()

    async def __aenter__(self) -> AsyncNormattiva:
        return self

    async def __aexit__(
        self,
        tipo: type[BaseException] | None,
        errore: BaseException | None,
        traccia: TracebackType | None,
    ) -> None:
        await self.close()

    async def dettaglio(
        self,
        atto: Urn | str | AttoTrovato,
        *,
        vigenza: Vigenza = None,
        se_troncato: SeTroncato = "segnala",
    ) -> DettaglioAtto:
        """Legge il testo di un atto o di un suo articolo.

        `atto` è un URN, oppure un `AttoTrovato` uscito da una ricerca. Per i
        dodici tipi di atto su trenta la cui forma URN non è verificata la
        libreria passa dalle coordinate di Gazzetta, che il servizio accetta
        allo stesso modo. Quel percorso però non supporta le date: chiedere una
        `vigenza` per un atto raggiungibile solo così solleva un errore, il
        parametro non viene ignorato in silenzio.

        Senza `vigenza` il servizio restituisce il testo vigente oggi, e nella
        risposta nulla dichiara a quale data corrisponde: indicarla è l'unico
        modo di saperlo. Quando si indica una data, la finestra restituita
        viene verificata contro di essa.

        Con `se_troncato="solleva"` un articolo che sembra tagliato solleva
        `TruncationError` invece di limitarsi a segnalarlo in una
        proprietà.

        Args:
            atto: un URN, la sua forma testuale, oppure un `AttoTrovato`
                uscito da una ricerca. Il comma viene rimosso automaticamente,
                perché il servizio lo rifiuta in ingresso.
            vigenza: il giorno a cui leggere il testo, `"originale"` per la
                prima pubblicazione, `None` per il testo di oggi.
            se_troncato: `"segnala"` registra il sospetto nella proprietà
                `possibile_troncamento`, `"solleva"` lo trasforma in eccezione.

        Returns:
            Il testo richiesto, con la finestra di vigenza in cui è valido.

        Examples:
            Il testo dell'articolo 19 della legge 241 com'era nel 2000, con la
            finestra in cui quel testo è stato in vigore::

                atto = normattiva.dettaglio(
                    "urn:nir:stato:legge:1990-08-07;241~art19",
                    vigenza=date(2000, 1, 1),
                )
                print(atto.finestra)  # 1994-01-01 → 2005-03-07

        Raises:
            NotFoundError: nessun atto risponde a quelle coordinate.
            AmbiguityError: l'URN corrisponde a più atti pubblicati; i
                candidati sono elencati nell'eccezione.
            NotYetInForceError: l'articolo non esisteva alla data
                richiesta.
            ValidityMismatchError: il servizio ha risposto con una versione che
                non copre la data richiesta.
            TruncationError: solo con `se_troncato="solleva"`, e solo se
                il testo sembra tagliato.
            InvalidUrnError: l'URN è malformato, oppure la forma URN di quel
                tipo di atto non è verificata.
            InvalidArgumentError: la vigenza è indicata due volte, oppure è
                chiesta per un atto raggiungibile solo dalle coordinate di
                Gazzetta.
        """
        _verifica_se_troncato(se_troncato)
        if isinstance(atto, AttoTrovato) and not atto.ha_urn:
            _verifica_senza_vigenza(atto, vigenza)
            codice, giorno = _coordinate_di_gazzetta(atto)
            return await self.dettaglio_da_gazzetta(codice, giorno, se_troncato=se_troncato)
        urn = atto.urn if isinstance(atto, AttoTrovato) else atto
        risposta = await self._trasporto.post(
            "atto/dettaglio-atto-urn", {"urn": str(_urn_con_vigenza(urn, vigenza))}
        )
        return _controlla_dettaglio(_wire.leggi_dettaglio(risposta.json()), vigenza, se_troncato)

    async def dettaglio_da_gazzetta(
        self,
        codice_redazionale: str,
        data: date,
        *,
        se_troncato: SeTroncato = "segnala",
    ) -> DettaglioAtto:
        """Legge un atto a partire dalle sue coordinate di Gazzetta.

        È il percorso per gli atti la cui forma URN non è verificata: il codice
        redazionale e la data di Gazzetta arrivano da una ricerca, e il servizio
        risponde anche per un decreto-legge luogotenenziale del 1917. Questo
        percorso però non supporta la multivigenza: restituisce sempre il testo
        vigente oggi, e per una data serve un URN.

        Args:
            codice_redazionale: l'identificativo di Gazzetta dell'atto, come
                arriva da `AttoTrovato.gazzetta.codice_redazionale`.
            data: la data di pubblicazione in Gazzetta.
            se_troncato: come per `dettaglio`.

        Returns:
            Il testo dell'atto, sempre nella versione vigente oggi.

        Raises:
            NotFoundError: nessun atto per quelle coordinate di Gazzetta.
            InvalidArgumentError: il codice redazionale è vuoto.
        """
        _verifica_se_troncato(se_troncato)
        risposta = await self._trasporto.post(
            "atto/dettaglio-atto", _corpo_gazzetta(codice_redazionale, data)
        )
        return _controlla_dettaglio(_wire.leggi_dettaglio(risposta.json()), None, se_troncato)

    async def cronologia(
        self, urn: Urn | str, *, massimo: int | None = None
    ) -> AsyncIterator[DettaglioAtto]:
        """Percorre tutte le versioni di un articolo, dall'originale a quella in vigore.

        Costa una richiesta per versione: le finestre di vigenza sono contigue,
        quindi ogni versione viene chiesta al giorno successivo alla fine della
        precedente. Con `massimo` l'iterazione si ferma dopo quel numero di
        versioni; senza, arriva all'ultima. Senza `massimo` la catena si ferma
        comunque dopo cinquecento passi: nessun articolo italiano ha
        cinquecento versioni, quindi una catena così lunga indica finestre non
        contigue.

        Args:
            urn: l'articolo di cui percorrere le versioni.
            massimo: quante versioni al più produrre. Senza, si arriva in fondo.

        Yields:
            Una versione per volta, dalla più vecchia alla più recente.

        Raises:
            UnexpectedResponseError: la catena non si chiude entro cinquecento
                passi, cioè le finestre di vigenza non sono contigue.
        """
        base = Urn.parse(urn).senza_comma
        prossima: Vigenza = "originale"
        prodotte = 0
        while massimo is None or prodotte < massimo:
            if massimo is None and prodotte >= PASSI_MASSIMI:
                raise UnexpectedResponseError(
                    f"la catena delle versioni non si chiude dopo {PASSI_MASSIMI} passi: "
                    "le finestre di vigenza non sono contigue"
                )
            atto = await self.dettaglio(base.con_vigenza(prossima))
            yield atto
            prodotte += 1
            chiusura = atto.finestra.fine if atto.finestra else None
            if chiusura is None:
                return
            prossima = chiusura + timedelta(days=1)

    async def ricerca(
        self,
        testo: str,
        *,
        pagina: int = 1,
        per_pagina: int = 20,
        sort: Sort | str = Sort.NEWEST,
        tipo: str | None = None,
        anno: int | None = None,
        emettitore: str | None = None,
    ) -> EsitoRicerca:
        """Cerca nel testo pieno del corpus.

        Le parole vengono combinate in AND dal servizio; non c'è modo di
        chiedere un OR. `tipo`, `anno` ed `emettitore` sono le faccette che la
        risposta stessa propone, non le coordinate dell'atto: per quelle c'è
        `ricerca_avanzata`.

        Args:
            testo: le parole da cercare, combinate in AND dal servizio.
            pagina: quale pagina di risultati, a partire da 1.
            per_pagina: quanti risultati per pagina.
            sort: `"newest"` dal più recente, `"oldest"` dal più vecchio.
            tipo: codice della faccetta per tipo di atto, come `"PLE"`.
            anno: faccetta per anno di provvedimento.
            emettitore: faccetta per amministrazione emanante.

        Returns:
            Una pagina di risultati, con il totale e le faccette per restringere.
        """
        corpo = _corpo_ricerca(
            testo,
            pagina=pagina,
            per_pagina=per_pagina,
            sort=sort,
            tipo=tipo,
            anno=anno,
            emettitore=emettitore,
        )
        risposta = await self._trasporto.post("ricerca/semplice", corpo)
        return _wire.leggi_ricerca(risposta.json())

    async def ricerca_avanzata(
        self,
        *,
        denominazione: str | None = None,
        anno: int | None = None,
        numero: int | str | None = None,
        giorno: int | None = None,
        mese: int | None = None,
        titolo: str | None = None,
        testo: str | None = None,
        vigente_al: date | None = None,
        classe: ClasseProvvedimento | int | None = None,
        emanazione: Intervallo | None = None,
        pubblicazione: Intervallo | None = None,
        sort: Sort | str = Sort.NEWEST,
        tipo: str | None = None,
        emettitore: str | None = None,
        pagina: int = 1,
        per_pagina: int = 20,
    ) -> EsitoRicerca:
        """Cerca per coordinate invece che per parole.

        Senza nessuna coordinata il servizio risponde con l'intero corpus: è
        una richiesta ammessa, e la libreria non la rifiuta.

        Args:
            denominazione: il tipo di atto come lo scrive il dizionario, per
                esempio `"LEGGE"` o `"DECRETO LEGISLATIVO"`.
            anno: anno di emanazione.
            numero: numero del provvedimento.
            giorno: giorno di emanazione.
            mese: mese di emanazione.
            titolo: parole da cercare nel titolo.
            testo: parole da cercare nel testo.
            vigente_al: tiene solo gli atti in vigore in quel giorno.
            classe: la classe redazionale dell'atto (senza aggiornamenti,
                aggiornato, abrogato).
            emanazione: intervallo di emanazione, come coppia `(dal, al)`. Un
                estremo può essere `None` per lasciare la finestra aperta.
            pubblicazione: intervallo di pubblicazione in Gazzetta, come sopra.
            sort: `"newest"` dal più recente, `"oldest"` dal più vecchio.
            tipo: faccetta per tipo di atto.
            emettitore: faccetta per amministrazione emanante.
            pagina: quale pagina di risultati, a partire da 1.
            per_pagina: quanti risultati per pagina.

        Returns:
            Una pagina di risultati, nella stessa forma che rende `ricerca`.
        """
        corpo = _corpo_avanzata(
            _coordinate(
                denominazione,
                anno,
                numero,
                giorno,
                mese,
                titolo,
                testo,
                vigente_al,
                classe,
                emanazione,
                pubblicazione,
            ),
            sort,
            pagina,
            per_pagina,
            tipo,
            emettitore,
        )
        risposta = await self._trasporto.post("ricerca/avanzata", corpo)
        return _wire.leggi_ricerca(risposta.json())

    async def ricerca_completa(
        self,
        testo: str,
        *,
        massimo: int | None = None,
        per_pagina: int = 50,
        sort: Sort | str = Sort.NEWEST,
        tipo: str | None = None,
        anno: int | None = None,
        emettitore: str | None = None,
    ) -> AsyncIterator[AttoTrovato]:
        """Scorre tutti gli atti che una ricerca trova, una pagina per volta.

        L'iteratore è pigro: ogni pagina viene chiesta solo quando serve,
        quindi consumare dieci risultati costa una richiesta sola. Con
        `massimo` ci si ferma dopo quel numero di atti; per sapere quanti ce
        n'erano in tutto basta una `ricerca` e il suo `totale`.

        Quel `totale` è anche la condizione di uscita: il numero di pagina
        restituito dal servizio non è affidabile, e usarlo come condizione
        potrebbe rileggere la prima pagina all'infinito.

        Args:
            testo: le parole da cercare.
            massimo: quanti atti al più produrre. Senza, si arriva in fondo.
            per_pagina: quanti risultati chiedere per richiesta.
            sort: `"newest"` dal più recente, `"oldest"` dal più vecchio.
            tipo: faccetta per tipo di atto.
            anno: faccetta per anno di provvedimento.
            emettitore: faccetta per amministrazione emanante.

        Yields:
            Un atto per volta, nell'ordine in cui il servizio li rende.
        """
        if massimo is not None and massimo <= 0:
            return
        prodotti = 0
        pagina = 1
        dichiarati: int | None = None
        quanti_per_pagina = per_pagina if massimo is None else min(per_pagina, massimo)
        while True:
            esito = await self.ricerca(
                testo,
                pagina=pagina,
                per_pagina=quanti_per_pagina,
                sort=sort,
                tipo=tipo,
                anno=anno,
                emettitore=emettitore,
            )
            if dichiarati is None:
                dichiarati = esito.totale
            for atto in esito.atti:
                yield atto
                prodotti += 1
                if massimo is not None and prodotti >= massimo:
                    return
            if not esito.atti or prodotti >= dichiarati or pagina >= PAGINE_MASSIME:
                return
            pagina += 1

    async def atti_aggiornati(self, dal: date, al: date) -> AsyncIterator[AttoTrovato]:
        """Elenca gli atti modificati fra due date.

        Il flusso contiene solo le modifiche: un atto pubblicato dentro la
        finestra ma mai modificato dopo non compare. Le finestre più lunghe di
        un anno vengono spezzate, perché il servizio le rifiuta.

        Args:
            dal: primo giorno della finestra, compreso.
            al: ultimo giorno della finestra, compreso.

        Yields:
            Un atto modificato per volta, finestra dopo finestra.

        Raises:
            RuleViolationError: `al` precede `dal`. Sollevata prima di toccare
                la rete, col codice `RuleCode.DATE_INVERTITE`.
        """
        _verifica_intervallo(dal, al)
        for inizio, fine in _intervalli(dal, al):
            risposta = await self._trasporto.post(
                "ricerca/aggiornati", _corpo_aggiornati(inizio, fine)
            )
            for atto in _wire.leggi_ricerca(risposta.json()).atti:
                yield atto

    async def _dizionario(
        self,
        chiave: str,
        percorso: str,
        lettore: Callable[[Any], tuple[Tipologica, ...]],
        reload: bool,
    ) -> tuple[Tipologica, ...]:
        if reload or chiave not in self._dizionari:
            risposta = await self._trasporto.get(percorso)
            self._dizionari[chiave] = lettore(risposta.json())
        return self._dizionari[chiave]

    async def denominazioni(self, *, reload: bool = False) -> tuple[Tipologica, ...]:
        """Elenca i tipi di atto che il corpus contiene, e tiene il risultato in memoria."""
        return await self._dizionario(
            "denominazioni", "tipologiche/denominazione-atto", _wire.leggi_denominazioni, reload
        )

    async def classi_provvedimento(self, *, reload: bool = False) -> tuple[Tipologica, ...]:
        """Elenca le classi redazionali a cui un atto può appartenere."""
        return await self._dizionario(
            "classi", "tipologiche/classe-provvedimento", _wire.leggi_classi, reload
        )

    async def export_formats(self, *, reload: bool = False) -> tuple[Tipologica, ...]:
        """Elenca i formati in cui si può chiedere un'esportazione."""
        return await self._dizionario(
            "estensioni", "tipologiche/estensioni", _wire.leggi_estensioni, reload
        )

    async def ricerche_predefinite(self) -> tuple[RicercaPredefinita, ...]:
        """Elenca le ricerche predefinite che il servizio propone."""
        risposta = await self._trasporto.get("ricerca/predefinita")
        return _wire.leggi_ricerche_predefinite(risposta.json())

    async def collections(self) -> tuple[Collection, ...]:
        """Elenca gli archivi già confezionati che il servizio mette a disposizione."""
        risposta = await self._trasporto.get("collections/collection-predefinite")
        return _wire.leggi_collezioni(risposta.json())

    async def _archivio_collezione(
        self, name: str, format: Format | str, mode: ExportMode | str
    ) -> bytes:
        risposta = await self._trasporto.get(
            "collections/download/collection-preconfezionata",
            parametri=_parametri_collezione(name, format, mode),
            segui_redirect=True,
        )
        return risposta.contenuto

    async def download_collection(
        self,
        name: str,
        *,
        format: Format | str = Format.JSON,
        mode: ExportMode | str = ExportMode.VIGENTE,
    ) -> Corpus:
        """Scarica un archivio già confezionato e legge gli atti che contiene.

        Raises:
            InvalidArgumentError: il formato chiesto non viene letto in
                modelli; usare `save_collection` per averlo come file.
        """
        _verifica_leggibile(Format(format), "save_collection()")
        return Corpus.from_data(await self._archivio_collezione(name, format, mode))

    async def save_collection(
        self,
        name: str,
        path: str | Path,
        *,
        format: Format | str = Format.JSON,
        mode: ExportMode | str = ExportMode.VIGENTE,
    ) -> Path:
        """Scarica su disco un archivio già confezionato, in qualunque formato sia."""
        destinazione = Path(path)
        destinazione.write_bytes(await self._archivio_collezione(name, format, mode))
        return destinazione

    async def start_export(
        self,
        *,
        format: Format | str = Format.JSON,
        mode: ExportMode | str = ExportMode.MULTIVIGENTE,
        massimo_atti: int | None = 100,
        escludi_testo: str | None = None,
        escludi_titolo: str | None = None,
        denominazione: str | None = None,
        anno: int | None = None,
        numero: int | str | None = None,
        giorno: int | None = None,
        mese: int | None = None,
        titolo: str | None = None,
        testo: str | None = None,
        vigente_al: date | None = None,
        classe: ClasseProvvedimento | int | None = None,
        emanazione: Intervallo | None = None,
        pubblicazione: Intervallo | None = None,
    ) -> AsyncExport:
        """Chiede l'esportazione completa degli atti che una ricerca trova.

        Le coordinate sono le stesse di `ricerca_avanzata`. Prima di avviare
        l'esportazione gli atti vengono contati con una ricerca sincrona,
        perché un'esportazione costa minuti di lavoro al servizio e, una volta
        partita, non si annulla. Con `massimo_atti=None` si parte senza
        conteggio.

        `escludi_testo` ed `escludi_titolo` escludono dal risultato gli atti
        che contengono quelle parole, e sono l'unico filtro che l'esportazione
        supporta e la ricerca no: il conteggio preventivo non ne tiene conto,
        quindi può contare più atti di quanti ne arriveranno.

        Args:
            format: in che formato produrre l'archivio. Solo `JSON` viene poi
                letto in modelli.
            mode: quante versioni includere nell'archivio.
            massimo_atti: il tetto oltre il quale l'esportazione non parte.
                `None` la avvia senza conteggio preventivo.
            escludi_testo: esclude gli atti che contengono questa parola.
            escludi_titolo: esclude gli atti il cui titolo la contiene.
            denominazione: come in `ricerca_avanzata`, e così tutti i criteri
                che seguono.
            anno: anno di emanazione.
            numero: numero del provvedimento.
            giorno: giorno di emanazione.
            mese: mese di emanazione.
            titolo: parole da cercare nel titolo.
            testo: parole da cercare nel testo.
            vigente_al: tiene solo gli atti in vigore in quel giorno.
            classe: la classe redazionale dell'atto (senza aggiornamenti,
                aggiornato, abrogato).
            emanazione: intervallo di emanazione, come coppia `(dal, al)`.
            pubblicazione: intervallo di pubblicazione in Gazzetta.

        Returns:
            L'esportazione appena avviata, da attendere e poi scaricare.

        Raises:
            TooManyResultsError: i criteri selezionano più atti di
                `massimo_atti`. L'esportazione non viene avviata.
            ConnectionError: il conteggio preventivo non è riuscito. Il
                messaggio indica come procedere senza.
        """
        coordinate = _coordinate(
            denominazione,
            anno,
            numero,
            giorno,
            mese,
            titolo,
            testo,
            vigente_al,
            classe,
            emanazione,
            pubblicazione,
        )
        corpo = _corpo_export(
            coordinate,
            format,
            mode,
            {"testoNot": escludi_testo, "titoloNot": escludi_titolo},
        )
        if massimo_atti is not None:
            try:
                esito = await self.ricerca_avanzata(**coordinate, per_pagina=1)
            except (ConnectionError, UnexpectedResponseError) as errore:
                raise _conteggio_non_riuscito(errore) from errore
            if esito.totale > massimo_atti:
                raise TooManyResultsError(esito.totale, massimo_atti)
        risposta = await self._trasporto.post(
            "ricerca-asincrona/nuova-ricerca", corpo, attesi=(200, 202)
        )
        token = risposta.testo
        await self._trasporto.put(
            "ricerca-asincrona/conferma-ricerca", {"token": token}, attesi=(200, 202, 204)
        )
        return AsyncExport(
            token,
            self._trasporto,
            format=Format(format),
            sleep=self._sleep,
            clock=self._clock,
        )

    async def export_from_token(
        self, token: str, *, format: Format | str = Format.JSON
    ) -> AsyncExport:
        """Riprende un'esportazione già in corso, dal suo token."""
        return await AsyncExport.from_token(token, self._trasporto, format=Format(format))


__all__ = ["AsyncNormattiva", "Normattiva"]
