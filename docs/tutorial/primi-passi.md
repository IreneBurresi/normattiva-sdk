# Primi passi

Prima lezione di quattro. Qui installiamo la libreria, apriamo il client e
leggiamo il testo di un articolo di legge. Ci vogliono cinque minuti.

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

Se articolo, comma e rubrica non ti sono familiari, il vocabolario è spiegato in
[come è fatto un atto](../capire/come-e-fatto-un-atto.md). Per la lezione basta
quello che abbiamo appena visto.

## Chiudiamo il client una volta sola

Il client tiene aperte le connessioni e regola la frequenza delle richieste, e
conviene costruirne uno solo per tutta la durata del programma. Aprirne e
chiuderne uno a ogni richiesta funziona, ma butta via le connessioni e riparte
ogni volta dal limite di frequenza.

```python
with Normattiva() as normattiva:
    primo = normattiva.dettaglio("urn:nir:stato:legge:1990-08-07;241~art1")
    secondo = normattiva.dettaglio("urn:nir:stato:legge:1990-08-07;241~art2")
```

## Che cosa abbiamo fatto

Abbiamo installato la libreria, aperto un client, letto il testo di un articolo
e guardato che cosa arriva insieme al testo: i commi separati, la pubblicazione
in Gazzetta, il link pubblico e la finestra di vigenza.

Quella finestra è il punto di partenza della prossima lezione:
[il testo a una data](il-testo-a-una-data.md).
