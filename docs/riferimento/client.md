# Il client sincrono

`Normattiva` è la classe da cui passa tutto: tiene aperta la connessione HTTP
verso l'API, il limitatore di richieste e la politica dei retry, ed espone un
metodo per ogni endpoint. Si costruisce una volta e si riusa, meglio se dentro
un `with`, che la chiude a fine blocco.

```python
from normattiva import Normattiva

with Normattiva() as normattiva:
    atto = normattiva.dettaglio("urn:nir:stato:legge:1990-08-07;241~art2")
```

```mermaid
stateDiagram-v2
    direction LR
    [*] --> Aperto : Normattiva(...)
    Aperto --> Aperto : dettaglio(), ricerca(), start_export(), ...
    Aperto --> Chiuso : close(), o uscita dal blocco with
    Chiuso --> [*]
    note right of Chiuso
        closed vale True.
        Un http_client passato da fuori
        non viene chiuso: lo chiude chi lo ha aperto.
    end note
```

Per l'uso asincrono c'è [`AsyncNormattiva`](client-asincrono.md), che rispecchia
questa classe metodo per metodo e firma per firma.

::: normattiva.Normattiva
