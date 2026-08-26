---
hide:
  - toc
---

# La riga di comando

Il pacchetto installa un comando che si chiama `normattiva`: se hai installato
`normattiva-sdk`, il comando c'è già.

```bash
normattiva --versione
python -m normattiva --versione
```

Le due forme sono equivalenti. La seconda serve dove lo script non è sul
`PATH`, per esempio dentro un container in cui si invoca sempre l'interprete.

Per i percorsi d'uso, con gli esempi e gli output reali, vedi
[usare la riga di comando](../come-fare/usare-la-riga-di-comando.md).

## I comandi

| Comando | Che cosa fa | Che cosa chiama |
|---|---|---|
| `testo` | legge il testo di un atto o di un articolo | [`dettaglio`][normattiva.Normattiva.dettaglio], [`dettaglio_da_gazzetta`][normattiva.Normattiva.dettaglio_da_gazzetta] |
| `cerca` | cerca parole nel testo pieno | [`ricerca`][normattiva.Normattiva.ricerca], [`ricerca_completa`][normattiva.Normattiva.ricerca_completa] |
| `cerca-avanzata` | cerca per coordinate | [`ricerca_avanzata`][normattiva.Normattiva.ricerca_avanzata] |
| `cronologia` | percorre le versioni di un articolo | [`cronologia`][normattiva.Normattiva.cronologia] |
| `aggiornati` | elenca gli atti modificati fra due date | [`atti_aggiornati`][normattiva.Normattiva.atti_aggiornati] |
| `esporta` | avvia un'esportazione e scrive l'archivio su disco | [`start_export`][normattiva.Normattiva.start_export], [`wait`][normattiva.Export.wait], [`save`][normattiva.Export.save] |
| `collezioni` | elenca gli archivi già confezionati | [`collections`][normattiva.Normattiva.collections] |
| `scarica-collezione` | scarica uno di quegli archivi | [`save_collection`][normattiva.Normattiva.save_collection] |
| `dizionario` | elenca i codici che il servizio accetta | [`denominazioni`][normattiva.Normattiva.denominazioni] e le altre due tipologiche |
| `urn` | scompone o compone un identificatore | [`Urn`][normattiva.Urn], senza rete |
| `codici` | elenca gli atti chiamabili per nome | [`codici`][normattiva.codici], senza rete |

`normattiva COMANDO --help` mostra le opzioni di ciascun comando, con un paio
di esempi pronti all'uso.

### Che cosa non copre

Il client asincrono, la lettura di un archivio in [`Corpus`][normattiva.Corpus],
`ricerche_predefinite` e l'iniezione di un client HTTP non hanno un comando
corrispondente.

## Le opzioni comuni

Valgono per ogni comando a cui si applicano, e vanno scritte dopo il nome del
comando.

| Opzione | Su | Che cosa fa |
|---|---|---|
| `--json` | tutti | scrive un documento JSON invece del testo impaginato |
| `--colore {auto,sempre,mai}` | tutti | `auto` colora solo se l'output è un terminale |
| `--timeout SECONDI` | quelli che usano la rete | quanto attendere ogni singola risposta. Predefinito: 30 |
| `--verboso` | quelli che usano la rete | scrive su stderr retry, attese e stati |

La variabile d'ambiente `NO_COLOR`, se impostata, disattiva i colori senza
bisogno di `--colore mai`.

## I codici di uscita

| Codice | Nome | Quando |
|---|---|---|
| 0 | `OK` | il comando è andato a buon fine |
| 1 | `ERRORE` | errore non imputabile né alla richiesta né al servizio: tipicamente l'archivio non si è potuto scrivere |
| 2 | `USO` | argomenti mancanti, malformati, o in contraddizione fra loro |
| 3 | `NON_TROVATO` | `NotFoundError`, `VersionNotFoundError`, `NotYetInForceError` |
| 4 | `RICHIESTA` | ogni altro errore della libreria: la richiesta era sbagliata |
| 5 | `SERVIZIO` | `ConnectionError`, `UnexpectedResponseError`, `RequestBlockedError`, `OverloadedError`, `ExportFailedError` |
| 130 | `INTERROTTO` | il processo ha ricevuto Ctrl-C |
| 141 | `LETTURA_INTERROTTA` | il processo che leggeva l'output ha chiuso il canale, come fa `\| head` |

I codici sono divisi per famiglia di causa e non per eccezione, perché è la
distinzione che serve in uno script: su un `4` c'è da correggere la richiesta,
su un `5` c'è da riprovare più tardi. Il messaggio va su stderr, sempre
preceduto da `normattiva: `.

## La forma del JSON

`--json` scrive un documento solo, indentato, con gli accenti non sfuggiti.

`testo` produce l'atto:

```json
{
  "citazione": "R.D. 16 marzo 1942, n. 262",
  "titolo": "REGIO DECRETO 16 marzo 1942, n. 262",
  "sottotitolo": "Approvazione del testo del Codice civile. (042U0262)",
  "urn": "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2043",
  "permalink": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:...",
  "estremi": {"denominazione": "REGIO DECRETO", "data": "1942-03-16", "numero": "262", "citazione": "..."},
  "gazzetta": {"data": "1942-04-04", "numero": 79, "codice_redazionale": null, "supplemento": null, "numero_supplemento": null},
  "vigenza": {"inizio": "1942-04-19", "fine": null},
  "preambolo": null,
  "testo": "Art. 2043.\n(Risarcimento per fatto illecito).\n...",
  "commi": [],
  "note_aggiornamento": null,
  "possibile_troncamento": false,
  "fonte": "Fonte: Normattiva (https://www.normattiva.it), Istituto Poligrafico e Zecca dello Stato, in licenza CC BY 4.0. Testo non autentico e gratuito: l'unico testo ufficiale è quello pubblicato sulla Gazzetta Ufficiale a mezzo stampa."
}
```

`urn` è `null` per i tipi di atto la cui forma URN non è verificata. Un
identificatore composto a tentativi otterrebbe un `404`, che chi lo riceve
leggerebbe come «l'atto non esiste».

Gli altri comandi:

| Comando | Chiavi di primo livello |
|---|---|
| `cerca`, `cerca-avanzata` | `totale`, `pagina`, `pagine`, `atti`, `faccette`, `fonte` |
| `cerca --massimo N`, `aggiornati` | `atti`, `fonte` |
| `cronologia` | `urn`, `versioni`, `fonte` |
| `esporta` | `token`, `formato`, `archivio`, `byte`, `fonte` |
| `scarica-collezione` | `archivio`, `byte`, `fonte` |
| `collezioni` | `collezioni` |
| `dizionario` | `denominazioni`, `classi` o `formati`, secondo quale è stato chiesto |
| `urn` | le parti dell'identificatore, più `permalink` |
| `codici` | `codici` |

`cerca` cambia forma quando riceve `--massimo`, perché cambia la domanda:
senza, si chiede una pagina e la risposta porta il totale e le faccette; con,
si chiede un flusso di atti e il concetto di pagina non si applica.

Ogni comando che produce dati di Normattiva include `fonte`, che è la stessa
stringa di [`ATTRIBUZIONE`][normattiva.ATTRIBUZIONE]. Nell'output per il
terminale la stessa riga compare in fondo. La licenza dei dati la richiede, e
la richiede anche a chi ripubblica quello che ha ottenuto da qui.

## I due formati di output

| | terminale | `--json` |
|---|---|---|
| Testo | mandato a capo alla larghezza della finestra, fino a cento colonne | le righe che il servizio ha mandato |
| Valori assenti | la riga non compare | la chiave c'è, con valore `null` |
| Colore | solo se l'output è un terminale | mai |
| Attribuzione | riga in fondo | chiave `fonte` |
