# Monitoraggio del contratto

Normattiva è un servizio di terzi che cambia senza preavviso. Questa cartella
serve ad accorgersi dei cambiamenti prima che li incontrino gli utenti della
libreria.

La suite gira ogni notte con
[`contratto.yml`](../../.github/workflows/contratto.yml). Quando qualcosa
cambia apre una issue etichettata `contratto`, e quando lo scostamento rientra
la chiude.

## Cosa verifica

**La forma delle risposte**, in [`test_impronte.py`](test_impronte.py).
Ogni campione del catalogo viene interrogato e la sua risposta ridotta a
un'*impronta*: l'insieme dei cammini che contiene, con i tipi osservati lungo
ciascuno. I valori non contano: un atto viene modificato, un conteggio sale, ed
è normale. Conta che i campi ci siano e siano del tipo registrato.

| Scostamento | Esito | Perché |
|---|---|---|
| un campo sparisce | **fallisce** | il codice che lo leggeva si rompe |
| un campo cambia tipo | **fallisce** | idem |
| un campo diventa anche nullo | passa | il codice che lo trattava come opzionale regge |
| compare un campo nuovo | passa, con avviso | è un'opportunità, non un guasto |
| l'endpoint non risponde | salta | è un guasto del servizio, non un cambio di contratto |

L'ultima riga è deliberata: un monitoraggio che segnala ogni disservizio come
guasto smette di essere letto.

**I percorsi**, in [`test_percorsi.py`](test_percorsi.py).
Le sequenze d'uso reali: cercare e poi leggere, esportare e poi riaprire da
disco, riagganciarsi a un export dal token, percorrere tutta la storia di un
articolo. Le librerie si rompono soprattutto nei punti di integrazione fra le
parti. Ogni metodo pubblico passa di qui almeno una volta, e
[`test_copertura_e2e.py`](../test_copertura_e2e.py) fallisce se qualcosa smette
di essere testato: la copertura è verificata, non dichiarata.

Anche il client asincrono è testato contro il servizio reale, non solo su
risposte simulate: una API che diverge in silenzio viene scoperta da chi la
usa, e tardi.

**Il comportamento**, in [`test_comportamenti.py`](test_comportamenti.py).
Che gli articoli dei codici rispondano solo dal loro allegato, che l'articolo
lungo sia ancora troncato, che l'URN ambiguo restituisca ancora due candidati,
che la finestra di vigenza contenga la data richiesta. Se una di queste
verifiche fallisce, la libreria documenta qualcosa che non è più vero, e in
alcuni casi sarebbe una buona notizia: se IPZS correggesse il troncamento,
`possibile_troncamento` diventerebbe inutile e andrebbe rimosso.

**I valori cablati**, in [`test_valori_stabili.py`](test_valori_stabili.py).
Le enum `Formato` e `ClasseProvvedimento`, le abbreviazioni delle citazioni, la
mappa degli allegati in `codici.py`: decisioni prese osservando il servizio una
volta sola, che qui vengono ricontrollate.

## Il catalogo

[`campioni.py`](campioni.py) elenca i casi, uno per ogni forma di risposta che
ciascun endpoint sa produrre: successi, rifiuti, e le risposte che sembrano
successi e non lo sono. Ogni campione riporta **perché** è nel catalogo: se un
giorno fallisce, quella riga dice che cosa stava proteggendo.

Sono coperti anche gli endpoint che la libreria non usa, come
`atto/dettaglio-atto`: un giorno potrebbe usarli, e conviene sapere in anticipo
se nel frattempo sono cambiati.

## Il dataset

[`dataset/impronte.json`](dataset/) è il riferimento: un'impronta per campione.
Accanto, `dataset/risposte/` conserva le risposte **ridotte**: i testi
troncati, le liste accorciate, la struttura intera. Servono a due cose: capire
rapidamente cos'è cambiato quando il monitoraggio segnala uno scostamento, e
avere un esempio reale di ogni forma senza doverla richiedere al servizio.

Per accettare uno scostamento come nuova normalità:

```bash
uv run python -m tests.contratto.registra
uv run python -m tests.contratto.registra urn_ambiguo ricerca_semplice  # solo alcuni
```

Il registratore va eseguito a mano e con criterio: rigenerare il dataset
significa dichiarare che il nuovo comportamento è quello corretto.

## Buona educazione

Le richieste sono serializzate e distanziate di un secondo e mezzo: il giro
completo richiede un paio di minuti, una volta al giorno. Il servizio non
pubblica quote, ma sotto raffica smette di rispondere e chiede di riprovare più
tardi, come osservato il 2026-08-24 durante la costruzione di questa suite. La
lentezza, qui, è intenzionale.

## In locale

```bash
uv run pytest -m rete                    # tutto il monitoraggio
uv run pytest -m rete -k impronte        # solo la forma
uv run pytest -m rete -k percorsi        # solo i percorsi utente
uv run pytest -m rete -k "not slow"      # senza il giro completo dell'export
```

Un endpoint che non risponde diventa uno `SKIP` con la sua ragione, mai una
cascata di errori. Vale per tutta la suite, non caso per caso: un
`ConnectionError` viene trasformato in skip da un unico gestore in
[`conftest.py`](conftest.py). Il motivo è stato osservato dal vivo il
2026-08-24, quando il servizio ha rallentato sotto le nostre richieste e sono
falliti trentacinque test insieme, per un solo guasto. Un report del genere si
impara a ignorare, ed è esattamente ciò che un monitoraggio non deve
diventare.

La suite normale (`uv run pytest`) non tocca la rete: `-m "not rete"` è nella
configurazione, così nessuno interroga la produzione per sbaglio.
