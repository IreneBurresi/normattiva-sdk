<div class="nrm-testata" markdown>

# normattiva-sdk

SDK Python non ufficiale per [Normattiva](https://www.normattiva.it), il portale
della legge vigente dello Stato italiano.

```python
from datetime import date
from normattiva import Normattiva, codici

with Normattiva() as normattiva:
    art2043 = normattiva.dettaglio(codici.CODICE_CIVILE.articolo(2043))
    print(art2043.testo)

    divorzio = normattiva.dettaglio(
        "urn:nir:stato:legge:1970-12-01;898~art5", vigenza=date(2005, 1, 1)
    )
    print(divorzio.finestra)  # 1987-03-12 → 2023-02-27
```

</div>

<div class="avvertenza" markdown>
**Progetto indipendente e non ufficiale**, gratuito e in licenza
[MIT](https://github.com/ireneburresi/normattiva-sdk/blob/main/LICENSE). Non è
affiliato con l'[Istituto Poligrafico e Zecca dello Stato](https://www.ipzs.it),
con [Normattiva](https://www.normattiva.it) né con la [Presidenza del Consiglio
dei Ministri](https://www.governo.it), e non è approvato da loro.

I dati arrivano da [dati.normattiva.it](https://dati.normattiva.it) in licenza
[**CC BY 4.0**](https://creativecommons.org/licenses/by/4.0/deed.it), che
obbliga a citarne la fonte. Il testo **non è autentico**: l'unico ufficiale è
quello pubblicato sulla Gazzetta Ufficiale a mezzo stampa, che prevale in caso
di discordanza. [Che cosa comporta](progetto/licenza.md).
</div>

## Che cos'è Normattiva

La banca dati che raccoglie il testo delle leggi dello Stato italiano, curata
dall'Istituto Poligrafico e Zecca dello Stato. Di ogni atto conserva il testo
vigente oggi e quello in vigore in ciascuna data del passato: ogni modifica apre
una versione nuova senza cancellare la precedente, e la legge 241 del 1990 ne ha
61. Alla domanda «cosa dice questo articolo» va quindi sempre affiancato un
«quando».

Lo stesso corpus è pubblicato come open data su
[dati.normattiva.it](https://dati.normattiva.it), con un'API HTTP gratuita che
risponde senza chiave e senza registrazione. `normattiva-sdk` la interroga da
Python: copre tutti e quindici gli endpoint, in versione sincrona e asincrona, e
traduce le risposte in oggetti tipizzati.

Se il diritto italiano non è il tuo mestiere,
[Come funziona la normativa italiana](capire/la-normativa-italiana.md) spiega
chi fa le leggi, che rango hanno, come cambiano nel tempo e come si scrive
l'identificatore di ciascun tipo di atto.

## Da dove cominciare

<div class="grid cards" markdown>

-   :material-school:{ .nrm-icona } **[Tutorial](tutorial/primi-passi.md)**

    Una lezione da fare al terminale. Si parte dal `pip install` e si arriva a
    leggere un articolo, cercarlo per parole e percorrerne la storia.

    Comincia da qui se non hai mai usato la libreria.

-   :material-hammer-wrench:{ .nrm-icona } **[Come fare](come-fare/index.md)**

    Una guida per obiettivo: installare, identificare un atto, cercarlo,
    leggerne il testo a una data, esportarlo intero, lavorare in asincrono,
    usare la riga di comando.

    Vieni qui quando sai già che cosa vuoi ottenere.

-   :material-book-open-variant:{ .nrm-icona } **[Riferimento](riferimento/index.md)**

    Classi, metodi, parametri, eccezioni, endpoint e comandi, con la firma
    esatta di ciascuno.

    Vieni qui quando ti serve un dettaglio preciso.

-   :material-lightbulb-on:{ .nrm-icona } **[Capire](capire/index.md)**

    Com'è fatto un atto, com'è fatto il servizio, che cosa fa la libreria
    quando il servizio risponde male, e perché è fatta così.

    Vieni qui quando vuoi il quadro d'insieme.

</div>

## Cosa si può chiedere

| Cosa | Come |
|---|---|
| Il testo di un atto o di un articolo, a una data | [`dettaglio`][normattiva.Normattiva.dettaglio] |
| Tutte le versioni di un articolo | [`cronologia`][normattiva.Normattiva.cronologia] |
| Ricerca a testo pieno e per coordinate | [`ricerca`][normattiva.Normattiva.ricerca], [`ricerca_avanzata`][normattiva.Normattiva.ricerca_avanzata] |
| Tutte le pagine di una ricerca | [`ricerca_completa`][normattiva.Normattiva.ricerca_completa] |
| Gli atti modificati in un periodo | [`atti_aggiornati`][normattiva.Normattiva.atti_aggiornati] |
| Export di atti interi, multivigente | [`start_export`][normattiva.Normattiva.start_export] |
| Archivi già confezionati | [`collections`][normattiva.Normattiva.collections], [`download_collection`][normattiva.Normattiva.download_collection] |
| I dizionari del servizio | [`denominazioni`][normattiva.Normattiva.denominazioni], [`classi_provvedimento`][normattiva.Normattiva.classi_provvedimento] |

Le stesse capacità sono disponibili dal terminale, con il comando `normattiva`:

```bash
normattiva testo codice-civile --articolo 2043
normattiva cerca procedimento amministrativo --anno 1990 --faccette
normattiva esporta --denominazione LEGGE --anno 1990 --numero 241 --archivio 241.zip
```

## Prima di metterla in produzione

Il servizio ha comportamenti che danno un risultato plausibile e sbagliato senza
sollevare nessun errore: un articolo troncato sembra un articolo corto. Sono
raccolti, con l'esempio che li riproduce e il modo di riconoscerli nel codice,
in [Le trappole](capire/trappole.md).

Il testo che ottieni non è autentico e in caso di discordanza prevale la
Gazzetta Ufficiale; se lo ripubblichi, l'obbligo di attribuzione passa a te.
Che cosa comporta, in pratica, sta in
[Licenza e attribuzione](progetto/licenza.md).
