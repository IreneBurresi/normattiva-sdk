# normattiva-sdk

[![PyPI](https://img.shields.io/pypi/v/normattiva-sdk?label=PyPI)](https://pypi.org/project/normattiva-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/normattiva-sdk?label=Python)](https://pypi.org/project/normattiva-sdk/)
[![Scaricamenti](https://img.shields.io/pypi/dm/normattiva-sdk?label=scaricamenti)](https://pypistats.org/packages/normattiva-sdk)
[![CI](https://github.com/ireneburresi/normattiva-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/ireneburresi/normattiva-sdk/actions/workflows/ci.yml)
[![Contratto](https://github.com/ireneburresi/normattiva-sdk/actions/workflows/contratto.yml/badge.svg)](https://github.com/ireneburresi/normattiva-sdk/actions/workflows/contratto.yml)
[![Licenza del codice: MIT](https://img.shields.io/badge/licenza%20del%20codice-MIT-blue)](https://github.com/ireneburresi/normattiva-sdk/blob/main/LICENSE)
[![Licenza dei dati: CC BY 4.0](https://img.shields.io/badge/licenza%20dei%20dati-CC%20BY%204.0-lightgrey)](https://creativecommons.org/licenses/by/4.0/deed.it)
[![Tipizzato: PEP 561](https://img.shields.io/badge/tipizzato-PEP%20561-blue)](https://peps.python.org/pep-0561/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![standard-readme compliant](https://img.shields.io/badge/readme%20style-standard-brightgreen.svg)](https://github.com/RichardLitt/standard-readme)

SDK non ufficiale per Normattiva, il portale della legge vigente dello Stato italiano

[Normattiva](https://www.normattiva.it) conserva di ogni atto tutte le versioni
che si sono succedute: il testo vigente oggi e quello in vigore in ciascuna data
del passato, perché ogni modifica apre una versione nuova senza cancellare la
precedente. Si chiama multivigenza. La legge 241 del 1990 ha sessantuno
versioni, e per leggerne una si indica la data che interessa.

Lo stesso corpus è pubblicato come open data su
[dati.normattiva.it](https://dati.normattiva.it), con un'API HTTP gratuita che
risponde senza chiave e senza registrazione. Questa libreria la interroga da
Python, in versione sincrona e asincrona, e traduce le risposte in oggetti
tipizzati.

> **Progetto indipendente e non ufficiale.** Non è affiliato con l'[Istituto
> Poligrafico e Zecca dello Stato](https://www.ipzs.it), con
> [Normattiva](https://www.normattiva.it) né con la [Presidenza del Consiglio
> dei Ministri](https://www.governo.it), e non è approvato da loro. Il testo
> restituito non è autentico: l'unico ufficiale è quello pubblicato sulla
> Gazzetta Ufficiale a mezzo stampa, che prevale in caso di discordanza.

## Indice

- [Installazione](#installazione)
- [Uso](#uso)
  - [Riga di comando](#riga-di-comando)
- [Documentazione](#documentazione)
- [API](#api)
- [Manutentori](#manutentori)
- [Contribuire](#contribuire)
- [Licenza](#licenza)

## Installazione

```bash
pip install normattiva-sdk
```

Si installa come `normattiva-sdk` e si importa come `normattiva`.
L'installazione porta anche il comando `normattiva`.

### Dipendenze

Python da 3.10 a 3.14, e [httpx](https://www.python-httpx.org/) come unica
dipendenza a runtime. Il pacchetto dichiara i propri tipi secondo il
[PEP 561](https://peps.python.org/pep-0561/).

## Uso

```python
from datetime import date

from normattiva import Normattiva, Urn, codici

with Normattiva() as normattiva:
    art2043 = normattiva.dettaglio(codici.CODICE_CIVILE.articolo("2043"))
    print(art2043.testo)

    divorzio = normattiva.dettaglio(Urn.legge(1970, 898, articolo="5"), vigenza=date(2005, 1, 1))
    print(divorzio.finestra)  # 1987-03-12 → 2023-02-27
```

Ogni `DettaglioAtto` porta il testo e ciò che serve a citarlo e a verificarlo
alla fonte:

```python
atto.testo  # il testo piano, senza le note redazionali
atto.commi  # (Comma(numero="1", testo="..."), ...)
atto.note_aggiornamento  # le note di aggiornamento, separate dal testo
atto.finestra  # la finestra di vigenza in cui quel testo è valido
atto.permalink  # il link pubblico, per verificare sulla fonte
atto.attribuzione  # la citazione che la licenza dei dati richiede
```

### Riga di comando

```bash
normattiva testo codice-civile --articolo 2043
normattiva cerca procedimento amministrativo --anno 1990 --faccette
normattiva cronologia urn:nir:stato:legge:1990-08-07\;241 --articolo 19
normattiva esporta --denominazione LEGGE --anno 1990 --numero 241 --archivio 241.zip
```

Con `--json` l'output è un documento pronto per `jq`, e il codice di uscita
distingue le famiglie di errore: `3` l'atto non esiste, `4` la richiesta era
sbagliata, `5` il servizio è in avaria.

## Documentazione

<https://ireneburresi.github.io/normattiva-sdk/>

Il [tutorial](https://ireneburresi.github.io/normattiva-sdk/tutorial/primi-passi/)
porta dall'installazione al testo di un articolo; le guide di
[Come fare](https://ireneburresi.github.io/normattiva-sdk/come-fare/) sono una
per obiettivo; [Capire](https://ireneburresi.github.io/normattiva-sdk/capire/)
spiega com'è fatto il servizio e come si comporta la libreria quando il servizio
risponde male; il
[Riferimento](https://ireneburresi.github.io/normattiva-sdk/riferimento/) elenca
classi, metodi ed eccezioni.

## API

`Normattiva` e `AsyncNormattiva` coprono tutti e quindici gli endpoint e si
rispecchiano metodo per metodo; nella versione asincrona gli iteratori diventano
iteratori asincroni.

| | |
|---|---|
| `dettaglio()`, `cronologia()` | il testo di un atto a una data, e tutte le sue versioni |
| `ricerca()`, `ricerca_completa()` | una pagina di risultati, o un iteratore pigro su tutte |
| `start_export()`, `export_from_token()` | avviare un'esportazione, o riprenderne una dal suo token |
| `wait()`, `download()` | attendere che finisca e leggerne il risultato |
| `Corpus.from_zip()`, `save()` | rileggere e salvare un archivio senza rete |
| `Urn.legge()`, `Urn.decreto_legislativo()` | comporre gli identificatori NIR |
| `codici` | gli atti notissimi, con l'allegato attraverso cui rispondono |
| `NormattivaError` e discendenti | una classe per percorso di gestione |

Gli errori che indicano una richiesta sbagliata sono tutti `ValueError` oltre
che `NormattivaError`, così si prendono insieme senza sapere quale strato li ha
sollevati.

Un [taccuino Jupyter](https://github.com/ireneburresi/normattiva-sdk/blob/main/esempi/normattiva-in-pratica.ipynb)
percorre la libreria su dati reali, con gli output salvati.

## Manutentori

[Irene Burresi](https://github.com/ireneburresi).

## Contribuire

Le domande e le segnalazioni vanno negli
[issue](https://github.com/ireneburresi/normattiva-sdk/issues). Le pull request
sono benvenute: per un cambiamento sostanziale conviene aprire prima un issue,
così si discute l'impostazione prima che sia scritta.

```bash
uv sync --all-groups
uv run pytest              # la suite offline, su risposte reali registrate
uv run pytest -m rete      # le prove di contratto, contro il servizio reale
uv run ruff check && uv run ruff format --check
uv run ty check src
```

Le prove di contratto interrogano la produzione e restano fuori
dall'esecuzione predefinita: come funziona il monitoraggio è spiegato in
[tests/contratto/](https://github.com/ireneburresi/normattiva-sdk/blob/main/tests/contratto/README.md).
Le prove nuove partono da una risposta reale registrata: quelle già raccolte
stanno in `tests/fixtures/` e in `tests/contratto/dataset/`.

## Licenza

Il **codice** è rilasciato con licenza [MIT](https://spdx.org/licenses/MIT.html),
Copyright (c) 2026 Irene Burresi. Il testo completo sta in
[LICENSE](https://github.com/ireneburresi/normattiva-sdk/blob/main/LICENSE).

I **dati** sono di IPZS, in licenza
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.it) dal 1° gennaio
2026. L'uso commerciale e la ridistribuzione sono consentiti, e l'unico obbligo
è l'attribuzione, che l'avviso legale del portale vuole in tre parti: la fonte,
il carattere non autentico del testo e la sua gratuità. Ogni modello la espone
già completa:

```
Fonte: Normattiva (https://www.normattiva.it), Istituto Poligrafico e Zecca
dello Stato, in licenza CC BY 4.0. Testo non autentico e gratuito: l'unico
testo ufficiale è quello pubblicato sulla Gazzetta Ufficiale a mezzo stampa.
```

L'obbligo passa a chi ridistribuisce: se pubblichi qualcosa costruito su questi
dati, quella riga va inclusa. Non è accorciabile restando conformi, perché le
tre menzioni devono esserci tutte.
