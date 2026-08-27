# Trovare un atto

Finora l'URN lo conoscevamo già. Quando non si conosce, si parte dalle parole.

```python
from normattiva import Normattiva

with Normattiva() as normattiva:
    ...
```

## Cerchiamo per parole

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

Le parole vengono combinate in AND: `ricerca("procedimento amministrativo")`
trova gli atti che contengono entrambe.

## Dal risultato al testo

Dal risultato si torna al testo passando l'oggetto stesso a `dettaglio`, senza
ricostruire nessun identificatore:

```python
primo = esito.atti[0]
print(normattiva.dettaglio(primo).testo[:200])
```

Conviene questa strada anche quando l'URN si saprebbe scrivere: per una dozzina
di tipi di atto, quasi tutti storici, una forma URN verificata non esiste, e
`dettaglio` per quelli passa dalle coordinate di Gazzetta.

## Scorriamo più di una pagina

`ricerca` restituisce una pagina per volta. Quando servono più risultati, a
scorrere le pagine pensa `ricerca_completa`:

```python
for trovato in normattiva.ricerca_completa("responsabilità civile", massimo=5):
    print(trovato.citazione)
```

È un iteratore pigro: chiede una pagina alla volta e si ferma dove ci fermiamo
noi, quindi cinque risultati costano una richiesta sola. Senza `massimo` scorre
fino in fondo, e le ricerche larghe hanno migliaia di risultati.

## Gli atti che hanno un nome

Per i codici e per gli atti più citati non serve né cercare né comporre l'URN a
mano: `codici` li conosce per nome.

```python
from normattiva import codici

art2043 = normattiva.dettaglio(codici.CODICE_CIVILE.articolo(2043))

print(art2043.atto.citazione)
print(art2043.testo[:120])
```

```
R.D. 16 marzo 1942, n. 262
Art. 2043.
(Risarcimento per fatto illecito).
Qualunque fatto doloso o colposo, che cagiona ad altri un danno ingiusto, obb
```

La citazione dice regio decreto perché il codice civile è, formalmente, un
allegato al R.D. 262 del 1942. È anche il motivo per cui `codici` esiste: gli
articoli dei codici rispondono solo attraverso l'allegato in cui furono
approvati, e quale sia cambia da codice a codice.

Finora abbiamo letto un articolo per volta. Nell'ultima lezione l'atto arriva
intero: [un atto intero](un-atto-intero.md).
