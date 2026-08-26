# Installare la libreria

Il pacchetto si chiama `normattiva-sdk`, il modulo da importare si chiama
`normattiva`.

=== "pip"

    ```bash
    pip install normattiva-sdk
    ```

=== "uv"

    ```bash
    uv add normattiva-sdk
    ```

=== "poetry"

    ```bash
    poetry add normattiva-sdk
    ```

## Che cosa serve

Python da 3.10 a 3.14, e nient'altro da configurare: l'API open data di
Normattiva risponde senza chiave, senza token e senza registrazione. L'unica
dipendenza a runtime è [httpx](https://www.python-httpx.org/) da 0.28 in su. Il
pacchetto porta `py.typed`, quindi mypy, pyright e ty leggono i tipi senza stub.

L'installazione porta anche il comando `normattiva`, descritto in
[usare la riga di comando](usare-la-riga-di-comando.md).

## Verificare che funzioni

```python
from normattiva import Normattiva

with Normattiva() as normattiva:
    atto = normattiva.dettaglio("urn:nir:stato:legge:1990-08-07;241~art1")
    print(atto.testo)
```

Se stampa il testo dell'articolo 1 della legge sul procedimento amministrativo,
l'installazione è a posto. Il passo successivo è il
[tutorial](../tutorial/primi-passi.md).

!!! tip "Il client si riusa"

    `Normattiva` tiene aperto un pool di connessioni e si autolimita a due
    richieste al secondo. Costruiscine uno per processo e passalo alle funzioni
    che ne hanno bisogno: l'autolimitazione conta le richieste di un client,
    quindi con un client per chiamata ogni richiesta parte senza attendere le
    altre.

## Lavorare sulla libreria stessa

Per clonare il repository, far girare le prove e costruire la documentazione,
vedi [sviluppo](../progetto/sviluppo.md).
