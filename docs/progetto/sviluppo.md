# Sviluppo

Come si prepara l'ambiente, si eseguono le prove e si costruisce la
documentazione di questo repository. Per installare il pacchetto in un
progetto, vedi [Installare la libreria](../come-fare/installare.md).

## Preparare l'ambiente

Serve [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/ireneburresi/normattiva-sdk
cd normattiva-sdk
uv sync --all-groups
```

## I test

```bash
uv run pytest              # la suite offline, su risposte reali registrate
uv run pytest -m rete      # i test di contratto contro il servizio reale
```

La suite predefinita non tocca la rete: `-m "not rete"` è nella
configurazione, così nessuno interroga la produzione per sbaglio. I test di
contratto costituiscono il [monitoraggio del contratto](monitoraggio.md), che
gira ogni notte su GitHub Actions e apre una issue se l'API cambia.

## Lint, formato e tipi

```bash
uv run ruff check
uv run ruff format
uv run ty check src
```

Le stesse verifiche girano in pre-commit e in CI, su Python da 3.10 a 3.14.

## La documentazione

```bash
uv run mkdocs serve
uv run mkdocs build --strict
```

`--strict` fallisce su qualunque link rotto o riferimento non risolto, ed è la
modalità con cui la CI costruisce il sito.

### I diagrammi

Mermaid gira nel browser: `mkdocs build` non ne verifica la sintassi, e un
diagramma sbagliato compare come blocco di testo grezzo. La suite controlla solo
gli errori più comuni (tipo dichiarato, etichette chiuse, archi tratteggiati
scritti bene). Per la verifica vera, con il sito servito in locale, si apre la
console del browser e si esegue:

```javascript
const mermaid = (await import("https://unpkg.com/mermaid@11/dist/mermaid.esm.min.mjs")).default;
const sitemap = await (await fetch("/normattiva-sdk/sitemap.xml")).text();
for (const [, url] of sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)) {
  const html = await (await fetch(new URL(url).pathname)).text();
  const pagina = new DOMParser().parseFromString(html, "text/html");
  for (const blocco of pagina.querySelectorAll("pre.mermaid")) {
    await mermaid.parse(blocco.textContent).catch((e) => console.error(url, e.message));
  }
}
```

Nessun errore in console vuol dire che tutti i diagrammi del sito si disegnano.

Il [riferimento](../riferimento/index.md) è generato dalle docstring con
mkdocstrings, quindi le firme si aggiornano dal codice.
Un test compila ogni blocco Python di queste pagine, esegue quelli
autosufficienti e verifica che ogni riferimento incrociato punti a qualcosa che
esiste.
