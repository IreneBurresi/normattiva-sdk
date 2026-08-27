"""Il parsing delle risposte grezze del servizio, concentrato in un solo modulo.

Le date arrivano in quattro forme, le assenze in tre, gli errori in cinque, e un
404 può presentarsi come un successo. Ogni risposta del servizio diventa qui un
modello o un'eccezione, così nessun altro modulo maneggia dizionari grezzi.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta
from typing import Any

from normattiva.errori import (
    TRANSIENT_CODES,
    AmbiguityError,
    ConnectionError,
    NotFoundError,
    NotYetInForceError,
    OverloadedError,
    RequestBlockedError,
    RuleCode,
    RuleViolationError,
    UnexpectedResponseError,
)
from normattiva.modelli import (
    Aggiornamento,
    AttoStorico,
    AttoTrovato,
    Collection,
    DettaglioAtto,
    EsitoRicerca,
    EstremiAtto,
    Evidenziazione,
    Faccetta,
    Faccette,
    FinestraVigenza,
    Partizione,
    PubblicazioneGazzetta,
    RicercaPredefinita,
    RiferimentoAggiornamento,
    Tipologica,
    VersioneAtto,
)
from normattiva.urn import Urn

APERTA = "99999999"
ASSENTI = frozenset({"", "0", APERTA, "null", "none"})
_COMPATTA = re.compile(r"^\d{8}$")
_ITALIANA = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_SPAZI = re.compile(r"\s+")
_VERSIONE_FILE = re.compile(r"_(?:VIGENZA_(\d{4}-\d{2}-\d{2})|ORIGINALE)_V(\d+)\.json$", re.I)


def leggi_data(grezza: object) -> date | None:
    """Legge una data in una qualsiasi delle forme che il servizio usa, o None se manca."""
    if grezza is None:
        return None
    testo = str(grezza).strip()
    if testo.lower() in ASSENTI:
        return None
    try:
        if _COMPATTA.match(testo):
            return date(int(testo[:4]), int(testo[4:6]), int(testo[6:]))
        italiana = _ITALIANA.match(testo)
        if italiana:
            giorno, mese, anno = italiana.groups()
            return date(int(anno), int(mese), int(giorno))
        return datetime.fromisoformat(testo.replace("Z", "+00:00")).date()
    except ValueError as errore:
        raise UnexpectedResponseError(f"data non interpretabile: {grezza!r}") from errore


def leggi_finestra(inizio: object, fine: object) -> FinestraVigenza | None:
    """Legge una finestra di vigenza.

    Un inizio assente insieme a una fine valorizzata non è una finestra: indica
    che l'articolo non era ancora vigente, e la fine è il giorno prima della sua
    entrata in vigore. Un inizio assente insieme a una fine aperta è solo un
    inizio non dichiarato.
    """
    apertura = leggi_data(inizio)
    chiusura = leggi_data(fine)
    if apertura is None:
        if chiusura is None:
            return None
        raise NotYetInForceError(chiusura + timedelta(days=1))
    return FinestraVigenza(apertura, chiusura)


def _testo(grezzo: object) -> str | None:
    """Il testo di un campo, con gli spazi normalizzati e le quadre esterne rimosse.

    Viene tolta solo una coppia bilanciata all'esterno: `strip("[]")` toglierebbe
    anche la quadra di chiusura di «Art. 5 [1]», che nel testo redazionale ha un
    significato.
    """
    if grezzo is None:
        return None
    ripulito = _SPAZI.sub(" ", str(grezzo)).strip()
    if len(ripulito) > 1 and ripulito.startswith("[") and ripulito.endswith("]"):
        ripulito = ripulito[1:-1].strip()
    return ripulito or None


def _intero(grezzo: object) -> int | None:
    if grezzo is None or grezzo == "":
        return None
    testo = str(grezzo).strip()
    try:
        return int(testo) if "." not in testo else int(float(testo))
    except ValueError as errore:
        raise UnexpectedResponseError(f"numero non interpretabile: {grezzo!r}") from errore


def _dati(payload: Mapping[str, Any], *chiavi: str) -> Any:
    """Scende nella risposta lungo le chiavi, e restituisce None dove il ramo manca.

    Un nodo assente non è una risposta malformata: la maggioranza degli atti non
    ha allegati, e in quel caso il servizio omette il ramo.
    """
    corrente: Any = payload
    for chiave in chiavi:
        if corrente is None:
            return None
        if not isinstance(corrente, Mapping):
            raise UnexpectedResponseError(f"il nodo {chiave!r} non ha la forma attesa")
        corrente = corrente.get(chiave)
    return corrente


def _giorno(nodo: Mapping[str, Any], anno: str, mese: str, giorno: str) -> date:
    numeri = [_intero(nodo.get(campo)) for campo in (anno, mese, giorno)]
    if any(numero is None for numero in numeri):
        raise UnexpectedResponseError(f"data incompleta nei campi {anno}/{mese}/{giorno}")
    quando_anno, quando_mese, quando_giorno = numeri
    try:
        return date(int(quando_anno or 0), int(quando_mese or 0), int(quando_giorno or 0))
    except ValueError as errore:
        raise UnexpectedResponseError(
            f"data inesistente nei campi {anno}/{mese}/{giorno}"
        ) from errore


def _giorno_dichiarato(nodo: Mapping[str, Any], anno: str, mese: str, giorno: str) -> date | None:
    """La stessa data di `_giorno`, ma None quando il servizio non la dichiara.

    Alcuni atti portano degli zeri al posto delle coordinate di data, e uno
    zero è un'assenza, non una data: la Costituzione, per esempio, è datata solo
    dalla sua pubblicazione.
    """
    numeri = [_intero(nodo.get(campo)) for campo in (anno, mese, giorno)]
    if any(not numero for numero in numeri):
        return None
    return _giorno(nodo, anno, mese, giorno)


def _numero_dichiarato(grezzo: object) -> str | None:
    numero = _testo(grezzo)
    return None if numero in (None, "0") else numero


def _supplemento(nodo: Mapping[str, Any], campo: str) -> tuple[str | None, int | None]:
    """Il supplemento di Gazzetta, quando l'atto ne ha uno.

    Il codice `NO` indica l'assenza di supplemento, e in quel caso il numero che
    lo accompagna vale zero. I due percorsi usano nomi diversi per il campo,
    `tipoSupplementoCode` nel dettaglio e `tipoSupplemento` nella ricerca: è
    l'unica ragione per cui questa funzione prende il nome del campo.
    """
    codice = _testo(nodo.get(campo))
    if codice is None or codice.upper() == "NO":
        return None, None
    return codice, _intero(nodo.get("numeroSupplemento")) or None


def _atto_da_dettaglio(nodo: Mapping[str, Any]) -> DettaglioAtto:
    denominazione = _testo(nodo.get("tipoProvvedimentoDescrizione"))
    if denominazione is None:
        raise UnexpectedResponseError("l'atto non dichiara la propria denominazione")
    supplemento, numero_supplemento = _supplemento(nodo, "tipoSupplementoCode")
    pubblicazione = _giorno(nodo, "annoGU", "meseGU", "giornoGU")
    emanazione = _giorno_dichiarato(
        nodo, "annoProvvedimento", "meseProvvedimento", "giornoProvvedimento"
    )
    return DettaglioAtto(
        estremi=EstremiAtto(
            denominazione=denominazione,
            data=emanazione or pubblicazione,
            numero=_numero_dichiarato(nodo.get("numeroProvvedimento")),
            codice_tipo=_testo(nodo.get("tipoProvvedimentoCodice")),
        ),
        gazzetta=PubblicazioneGazzetta(
            data=pubblicazione,
            numero=_intero(nodo.get("numeroGU")) or None,
            codice_redazionale=_testo(nodo.get("codiceRedazionale")),
            supplemento=supplemento,
            numero_supplemento=numero_supplemento,
        ),
        titolo=_testo(nodo.get("titolo")) or "",
        sottotitolo=_testo(nodo.get("sottoTitolo")),
        testo_html=nodo.get("articoloHtml") or "",
        finestra=leggi_finestra(
            nodo.get("articoloDataInizioVigenza"), nodo.get("articoloDataFineVigenza")
        ),
    )


def leggi_dettaglio(payload: Mapping[str, Any]) -> DettaglioAtto:
    """Legge una risposta di dettaglio-atto-urn, ambiguità e assenze comprese."""
    if not isinstance(payload, Mapping) or "data" not in payload:
        raise UnexpectedResponseError("la risposta non ha la forma attesa")
    dati = _dati(payload, "data")
    if not isinstance(dati, Mapping):
        raise UnexpectedResponseError("la risposta non porta alcun dato")
    candidati = dati.get("lista")
    if candidati:
        raise AmbiguityError(tuple(_atto_da_dettaglio(c) for c in candidati))
    atto = dati.get("atto")
    if not atto:
        raise NotFoundError(_testo(dati.get("message")) or "nessun atto per la richiesta")
    return _atto_da_dettaglio(atto)


def _evidenziazioni(nodo: Mapping[str, Any]) -> tuple[Evidenziazione, ...]:
    grezze = nodo.get("hlArticoli") or ()
    return tuple(
        Evidenziazione(
            articolo=_testo(e.get("descNumArticolo") or e.get("numArticolo")),
            frammenti=tuple(e.get("fragments") or ()),
        )
        for e in grezze
    )


def _atto_trovato(nodo: Mapping[str, Any]) -> AttoTrovato:
    denominazione = _testo(nodo.get("denominazioneAtto"))
    if denominazione is None:
        raise UnexpectedResponseError("il risultato non dichiara la denominazione dell'atto")
    modificanti = _testo(nodo.get("ultimiAttiModificanti")) or ""  # codici redazionali spaziati
    numero_gu = _intero(nodo.get("numeroGU"))
    supplemento, numero_supplemento = _supplemento(nodo, "tipoSupplemento")
    pubblicazione = leggi_data(nodo.get("dataGU")) or leggi_data(nodo.get("dataEmanazione"))
    emanazione = _giorno_dichiarato(
        nodo, "annoProvvedimento", "meseProvvedimento", "giornoProvvedimento"
    ) or leggi_data(nodo.get("dataEmanazione"))
    quando = emanazione or pubblicazione
    if quando is None:
        raise UnexpectedResponseError("il risultato non porta alcuna data")
    return AttoTrovato(
        estremi=EstremiAtto(
            denominazione=denominazione,
            data=quando,
            numero=_numero_dichiarato(
                nodo.get("numeroAttoAlfanumerico") or nodo.get("numeroProvvedimento")
            ),
        ),
        gazzetta=PubblicazioneGazzetta(
            data=pubblicazione or quando,
            numero=numero_gu,
            codice_redazionale=_testo(nodo.get("codiceRedazionale")),
            supplemento=supplemento,
            numero_supplemento=numero_supplemento,
        ),
        titolo=_testo(nodo.get("titoloAtto")) or "",
        descrizione=_testo(nodo.get("descrizioneAtto")),
        ultima_modifica=leggi_data(nodo.get("dataUltimaModifica")),
        atti_modificanti=tuple(modificanti.split()),
        evidenziazioni=_evidenziazioni(nodo),
    )


def _faccetta(nodo: Mapping[str, Any]) -> Faccetta:
    return Faccetta(
        codice=_testo(nodo.get("codice")) or "",
        conteggio=_intero(nodo.get("valore")) or 0,
        descrizione=_testo(nodo.get("descrizione")),
    )


def leggi_ricerca(payload: Mapping[str, Any]) -> EsitoRicerca:
    """Legge una qualsiasi delle tre risposte di ricerca: hanno tutte la stessa forma."""
    if not isinstance(payload, Mapping):
        raise UnexpectedResponseError("la risposta di ricerca non ha la forma attesa")
    faccette = payload.get("facetMap") or {}
    return EsitoRicerca(
        atti=tuple(_atto_trovato(a) for a in payload.get("listaAtti") or ()),
        totale=_intero(payload.get("numeroAttiTrovati")) or 0,
        pagina=_intero(payload.get("paginaCorrente")) or 1,
        pagine=_intero(payload.get("numeroPagine")) or 1,
        faccette=Faccette(
            per_anno=tuple(_faccetta(f) for f in faccette.get("anno_provvedimento") or ()),
            per_tipo=tuple(_faccetta(f) for f in faccette.get("codice_tipo_provvedimento") or ()),
            per_emettitore=tuple(
                _faccetta(f) for f in faccette.get("descrizione_emettitore") or ()
            ),
        ),
    )


def _tipologiche(
    voci: Iterable[Mapping[str, Any]], *, codice: str, descrizione: str
) -> tuple[Tipologica, ...]:
    return tuple(
        Tipologica(
            codice=_testo(v.get(codice)) or "",
            descrizione=_testo(v.get(descrizione)) or "",
        )
        for v in voci
    )


def leggi_denominazioni(payload: Iterable[Mapping[str, Any]]) -> tuple[Tipologica, ...]:
    """Legge il dizionario dei tipi di atto."""
    return _tipologiche(payload, codice="label", descrizione="value")


def leggi_classi(payload: Iterable[Mapping[str, Any]]) -> tuple[Tipologica, ...]:
    """Legge il dizionario delle classi di provvedimento."""
    return _tipologiche(payload, codice="label", descrizione="value")


def leggi_estensioni(payload: Iterable[Mapping[str, Any]]) -> tuple[Tipologica, ...]:
    """Legge il dizionario dei formati di esportazione."""
    return _tipologiche(payload, codice="label", descrizione="value")


def leggi_collezioni(payload: Iterable[Mapping[str, Any]]) -> tuple[Collection, ...]:
    """Legge il catalogo degli archivi già confezionati."""
    return tuple(
        Collection(
            name=_testo(c.get("nomeCollezione")) or "",
            format=_testo(c.get("formatoCollezione")) or "",
            total_atti=_intero(c.get("numeroAtti")) or 0,
            description=_testo(c.get("descrizioneFormatoCollezione")),
            created_at=leggi_data(c.get("dataCreazione")),
        )
        for c in payload
    )


def leggi_ricerche_predefinite(
    payload: Mapping[str, Any],
) -> tuple[RicercaPredefinita, ...]:
    """Legge le ricerche predefinite che il servizio propone."""
    grezze = payload.get("ricerchePredefinite") if isinstance(payload, Mapping) else None
    return tuple(
        RicercaPredefinita(
            nome=_testo(r.get("nome")) or "",
            parametri=tuple(
                (_testo(d.get("nomeCampo")) or "", _testo(d.get("valoreCampo")) or "")
                for d in r.get("dettagli") or ()
            ),
        )
        for r in grezze or ()
    )


def _finestre(nodo: Mapping[str, Any]) -> tuple[FinestraVigenza, ...]:
    finestre = []
    for periodo in nodo.get("dataVigoreVersione") or ():
        inizio = leggi_data(periodo.get("inizioVigore"))
        if inizio is None:
            continue
        finestre.append(FinestraVigenza(inizio, leggi_data(periodo.get("fineVigore"))))
    return tuple(finestre)


def _partizione(nodo: Mapping[str, Any]) -> Partizione:
    return Partizione(
        tipo=_testo(nodo.get("nomeNir")),
        numero=_testo(nodo.get("numNir")) or "",
        testo=str(nodo.get("testo") or "").strip(),
        rubrica=_testo(nodo.get("rubricaNir")),
        finestre=_finestre(nodo),
        figli=tuple(_partizione(f) for f in nodo.get("elementi") or ()),
    )


def _aggiornamenti(metadati: Mapping[str, Any]) -> tuple[Aggiornamento, ...]:
    aggiornamenti = []
    for grezzo in metadati.get("aggiornamentiAtto") or ():
        quando = leggi_data(grezzo.get("data"))
        if quando is None:
            continue
        riferimenti = []
        for modifica in grezzo.get("urnModifiche") or ():
            articolo = modifica.get("articoloAggiornante") or {}
            quando_gu = leggi_data(articolo.get("dataPubblicazioneGazzetta"))
            if quando_gu is None:
                continue
            riferimenti.append(
                RiferimentoAggiornamento(
                    gazzetta=PubblicazioneGazzetta(
                        data=quando_gu,
                        codice_redazionale=_testo(articolo.get("codiceRedazionale")),
                    ),
                    articolo=_testo(articolo.get("idNir")),
                )
            )
        aggiornamenti.append(
            Aggiornamento(
                data=quando,
                testo=_testo(grezzo.get("testo")) or "",
                riferimenti=tuple(riferimenti),
            )
        )
    return tuple(aggiornamenti)


def _versione(documento: Mapping[str, Any], nome: str) -> VersioneAtto:
    """Una versione dell'atto, datata dal nome del file che la contiene.

    La data di vigenza non è nel documento: compare solo nel nome del file,
    nella forma `..._VIGENZA_2005-01-01_V3.json`. Un nome che non la dichiara
    non viene letto come «versione originale», perché sarebbe indistinguibile
    da un cambio di convenzione: ogni versione risulterebbe l'originale, e
    `alla_data` restituirebbe il testo di partenza per qualunque data, senza
    alcun segnale di errore.
    """
    pezzi = _VERSIONE_FILE.search(nome)
    if pezzi is None:
        raise UnexpectedResponseError(
            f"il nome {nome!r} non dichiara la versione: l'archivio non segue più la "
            "convenzione da cui si legge la data di vigenza"
        )
    return VersioneAtto(
        vigente_dal=leggi_data(pezzi.group(1)) if pezzi.group(1) else None,
        articolato=tuple(_partizione(n) for n in _dati(documento, "articolato", "elementi") or ()),
        annessi=tuple(_partizione(n) for n in _dati(documento, "annessi", "elementi") or ()),
    )


def _atto_storico(documenti: list[tuple[str, Mapping[str, Any]]]) -> AttoStorico:
    documenti.sort(
        key=lambda coppia: ((m := _VERSIONE_FILE.search(coppia[0])) and int(m.group(2))) or 0
    )
    ultimo = documenti[-1][1]
    metadati = ultimo.get("metadati") or {}
    denominazione = _testo(metadati.get("tipoDoc"))
    emanazione = leggi_data(metadati.get("dataDoc"))
    if denominazione is None or emanazione is None:
        raise UnexpectedResponseError("l'atto esportato non dichiara tipo e data")
    pubblicazione = leggi_data(metadati.get("dataPubblicazione"))
    urn = _testo(metadati.get("urn"))
    return AttoStorico(
        urn=Urn.parse(urn) if urn else EstremiAtto(denominazione, emanazione).urn,
        estremi=EstremiAtto(
            denominazione=denominazione,
            data=emanazione,
            numero=_testo(metadati.get("numDoc")),
        ),
        versioni=tuple(_versione(documento, nome) for nome, documento in documenti),
        eli=_testo(metadati.get("eli")),
        gazzetta=(
            PubblicazioneGazzetta(
                data=pubblicazione,
                numero=_intero(metadati.get("numeroPubblicazione")) or None,
                codice_redazionale=_testo(metadati.get("redazione")),
            )
            if pubblicazione
            else None
        ),
        abrogato=str(metadati.get("abrogato") or "no").strip().lower() in ("si", "sì", "true"),
        aggiornamenti=_aggiornamenti(metadati),
    )


def leggi_corpus(archivio: bytes) -> tuple[AttoStorico, ...]:
    """Legge un archivio di esportazione: un atto per ogni cartella che contiene."""
    if not archivio:
        raise UnexpectedResponseError("il servizio ha restituito un archivio vuoto")
    try:
        zip_export = zipfile.ZipFile(io.BytesIO(archivio))
        nomi = [n for n in zip_export.namelist() if n.lower().endswith(".json")]
        per_atto: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
        for nome in nomi:
            per_atto.setdefault(nome.rsplit("/", 1)[0], []).append(
                (nome, json.loads(zip_export.read(nome)))
            )
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError) as errore:
        raise UnexpectedResponseError("l'archivio scaricato non è leggibile") from errore
    return tuple(_atto_storico(documenti) for documenti in per_atto.values())


def _corpo(contenuto: bytes) -> Mapping[str, Any] | None:
    try:
        letto = json.loads(contenuto)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return letto if isinstance(letto, Mapping) else None


def _codice(grezzo: object) -> int | None:
    """Il codice di errore, se è un numero; None se manca o non è interpretabile."""
    if grezzo is None or grezzo == "":
        return None
    try:
        return int(str(grezzo).strip())
    except ValueError:
        return None


def regola_nota(contenuto: bytes) -> RuleCode | None:
    """La regola permanente che un corpo di errore invoca, se ne invoca una.

    Contano solo i codici che questa libreria conosce come permanenti:
    descrivono la richiesta, e ripeterla non cambierebbe l'esito. Un codice
    sconosciuto non dà questa garanzia, e nemmeno i codici transitori: il
    servizio fallisce anche in modo temporaneo, chiedendo di riprovare più
    tardi.
    """
    codice = _codice((_corpo(contenuto) or {}).get("code"))
    if codice is None:
        return None
    try:
        regola = RuleCode(codice)
    except ValueError:
        return None
    return None if regola in TRANSIENT_CODES else regola


def _passeggero(stato: int, codice: int) -> bool:
    """True se il fallimento riguarda il servizio e non la richiesta.

    Un `5xx` è per definizione un guasto del servizio: il codice nel corpo non
    descrive la richiesta di chi chiama, e presentarlo come una regola violata
    lo manderebbe a correggere una richiesta già corretta. Il codice 1000
    arriva anche per un URN perfettamente valido, quando l'API è in avaria.
    """
    return stato >= 500 or codice in {r.value for r in TRANSIENT_CODES}


def solleva_errore(stato: int, contenuto: bytes, tipo_contenuto: str | None = None) -> None:
    """Trasforma una risposta fallita nell'eccezione che la descrive."""
    corpo = _corpo(contenuto)
    if stato == 409 or (corpo or {}).get("supportId"):
        raise RequestBlockedError(
            "la richiesta è stata respinta dai sistemi di protezione del servizio"
        )
    if stato in (503, 529):
        raise OverloadedError()
    if corpo is not None:
        codice = _codice(corpo.get("code"))
        messaggio_codice = _testo(corpo.get("message"))
        if codice == stato:
            # Per un atto che non esiste il servizio ripete lo stato HTTP dentro
            # `code`: `{"message": "atto non trovato", "code": "404"}`. Altrove
            # quel campo porta i codici di regola, che sono tutti a quattro
            # cifre. Un codice che ripete lo stato non aggiunge informazione, e
            # trattarlo come regola violata segnalerebbe una richiesta sbagliata
            # invece di un atto inesistente.
            codice = None
        if codice is not None and _passeggero(stato, codice):
            raise ConnectionError(
                f"il servizio ha risposto {stato}: {messaggio_codice or 'senza dettagli'}"
            )
        if codice is not None:
            raise RuleViolationError(codice, messaggio_codice)
        if stato == 404:
            raise NotFoundError("nessun atto per la richiesta")
        messaggio = _testo(corpo.get("error")) or _testo(corpo.get("message"))
        raise UnexpectedResponseError(
            f"il servizio ha risposto {stato}: {messaggio or 'senza dettagli'}"
        )
    raise UnexpectedResponseError(
        f"il servizio ha risposto {stato} con un corpo non interpretabile"
    )
