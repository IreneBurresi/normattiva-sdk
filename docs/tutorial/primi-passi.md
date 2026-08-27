# Primi passi

L'API di Normattiva non chiede chiavi né registrazione: servono solo Python e
una connessione.

```bash
pip install normattiva-sdk
```

## Apriamo il client

`Normattiva` è la classe da cui passa tutto: apre le connessioni verso l'API e
ha un metodo per ciascuna cosa che si può chiedere. Il `with` la chiude quando
il blocco finisce.

```python
from normattiva import Normattiva

with Normattiva() as normattiva:
    ...
```

Il codice che segue sta dentro quel blocco.

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

Se articolo, comma e rubrica non ti sono familiari, il vocabolario è spiegato in
[come è fatto un atto](../capire/come-e-fatto-un-atto.md). Per la lezione basta
quello che abbiamo appena visto.

La finestra è il punto di partenza della prossima lezione:
[il testo a una data](il-testo-a-una-data.md).
