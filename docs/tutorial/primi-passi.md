# Primi passi

In questa lezione leggeremo il testo di un articolo di legge, lo rileggeremo
com'era vent'anni fa, ne percorreremo la storia e infine cercheremo un atto
partendo dalle parole. Ci vuole una decina di minuti.

Serve solo Python e una connessione: l'API di Normattiva non chiede chiavi né
registrazione, quindi non c'è niente da configurare prima di cominciare.

```bash
pip install normattiva-sdk
```

Ogni blocco di codice di questa pagina si incolla in un interprete e funziona da
solo.

## Apriamo il client

`Normattiva` è la classe da cui passa tutto: apre le connessioni verso l'API e
ha un metodo per ciascuna cosa che si può chiedere. Va chiusa quando abbiamo
finito, e il `with` la chiude da sé.

```python
from normattiva import Normattiva

with Normattiva() as normattiva:
    ...
```

Da qui in avanti lavoriamo dentro quel blocco.

## Leggiamo un articolo

Gli atti si indirizzano con un URN. Quello che segue si legge «articolo 1 della
legge dello Stato del 7 agosto 1990, numero 241», cioè la legge sul procedimento
amministrativo.

```python
atto = normattiva.dettaglio("urn:nir:stato:legge:1990-08-07;241~art1")

print(atto.titolo)
print(atto.testo)
```

```
LEGGE 7 agosto 1990, n. 241
Art. 1
(Principi generali dell'attività amministrativa)
1. L'attività amministrativa persegue i fini determinati dalla legge ed è retta
da criteri di economicità, di efficacia, di imparzialità, di pubblicità e di
trasparenza secondo le modalità previste dalla presente legge ...
```

Il primo `print` scrive il nome per esteso dell'atto, il secondo il testo
dell'articolo. Notiamo che il testo comincia dal numero dell'articolo e dalla
sua **rubrica**, il titoletto fra parentesi.

## Guardiamo che altro è arrivato

La risposta porta molto più del testo. Chiediamole qualche altra cosa:

```python
print(atto.commi[0])
print(atto.finestra)
print(atto.gazzetta)
print(atto.permalink)
```

```
Comma(numero='1', testo="L'attività amministrativa persegue i fini ...")
2020-09-15 → oggi
G.U. n. 192 del 1990-08-18
https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1990-08-07;241
```

I **commi** sono i capoversi numerati dell'articolo, già separati uno per uno.
La **gazzetta** dice dove l'atto è stato pubblicato, e il **permalink** è il
link alla sua pagina su Normattiva: è quello da mettere in un documento, perché
chi legge possa verificare sulla fonte.

Guardiamo la **finestra**: comincia il 15 settembre 2020, non nel 1990. Dice da
quando a quando vale il testo che abbiamo appena stampato, e ci sta dicendo che
anche l'articolo 1 di questa legge è stato riscritto, l'ultima volta nel 2020.
Il testo di oggi è solo l'ultima di molte versioni.

Se articolo, comma e rubrica non ti sono familiari, il vocabolario è spiegato in
[Come è fatto un atto](../capire/come-e-fatto-un-atto.md). Per la lezione basta
quello che abbiamo appena visto.

## Chiediamo il testo di vent'anni fa

Le leggi cambiano, e Normattiva conserva ogni versione. Per chiedere il testo di
un giorno preciso si aggiunge `vigenza`: qui chiediamo l'articolo 19 della stessa
legge com'era il primo gennaio 2000.

```python
from datetime import date

vecchio = normattiva.dettaglio(
    "urn:nir:stato:legge:1990-08-07;241~art19", vigenza=date(2000, 1, 1)
)

print(vecchio.finestra)
print(vecchio.testo[:60])
```

```
1994-01-01 → 2005-03-07
Art. 19
((1. In tutti i casi in cui l'esercizio di un'attività
```

La finestra non è la data che abbiamo chiesto: è il tratto di tempo che la
contiene. Abbiamo chiesto un giorno, il servizio risponde con la versione in
vigore quel giorno, e ci dice che è rimasta in vigore dal 1994 al marzo 2005.

Proviamo a chiedere lo stesso articolo a un'altra data, per vedere il testo
cambiare:

```python
recente = normattiva.dettaglio(
    "urn:nir:stato:legge:1990-08-07;241~art19", vigenza=date(2015, 1, 1)
)

print(recente.finestra)
print(len(vecchio.testo), "caratteri nel 2000")
print(len(recente.testo), "caratteri nel 2015")
```

```
2014-11-12 → 2015-08-27
1618 caratteri nel 2000
6376 caratteri nel 2015
```

Stesso articolo, stessa legge, due testi diversi: nel 2015 era quattro volte
più lungo, e la finestra che lo conteneva è durata nove mesi. È la ragione per cui la data
va indicata sempre: senza `vigenza` si ottiene il testo di oggi, e nella
risposta non c'è niente che dica a quale data corrisponde.

## Percorriamo tutta la storia

`cronologia` fa lo stesso lavoro per ogni versione, dalla prima pubblicazione a
quella in vigore. Fermiamoci alle prime cinque:

```python
for versione in normattiva.cronologia(
    "urn:nir:stato:legge:1990-08-07;241~art19", massimo=5
):
    print(versione.finestra, len(versione.testo))
```

```
1990-09-02 → 1992-06-10 2205
1992-06-11 → 1993-12-31 3001
1994-01-01 → 2005-03-07 1618
2005-03-08 → 2005-05-14 2440
2005-05-15 → 2009-07-03 3344
```

Una riga per versione: la finestra, e quanti caratteri aveva il testo in quella
finestra. Ogni finestra comincia il giorno dopo la fine della precedente: non ci
sono sovrapposizioni e non ci sono buchi. Questo articolo ha 20 versioni in
tutto, e `massimo=5` ci ha fatto fermare alla quinta.

Ogni elemento è un `DettaglioAtto` completo, con il testo di quella versione:
`cronologia` costa una richiesta per versione, quindi con `massimo` si paga solo
quello che serve.

## Cerchiamo per parole

Finora conoscevamo l'URN. Quando non lo conosciamo, si parte dalle parole:

```python
esito = normattiva.ricerca("procedimento amministrativo", per_pagina=5)

print(esito.totale)
for trovato in esito:
    print(trovato.citazione)
```

```
2159
L. 7 agosto 2026, n. 152
D.P.C.M. 12 giugno 2026, n. 150
D.Lgs. 7 agosto 2026, n. 149
D.Lgs. 5 agosto 2026, n. 141
D.Lgs. 26 giugno 2026, n. 138
```

Il totale e i primi risultati cambiano a ogni nuova pubblicazione, quindi i tuoi
numeri saranno diversi dai nostri. `totale` dice quanti atti ha trovato la
ricerca, mentre le righe stampate sono solo i cinque di questa pagina.
`citazione` scrive ciascun atto come lo si cita nella pratica giuridica.

Dal risultato si torna al testo passando l'oggetto stesso a `dettaglio`, senza
ricostruire nessun identificatore:

```python
primo = esito.atti[0]
print(normattiva.dettaglio(primo).testo[:200])
```

## Il programma completo

```python
from datetime import date

from normattiva import Normattiva, codici

with Normattiva() as normattiva:
    # un articolo di un codice, chiamato per nome
    art2043 = normattiva.dettaglio(codici.CODICE_CIVILE.articolo(2043))
    print(art2043.atto.citazione)
    print(art2043.testo[:200])

    # lo stesso articolo di legge a due date diverse
    for anno in (2000, 2015):
        versione = normattiva.dettaglio(
            "urn:nir:stato:legge:1990-08-07;241~art19", vigenza=date(anno, 1, 1)
        )
        print(anno, versione.finestra, len(versione.testo))

    # e una ricerca per parole
    for trovato in normattiva.ricerca_completa("responsabilità civile", massimo=5):
        print(trovato.citazione)
```

Nell'ultimo blocco compaiono due cose nuove. `codici` conosce per nome gli atti
più citati, e compone l'URN dei loro articoli al posto nostro:
`CODICE_CIVILE.articolo(2043)` è l'articolo sul risarcimento del danno.
`ricerca_completa` scorre da solo le pagine dei risultati, una alla volta.

## Che cosa abbiamo fatto

In questa lezione hai letto il testo di un articolo, l'hai riletto com'era in due
date del passato, ne hai percorso la storia versione per versione e hai trovato
un atto partendo dalle parole. Sono le quattro operazioni di base, e tutto il
resto della libreria le combina.

Da qui:

- [Come fare](../come-fare/index.md), una guida per ciascun obiettivo:
  identificare un atto, cercarlo, leggerlo a una data, esportarlo intero,
  lavorare in asincrono, usarlo dal terminale.
- [Il notebook Jupyter](https://github.com/ireneburresi/normattiva-sdk/blob/main/esempi/normattiva-in-pratica.ipynb),
  che percorre la libreria su dati reali con gli output già dentro.
