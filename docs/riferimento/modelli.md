# I modelli

Tutti i modelli sono `dataclass` **congelate**: non si modificano dopo la
costruzione, si hashano e si confrontano per valore. Nessuno di questi va
costruito a mano nell'uso normale: arrivano dalle risposte del servizio.

## Quale oggetto arriva da quale chiamata

| Chiamata | Restituisce | Contiene |
|---|---|---|
| [`dettaglio`][normattiva.Normattiva.dettaglio] | `DettaglioAtto` | il testo di un atto o articolo in una finestra di vigenza |
| [`cronologia`][normattiva.Normattiva.cronologia] | iteratore di `DettaglioAtto` | una versione per volta, dalla più vecchia |
| [`ricerca`][normattiva.Normattiva.ricerca], [`ricerca_avanzata`][normattiva.Normattiva.ricerca_avanzata] | `EsitoRicerca` | una pagina di `AttoTrovato`, più totale e faccette |
| [`ricerca_completa`][normattiva.Normattiva.ricerca_completa] | iteratore di `AttoTrovato` | gli atti di tutte le pagine, uno per volta |
| [`atti_aggiornati`][normattiva.Normattiva.atti_aggiornati] | iteratore di `AttoTrovato` | gli atti modificati nel periodo |
| [`start_export`][normattiva.Normattiva.start_export] | `Export` | il lavoro in corso, con il suo token |
| [`Export.download`][normattiva.Export.download] | `Corpus` | un `AttoStorico` per atto, con tutte le versioni |
| [`denominazioni`][normattiva.Normattiva.denominazioni] e le altre tipologiche | tupla di `Tipologica` | i codici che i criteri accettano |
| [`collections`][normattiva.Normattiva.collections] | tupla di `Collection` | gli archivi già confezionati |

```mermaid
classDiagram
    direction LR
    class DettaglioAtto {
        +str titolo
        +str testo
        +tuple~Comma~ commi
        +str note_aggiornamento
        +bool possibile_troncamento
        +str permalink
    }
    class EstremiAtto {
        +str denominazione
        +date data
        +str numero
        +str citazione
    }
    class PubblicazioneGazzetta {
        +date data
        +int numero
        +str codice_redazionale
    }
    class FinestraVigenza {
        +date inizio
        +date fine
        +bool aperta
        +contiene(giorno) bool
    }
    class Comma {
        +str numero
        +str testo
    }
    class EsitoRicerca {
        +int totale
        +int pagina
        +bool ultima_pagina
    }
    class AttoTrovato {
        +str titolo
        +bool ha_urn
        +Urn urn
    }
    class Faccette {
        +tuple per_anno
        +tuple per_tipo
        +tuple per_emettitore
    }

    DettaglioAtto *-- "1" EstremiAtto : atto
    DettaglioAtto *-- "1" PubblicazioneGazzetta : gazzetta
    DettaglioAtto *-- "1" FinestraVigenza : finestra
    DettaglioAtto *-- "0..n" Comma : commi
    EsitoRicerca *-- "0..n" AttoTrovato : atti
    EsitoRicerca *-- "1" Faccette : faccette
    AttoTrovato *-- "1" EstremiAtto : estremi
    AttoTrovato *-- "1" PubblicazioneGazzetta : gazzetta
```

Dall'esportazione arriva invece un albero, dove `Partizione` contiene sé stessa:

```mermaid
classDiagram
    direction LR
    class Corpus {
        +tuple~AttoStorico~ atti
        +save(path)
        +from_zip(path)$ Corpus
    }
    class AttoStorico {
        +Urn urn
        +bool abrogato
        +date pubblicato_il
        +alla_data(giorno) VersioneAtto
        +originale VersioneAtto
        +vigente VersioneAtto
    }
    class VersioneAtto {
        +date vigente_dal
        +bool originale
        +articoli() Iterator
    }
    class Partizione {
        +str tipo
        +str numero
        +str rubrica
        +str testo
    }
    class Aggiornamento {
        +date data
        +str testo
    }

    Corpus *-- "1..n" AttoStorico : atti
    AttoStorico *-- "1..n" VersioneAtto : versioni
    AttoStorico *-- "0..n" Aggiornamento : aggiornamenti
    VersioneAtto *-- "0..n" Partizione : articolato
    VersioneAtto *-- "0..n" Partizione : annessi
    Partizione *-- "0..n" Partizione : figli
```

I due percorsi producono modelli diversi perché le due risposte del servizio
sono strutturalmente diverse: `DettaglioAtto` porta testo e commi di **una**
versione, `AttoStorico` porta l'albero dell'articolato di **tutte**. Il
confronto sta in
[Com'è fatto il servizio](../capire/il-servizio.md#due-modelli-di-risposta).

## Il testo di un atto o di un articolo

::: normattiva.DettaglioAtto

::: normattiva.Comma

## Le coordinate di un atto

::: normattiva.EstremiAtto

::: normattiva.PubblicazioneGazzetta

::: normattiva.FinestraVigenza

## I risultati di una ricerca

::: normattiva.EsitoRicerca

::: normattiva.AttoTrovato

::: normattiva.Evidenziazione

::: normattiva.Faccette

::: normattiva.Faccetta

## L'atto intero, dall'esportazione

::: normattiva.AttoStorico

::: normattiva.VersioneAtto

::: normattiva.Partizione

::: normattiva.Aggiornamento

::: normattiva.RiferimentoAggiornamento

## I dizionari del servizio

::: normattiva.Tipologica

::: normattiva.Collection

::: normattiva.RicercaPredefinita

## Le enumerazioni

::: normattiva.Format

::: normattiva.ExportMode

::: normattiva.ClasseProvvedimento

::: normattiva.Sort

## Le costanti

::: normattiva.modelli.ATTRIBUZIONE

::: normattiva.modelli.DENOMINAZIONI_URN

::: normattiva.modelli.ABBREVIAZIONI

::: normattiva.modelli.ARTICOLO
