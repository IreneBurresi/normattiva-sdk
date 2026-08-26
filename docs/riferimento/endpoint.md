# Gli endpoint

L'API open data di Normattiva espone quindici endpoint. La tabella indica quale
metodo della libreria copre ciascuno.

| Endpoint | Metodo della libreria |
|---|---|
| `atto/dettaglio-atto-urn` | [`dettaglio`][normattiva.Normattiva.dettaglio] |
| `atto/dettaglio-atto` | [`dettaglio_da_gazzetta`][normattiva.Normattiva.dettaglio_da_gazzetta] |
| `ricerca/semplice` | [`ricerca`][normattiva.Normattiva.ricerca], [`ricerca_completa`][normattiva.Normattiva.ricerca_completa] |
| `ricerca/avanzata` | [`ricerca_avanzata`][normattiva.Normattiva.ricerca_avanzata] |
| `ricerca/aggiornati` | [`atti_aggiornati`][normattiva.Normattiva.atti_aggiornati] |
| `ricerca/predefinita` | [`ricerche_predefinite`][normattiva.Normattiva.ricerche_predefinite] |
| `ricerca-asincrona/nuova-ricerca` | [`start_export`][normattiva.Normattiva.start_export] |
| `ricerca-asincrona/conferma-ricerca` | [`start_export`][normattiva.Normattiva.start_export] |
| `ricerca-asincrona/check-status/{token}` | [`Export.refresh`][normattiva.Export.refresh] |
| `collections/download/collection-asincrona/{token}` | [`Export.download`][normattiva.Export.download] |
| `collections/collection-predefinite` | [`collections`][normattiva.Normattiva.collections] |
| `collections/download/collection-preconfezionata` | [`download_collection`][normattiva.Normattiva.download_collection] |
| `tipologiche/denominazione-atto` | [`denominazioni`][normattiva.Normattiva.denominazioni] |
| `tipologiche/classe-provvedimento` | [`classi_provvedimento`][normattiva.Normattiva.classi_provvedimento] |
| `tipologiche/estensioni` | [`export_formats`][normattiva.Normattiva.export_formats] |

## I criteri con due nomi

La ricerca avanzata e l'esportazione accettano gli stessi criteri, ma tre campi
cambiano nome da uno schema all'altro. La libreria traduce i nomi da sé; la
tabella serve a chi confronta le risposte con la specifica.

| Nome nella ricerca | Nome nell'esportazione | Parametro della libreria |
|---|---|---|
| `vigenza` | `dataVigenza` | `vigente_al` |
| `dataInizioPubProvvedimento` | `dataInizioPubblicazione` | `pubblicazione[0]` |
| `dataFinePubProvvedimento` | `dataFinePubblicazione` | `pubblicazione[1]` |

Perché questa differenza sia pericolosa lo spiega
[Com'è fatto il servizio](../capire/il-servizio.md#i-criteri-con-due-nomi).

## I campi non esposti

Alcuni campi della specifica non hanno un parametro nella libreria:

| Campo | Perché no |
|---|---|
| `numeroArticolo` nell'export | non ha effetto: l'archivio torna con tutti gli articoli |
| `dataVigenza` su `dettaglio-atto` | non ha effetto: la finestra restituita è la stessa con e senza |
| `testoContainsType`, `titoloContainsType` | i valori ammessi non sono documentati né deducibili |
| `email` sull'export | manderebbe l'archivio per posta elettronica: un effetto collaterale che una libreria non deve produrre implicitamente |
| `testoInVigore`, `dataPubblicazioneInGazzetta`, `numeroFileRicerca` | sempre nulli o a zero in ogni risposta osservata |
