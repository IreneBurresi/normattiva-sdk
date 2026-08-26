# Perché la libreria fa così

Alcune scelte di questa libreria sorprendono chi la usa per la prima volta:
un limite che rifiuta invece di troncare, un identificatore che solleva
un'eccezione anziché tentare, metà dei nomi in italiano e metà in inglese.

## Limitare o rifiutare

Due parametri che sembrano fare la stessa cosa fanno l'opposto. Nella ricerca,
`massimo` **limita**: l'iteratore scorre i risultati e si ferma dopo quel
numero. Nell'esportazione, `massimo_atti` **rifiuta**: gli atti vengono contati
prima di partire e, se sono più del limite, l'esportazione non parte affatto.

La differenza sta in chi fa il lavoro. Scorrere una ricerca è lavoro di chi la
chiede: fermarsi a metà risparmia qualche richiesta e non riguarda nessun
altro. Un'esportazione è lavoro del servizio: dura minuti e una volta partita
non si annulla, quindi un filtro che per sbaglio prende mezzo corpus impegna il
servizio fino in fondo.

Contare prima costa una richiesta, e con `massimo_atti=None` si può saltare.

## Non indovinare un identificatore

Delle trenta denominazioni del corpus, diciotto rispondono a un URN composto
secondo la regola standard. Per le altre dodici quella regola non funziona e la
forma corretta non è nota. Per quelle, `AttoTrovato.urn` solleva
[`InvalidUrnError`][normattiva.InvalidUrnError] invece di comporre un URN
plausibile.

Un identificatore inventato non fallisce in modo visibile: ottiene un `404`,
che è la stessa risposta che il servizio dà a un atto inesistente. Chi lo
riceve conclude che l'atto non c'è, e va a cercare altrove un testo che invece
esiste. Sollevare distingue i due casi.

Lo stesso vale per gli allegati dei codici, che la libreria non deduce ma
elenca uno per uno in [`codici`](../riferimento/codici.md), e per la `vigenza`
chiesta a un atto raggiungibile solo dalle coordinate di Gazzetta: quel
percorso le date non le conosce, e ignorare il parametro restituirebbe il testo
di oggi facendolo passare per quello storico.

## Italiano e inglese nello stesso nome

Il confine non è fra italiano e inglese, ma fra dominio e tecnica.

Il dominio giuridico è in italiano: `dettaglio`, `vigenza`, `atto`, `comma`,
`gazzetta`, `cronologia`. Tradurre `vigenza` vorrebbe dire inventare un termine
che nessun giurista riconosce, e la parola inventata sarebbe più difficile da
capire dell'originale, non meno.

Lo strato tecnico è in inglese: `ConnectionError`, `retries`, `timeout`,
`wait()`, `download()`, `ExportStatus`. Sono nomi con una forma canonica, che
chi scrive Python riconosce da qualunque altra libreria; italianizzarli
costringerebbe a impararli di nuovo.

I due mondi si incontrano senza mescolarsi dentro lo stesso nome: `Export` ha
un metodo `wait()` e restituisce `AttoStorico`; `dettaglio()` accetta `vigenza`
e solleva `ConnectionError`. Messaggi d'errore e documentazione restano in
italiano.

## Che cosa non viene esposto

Alcuni campi che la specifica dell'API documenta non hanno un parametro nella
libreria. L'elenco, con la ragione di ciascuno, sta fra
[gli endpoint](../riferimento/endpoint.md#i-campi-non-esposti).

Il criterio è uno solo: un parametro viene esposto se si è visto che ha
effetto. Un parametro accettato e ignorato dal servizio produce risultati
sbagliati che sembrano giusti, e non c'è modo di accorgersene guardando la
risposta; un parametro che non c'è si nota alla prima riga di codice.
