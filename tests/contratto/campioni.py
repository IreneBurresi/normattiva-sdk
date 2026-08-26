"""Il catalogo dei casi che il monitoraggio interroga ogni giorno.

Copre tutti gli endpoint pubblicati, ciascuno nelle forme di risposta che sa
produrre: i successi, i rifiuti, e le risposte che sembrano successi e non lo
sono. Anche gli endpoint che la libreria non usa sono qui, perché un giorno
potrebbe usarli e conviene sapere prima se cambiano.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

URN = "atto/dettaglio-atto-urn"
PAGINAZIONE = {"paginaCorrente": 1, "numeroElementiPerPagina": 5}


def _finestra_recente(giorni: int = 10) -> tuple[str, str]:
    fine = date.today() - timedelta(days=1)
    inizio = fine - timedelta(days=giorni)
    return f"{inizio.isoformat()}T00:00:00Z", f"{fine.isoformat()}T00:00:00Z"


@dataclass(frozen=True, slots=True)
class Campione:
    """Una richiesta, e cosa ci si aspetta di imparare dalla sua risposta."""

    nome: str
    metodo: str
    percorso: str
    perche: str
    corpo: dict | None = None
    parametri: dict | None = None
    intestazioni: dict[str, str] = field(default_factory=dict)
    forma: str = "json"
    dinamico: bool = False

    @property
    def gruppo(self) -> str:
        """L'endpoint a cui il campione appartiene."""
        return self.percorso.split("/{")[0]


def _urn(nome: str, urn: str, perche: str) -> Campione:
    return Campione(nome, "POST", URN, perche, corpo={"urn": urn})


LOOKUP = [
    Campione(
        "tipologiche_denominazioni",
        "GET",
        "tipologiche/denominazione-atto",
        "i trenta tipi di atto: se ne sparisce uno, i codici che usiamo non reggono più",
    ),
    Campione(
        "tipologiche_classi",
        "GET",
        "tipologiche/classe-provvedimento",
        "le tre classi dietro ClasseProvvedimento",
    ),
    Campione(
        "tipologiche_estensioni",
        "GET",
        "tipologiche/estensioni",
        "gli otto formati dietro l'enum Format",
    ),
    Campione(
        "ricerche_predefinite",
        "GET",
        "ricerca/predefinita",
        "le ricerche preconfezionate e la forma dei loro parametri",
    ),
]

COLLEZIONI = [
    Campione(
        "collezioni_catalogo",
        "GET",
        "collections/collection-predefinite",
        "il catalogo degli archivi già pronti",
    ),
    Campione(
        "collezione_preconfezionata",
        "GET",
        "collections/download/collection-preconfezionata",
        "l'unico scarico sincrono: struttura dello ZIP e del JSON dentro",
        parametri={
            "nome": "Leggi di delegazione europea",
            "formato": "JSON",
            "formatoRichiesta": "O",
        },
        forma="zip",
    ),
]

ATTI = [
    _urn(
        "urn_atto_intero",
        "urn:nir:stato:legge:1990-08-07;241",
        "un atto senza articolo: il preambolo e la formula di promulgazione",
    ),
    _urn(
        "urn_articolo",
        "urn:nir:stato:legge:1990-08-07;241~art2",
        "l'articolo tipico, con i commi marcati",
    ),
    _urn(
        "urn_articolo_con_aggiornamento",
        "urn:nir:stato:legge:1990-08-07;241~art19",
        "il blocco art_aggiornamento-akn che separiamo dal testo",
    ),
    _urn(
        "urn_ordinale_contratto",
        "urn:nir:stato:legge:1990-08-07;241~art2bis",
        "gli ordinali contratti nella grammatica URN",
    ),
    _urn(
        "urn_da_allegato",
        "urn:nir:stato:regio.decreto:1930-10-19;1398:1~art416bis",
        "gli articoli dei codici, che rispondono solo dal loro allegato",
    ),
    _urn(
        "urn_costituzione",
        "urn:nir:stato:costituzione:1947-12-27~art3",
        "l'atto con le coordinate di provvedimento a zero",
    ),
    _urn(
        "urn_vigenza_esplicita",
        "urn:nir:stato:legge:1970-12-01;898~art5!vig=2005-01-01",
        "il point-in-time e la finestra che deve contenerlo",
    ),
    _urn(
        "urn_versione_originale",
        "urn:nir:stato:legge:1990-08-07;241~art1@originale",
        "il testo come pubblicato la prima volta",
    ),
    _urn(
        "urn_data_impossibile",
        "urn:nir:stato:legge:1970-12-01;898~art5!vig=2005-13-45",
        "la data inesistente accettata invece che rifiutata",
    ),
    _urn(
        "urn_troncato",
        "urn:nir:stato:legge:2016-12-11;232~art1",
        "l'articolo lungo servito a metà senza dirlo",
    ),
    _urn(
        "urn_ambiguo",
        "urn:nir:stato:legge:2001-12-28;448~art2",
        "due pubblicazioni per lo stesso atto: la lista dei candidati",
    ),
    _urn(
        "urn_non_ancora_vigente",
        "urn:nir:stato:regio.decreto:1930-10-19;1398:1~art416bis!vig=1981-01-01",
        "la finestra che descrive un'assenza invece di una vigenza",
    ),
]

RIFIUTI = [
    _urn(
        "urn_rifiuto_comma",
        "urn:nir:stato:legge:2007-12-24;244~art2-com428",
        "il comma che compare nei testi restituiti e viene rifiutato in ingresso",
    ),
    _urn(
        "urn_rifiuto_ordinale_con_trattino",
        "urn:nir:stato:legge:1990-08-07;241~art5-bis",
        "la grafia con trattino che la grammatica non ammette",
    ),
    _urn(
        "urn_rifiuto_numero_romano",
        "urn:nir:stato:legge:1990-08-07;241~artXIV",
        "i numeri romani non sono numeri di articolo",
    ),
    _urn(
        "urn_rifiuto_vigenza_malformata",
        "urn:nir:stato:legge:1990-08-07;241!vig=NONSENSE",
        "la vigenza non a forma di data, che invece viene rifiutata",
    ),
    _urn(
        "urn_articolo_inesistente",
        "urn:nir:stato:legge:1990-08-07;241~art999",
        "l'articolo che non c'è: forma del 404 di business",
    ),
    _urn(
        "urn_atto_inesistente",
        "urn:nir:stato:legge:1990-08-07;9999",
        "l'atto che non c'è: il 404 che ripete lo stato dentro `code`, diverso "
        "da quello dell'articolo inesistente",
    ),
    _urn(
        "urn_codice_senza_allegato",
        "urn:nir:stato:regio.decreto:1942-03-16;262~art2043",
        "il codice civile interrogato senza allegato, con i parametri interni nel messaggio",
    ),
]

RICERCHE = [
    Campione(
        "ricerca_semplice",
        "POST",
        "ricerca/semplice",
        "la ricerca a testo libero e le sue faccette",
        corpo={"testoRicerca": "divorzio", "orderType": "recente", "paginazione": PAGINAZIONE},
    ),
    Campione(
        "ricerca_semplice_filtrata",
        "POST",
        "ricerca/semplice",
        "i tre filtri a faccetta che compongono",
        corpo={
            "testoRicerca": "trasparenza",
            "orderType": "recente",
            "paginazione": PAGINAZIONE,
            "filtriMap": {"codice_tipo_provvedimento": "PLE", "anno_provvedimento": "2016"},
        },
    ),
    Campione(
        "ricerca_senza_risultati",
        "POST",
        "ricerca/semplice",
        "la risposta vuota, che resta un 200 pulito",
        corpo={
            "testoRicerca": "qwertyuiopasdfgh",
            "orderType": "recente",
            "paginazione": PAGINAZIONE,
        },
    ),
    Campione(
        "ricerca_senza_paginazione",
        "POST",
        "ricerca/semplice",
        "il campo che lo schema dice opzionale e il servizio pretende: forma del 500 Spring",
        corpo={"testoRicerca": "divorzio", "orderType": "recente"},
    ),
    Campione(
        "ricerca_avanzata",
        "POST",
        "ricerca/avanzata",
        "la ricerca per coordinate, unica fonte del codice redazionale",
        corpo={
            "denominazioneAtto": "LEGGE",
            "annoProvvedimento": 1990,
            "numeroProvvedimento": 241,
            "orderType": "recente",
            "paginazione": PAGINAZIONE,
        },
    ),
    Campione(
        "ricerca_avanzata_con_vigenza",
        "POST",
        "ricerca/avanzata",
        "il filtro di vigenza sulla ricerca per coordinate",
        corpo={
            "denominazioneAtto": "LEGGE",
            "annoProvvedimento": 2016,
            "vigenza": "2020-01-01",
            "orderType": "recente",
            "paginazione": PAGINAZIONE,
        },
    ),
]


def _aggiornati(nome: str, perche: str, inizio: str, fine: str) -> Campione:
    return Campione(
        nome,
        "POST",
        "ricerca/aggiornati",
        perche,
        corpo={"dataInizioAggiornamento": inizio, "dataFineAggiornamento": fine},
        dinamico=True,
    )


_INIZIO, _FINE = _finestra_recente()

AGGIORNATI = [
    _aggiornati(
        "aggiornati_finestra_breve",
        "il feed delle modifiche e i suoi due campi in più",
        _INIZIO,
        _FINE,
    ),
    _aggiornati(
        "aggiornati_oltre_dodici_mesi",
        "il limite dei dodici mesi: forma dell'errore di business 1501",
        "2020-01-01T00:00:00Z",
        "2023-01-01T00:00:00Z",
    ),
    _aggiornati(
        "aggiornati_date_invertite",
        "le date invertite: forma dell'errore di business 1503",
        "2026-08-20T00:00:00Z",
        "2026-08-01T00:00:00Z",
    ),
]

PROTEZIONE = [
    Campione(
        "waf_content_type_senza_corpo",
        "GET",
        "tipologiche/estensioni",
        "il blocco del WAF quando una richiesta senza corpo dichiara un Content-Type",
        intestazioni={"Content-Type": "application/json"},
        forma="testo",
    ),
]

NON_USATI = [
    Campione(
        "dettaglio_atto_coordinate",
        "POST",
        "atto/dettaglio-atto",
        "l'endpoint a coordinate che non esponiamo, monitorato per sapere se cambia",
        corpo={
            "dataGU": "1990-08-18",
            "codiceRedazionale": "090G0294",
            "idArticolo": 2,
            "sottoArticolo": 1,
            "sottoArticolo1": 10,
            "idGruppo": 1,
            "progressivo": 0,
            "versione": 0,
        },
    ),
    Campione(
        "dettaglio_atto_originario",
        "POST",
        "atto/dettaglio-atto",
        "l'unico interruttore che su quell'endpoint ha effetto",
        corpo={
            "dataGU": "1990-08-18",
            "codiceRedazionale": "090G0294",
            "idArticolo": 2,
            "sottoArticolo": 1,
            "sottoArticolo1": 10,
            "idGruppo": 1,
            "progressivo": 0,
            "tipoDettaglio": "originario",
        },
    ),
]

TUTTI: tuple[Campione, ...] = (
    *LOOKUP,
    *COLLEZIONI,
    *ATTI,
    *RIFIUTI,
    *RICERCHE,
    *AGGIORNATI,
    *PROTEZIONE,
    *NON_USATI,
)


def per_nome(nome: str) -> Campione:
    """Il campione che si chiama così."""
    trovato = next((c for c in TUTTI if c.nome == nome), None)
    if trovato is None:
        raise KeyError(f"campione sconosciuto: {nome}")
    return trovato
