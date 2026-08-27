# Cercare un atto

Ci sono due ricerche, e rispondono a due domande diverse.

- [`ricerca`][normattiva.Normattiva.ricerca] cerca **parole nel testo** degli
  atti. Serve quando sai di che cosa parla l'atto ma non come si chiama.
- [`ricerca_avanzata`][normattiva.Normattiva.ricerca_avanzata] cerca
  **coordinate**: tipo, anno, numero, date di emanazione e di pubblicazione.
  Serve quando l'atto lo sai già identificare, almeno in parte.

Le due si combinano, perché `ricerca_avanzata` accetta anche un criterio
`testo`.

## Cercare per parole

```python
from normattiva import Normattiva

with Normattiva() as normattiva:
    esito = normattiva.ricerca("silenzio assenso", per_pagina=3)

print(esito.totale, "atti trovati")
print("pagina", esito.pagina, "di", esito.pagine)

for trovato in esito:
    print(trovato.citazione, "|", trovato.titolo[:50])
```

```
65 atti trovati
pagina 1 di 22
L. 20 aprile 2026, n. 50 | Conversione in legge, con modificazioni, del d
D.L. 19 febbraio 2026, n. 19 | Ulteriori disposizioni urgenti per l'attu
L. 2 dicembre 2025, n. 182 | Disposizioni per la semplificazione e la di
```

I numeri cambiano a ogni nuova pubblicazione: quelli qui sopra sono un esempio
della forma, non un valore stabile.

Il servizio combina le parole in **AND**: `"silenzio assenso"` trova gli atti
che contengono entrambe le parole, ovunque siano nel testo. Non c'è modo di
chiedere un OR né una frase esatta.

### Che cosa arriva indietro

[`EsitoRicerca`][normattiva.EsitoRicerca] è **una pagina** di risultati, non
tutti i risultati:

| Attributo | Che cos'è |
|---|---|
| `totale` | quanti atti ha trovato la ricerca in tutto |
| `atti` | gli atti di questa pagina, come tupla |
| `pagina`, `pagine` | il numero di questa pagina e quante ce ne sono |
| `ultima_pagina` | `True` quando non c'è altro da chiedere |
| `faccette` | i valori con cui restringere, vedi sotto |

L'oggetto è iterabile, e itera sugli atti di questa pagina.

!!! warning "`len(esito)` non esiste"

    Non è definito apposta: `len` di una pagina di 20 risultati su 65 trovati
    non direbbe quale dei due numeri. Usa `len(esito.atti)`
    per questa pagina e `esito.totale` per la ricerca.

Ogni elemento di `atti` è un [`AttoTrovato`][normattiva.AttoTrovato], che porta
le coordinate dell'atto ma **non il testo**:

```python
trovato = esito.atti[0]

trovato.estremi.denominazione  # 'LEGGE'
trovato.estremi.data           # datetime.date(2026, 4, 20)
trovato.estremi.numero         # '50'
trovato.citazione              # 'L. 20 aprile 2026, n. 50'
trovato.titolo                 # 'Conversione in legge, con modificazioni, del ...'
trovato.gazzetta               # G.U. n. 91 del 2026-04-20
trovato.gazzetta.codice_redazionale  # '26G00067'
trovato.ha_urn                 # True
trovato.urn                    # urn:nir:stato:legge:2026-04-20;50
```

Il **codice redazionale** è l'identificativo che IPZS assegna al singolo
documento pubblicato in Gazzetta. Non è leggibile e non è un URN, ma è l'unico
identificatore che hanno gli atti per cui una forma URN non esiste: vedi
[identificare un atto](identificare-un-atto.md#dal-risultato-di-una-ricerca-allurn).

### Dal risultato al testo

Il testo costa una seconda richiesta, e si chiede passando il risultato stesso a
`dettaglio`, senza ricostruire nessun identificatore:

```python
for trovato in normattiva.ricerca_completa("responsabilità civile", massimo=5):
    atto = normattiva.dettaglio(trovato)
    print(trovato.citazione, len(atto.testo), "caratteri")
```

`dettaglio` accetta l'`AttoTrovato` e sceglie da sé la strada: per URN dove la
forma è verificata, per coordinate di Gazzetta dove non lo è.

### Restringere con le faccette

Ogni risposta porta tre elenchi di valori con cui restringere la ricerca.
Arrivano dentro la risposta della ricerca stessa, quindi leggerli non costa una
richiesta in più.

```python
esito = normattiva.ricerca("silenzio assenso")

print(esito.faccette.per_tipo[:3])
print(esito.faccette.per_anno[:3])
```

```
(Faccetta(codice='PLE', conteggio=21, descrizione='LEGGE'),
 Faccetta(codice='PLL', conteggio=15, descrizione='DECRETO LEGISLATIVO'),
 Faccetta(codice='PDL', conteggio=14, descrizione='DECRETO-LEGGE'))
(Faccetta(codice='2010', conteggio=6, descrizione='2010'),
 Faccetta(codice='2011', conteggio=5, descrizione='2011'),
 Faccetta(codice='2015', conteggio=4, descrizione='2015'))
```

Di ogni [`Faccetta`][normattiva.Faccetta]: `codice` è il valore da passare come
filtro, `descrizione` è quella da mostrare a chi legge, `conteggio` dice quanti
atti restano scegliendo quella voce. I codici come `PLE` o `PLL` sono quelli
interni del servizio; l'elenco completo lo restituisce `denominazioni()`.

Le tre faccette si ripassano alla ricerca come parametri:

```python
esito = normattiva.ricerca("silenzio assenso", tipo="PLE", anno=2010)
```

!!! note "`anno` vuol dire due cose diverse"

    In `ricerca`, `tipo`, `anno` ed `emettitore` sono **faccette**: restringono
    l'elenco che la ricerca ha già trovato. In `ricerca_avanzata`, `anno` è
    invece l'anno di emanazione dell'atto, cioè una sua coordinata. Portano lo
    stesso nome perché così li chiama il servizio.

## Cercare per coordinate

```python
from datetime import date

from normattiva import ClasseProvvedimento, Normattiva

with Normattiva() as normattiva:
    esito = normattiva.ricerca_avanzata(
        denominazione="DECRETO-LEGGE",
        emanazione=(date(2020, 3, 1), date(2020, 6, 30)),
        classe=ClasseProvvedimento.AGGIORNATO,
        per_pagina=50,
    )

print(esito.totale)
```

La risposta ha la stessa forma di quella di `ricerca`, faccette comprese.

I criteri accettati sono tipo, data a pezzi (`anno`, `mese`, `giorno`), numero,
parole nel titolo o nel testo, vigenza a una data, classe redazionale e i due
intervalli di date. L'elenco completo, con il tipo di ciascuno, sta in
[`ricerca_avanzata`][normattiva.Normattiva.ricerca_avanzata].

**`denominazione` vuole il nome esatto del dizionario**, cioè `"LEGGE"` o
`"DECRETO LEGISLATIVO"`, non l'abbreviazione. I valori ammessi li elenca
`denominazioni()`, ed è l'unico modo di conoscerli: non c'è una regola per
ricavarli. Che differenza ci sia fra i tipi di atto lo spiega
[come è fatto un atto](../capire/come-e-fatto-un-atto.md#i-tipi-di-atto).

**Gli intervalli sono coppie, e un estremo può mancare:**

```python
emanazione = (date(2020, 1, 1), None)      # dal 2020 in poi
emanazione = (None, date(1950, 12, 31))    # fino al 1950
```

**`classe` è la classificazione redazionale dell'atto**, non il suo stato
giuridico: `SENZA_AGGIORNAMENTI` è un atto mai modificato, `AGGIORNATO` un atto
modificato almeno una volta, `ABROGATO` un atto abrogato. Che cosa comporti
l'abrogazione lo spiega
[come è fatto un atto](../capire/come-e-fatto-un-atto.md#la-vita-di-un-atto-nel-tempo).

Senza nessun criterio la ricerca avanzata risponde con l'intero corpus, oltre
duecentomila atti: è una richiesta ammessa, e la prima pagina costa quanto
qualunque altra.

## Scorrere tutte le pagine

`ricerca_completa` scorre le pagine da solo. È un iteratore **pigro**: chiede
una pagina alla volta, e solo quando la precedente è esaurita.

=== "Sincrono"

    ```python
    for trovato in normattiva.ricerca_completa("divorzio"):
        print(trovato.citazione)
    ```

=== "Asincrono"

    ```python
    async for trovato in normattiva.ricerca_completa("divorzio"):
        print(trovato.citazione)
    ```

Consumarne dieci risultati costa una richiesta sola, non tutte quelle che
servirebbero ad arrivare in fondo. `massimo` ferma l'iterazione:

```python
primi_dieci = list(normattiva.ricerca_completa("appalti", massimo=10))
```

Qui `massimo` **limita** senza rifiutare: se gli atti sono di più, gli altri
semplicemente non vengono prodotti. Nell'esportazione lo stesso concetto si
comporta all'opposto, e il perché sta in
[perché la libreria fa così](../capire/scelte.md#limitare-o-rifiutare).

Per sapere quanti sono prima di scorrerli basta una `ricerca` con una pagina
minima:

```python
quanti = normattiva.ricerca("appalti", per_pagina=1).totale
if quanti < 500:
    atti = list(normattiva.ricerca_completa("appalti"))
```

!!! tip "`per_pagina` decide quante richieste servono"

    Il predefinito è 50 in `ricerca_completa` e 20 in `ricerca`. Alzarlo riduce
    il numero di richieste a parità di risultati, e con l'autolimitazione a due
    richieste al secondo la differenza è misurabile: mille atti a 20 per pagina
    sono cinquanta richieste e venticinque secondi, a 100 per pagina sono dieci
    richieste e cinque secondi.

## Gli atti modificati in un periodo

`atti_aggiornati` risponde a una domanda diversa dalle due ricerche: quali atti
sono stati **modificati** fra due date.

```python
from datetime import date

for atto in normattiva.atti_aggiornati(date(2026, 1, 1), date(2026, 6, 30)):
    print(atto.citazione, atto.ultima_modifica, atto.atti_modificanti)
```

```
D.L. 22 maggio 2026, n. 89 2026-06-27 ('26G00129',)
D.L. 30 aprile 2026, n. 63 2026-06-27 ('26G00129',)
D.L. 30 aprile 2026, n. 62 2026-06-27 ('26G00128',)
```

`atti_modificanti` contiene i codici redazionali di Gazzetta degli atti che
hanno prodotto la modifica. Non sono URN e non sono titoli: per risalire al
testo di quegli atti servirebbe anche la loro data di pubblicazione, che il
servizio qui non manda.

!!! warning "«Aggiornato» vuol dire modificato, non pubblicato"

    Un atto pubblicato dentro la finestra e mai più toccato non compare in
    questo elenco. Le pubblicazioni si chiedono con
    `ricerca_avanzata(pubblicazione=(dal, al))`.

Il servizio rifiuta le finestre più lunghe di dodici mesi. La libreria le spezza
da sé, quindi un intervallo di dieci anni funziona e costa dieci richieste:

```python
storia = list(normattiva.atti_aggiornati(date(2016, 1, 1), date(2026, 1, 1)))
```

Se `al` precede `dal`, la libreria solleva
[`RuleViolationError`][normattiva.RuleViolationError] con il codice
`DATE_INVERTITE` prima di toccare la rete.

## I dizionari del servizio

I valori che i criteri accettano non sono liberi: li elenca il servizio.

```python
for voce in normattiva.denominazioni():
    print(voce.codice, voce.descrizione)
```

```
COS COSTITUZIONE
DCT DECRETO
PCG DECRETO DEL CAPO DEL GOVERNO
3NA DECRETO DEL CAPO DEL GOVERNO, PRIMO MINISTRO SEGRETARIO DI STATO
...
```

Sono trenta denominazioni, molte storiche. Gli altri due dizionari sono più
corti:

```python
normattiva.classi_provvedimento()
# (Tipologica(codice='1', descrizione='atto normativo – senza aggiornamenti'),
#  Tipologica(codice='2', descrizione='atto normativo – aggiornato'),
#  Tipologica(codice='3', descrizione='atto normativo – abrogato'))

normattiva.export_formats()
# (Tipologica(codice='AKN', descrizione='Esporta AKN'), ...)
```

I tre dizionari cambiano di rado, quindi la libreria li tiene in memoria dopo la
prima chiamata. Per forzare una rilettura, `reload=True`.
