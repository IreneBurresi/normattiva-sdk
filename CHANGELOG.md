# Diario delle modifiche

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/), e le
versioni il [versionamento semantico](https://semver.org/lang/it/).

## Non ancora rilasciato

Prima versione. Finché non esce la 0.1.0 l'API pubblica può ancora cambiare
senza preavviso.

### Aggiunto

- `Normattiva` e `AsyncNormattiva`: dettaglio a una data, cronologia di un
  articolo, ricerca semplice e per coordinate, atti aggiornati, dizionari,
  collezioni preconfezionate ed esportazione asincrona.
- `Urn`, con i costruttori dei tipi di atto più comuni e il permalink pubblico.
- `codici`: gli atti notissimi con l'allegato attraverso cui i loro articoli
  rispondono.
- `Corpus` e `AttoStorico`: un export si riapre da disco senza rete, e
  `alla_data` restituisce la versione in vigore a una data.
- Il comando `normattiva`, che copre le stesse capacità dal terminale: `testo`,
  `cerca`, `cerca-avanzata`, `cronologia`, `aggiornati`, `esporta`,
  `collezioni`, `scarica-collezione`, `dizionario`, `urn`, `codici`. Con
  `--json` l'output diventa un documento per gli script; il codice di uscita
  distingue la richiesta sbagliata, l'atto non trovato e il servizio in avaria.
- Un notebook Jupyter in `esempi/`, eseguito su dati reali e con gli output
  salvati.
- Monitoraggio giornaliero del contratto dell'API su GitHub Actions.
