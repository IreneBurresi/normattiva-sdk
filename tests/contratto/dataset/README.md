# Il dataset del monitoraggio

`impronte.json` è il riferimento: la **forma** di ogni risposta, cioè i cammini
e i tipi osservati lungo ciascuno, senza i valori. È quello che il monitoraggio
confronta ogni notte.

`risposte/` conserva le risposte **ridotte** da cui quelle impronte sono state
calcolate: i testi troncati, le liste accorciate, la struttura intera. Servono a
capire al volo cos'è cambiato quando il monitoraggio segnala, e ad avere sotto
mano un esempio reale di ogni forma senza doverla richiedere.

Si rigenerano a mano, e rigenerarle significa dichiarare che il nuovo
comportamento è quello giusto:

```bash
uv run python -m tests.contratto.registra
```

## Provenienza

Fonte: [Normattiva](https://www.normattiva.it), Istituto Poligrafico e Zecca
dello Stato, in licenza
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.it).
Testo non autentico e gratuito: l'unico testo ufficiale è quello pubblicato
sulla Gazzetta Ufficiale a mezzo stampa.
