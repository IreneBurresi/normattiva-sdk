# Un atto intero

Quarta e ultima lezione. Finora abbiamo letto un articolo per volta. Qui
prendiamo un atto intero, con tutte le sue versioni, e lo rileggiamo da disco
senza tornare in rete.

Questa lezione fa una richiesta lunga: l'esportazione impiega circa un minuto.

```python
from datetime import date

from normattiva import Normattiva

with Normattiva() as normattiva:
    ...
```

## Perché non basta `dettaglio`

Il percorso che abbiamo usato finora restituisce un articolo alla volta, e degli
articoli molto lunghi restituisce solo i primi cento commi. L'esportazione
restituisce l'atto completo, articolato e versioni comprese, e non si ferma ai
cento commi.

In cambio non è immediata: si avvia, si attende, si scarica.

## Avviamo e attendiamo

```python
esportazione = normattiva.start_export(anno=1990, numero=241)
print(esportazione.token)

esportazione.wait()
corpus = esportazione.download()

atto = corpus.atti[0]
print(
    f"{atto.estremi.citazione}: {len(atto.versioni)} versioni, "
    f"{len(atto.aggiornamenti)} aggiornamenti"
)
```

```
07e1fef4-c8d6-47a7-8b5c-00cdd6080817
L. 7 agosto 1990, n. 241: 61 versioni, 60 aggiornamenti
```

Il `token` identifica il lavoro presso il servizio, e sarà diverso ogni volta.
Serve se il programma che aspetta finisce prima dell'esportazione: con
`normattiva.export_from_token(token)` ci si riaggancia più tardi, senza
ricominciare.

`wait()` aspetta che il servizio abbia finito; `download()` scarica l'archivio e
lo legge in modelli. Sessantuno versioni, per una legge del 1990: ogni modifica
in trentasei anni ne ha aperta una nuova.

## Leggiamo l'atto a una data

`alla_data` sceglie la versione in vigore quel giorno, e da lì si scorrono gli
articoli:

```python
vigente_nel_2005 = atto.alla_data(date(2005, 1, 1))
articoli = list(vigente_nel_2005.articoli())

print(f"in vigore dal {vigente_nel_2005.vigente_dal}, {len(articoli)} articoli")
print(next(a.testo for a in articoli if a.numero == "19")[:80])
```

```
in vigore dal 2004-04-29, 34 articoli
Art. 19.

 ((1. In tutti i casi in cui l'esercizio di un'attivita' privata
```

È la stessa domanda della seconda lezione, ma adesso la risposta arriva da
un archivio già in memoria: nessuna richiesta in più, e tutti gli articoli
insieme invece di uno per volta.

Gli accenti qui sono vocale più apostrofo, `attivita'`: nell'esportazione
arrivano così. Per confrontare o cercare nel testo c'è `normalize_accents`, che
riscrive `attivita'` come `attività`.

## Salviamo e rileggiamo

```python
corpus.save("241.zip")
```

```python
from normattiva import Corpus

di_nuovo = Corpus.from_zip("241.zip")
print(len(di_nuovo.atti[0].versioni))
```

```
61
```

Da qui in avanti l'atto si rilegge da disco quante volte serve, senza chiedere
di nuovo al servizio la stessa cosa.

## Che cosa abbiamo fatto

In quattro lezioni abbiamo letto il testo di un articolo, l'abbiamo riletto a
due date del passato, ne abbiamo percorso la storia, trovato un atto partendo
dalle parole e infine scaricato un atto intero con tutte le sue versioni.

Da qui:

- le guide di [come fare](../come-fare/index.md), una per obiettivo:
  identificare un atto, cercarlo, leggerlo a una data, esportarlo intero,
  lavorare in asincrono, usarlo dal terminale;
- [capire](../capire/index.md), per com'è fatto il servizio e perché la libreria
  si comporta così;
- il [taccuino Jupyter](https://github.com/ireneburresi/normattiva-sdk/blob/main/esempi/normattiva-in-pratica.ipynb),
  che percorre la libreria su dati reali con gli output già dentro.
