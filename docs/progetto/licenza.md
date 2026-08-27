# Licenza e attribuzione

Tre cose diverse, con tre regimi diversi: **questa libreria**, **i dati** che
restituisce, e **il rapporto** fra il progetto e chi quei dati li pubblica.

## Questa libreria non è ufficiale

`normattiva-sdk` è un **progetto indipendente della comunità**. Non è affiliato
con l'Istituto Poligrafico e Zecca dello Stato, né con la Presidenza del
Consiglio dei Ministri, né con Normattiva. Non è approvato, sostenuto o
mantenuto da loro, e nessuno di loro risponde di quello che fa.

Il nome «Normattiva» compare qui per identificare il servizio con cui la
libreria dialoga, non per suggerire un rapporto che non esiste.

La libreria è distribuita con licenza **MIT**. Il testo completo è nel file
[`LICENSE`](https://github.com/ireneburresi/normattiva-sdk/blob/main/LICENSE)
del repository.

## Da dove vengono i dati

Da [dati.normattiva.it](https://dati.normattiva.it), il portale open data
allestito dall'**Istituto Poligrafico e Zecca dello Stato** sotto la
supervisione della Presidenza del Consiglio dei Ministri, della Camera dei
Deputati e del Senato della Repubblica.

Il pacchetto installato non ospita e non rielabora nulla: ogni risposta arriva
dal servizio nel momento in cui viene richiesta, e la libreria si limita a
tradurla in oggetti Python.

Il repository e l'archivio sorgente contengono invece alcune risposte reali,
registrate e ridotte, che permettono alla suite di girare senza rete: sono dati
IPZS ridistribuiti in licenza CC BY 4.0, con l'attribuzione accanto ai dati in
`tests/fixtures/` e in `tests/contratto/dataset/`.

## Con che licenza

**Creative Commons [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.it)**,
verificato sul portale il 24 agosto 2026.

IPZS ha aperto i dati per fasi, e la fase con la clausola non commerciale è
terminata:

| Da quando | Licenza | Che cosa copre |
|---|---|---|
| fase sperimentale, fino al 30 giugno 2025 | CC BY 4.0 **NC** | funzionalità ridotte |
| 1° luglio 2025 | CC BY 4.0 | gli stessi dati, senza la clausola NC |
| **1° gennaio 2026** | **CC BY 4.0** | **tutti gli atti, in originale, a una data e multivigente** |

Dal 1° gennaio 2026 vale quindi la CC BY 4.0 semplice: **l'uso commerciale e la
ridistribuzione sono consentiti**, e l'unico obbligo è l'attribuzione. Una copia
scaricata durante la fase sperimentale resta però soggetta alla licenza sotto
cui è stata ottenuta, clausola non commerciale compresa.

## L'attribuzione è dovuta, e richiede tre menzioni

L'avviso legale del portale non chiede una generica riga di cortesia. Chiede
che chi riproduce i testi menzioni **la fonte**, il **carattere non autentico**
e il **carattere gratuito**.

La libreria espone l'attribuzione già completa di tutte e tre le menzioni:

```python
atto.attribuzione
corpus.attribuzione
```

```
Fonte: Normattiva (https://www.normattiva.it), Istituto Poligrafico e Zecca
dello Stato, in licenza CC BY 4.0. Testo non autentico e gratuito: l'unico
testo ufficiale è quello pubblicato sulla Gazzetta Ufficiale a mezzo stampa.
```

!!! warning "L'attribuzione passa a chi ripubblica"

    L'obbligo passa a te nel momento in cui ridistribuisci. Non basta che la
    libreria conosca l'attribuzione: deve arrivare a chi legge il tuo prodotto.

    Non è possibile accorciarla e restare conformi: le tre menzioni che
    l'avviso legale richiede devono esserci tutte e tre.

## Il testo non è ufficiale

Il testo di Normattiva è una **ricostruzione redazionale**: le modifiche
successive sono state applicate al testo originale da una redazione, che può
sbagliare. La raccolta, per quanto vasta, è frutto di una selezione
redazionale.

**L'unico testo ufficiale e definitivo è quello pubblicato sulla Gazzetta
Ufficiale a mezzo stampa, che prevale in caso di discordanza.**

I dati sono forniti a scopo informativo. La Presidenza del Consiglio dei
Ministri e IPZS non rispondono di eventuali errori o imprecisioni, né dei danni
conseguenti a decisioni prese consultando il portale. A maggior ragione non ne
risponde questa libreria, che è un progetto indipendente e senza garanzie.

Per questo ogni `DettaglioAtto` porta il `permalink` alla pagina pubblica e le
coordinate di Gazzetta: conviene che un documento costruito su questi dati li
includa entrambi, così chi lo legge può risalire alla fonte e verificare.

```python
atto.permalink  # https://www.normattiva.it/uri-res/N2Ls?urn:nir:...
atto.gazzetta  # G.U. n. 192 del 1990-08-18
```

## Verso il servizio

Il servizio è gratuito, non pubblica quote e non garantisce un livello di
servizio. La libreria si autolimita a due richieste al secondo e si presenta
con uno User-Agent che la identifica. Sono scelte di cortesia più che obblighi
tecnici, e mantenerle resta a carico di chi usa la libreria:

```python
Normattiva(user_agent="il-mio-servizio/1.2 (+https://esempio.it/contatti)")
```

Vedi [l'affidabilità](../capire/affidabilita.md).

## Dove leggere le fonti

- [dati.normattiva.it](https://dati.normattiva.it): il portale, con avviso
  legale, informativa e licenza d'uso
- [Come scaricare i dati](https://dati.normattiva.it/come-fare-per): i formati,
  le collezioni e le API
- [Normattiva](https://www.normattiva.it): il portale di consultazione
