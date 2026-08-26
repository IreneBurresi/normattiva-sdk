# Usare la riga di comando

Il pacchetto installa un comando che si chiama `normattiva`. Copre le stesse
funzioni della libreria, senza scrivere Python: legge il testo di un atto, cerca
nel corpus, percorre le versioni di un articolo, scarica un archivio.

Conviene quando la domanda è una sola e la risposta si legge subito, o quando il
risultato deve finire dentro un altro programma. Se invece stai costruendo
qualcosa che fa molte richieste e ne combina i risultati, la libreria resta più
comoda: la riga di comando non conserva oggetti fra un comando e il successivo.

```bash
normattiva --help
```

## Leggere il testo di un atto

L'argomento `atto` è un URN:

```bash
normattiva testo urn:nir:stato:legge:1990-08-07\;241 --articolo 19
```

Il punto e virgola va protetto dalla shell, con la barra rovesciata come qui
oppure mettendo tutto l'URN fra apici singoli.

I dodici atti più citati si indicano per nome, e in quel caso l'allegato
attraverso cui i loro articoli rispondono lo sceglie il comando:

```bash
normattiva testo codice-civile --articolo 2043
```

```text
REGIO DECRETO 16 marzo 1942, n. 262
Approvazione del testo del Codice civile. (042U0262)

Citazione  R.D. 16 marzo 1942, n. 262
Articolo   2043
Gazzetta   G.U. n. 79 del 1942-04-04
Vigenza    1942-04-19 → oggi
URN        urn:nir:stato:regio.decreto:1942-03-16;262:2~art2043
Permalink  https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:regio.decreto:1942-03-16;262:2~art2043

Art. 2043.
(Risarcimento per fatto illecito).
Qualunque fatto doloso o colposo, che cagiona ad altri un danno ingiusto,
obbliga colui che ha commesso il fatto a risarcire il danno.

Fonte: Normattiva (https://www.normattiva.it), Istituto Poligrafico e Zecca
dello Stato, in licenza CC BY 4.0. Testo non autentico e gratuito: l'unico testo
ufficiale è quello pubblicato sulla Gazzetta Ufficiale a mezzo stampa.
```

L'elenco completo dei nomi è `normattiva codici`, e la stessa tabella con la
spiegazione degli allegati sta in
[Identificare un atto](identificare-un-atto.md).

### Il testo com'era a una certa data

`--vigenza` prende un giorno, oppure la parola `originale`:

=== "a una data"

    ```bash
    normattiva testo urn:nir:stato:legge:1990-08-07\;241 \
        --articolo 19 --vigenza 2000-01-01
    ```

    La riga `Vigenza` dell'intestazione dice in che finestra quel testo è stato
    in vigore: `1994-01-01 → 2005-03-07`, cioè da prima della data chiesta a
    dopo. Nessuna delle due date è quella che hai scritto tu, ed è normale: hai
    chiesto un istante, il servizio risponde con il tratto di tempo che lo
    contiene.

=== "come fu pubblicato"

    ```bash
    normattiva testo urn:nir:stato:legge:1990-08-07\;241 \
        --articolo 19 --vigenza originale
    ```

    Il testo della prima pubblicazione in Gazzetta, prima di qualunque modifica.

=== "oggi"

    ```bash
    normattiva testo urn:nir:stato:legge:1990-08-07\;241 --articolo 19
    ```

    Senza `--vigenza` si ottiene il testo in vigore adesso. Nell'output nulla
    distingue questo caso da una data richiesta e non applicata, quindi per un
    testo storico la data va sempre scritta.

### Gli atti senza URN

Per dodici tipi di atto su trenta, quasi tutti storici, la forma dell'URN non è
verificata: chiederli per URN otterrebbe un 404 senza chiarirne la causa. Quegli
atti si leggono dalle coordinate di Gazzetta, che una ricerca mostra sempre:

```bash
normattiva testo --gazzetta 017U1234 --data 1917-05-20
```

Quella strada però non supporta le date: risponde sempre con il testo di oggi.

## Cercare

```bash
normattiva cerca procedimento amministrativo --anno 1990
```

Le parole vengono combinate in AND dal servizio: non c'è modo di chiedere un OR
né una frase esatta.

Con `--faccette` la risposta mostra anche i valori con cui restringere, con
accanto il nome dell'opzione che li accetta:

```bash
normattiva cerca trasparenza --anno 1990 --faccette
```

```text
8 atti trovati

   1  D.L. 13 novembre 1990, n. 324
      Provvedimenti urgenti in tema di lotta alla criminalita' organizzata e di
      trasparenza e buon andamento dell'attivita' amministrativa.
      urn:nir:stato:decreto.legge:1990-11-13;324

...

--tipo
codice  atti  descrizione
PPR     4     DECRETO DEL PRESIDENTE DELLA REPUBBLICA
PLE     3     LEGGE
PDL     1     DECRETO-LEGGE
```

Le faccette arrivano dentro la stessa risposta della ricerca, quindi non
costano una richiesta in più.

### Una pagina, oppure tutte

Senza `--massimo` si paga una richiesta sola e si ottiene una pagina, che si
sfoglia con `--pagina` e `--per-pagina`. Con `--massimo` il comando scorre le
pagine finché ha raccolto quel numero di atti, e quindi costa più richieste: il
nome dell'opzione rende esplicito il costo.

```bash
normattiva cerca appalti --massimo 200 --json > appalti.json
```

### Cercare per coordinate

Quando l'atto lo sai già identificare, `cerca-avanzata` cerca il tipo, l'anno e
il numero invece delle parole:

```bash
normattiva cerca-avanzata --denominazione LEGGE --anno 1990 --numero 241
```

I valori che `--denominazione` accetta li elenca il servizio:

```bash
normattiva dizionario denominazioni
```

## Percorrere le versioni di un articolo

```bash
normattiva cronologia urn:nir:stato:legge:1990-08-07\;241 --articolo 19 --massimo 4
```

```text
4 versioni di urn:nir:stato:legge:1990-08-07;241~art19

   1  1990-09-02 → 1992-06-10
   2  1992-06-11 → 1993-12-31
   3  1994-01-01 → 2005-03-07
   4  2005-03-08 → 2005-05-14
```

Costa una richiesta per versione, e l'articolo 19 della 241 ne ha venti:
`--massimo` serve a non pagarle tutte quando ne bastano poche.

La data che apre ogni finestra è quella da passare a `normattiva testo
--vigenza` per rileggere quella versione. In JSON l'URN completo è già pronto in
ogni voce, con il suffisso di vigenza attaccato.

!!! trappola "Non tutti gli articoli hanno un originale"

    `cronologia` parte dalla prima pubblicazione. Un articolo inserito da una
    novella, come il 416-bis del codice penale, nel testo originale non c'era: il
    comando esce con `nessun atto per la richiesta` e il codice 3. Non è un
    difetto della richiesta, è la storia di quell'articolo.

## Scaricare un archivio

`esporta` chiede al servizio un archivio con gli atti che i criteri trovano,
attende che sia pronto e lo scrive su disco. I criteri sono gli stessi di
`cerca-avanzata`.

```bash
normattiva esporta --denominazione LEGGE --anno 1990 --numero 241 \
    --archivio 241.zip --verboso
```

```text
normattiva: esportazione avviata, token 0fc601b0-da5c-4bb7-b717-4cfb6648015e
normattiva: in attesa dell'archivio, al più 600 secondi
normattiva: esportazione 0fc601b0-...: stato PROCESSING, 0/61 atti
Archivio    241.zip
Formato     JSON
Dimensione  1.6 MB
Token       0fc601b0-da5c-4bb7-b717-4cfb6648015e
```

Il token viene scritto su stderr **prima** dell'attesa, che dura minuti: se il
comando si interrompe, l'esportazione resta viva dalla parte del servizio e si
riprende senza ricominciarla.

```bash
normattiva esporta --token 0fc601b0-da5c-4bb7-b717-4cfb6648015e --archivio 241.zip
```

Prima di avviarla, il comando conta quanti atti prenderebbero i criteri, e oltre
cento non parte. È il modo di accorgersi che un filtro prende mezzo corpus prima
che il servizio ci lavori per un'ora. Il tetto si alza con `--massimo-atti`,
oppure si toglie del tutto con `--senza-conteggio`, che salta anche la richiesta
di conteggio.

Alcuni archivi il servizio li tiene già pronti, e non c'è niente da attendere:

```bash
normattiva collezioni
normattiva scarica-collezione Codici --archivio codici.zip
```

## Comporre un URN senza toccare la rete

`urn` convalida un identificatore e lo scompone, oppure ne compone uno a partire
dal nome di un atto noto. Non fa nessuna richiesta: se l'URN è malformato lo
segnala subito, senza toccare la rete.

```bash
normattiva urn codice-penale --articolo 416bis --vigenza 2010-01-01
```

```text
urn:nir:stato:regio.decreto:1930-10-19;1398:1~art416bis!vig=2010-01-01

Autorità       stato
Denominazione  regio.decreto
Anno           1930
Data           1930-10-19
Numero         1398
Allegato       1
Articolo       416bis
Versione       2010-01-01
Permalink      https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:regio.decreto:1930-10-19;1398:1~art416bis!vig=2010-01-01
```

L'allegato `1` non è stato dedotto: gli articoli del codice penale furono
approvati come allegato al regio decreto e non rispondono sotto il decreto
stesso. Quale allegato cambia da codice a codice, ed è una delle informazioni
che `normattiva codici` conosce già.

## Passare il risultato a un altro programma

Con `--json` l'output passa da testo impaginato a JSON, per ogni comando:

```bash
normattiva testo codice-civile --articolo 2043 --json | jq -r .testo
```

L'output per il terminale manda a capo i capoversi alla larghezza della
finestra; quello JSON porta il testo con le righe che il servizio ha mandato. La
forma di ogni documento è descritta nel
[riferimento della riga di comando](../riferimento/cli.md#la-forma-del-json).

### Il codice di uscita dice che cosa è andato storto

Dentro uno script si legge il codice, non il messaggio. Quello che serve più
spesso è la distinzione fra `4`, la richiesta da correggere, e `5`, il servizio
da riprovare più tardi; `3` vuol dire che l'atto non c'è. La tabella completa
sta nel [riferimento](../riferimento/cli.md#i-codici-di-uscita).

```bash
if ! normattiva testo "$urn" --json > atto.json; then
    case $? in
        3) echo "quell'atto non c'è" ;;
        5) echo "servizio non disponibile, riprovo dopo" ;;
    esac
fi
```

## Colori e larghezza

I colori compaiono solo quando l'output va a un terminale: redirigendo l'output
in un file o in un altro programma spariscono da soli. Si forzano in un senso o
nell'altro con `--colore sempre` e `--colore mai`, e la variabile d'ambiente
`NO_COLOR` li disattiva senza bisogno di opzioni.

Il testo viene mandato a capo alla larghezza della finestra, fino a un massimo
di cento colonne, perché le righe più lunghe si leggono male.

## Vedere che cosa succede sotto

`--verboso` manda su stderr i log della libreria: i retry, le attese
dell'autolimitazione, gli stati di un'esportazione. Vanno su stderr, così
l'output del comando resta pulito e si può ancora redirigere.

```bash
normattiva cerca appalti --massimo 500 --verboso > appalti.txt
```
