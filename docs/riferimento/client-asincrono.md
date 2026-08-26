# Il client asincrono

`AsyncNormattiva` rispecchia [`Normattiva`](client.md) metodo per metodo e firma
per firma: cambiano `await` e `async for`, e gli argomenti del costruttore sono
gli stessi, salvo `http_client`, che qui vuole un `httpx.AsyncClient`.

Più corutine che condividono lo stesso client condividono anche la sua
autolimitazione, quindi si mettono in fila da sole. Quando conviene usarlo lo
spiega [lavorare in asincrono](../come-fare/lavorare-in-asincrono.md).

::: normattiva.AsyncNormattiva
