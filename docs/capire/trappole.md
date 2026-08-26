# Le trappole

I comportamenti del servizio che sorprendono chi non li conosce, ognuno con
l'esempio che lo riproduce e con il nome che ha nella libreria: una proprietà
da guardare, un errore da catturare.

Quasi nessuno produce un errore: quello che arriva è un risultato plausibile e
sbagliato, che passa inosservato. Un articolo troncato sembra un articolo
corto, e un conteggio di commi fermo a cento sembra un conteggio corretto.

## Gli articoli lunghi sono troncati

Il servizio memorizza gli articoli lunghi a **blocchi di cento commi**, e il
percorso interattivo restituisce solo il primo blocco, senza segnalarlo: nella
risposta non c'è nessun campo che indichi la presenza di altri commi.

L'articolo 1 della legge di bilancio 2017 ha oltre seicento commi:

```python
atto = normattiva.dettaglio("urn:nir:stato:legge:2016-12-11;232~art1")

atto.atto.citazione  # 'L. 11 dicembre 2016, n. 232'
len(atto.commi)  # 105
atto.commi[-1].numero  # '100'
atto.ultimo_comma_numerato  # 100
atto.possibile_troncamento  # True
```

L'indizio del troncamento sta nell'**etichetta dell'ultimo comma**, non nel
numero di commi ricevuti. I commi sono 105 ma l'ultimo si chiama «100», perché
cinque sono aggiunte successive con un ordinale (`85-bis`, `94-bis`, `95-bis`,
`95-ter`, `95-quater`). Il conteggio darebbe 105 e non segnalerebbe nulla;
un'etichetta che cade esattamente su un multiplo di cento, invece, è un indizio
di troncamento.

!!! trappola "`possibile_troncamento` segnala un sospetto"

    Un articolo che finisce davvero al comma cento è indistinguibile da uno
    troncato. Per questo la proprietà si chiama `possibile_troncamento`.

Il sospetto si può trasformare in eccezione:

```python
from normattiva import TruncationError

try:
    normattiva.dettaglio(urn, se_troncato="solleva")
except TruncationError as errore:
    print(errore.ultimo_comma)  # 100
```

**Il testo integrale si ottiene dall'esportazione**, che non tronca.

## Un URN, due atti

Lo stesso URN può corrispondere a due provvedimenti distinti, pubblicati in
Gazzette diverse. Il servizio risponde con l'elenco al posto dell'atto.

```python
from normattiva import AmbiguityError

try:
    normattiva.dettaglio("urn:nir:stato:legge:2001-12-28;448~art2")
except AmbiguityError as errore:
    print(errore)
    for candidato in errore.candidati:
        print(candidato.gazzetta, "|", candidato.titolo)
```

```
l'URN corrisponde a 2 atti distinti: scegliere quale usare
G.U. n. 301 del 2001-12-29, suppl. SO n. 285 | LEGGE 28 dicembre 2001, n. 448
G.U. n. 25 del 2002-01-30, suppl. SO n. 20 | LEGGE 28 dicembre 2001, n. 448
```

I candidati arrivano nella stessa risposta in cui l'ambiguità è emersa, quindi
leggerli non costa richieste aggiuntive.

!!! trappola "I due candidati si distinguono solo dalla Gazzetta"

    Nell'esempio i due titoli sono **identici**. Si distinguono solo dalle
    coordinate di Gazzetta: data, numero e codice redazionale. Non dalla
    lunghezza del testo, che non indica in alcun modo quale sia l'atto giusto.

    La libreria non sceglie automaticamente, perché non ha modo di sapere quale
    dei due intendevi.

## Il servizio non è deterministico

La stessa lettura può rispondere `200` una volta e `400` quella successiva,
senza che nulla sia cambiato nel frattempo: né la richiesta, né l'atto, né i
parametri.

Tutte le chiamate di questa libreria sono letture, quindi ripeterle è sicuro:
un `400` viene **ritentato**. Un `409` no, perché arriva dallo strato di
protezione che rifiuta la forma della richiesta e la rifiuterebbe di nuovo. Il
meccanismo completo è descritto in [L'affidabilità](affidabilita.md).

## Un `500` arriva anche a richieste valide

Quando è in avaria, il servizio risponde `500` con il codice `1000` anche a un
URN **perfettamente valido**:

```json
{"message": "Errore generico, riprovare piu' tardi", "code": 1000}
```

L'avaria può durare diversi minuti. La libreria tratta la risposta come un
guasto del servizio, non come una richiesta da correggere:

```python
from normattiva import ConnectionError, RuleViolationError

try:
    normattiva.dettaglio(urn)
except ConnectionError:
    ...  # il servizio ha un problema: riprovare più tardi ha senso
except RuleViolationError:
    ...  # la richiesta ha un problema: riprovare non serve
```

!!! trappola "Un `5xx` resta un problema del servizio"

    Presentare un `5xx` come regola violata spingerebbe chi lo riceve a
    correggere una richiesta che era già corretta. Un `5xx` descrive lo stato
    del servizio, qualunque codice porti nel corpo.

## Il servizio accetta date che non esistono

Chiedere il 30 febbraio non produce un rifiuto: il servizio risponde comunque
qualcosa. La libreria non manda quelle date, perché lavora con le `date` di
Python, che non possono rappresentare il 30 febbraio, e perché `Urn.parse`
scarta una data impossibile prima di fare la richiesta.

La protezione vale finché si usano oggetti `date`. Costruendo a mano la stringa
dell'URN e usandola altrove, la protezione non si applica.

## Dodici tipi di atto non hanno una forma URN verificata

Delle trenta denominazioni del corpus, diciotto rispondono a un URN composto
secondo la regola standard. Per le altre dodici quella regola non funziona e la
forma corretta non è nota; sono quasi tutte tipologie storiche: «regolamento»,
«decreto del Duce», «regio decreto-legge», «determinazione del commissario per
la produzione bellica».

```python
trovato.ha_urn  # False
trovato.urn  # InvalidUrnError
```

!!! trappola "Perché `urn` solleva invece di comporre un URN a tentativi"

    Un URN costruito per tentativi produce un `404`, che chi lo riceve legge
    come «quest'atto non c'è» mentre il difetto sta nell'identificatore.
    `ha_urn` permette di saperlo prima, senza sollevare.

Questi atti restano comunque leggibili dalle coordinate di Gazzetta: passando a
`dettaglio` il risultato della ricerca, la libreria prende da sé quella strada.
Quel percorso però **non supporta le date**: una `vigenza` chiesta per un atto
raggiungibile solo così solleva `InvalidArgumentError`, perché ignorarla
restituirebbe il testo di oggi al posto di quello storico.

## Nell'export di un codice, `articoli()` non trova gli articoli

Il codice civile è l'allegato di un regio decreto, e nell'archivio
dell'esportazione questa struttura è visibile: l'articolato del decreto
contiene i suoi due articoli di promulgazione, e il codice vero e proprio sta
negli **annessi**.

```python
v = corpus.atti[0].vigente  # corpus: l'export del R.D. 262/1942

len(list(v.articoli()))  # 2
len(v.annessi)  # 404
```

I due articoli sono «Approvazione del testo del Codice civile» e la formula di
sottoscrizione. Gli altri 3280 nodi stanno negli annessi, e `articoli()` non li
trova nemmeno chiamato su di loro: nell'allegato il servizio dichiara quei nodi
come `allegato`, non come `articolo`.

```python
sum(1 for radice in v.annessi for _ in radice.articoli())  # 0
```

!!! trappola "`articoli()` non scende negli annessi"

    `articoli()` percorre i nodi il cui `tipo` è `articolo`, e li percorre
    correttamente. È il servizio a etichettare in modo diverso gli stessi
    oggetti a seconda di dove stanno, e la libreria non riscrive
    quell'etichetta.

    Per scendere negli annessi si percorrono i `figli`:

    ```python
    def foglie(nodo):
        if not nodo.figli:
            yield nodo
        for figlio in nodo.figli:
            yield from foglie(figlio)


    articoli = [n for radice in v.annessi for n in foglie(radice)]
    len(articoli)  # 3280
    articoli[-1].rubrica  # 'Risarcimento per fatto illecito.' per l'art. 2043
    ```

I numeri vengono da un export `VIGENTE` del R.D. 262/1942 del 25 agosto 2026.

## Le partizioni dell'export portano l'etichetta grezza

I nodi che raggruppano gli articoli (capi, titoli, libri) arrivano con `tipo` a
`None` e con l'intera gerarchia concatenata dentro `numero`, separata da
asterischi:

```python
v.annessi[0].numero
# 'Disposizioni sulla legge in generale*-*-*-*CAPO I*Delle fonti del diritto*'
```

Ogni livello occupa due posizioni, etichetta e rubrica, e un trattino indica il
livello assente. La libreria restituisce la stringa così com'è, perché il
formato non è documentato e interpretarlo richiederebbe supposizioni.

## Nell'export gli accenti sono vocale più apostrofo

Il testo dell'esportazione scrive `attivita'` dove il testo interattivo scrive
`attività`. Una ricerca sulla grafia corretta non troverebbe nulla.

```python
from normattiva import normalize_accents

normalize_accents("l'attivita' e' una liberta'")
# "l'attività è una libertà"
```

!!! trappola "Non tutti gli apostrofi sono accenti mancanti"

    In `po'`, `va'`, `fa'`, `de' Medici` l'apostrofo indica un **troncamento**.
    Accentarli produrrebbe `pò`, che in italiano non esiste.

    Alcuni casi restano ambigui anche per un lettore umano: `ne'` può stare per
    «nei» o per «né», `se'` per «sei» o per «sé». Lì la libreria lascia il testo
    com'è: correggere a indovinare cambierebbe una parola del testo di legge.

## La data di vigenza sta nel nome del file

Nell'archivio dell'esportazione, la data da cui una versione vale sta **solo**
nel nome del file. Nessun campo del documento la contiene.

```
LEGGE_19900807_241/1990-08-18_090G0294_ORIGINALE_V0.json
LEGGE_19900807_241/1990-08-18_090G0294_VIGENZA_2005-01-01_V3.json
```

Se IPZS cambiasse quella convenzione, ogni versione diventerebbe
indistinguibile dall'originale, e `alla_data` restituirebbe il testo di
partenza per qualunque data, senza segnalare nulla. Per questo la libreria
**rifiuta** un archivio i cui nomi non dichiarano la versione.

## Che cosa conta come atto «aggiornato»

`atti_aggiornati(dal, al)` restituisce gli atti **modificati** in quella
finestra. Un atto pubblicato dentro la finestra e mai più modificato non
compare.

Le pubblicazioni si richiedono invece con
`ricerca_avanzata(pubblicazione=(dal, al))`.

## Lo scarico sincrono delle collezioni è rotto

`download_collection` restituisce un archivio vuoto. Il difetto sta dal lato di
IPZS, ed era ancora presente il 24 agosto 2026. Finché dura, quelle collezioni
si prendono con `save_collection`, che scrive il file su disco.

## Se una smette di valere

Il servizio può correggere una di queste anomalie in qualsiasi momento. Il
[monitoraggio](affidabilita.md#il-monitoraggio) notturno le ricontrolla una per
una, e questa pagina viene aggiornata quando una di loro non si presenta più.
