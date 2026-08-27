# Gli atti notissimi

Ogni voce è un [`AttoNoto`][normattiva.AttoNoto]: l'atto nel suo insieme, più
l'allegato attraverso cui rispondono i suoi articoli.

::: normattiva.AttoNoto

## L'elenco

| Costante | Atto |
|---|---|
| `COSTITUZIONE` | Costituzione della Repubblica |
| `CODICE_CIVILE` | R.D. 16 marzo 1942, n. 262 |
| `CODICE_PENALE` | R.D. 19 ottobre 1930, n. 1398 |
| `CODICE_PROCEDURA_CIVILE` | R.D. 28 ottobre 1940, n. 1443 |
| `CODICE_PROCEDURA_PENALE` | D.P.R. 22 settembre 1988, n. 447 |
| `CODICE_AMMINISTRAZIONE_DIGITALE` | D.Lgs. 7 marzo 2005, n. 82 |
| `CODICE_PRIVACY` | D.Lgs. 30 giugno 2003, n. 196 |
| `CODICE_DELLA_STRADA` | D.Lgs. 30 aprile 1992, n. 285 |
| `CODICE_DEL_CONSUMO` | D.Lgs. 6 settembre 2005, n. 206 |
| `TUIR` | D.P.R. 22 dicembre 1986, n. 917 |
| `TESTO_UNICO_EDILIZIA` | D.P.R. 6 giugno 2001, n. 380 |
| `STATUTO_DEI_LAVORATORI` | L. 20 maggio 1970, n. 300 |

Gli articoli di ciascuno rispondono attraverso l'allegato indicato da
`allegato_articoli`, che `articolo()` mette nell'URN al posto tuo.

::: normattiva.codici
    options:
      show_root_heading: false
      members: true
      filters: ["!^AttoNoto$"]
