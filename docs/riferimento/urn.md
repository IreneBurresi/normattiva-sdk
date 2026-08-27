# Gli identificatori

`Urn` rappresenta un URN NIR, l'indirizzo con cui Normattiva identifica gli
atti. Si compone dai pezzi, si legge da una stringa con `parse` e si trasforma
con i metodi `con_*`, che restituiscono sempre un URN nuovo. Nessuna di queste
operazioni tocca la rete: un identificatore malformato viene rifiutato subito.

Come si usa, con gli esempi, sta in
[identificare un atto](../come-fare/identificare-un-atto.md).

## Le parti di un URN

```
urn:nir:stato:legge:1990-08-07;241:2~art5-com3!vig=2005-01-01
     │    │     │        │       │ │   │    │    │
     │    │     │        │       │ │   │    │    └── vigenza a una data
     │    │     │        │       │ │   │    └─────── comma
     │    │     │        │       │ │   └──────────── articolo
     │    │     │        │       │ └──────────────── allegato
     │    │     │        │       └────────────────── numero
     │    │     │        └────────────────────────── data di emanazione
     │    │     └─────────────────────────────────── denominazione
     │    └───────────────────────────────────────── autorità emanante
     └────────────────────────────────────────────── schema
```

| Parte | Attributo | Obbligatoria |
|---|---|---|
| autorità emanante | `autorita` | sì, sempre `stato` |
| denominazione | `denominazione` | sì, nella forma NIR (`regio.decreto`) |
| data di emanazione | `data` | no: senza, l'URN porta solo l'anno |
| anno | `anno` | sì |
| numero | `numero` | sì, tranne per la Costituzione |
| allegato | `allegato` | solo per gli atti che rispondono da un allegato |
| articolo | `articolo` | no |
| comma | `comma` | no, e il servizio lo rifiuta in ingresso |
| vigenza | `versione` | no |

Il campo si chiama `versione` perché nella grammatica NIR il suffisso dopo
l'atto individua la *versione* del documento; `vigenza` è il nome con cui la si
chiede, in `con_vigenza` e in `dettaglio`.

::: normattiva.Urn
