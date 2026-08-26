# Esempi

## `normattiva-in-pratica.ipynb`

Un notebook che percorre la libreria su dati reali: legge un articolo, mostra
la stessa norma a date diverse, ne ricostruisce la storia in una tabella e in
un grafico, cerca nel corpus, mostra le trappole del servizio ed esporta un
atto intero.

Le celle interrogano il servizio, quindi serve una connessione. Gli output
salvati nel notebook sono quelli del 25 agosto 2026: si possono leggere senza
eseguire nulla; per avere i dati aggiornati basta rieseguire le celle.

```bash
pip install normattiva-sdk pandas matplotlib jupyterlab
jupyter lab normattiva-in-pratica.ipynb
```

`pandas` e `matplotlib` servono al notebook, non alla libreria: mostrano come i
modelli passano in una tabella e in un grafico. La libreria da sola dipende
solo da `httpx`.

L'ultima cella salva `241.zip` nella cartella da cui si esegue il notebook. Il
file è ignorato da git.

Fonte: [Normattiva](https://www.normattiva.it), dati rilasciati da IPZS in
licenza CC BY 4.0. Il testo non ha carattere di ufficialità.
