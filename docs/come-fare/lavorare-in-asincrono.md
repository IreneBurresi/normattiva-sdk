# Lavorare in asincrono

`AsyncNormattiva` ha gli stessi metodi di `Normattiva`, con le stesse firme e lo
stesso comportamento: cambia solo che vanno attesi con `await`.

```python
import asyncio
from normattiva import AsyncNormattiva


async def main() -> None:
    async with AsyncNormattiva() as normattiva:
        atto = await normattiva.dettaglio("urn:nir:stato:legge:1990-08-07;241~art1")
        print(atto.testo)


asyncio.run(main())
```

## Gli iteratori diventano asincroni

```python
async for trovato in normattiva.ricerca_completa("appalti", massimo=100):
    print(trovato.citazione)

async for versione in normattiva.cronologia(urn):
    print(versione.finestra)

async for atto in normattiva.atti_aggiornati(dal, al):
    print(atto.citazione)
```

Restano pigri come gli equivalenti sincroni: una pagina alla volta, e solo
quando serve.

## L'esportazione

```python
esportazione = await normattiva.start_export(anno=1990, numero=241)
await esportazione.wait()
corpus = await esportazione.download()
```

`AsyncExport` ha gli stessi metodi e le stesse proprietà di
`Export`, e `wait` lascia libero il ciclo di eventi: l'attesa fra un
controllo e l'altro passa da `asyncio.sleep`.

## Concorrenza

Il limitatore asincrono usa un `asyncio.Lock`, quindi più corutine che
condividono lo stesso client si mettono in fila da sole:

```python
async with AsyncNormattiva() as normattiva:
    atti = await asyncio.gather(*(normattiva.dettaglio(urn) for urn in urns))
```

Le richieste partono insieme e il client le serve a due al secondo, una alla
volta: il semaforo è già dentro.

!!! trappola "Un client per processo"

    L'autolimitazione conta le richieste di un client. Creandone uno per ogni
    corutina, ciascuno conta le proprie e nessuno conta il totale: cento
    corutine con cento client mandano cento richieste insieme, e sotto quel
    carico il servizio smette di rispondere.

    ```python
    # sbagliato
    async def leggi(urn):
        async with AsyncNormattiva() as n:  # un client per chiamata
            return await n.dettaglio(urn)


    # giusto
    async def leggi(normattiva, urn):
        return await normattiva.dettaglio(urn)
    ```

## Iniettare il proprio client HTTP

Per metriche, tracing o intestazioni aggiuntive:

```python
import httpx

cliente = httpx.AsyncClient(event_hooks={"response": [misura]})
normattiva = AsyncNormattiva(http_client=cliente)
```

Un client iniettato dall'esterno sopravvive a `close()`: chiuderlo spetta a chi
l'ha aperto.

## Quando conviene

L'asincrono non rende le richieste più veloci: l'autolimitazione è la stessa. Usa
`AsyncNormattiva` quando il programma ha altro da fare mentre aspetta, per
esempio un servizio web che nel frattempo serve altre richieste. Per uno script
che scarica e basta, il client sincrono fa la stessa cosa con meno codice.
