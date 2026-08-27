---
hide:
  - toc
---

# Il progetto

`normattiva-sdk` è un progetto indipendente, non affiliato con IPZS né con la
Presidenza del Consiglio dei Ministri.

- [Licenza e attribuzione](licenza.md): MIT per il codice, CC BY 4.0 per i dati,
  e che cosa comporta l'attribuzione dovuta.
- [Sviluppo](sviluppo.md): come si prepara l'ambiente, si eseguono i test e si
  costruisce la documentazione.
- [Il monitoraggio del contratto](monitoraggio.md): come viene sorvegliata
  l'API di Normattiva, e cosa succede quando cambia.
- [Diario delle modifiche](changelog.md): che cosa è cambiato, versione per
  versione.

## La documentazione in Markdown

Ogni pagina di questo sito esiste anche in Markdown, allo stesso indirizzo con
`index.md` in fondo. Questa pagina, per esempio, si legge anche da
[https://normattiva-sdk.ireneburresi.dev/progetto/index.md](https://normattiva-sdk.ireneburresi.dev/progetto/index.md).

Il Markdown è ricavato dall'HTML costruito e non dal sorgente, quindi contiene
anche il riferimento generato dalle docstring, che nel sorgente è una riga di
direttiva, e i diagrammi restano blocchi ```` ```mermaid ````.

Ci sono poi due file nel formato [llms.txt](https://llmstxt.org), pensati per
chi dà la documentazione in pasto a un modello linguistico:

- [`/llms.txt`](https://normattiva-sdk.ireneburresi.dev/llms.txt), l'indice di tutte le pagine con una riga di
  descrizione ciascuna;
- [`/llms-full.txt`](https://normattiva-sdk.ireneburresi.dev/llms-full.txt), l'intera documentazione in un file
  solo.

Il codice sta su [GitHub](https://github.com/ireneburresi/normattiva-sdk).
