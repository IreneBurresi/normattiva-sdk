# Il testo a una data

Seconda lezione di quattro. Nella prima abbiamo visto che ogni risposta porta
una finestra di vigenza. Qui la usiamo: chiediamo il testo di un giorno preciso,
confrontiamo due versioni dello stesso articolo e percorriamo tutta la storia.

Riprendiamo da dove eravamo, dentro il blocco `with`:

```python
from datetime import date

from normattiva import Normattiva

with Normattiva() as normattiva:
    ...
```

## Chiediamo il testo di vent'anni fa

Le leggi cambiano, e Normattiva conserva ogni versione. Per chiedere il testo di
un giorno preciso si aggiunge `vigenza`: qui chiediamo l'articolo 19 della legge
241 com'era il primo gennaio 2000.

```python
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

## Confrontiamo due date

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

Stesso articolo, stessa legge, due testi diversi: nel 2015 era quattro volte più
lungo, e la finestra che lo conteneva è durata nove mesi. È la ragione per cui
la data va indicata sempre. Senza `vigenza` si ottiene il testo di oggi, e nella
risposta non c'è niente che dica a quale data corrisponde.

## Chiediamo una data prima dell'articolo

Non tutte le date hanno una risposta. L'articolo 19 esiste dal 1990, quindi il
1985 cade fuori dalla sua vita:

```python
from normattiva import NotYetInForceError

try:
    normattiva.dettaglio(
        "urn:nir:stato:legge:1990-08-07;241~art19", vigenza=date(1985, 1, 1)
    )
except NotYetInForceError as errore:
    print("niente da leggere:", errore)
```

```
niente da leggere: l'articolo non era ancora in vigore alla data richiesta
(in vigore dal 1990-09-02)
```

L'errore dice anche da quando l'articolo esiste, così la data si corregge senza
doverla cercare altrove. La libreria solleva invece di restituire la versione
più vicina, che sarebbe il testo di un giorno diverso da quello chiesto.

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
finestra. Ogni finestra comincia il giorno dopo la fine della precedente, senza
sovrapposizioni e senza buchi. Questo articolo ha 20 versioni in tutto, e
`massimo=5` ci ha fatto fermare alla quinta.

Ogni elemento è un `DettaglioAtto` completo, con il testo di quella versione.
`cronologia` costa una richiesta per versione, quindi con `massimo` si paga solo
quello che serve.

## Che cosa abbiamo fatto

Abbiamo chiesto il testo di una data precisa, letto la finestra che il servizio
restituisce insieme al testo, confrontato due versioni dello stesso articolo e
percorso la sua storia una versione per volta.

Finora l'identificatore lo conoscevamo già. Nella prossima lezione partiamo
dalle parole: [trovare un atto](trovare-un-atto.md).
