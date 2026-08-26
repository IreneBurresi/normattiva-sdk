---
hide:
  - toc
---

# Capire

Che cosa sono gli oggetti che la libreria restituisce, com'è fatto il servizio
che li produce e come la libreria si comporta quando quel servizio risponde
male. Per scrivere le prime righe di codice bastano il
[tutorial](../tutorial/primi-passi.md) e le guide di
[Come fare](../come-fare/index.md); queste pagine servono quando serve capire.

| Pagina | A che domanda risponde |
|---|---|
| [Come funziona la normativa italiana](la-normativa-italiana.md) | chi fa le leggi, che rango hanno, come cambiano nel tempo, che cosa Normattiva contiene e che cosa no |
| [Come è fatto un atto](come-e-fatto-un-atto.md) | che cos'è un comma, una rubrica, un decreto-legge, e perché lo stesso testo ha più versioni |
| [Com'è fatto il servizio](il-servizio.md) | chi gestisce Normattiva, che licenza hanno i dati, perché i modelli sono due |
| [Le trappole](trappole.md) | i comportamenti del servizio che danno un risultato plausibile e sbagliato, e come riconoscerli |
| [Gli errori](errori.md) | la gerarchia delle eccezioni, e quando ha senso riprovare |
| [L'affidabilità](affidabilita.md) | retry, autolimitazione, log, e come ci si accorge se l'API cambia |
| [Perché la libreria fa così](scelte.md) | limiti che rifiutano, identificatori che non si indovinano, nomi metà in italiano |

[Le trappole](trappole.md) conviene leggerla per prima: quasi nessuna di quelle
anomalie produce un errore, quindi non si scopre da sé.
