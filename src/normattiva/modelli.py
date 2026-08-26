"""Modelli di dati restituiti da questa libreria.

Ci sono due famiglie. Una descrive quello che restituisce il percorso
interattivo: il testo di un atto, com'era in una finestra di vigenza.
L'altra descrive quello che restituisce l'esportazione: un atto intero con la
sua struttura e tutta la sua storia. Sono separate perché il servizio
restituisce davvero due cose diverse: un modello unico e appiattito
richiederebbe campi opzionali privi di significato in metà dei casi.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from enum import Enum, IntEnum
from functools import cached_property

from normattiva.errori import (
    InvalidArgumentError,
    InvalidUrnError,
    VersionNotFoundError,
)
from normattiva.testo import Comma, Contenuto, estrai
from normattiva.urn import Urn

ATTRIBUZIONE = (
    "Fonte: Normattiva (https://www.normattiva.it), Istituto Poligrafico e Zecca "
    "dello Stato, in licenza CC BY 4.0. Testo non autentico e gratuito: l'unico "
    "testo ufficiale è quello pubblicato sulla Gazzetta Ufficiale a mezzo stampa."
)
"""La riga di attribuzione che la licenza dei dati richiede.

L'avviso legale del portale richiede tre menzioni: «La riproduzione dei
testi forniti nel formato elettronico è consentita purché venga menzionata la
fonte, il carattere non autentico e gratuito». La riga le contiene tutte e tre,
e `tests/test_licenza.py` lo verifica, perché è facile accorciare
un'attribuzione senza accorgersi di aver perso una menzione.
"""

MESI = (
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
)
ABBREVIAZIONI = {
    "COSTITUZIONE": "Cost.",
    "LEGGE": "L.",
    "LEGGE COSTITUZIONALE": "L. cost.",
    "DECRETO-LEGGE": "D.L.",
    "DECRETO LEGISLATIVO": "D.Lgs.",
    "DECRETO DEL PRESIDENTE DELLA REPUBBLICA": "D.P.R.",
    "DECRETO DEL PRESIDENTE DEL CONSIGLIO DEI MINISTRI": "D.P.C.M.",
    "DECRETO MINISTERIALE": "D.M.",
    "REGIO DECRETO": "R.D.",
    "REGIO DECRETO-LEGGE": "R.D.L.",
    "REGIO DECRETO LEGISLATIVO": "R.D.Lgs.",
}
"""Abbreviazione di ogni tipo di atto nelle citazioni.

Non coincide con `DENOMINAZIONI_URN`, e la differenza è voluta: abbreviare è
una convenzione editoriale applicabile anche a un atto che questa libreria non
sa indirizzare, come il regio decreto-legge, mentre comporre un URN richiede di
conoscere la forma esatta che il servizio accetta.

Un tipo che qui non compare si cita per esteso, quindi
`EstremiAtto.citazione` risponde per tutti.
"""

DENOMINAZIONI_URN = {
    "COSTITUZIONE": "costituzione",
    "DECRETO": "decreto",
    "DECRETO DEL CAPO PROVVISORIO DELLO STATO": "decreto.del.capo.provvisorio.dello.status",
    "DECRETO DEL PRESIDENTE DEL CONSIGLIO DEI MINISTRI": (
        "decreto.del.presidente.del.consiglio.dei.ministri"
    ),
    "DECRETO DEL PRESIDENTE DELLA REPUBBLICA": "decreto.del.presidente.della.repubblica",
    "DECRETO LEGISLATIVO": "decreto.legislativo",
    "DECRETO LEGISLATIVO LUOGOTENENZIALE": "decreto.legislativo.luogotenenziale",
    "DECRETO LEGISLATIVO PRESIDENZIALE": "decreto.legislativo.presidenziale",
    "DECRETO LUOGOTENENZIALE": "decreto.luogotenenziale",
    "DECRETO MINISTERIALE": "decreto.ministeriale",
    "DECRETO PRESIDENZIALE": "decreto.presidenziale",
    "DECRETO-LEGGE": "decreto.legge",
    "DELIBERAZIONE": "deliberazione",
    "LEGGE": "legge",
    "LEGGE COSTITUZIONALE": "legge.costituzionale",
    "ORDINANZA": "ordinanza",
    "REGIO DECRETO": "regio.decreto",
    "REGIO DECRETO LEGISLATIVO": "regio.decreto.legislativo",
}
"""Forma di ogni tipo di atto dentro un URN, verificata contro il servizio.

Sono le diciotto denominazioni su trenta per cui un URN così composto risponde
davvero. Per le altre, quasi tutte tipologie storiche come «DECRETO DEL DUCE» o
«REGOLAMENTO», la forma NIR non è nota: indovinarla porta a un 404 che sembra un
difetto dell'atto e invece è un URN composto male. `EstremiAtto.ha_urn` permette
di verificarlo in anticipo.
"""

ARTICOLO = "articolo"
"""Valore del campo `tipo` di `Partizione` per i nodi di tipo articolo."""

_COMMA_NUMERICO = re.compile(r"^(\d+)$")

TAGLIO_PARTI = 100
"""Il servizio conserva gli articoli lunghi a blocchi di questo numero di commi."""


class Format(str, Enum):
    """Formati in cui il servizio può produrre un'esportazione."""

    JSON = "JSON"
    AKN = "AKN"
    XML = "XML"
    URI = "URI"
    HTML = "HTML"
    PDF = "PDF"
    EPUB = "EPUB"
    RTF = "RTF"

    __str__ = str.__str__


class ExportMode(str, Enum):
    """Quali versioni di un atto deve includere un'esportazione."""

    ORIGINALE = "originale"
    VIGENTE = "vigente"
    MULTIVIGENTE = "multivigente"

    __str__ = str.__str__


class ClasseProvvedimento(IntEnum):
    """Stato redazionale di un atto: mai aggiornato, aggiornato o abrogato."""

    SENZA_AGGIORNAMENTI = 1
    AGGIORNATO = 2
    ABROGATO = 3


class Sort(str, Enum):
    """L'ordinamento dei risultati di una ricerca.

    `NEWEST` mette per primi gli atti più recenti, `OLDEST` i più antichi.
    """

    NEWEST = "newest"
    OLDEST = "oldest"

    __str__ = str.__str__


@dataclass(frozen=True, slots=True)
class Tipologica:
    """Una voce di uno dei dizionari (tipologiche) del servizio."""

    codice: str
    descrizione: str


@dataclass(frozen=True, slots=True)
class FinestraVigenza:
    """Intervallo di tempo in cui una versione di un testo è stata in vigore."""

    inizio: date
    fine: date | None = None

    def __post_init__(self) -> None:
        if self.fine is not None and self.fine < self.inizio:
            raise InvalidArgumentError(f"la fine {self.fine} precede l'inizio {self.inizio}")

    @property
    def aperta(self) -> bool:
        """Se questa è la versione tuttora in vigore."""
        return self.fine is None

    def contiene(self, giorno: date) -> bool:
        """Indica se il giorno indicato cade dentro questa finestra.

        Una finestra aperta, cioè senza fine, contiene ogni giorno a partire
        dal suo inizio.
        """
        return self.inizio <= giorno and (self.fine is None or giorno <= self.fine)

    def __str__(self) -> str:
        fine = self.fine.isoformat() if self.fine else "oggi"
        return f"{self.inizio.isoformat()} → {fine}"


@dataclass(frozen=True, slots=True)
class EstremiAtto:
    """Gli estremi che identificano un provvedimento: tipo, data e numero."""

    denominazione: str
    data: date
    numero: str | None = None
    codice_tipo: str | None = None

    @property
    def ha_urn(self) -> bool:
        """Indica se per questo tipo di atto si sa comporre l'URN.

        Da verificare prima di leggere `urn` scorrendo risultati di ricerca:
        dodici tipi di atto su trenta, quasi tutti storici, non hanno una forma
        NIR verificata, e per quelli `urn` solleva un'eccezione invece di
        indovinare.
        """
        return self.denominazione.strip().upper() in DENOMINAZIONI_URN

    @property
    def urn(self) -> Urn:
        """L'URN che identifica questo atto.

        Solleva `InvalidUrnError` per i tipi di atto la cui forma URN non è
        stata verificata: un URN inventato otterrebbe un 404 dal servizio, e
        chi lo riceve non avrebbe modo di capire che il difetto è nell'URN.
        `ha_urn` permette di verificarlo in anticipo, senza sollevare.

        Raises:
            InvalidUrnError: la forma URN di questo tipo di atto non è
                verificata.
        """
        nome = self.denominazione.strip().upper()
        denominazione = DENOMINAZIONI_URN.get(nome)
        if denominazione is None:
            raise InvalidUrnError(
                self.denominazione,
                "la forma URN di questo tipo di atto non è verificata: "
                "usare l'esportazione, che cerca per denominazione e coordinate",
            )
        return Urn(
            denominazione=denominazione,
            anno=self.data.year,
            data=self.data,
            numero=self.numero,
        )

    @property
    def citazione(self) -> str:
        """L'atto nella forma in cui si cita nella pratica giuridica italiana."""
        nome = self.denominazione.strip().upper()
        abbreviazione = ABBREVIAZIONI.get(nome, self.denominazione.strip().capitalize())
        quando = f"{self.data.day} {MESI[self.data.month - 1]} {self.data.year}"
        numero = f", n. {self.numero}" if self.numero else ""
        return f"{abbreviazione} {quando}{numero}"


@dataclass(frozen=True, slots=True)
class PubblicazioneGazzetta:
    """Dove e quando un atto è stato pubblicato in Gazzetta Ufficiale.

    `numero` è opzionale perché il servizio non lo fornisce ovunque: gli atti
    aggiornanti citati dentro un'esportazione hanno la data di Gazzetta ma non
    il numero, e in quel caso il campo resta `None`.
    """

    data: date
    numero: int | None = None
    codice_redazionale: str | None = None
    supplemento: str | None = None
    numero_supplemento: int | None = None

    @property
    def in_supplemento(self) -> bool:
        """Se l'atto è uscito in un supplemento e non nella Gazzetta ordinaria."""
        return self.supplemento is not None

    def __str__(self) -> str:
        quando = self.data.isoformat()
        testa = f"G.U. n. {self.numero} del {quando}" if self.numero else f"G.U. del {quando}"
        if self.supplemento is None:
            return testa
        numero = f" n. {self.numero_supplemento}" if self.numero_supplemento else ""
        return f"{testa}, suppl. {self.supplemento}{numero}"


@dataclass(frozen=True)
class DettaglioAtto:
    """Il testo di un atto o di un articolo a un punto nel tempo.

    Porta il testo già separato dalle note redazionali, i commi numerati, la
    finestra di vigenza in cui quel testo è valido, le coordinate di Gazzetta e
    il permalink alla pagina pubblica. Le proprietà che leggono l'HTML del
    servizio lo fanno alla prima richiesta e tengono il risultato.
    """

    atto: EstremiAtto
    gazzetta: PubblicazioneGazzetta
    titolo: str
    sottotitolo: str | None
    testo_html: str
    finestra: FinestraVigenza | None

    @cached_property
    def _contenuto(self) -> Contenuto:
        return estrai(self.testo_html)

    @property
    def testo(self) -> str:
        """Il solo testo, senza le note redazionali di aggiornamento."""
        return self._contenuto.corpo

    @property
    def commi(self) -> tuple[Comma, ...]:
        """I commi numerati, quando l'articolo è marcato come tale."""
        return self._contenuto.commi

    @property
    def note_aggiornamento(self) -> str | None:
        """Le note redazionali sulle modifiche a questo testo, se presenti."""
        return self._contenuto.note

    @property
    def preambolo(self) -> str | None:
        """La formula introduttiva, quando la risposta la include."""
        return self._contenuto.preambolo

    @property
    def commi_presenti(self) -> int | None:
        """Quanti commi sono arrivati, o None se il testo non ne ha."""
        return len(self.commi) or None

    @property
    def ultimo_comma_numerato(self) -> int | None:
        """L'etichetta dell'ultimo comma numerato, o None se non ce n'è nessuno.

        Non coincide con `commi_presenti`: un articolo può avere commi con
        etichette non numeriche, e sono le etichette a indicare dove il testo
        si ferma.
        """
        return next(
            (
                int(pezzi.group(1))
                for comma in reversed(self.commi)
                if (pezzi := _COMMA_NUMERICO.match(comma.numero))
            ),
            None,
        )

    @property
    def possibile_troncamento(self) -> bool:
        """Indica se questo testo sembra troncato.

        Il servizio conserva gli articoli lunghi a blocchi di cento commi e ne
        restituisce solo il primo, senza segnalarlo. Un articolo il cui ultimo
        comma numerato cade esattamente su un multiplo di cento è quindi
        sospetto. Un articolo che finisce davvero lì resta indistinguibile da
        uno troncato: per questo il valore esprime un sospetto, non una
        certezza.
        """
        ultimo = self.ultimo_comma_numerato or 0
        return ultimo >= TAGLIO_PARTI and ultimo % TAGLIO_PARTI == 0

    @property
    def urn(self) -> Urn:
        """L'URN dell'atto a cui questo testo appartiene."""
        return self.atto.urn

    @property
    def permalink(self) -> str:
        """Il link pubblico di Normattiva, per verificare sulla fonte."""
        return self.urn.permalink

    @property
    def attribuzione(self) -> str:
        """La riga di attribuzione richiesta dalla licenza."""
        return ATTRIBUZIONE


@dataclass(frozen=True, slots=True)
class Evidenziazione:
    """Il punto in cui un termine di ricerca è stato trovato dentro un atto."""

    articolo: str | None
    frammenti: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Faccetta:
    """Un valore di una faccetta di ricerca, con quanti atti lo portano."""

    codice: str
    conteggio: int
    descrizione: str | None = None


@dataclass(frozen=True, slots=True)
class Faccette:
    """Le tre faccette che la ricerca restituisce."""

    per_anno: tuple[Faccetta, ...] = ()
    per_tipo: tuple[Faccetta, ...] = ()
    per_emettitore: tuple[Faccetta, ...] = ()


@dataclass(frozen=True, slots=True)
class AttoTrovato:
    """Un atto come restituito da una ricerca."""

    estremi: EstremiAtto
    gazzetta: PubblicazioneGazzetta
    titolo: str
    descrizione: str | None = None
    ultima_modifica: date | None = None
    atti_modificanti: tuple[str, ...] = ()
    """I codici redazionali degli ultimi atti che hanno modificato questo, come `26G00129`.

    Non sono URN né titoli: sono gli identificativi di Gazzetta degli atti
    modificanti, e per risalire all'atto serve anche la loro data, che il
    servizio qui non fornisce. Osservati il 2026-08-24 nel flusso degli atti
    aggiornati.
    """

    evidenziazioni: tuple[Evidenziazione, ...] = ()

    @property
    def ha_urn(self) -> bool:
        """Indica se per questo atto si sa comporre l'URN: da verificare prima di leggerlo."""
        return self.estremi.ha_urn

    @property
    def urn(self) -> Urn:
        """L'URN con cui chiedere il testo di questo atto.

        Solleva `InvalidUrnError` per i tipi di atto storici la cui forma NIR
        non è verificata: scorrendo i risultati conviene filtrare su `ha_urn`.
        """
        return self.estremi.urn

    @property
    def citazione(self) -> str:
        """L'atto nella forma in cui si cita nella pratica giuridica italiana."""
        return self.estremi.citazione


@dataclass(frozen=True, slots=True)
class EsitoRicerca:
    """Una pagina di risultati di ricerca.

    Non definisce `__len__`: non sarebbe chiaro se conta i risultati di questa
    pagina o quelli dell'intera ricerca, e un esito con la pagina vuota ma
    cinquemila atti in totale risulterebbe falso dentro un `if`. Si iterano gli
    `atti` di questa pagina, e si legge `totale` per il conteggio complessivo.
    """

    atti: tuple[AttoTrovato, ...]
    totale: int
    pagina: int = 1
    pagine: int = 1
    faccette: Faccette = Faccette()

    def __iter__(self) -> Iterator[AttoTrovato]:
        return iter(self.atti)

    @property
    def ultima_pagina(self) -> bool:
        """Indica se non ci sono altre pagine da chiedere."""
        return self.pagina >= self.pagine


@dataclass(frozen=True, slots=True)
class Collection:
    """Un archivio già confezionato messo a disposizione dal servizio."""

    name: str
    format: str
    total_atti: int
    description: str | None = None
    created_at: date | None = None


@dataclass(frozen=True, slots=True)
class RicercaPredefinita:
    """Una ricerca predefinita suggerita dal servizio."""

    nome: str
    parametri: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Partizione:
    """Un nodo della struttura di un atto: un capo, un articolo, un allegato.

    `tipo` contiene il nome NIR del nodo così come lo dichiara il servizio; per
    gli articoli vale la costante `ARTICOLO`.
    """

    tipo: str | None
    numero: str
    testo: str
    rubrica: str | None = None
    finestre: tuple[FinestraVigenza, ...] = ()
    figli: tuple[Partizione, ...] = ()

    def articoli(self) -> Iterator[Partizione]:
        """Itera gli articoli a partire da questo nodo, incluso il nodo stesso.

        Yields:
            Ogni nodo il cui `tipo` è `ARTICOLO`, in ordine di lettura.
        """
        if self.tipo == ARTICOLO:
            yield self
        for figlio in self.figli:
            yield from figlio.articoli()


@dataclass(frozen=True, slots=True)
class RiferimentoAggiornamento:
    """L'articolo che ha introdotto una modifica."""

    gazzetta: PubblicazioneGazzetta
    articolo: str | None = None


@dataclass(frozen=True, slots=True)
class Aggiornamento:
    """Una modifica subita dall'atto, come descritta dal servizio."""

    data: date
    testo: str
    riferimenti: tuple[RiferimentoAggiornamento, ...] = ()


@dataclass(frozen=True, slots=True)
class VersioneAtto:
    """Una versione dell'atto, in vigore da una certa data in poi."""

    vigente_dal: date | None
    articolato: tuple[Partizione, ...] = ()
    annessi: tuple[Partizione, ...] = ()

    @property
    def originale(self) -> bool:
        """Indica se questa è la versione originale, come pubblicata la prima volta."""
        return self.vigente_dal is None

    def articoli(self) -> Iterator[Partizione]:
        """Itera gli articoli di questa versione, in ordine.

        Scende solo nell'articolato: gli allegati stanno in `annessi`, che è un
        ramo separato dell'atto.

        Yields:
            Un articolo per volta, in ordine di lettura.
        """
        for nodo in self.articolato:
            yield from nodo.articoli()


@dataclass(frozen=True, slots=True)
class AttoStorico:
    """Un atto intero con tutte le versioni incluse nell'esportazione."""

    urn: Urn
    estremi: EstremiAtto
    versioni: tuple[VersioneAtto, ...]
    eli: str | None = None
    gazzetta: PubblicazioneGazzetta | None = None
    abrogato: bool = False
    aggiornamenti: tuple[Aggiornamento, ...] = ()

    def __post_init__(self) -> None:
        if sum(1 for v in self.versioni if v.originale) > 1:
            raise InvalidArgumentError(
                "più di una versione dichiara di essere l'originale: "
                "le date di vigenza non sono state riconosciute"
            )

    @property
    def pubblicato_il(self) -> date:
        """La data da cui l'atto esiste: la data di Gazzetta, o in mancanza quella di emanazione."""
        return self.gazzetta.data if self.gazzetta else self.estremi.data

    def alla_data(self, giorno: date) -> VersioneAtto:
        """Restituisce la versione dell'atto in vigore nel giorno indicato.

        Prima della prima modifica vale il testo originale, che nell'export non
        ha una data di inizio: vale la data di pubblicazione dell'atto. Un atto
        mai modificato ha solo quella versione, valida senza limite di tempo.

        Args:
            giorno: il giorno di cui si vuole il testo.

        Returns:
            La versione in vigore quel giorno, con il suo articolato.

        Raises:
            VersionNotFoundError: nessuna versione copre quel giorno,
                tipicamente perché è anteriore alla pubblicazione.
        """
        datate = [
            (v.vigente_dal, v)
            for v in self.versioni
            if v.vigente_dal is not None and v.vigente_dal <= giorno
        ]
        if datate:
            return max(datate, key=lambda coppia: coppia[0])[1]
        originale = self.originale
        if originale is not None and giorno >= self.pubblicato_il:
            return originale
        raise VersionNotFoundError(giorno)

    @property
    def originale(self) -> VersioneAtto | None:
        """La versione originale dell'atto, se inclusa nell'export."""
        return next((v for v in self.versioni if v.originale), None)

    @property
    def vigente(self) -> VersioneAtto | None:
        """La versione più recente inclusa nell'export.

        Per un atto mai modificato è l'originale: non esiste un testo più
        recente di quello di pubblicazione.
        """
        datate = [(v.vigente_dal, v) for v in self.versioni if v.vigente_dal is not None]
        if datate:
            return max(datate, key=lambda coppia: coppia[0])[1]
        return self.originale

    @property
    def attribuzione(self) -> str:
        """La riga di attribuzione richiesta dalla licenza."""
        return ATTRIBUZIONE


__all__ = [
    "ABBREVIAZIONI",
    "ARTICOLO",
    "ATTRIBUZIONE",
    "DENOMINAZIONI_URN",
    "Aggiornamento",
    "AttoStorico",
    "AttoTrovato",
    "ClasseProvvedimento",
    "Collection",
    "Comma",
    "DettaglioAtto",
    "EsitoRicerca",
    "EstremiAtto",
    "Evidenziazione",
    "ExportMode",
    "Faccetta",
    "Faccette",
    "FinestraVigenza",
    "Format",
    "Partizione",
    "PubblicazioneGazzetta",
    "RicercaPredefinita",
    "RiferimentoAggiornamento",
    "Sort",
    "Tipologica",
    "VersioneAtto",
]
