# Il monitoraggio del contratto

Il rischio più serio per una libreria che parla con un servizio di terzi non è
un difetto proprio: è che il servizio cambi senza che nessuno se ne accorga,
finché il problema non arriva a chi la usa. L'API di Normattiva non ha una
specifica pubblicata a cui il servizio si impegni, quindi un cambiamento può
comparire in qualunque momento.

Ogni notte, alle 05:17 UTC, una suite interroga la produzione su tutti e
quindici gli endpoint e confronta le risposte con un riferimento registrato.
Per il solo riassunto basta
[l'affidabilità](../capire/affidabilita.md#il-monitoraggio).

## Le impronte

Ogni risposta viene ridotta a un'*impronta*: l'insieme dei cammini che
contiene, con i tipi osservati lungo ciascuno. I valori non entrano nel
confronto, perché cambiano di continuo ed è normale che lo facciano. Conta che
i campi ci siano, e che siano del tipo registrato.

| Scostamento | Esito | Perché |
|---|---|---|
| un campo sparisce | **fallisce** | il codice che lo leggeva si rompe |
| un campo cambia tipo | **fallisce** | idem |
| un campo diventa anche nullo | passa | il codice che lo trattava come opzionale regge |
| compare un campo nuovo | passa, con avviso | è un'opportunità, non un guasto |
| l'endpoint non risponde | **salta** | il servizio è in avaria; il contratto è un'altra cosa |

L'ultima riga è la più importante. Un servizio in avaria fa fallire tutti i
test insieme, e un monitoraggio che segnala ogni disservizio come scostamento
smette di essere letto. Un unico gestore trasforma quindi ogni
`ConnectionError` in uno skip motivato; uno scostamento vero continua a
fallire.

## Cosa verifica oltre le impronte

**I percorsi.** Le sequenze d'uso reali: cercare e poi leggere, esportare e poi
riaprire da disco, riagganciarsi a un export dal token, percorrere tutta la
storia di un articolo.

**I comportamenti.** Che l'articolo lungo sia ancora troncato, che l'URN
ambiguo restituisca ancora due candidati, che gli articoli dei codici
rispondano solo dal loro allegato, che i nomi dei file dell'export dichiarino
ancora la vigenza. Sono i comportamenti su cui la libreria fa affidamento, e il
test serve ad accorgersi del giorno in cui smettono di essere veri.

**I valori cablati.** Le enum, le abbreviazioni delle citazioni, la mappa degli
allegati: decisioni prese osservando il servizio una volta sola, che qui
vengono ricontrollate.

## Chi controlla che la copertura resti

Un test legge il sorgente della suite di contratto e fallisce se un metodo
pubblico, una proprietà o un errore smette di comparirvi. Le poche esclusioni
riportano la ragione per cui sono escluse.

Anche il client asincrono viene esercitato contro il servizio reale, non solo
su risposte simulate.

## Eseguirlo

```bash
uv run pytest -m rete               # tutto il monitoraggio
uv run pytest -m rete -k "not slow" # senza il giro completo dell'export
```

La suite predefinita non tocca la rete: `-m "not rete"` è nella configurazione,
così nessuno interroga la produzione per sbaglio.

## Quando qualcosa cambia

Il workflow apre una issue etichettata `contratto` con il report, e la chiude
quando lo scostamento rientra. Se lo scostamento è la nuova normalità, si
accetta rigenerando il riferimento:

```bash
uv run python -m tests.contratto.registra
```

Va fatto a mano e con criterio: rigenerare significa dichiarare che il nuovo
comportamento è quello corretto.
