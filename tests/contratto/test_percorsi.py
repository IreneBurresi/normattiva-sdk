"""I percorsi che un utente fa davvero, dall'inizio alla fine.

Le impronte guardano le risposte una per una; qui si guardano le catene: cercare
e poi leggere, esportare e poi riaprire da disco, riagganciarsi a un export
avviato prima. È dove i pezzi si toccano che le librerie si rompono.

Ogni metodo pubblico del client passa di qui almeno una volta, e lo garantisce
`test_copertura.py`, che fallisce se qualcosa smette di essere provato.
"""

from __future__ import annotations

import io
import zipfile
from contextlib import suppress
from datetime import date, timedelta
from itertools import pairwise

import pytest

from normattiva import (
    ARTICOLO,
    AmbiguityError,
    AttoTrovato,
    ConnectionError,
    Corpus,
    DettaglioAtto,
    EstremiAtto,
    ExportFailedError,
    ExportStatus,
    InvalidArgumentError,
    InvalidUrnError,
    Normattiva,
    NotYetInForceError,
    OverloadedError,
    PubblicazioneGazzetta,
    RuleCode,
    RuleViolationError,
    TooManyResultsError,
    TruncationError,
    Urn,
    codici,
    normalize_accents,
)
from normattiva._wire import _VERSIONE_FILE
from normattiva.modelli import ExportMode, Format

pytestmark = [pytest.mark.rete, pytest.mark.timeout(600)]

L241 = "urn:nir:stato:legge:1990-08-07;241"


def _leggendo(client: Normattiva, urn) -> DettaglioAtto | None:
    """Il dettaglio, oppure None se l'atto ha più pubblicazioni.

    Un atto ambiguo è un esito legittimo di questo percorso, non un guasto:
    l'ambiguità ha una prova tutta sua in TestTrappole.
    """
    with suppress(AmbiguityError):
        return client.dettaglio(urn)
    return None


class TestDallaRicercaAlTesto:
    """Il percorso più comune: non so l'URN, so le parole."""

    def test_cerco_scelgo_e_leggo(self, client: Normattiva, nonostante_i_guasti) -> None:
        esito = nonostante_i_guasti(client.ricerca, "procedimento amministrativo", per_pagina=5)
        assert esito.atti
        trovato = next(
            (a for a in esito.atti if a.estremi.numero and a.ha_urn),
            None,
        )
        if trovato is None:
            pytest.skip("nessun risultato di un tipo di atto con forma URN verificata")
        assert trovato.citazione
        assert trovato.gazzetta.codice_redazionale
        atto = _leggendo(client, trovato.urn)
        if atto is None:
            return
        assert atto.testo
        assert atto.permalink.startswith("https://www.normattiva.it/uri-res/")

    def test_leggo_un_atto_di_cui_non_so_comporre_l_urn(
        self, client: Normattiva, nonostante_i_guasti
    ) -> None:
        """Dodici tipi di atto su trenta non hanno una forma URN verificata.

        Restavano illeggibili: si trovavano cercando e poi ci si fermava. Il
        servizio però li rende dalle coordinate di Gazzetta, che il risultato
        della ricerca porta già, come verificato su un decreto-legge
        luogotenenziale del 1917. Se un giorno smettesse, questa prova cade e la libreria torna a
        promettere una lettura che non può fare.
        """
        senza_urn = None
        for parola in ("regolamento", "luogotenenziale", "commissario"):
            esito = nonostante_i_guasti(client.ricerca, parola, ordine="vecchio", per_pagina=50)
            senza_urn = next((a for a in esito.atti if not a.ha_urn), None)
            if senza_urn is not None:
                break
        if senza_urn is None:
            pytest.skip("nessun atto di tipo non mappato in queste pagine")

        with pytest.raises(InvalidUrnError):
            _ = senza_urn.urn
        atto = client.dettaglio(senza_urn)
        assert atto.testo
        assert atto.estremi.denominazione == senza_urn.estremi.denominazione

        diretto = client.dettaglio_da_gazzetta(
            senza_urn.gazzetta.codice_redazionale or "", senza_urn.gazzetta.data
        )
        assert diretto.testo == atto.testo, "il ponte e la primitiva devono dare lo stesso testo"

    def test_una_vigenza_su_quella_strada_e_un_errore_non_un_silenzio(
        self, client: Normattiva
    ) -> None:
        """`dataVigenza` esiste nello schema di dettaglio-atto ma non ha effetto.

        Accettarla e scartarla darebbe il testo di oggi spacciandolo per storico.
        """
        finto = AttoTrovato(
            estremi=EstremiAtto("DECRETO DEL DUCE", date(1938, 1, 1), "1"),
            gazzetta=PubblicazioneGazzetta(date(1938, 1, 1), codice_redazionale="038U0001"),
            titolo="",
        )
        with pytest.raises(InvalidArgumentError, match="richiede un URN"):
            client.dettaglio(finto, vigenza=date(1940, 1, 1))

    def test_cerco_per_coordinate_e_leggo(self, client: Normattiva, nonostante_i_guasti) -> None:
        esito = nonostante_i_guasti(
            client.ricerca_avanzata, denominazione="LEGGE", anno=1990, numero=241
        )
        assert esito.totale >= 1
        assert esito.atti[0].gazzetta.codice_redazionale == "090G0294"

    def test_scorro_tutte_le_pagine(self, client: Normattiva, nonostante_i_guasti) -> None:
        quanti = nonostante_i_guasti(client.ricerca, "divorzio", per_pagina=1).totale
        atti = list(client.ricerca_completa("divorzio", per_pagina=20))
        assert len(atti) == quanti, "la paginazione non ha raccolto tutti i risultati"
        assert len(atti) > 20, "la prova non attraversa più di una pagina"
        assert len({a.gazzetta.codice_redazionale for a in atti}) == len(atti)

    def test_il_limite_si_ferma_dove_gli_ho_detto(self, client: Normattiva) -> None:
        """Chiedere al più cinque atti costa una pagina, non duecento."""
        atti = list(client.ricerca_completa("decreto", massimo=5))
        assert len(atti) == 5

    def test_un_export_troppo_largo_non_parte_nemmeno(
        self, client: Normattiva, nonostante_i_guasti
    ) -> None:
        """Qui il limite deve rifiutare: l'export è lavoro del servizio, non nostro."""

        def esporta_tutte_le_leggi() -> None:
            client.start_export(denominazione="LEGGE", massimo_atti=5)

        with pytest.raises(TooManyResultsError) as errore:
            nonostante_i_guasti(esporta_tutte_le_leggi)
        assert errore.value.totale > 5


class TestPointInTime:
    """Il motivo per cui esiste Normattiva: il testo a una data."""

    def test_leggo_lo_stesso_articolo_a_due_date_diverse(self, client: Normattiva) -> None:
        vecchio = client.dettaglio(f"{L241}~art19", vigenza=date(2000, 1, 1))
        odierno = client.dettaglio(f"{L241}~art19")
        assert vecchio.testo != odierno.testo
        assert vecchio.finestra is not None
        assert vecchio.finestra.contiene(date(2000, 1, 1))

    def test_il_testo_originale(self, client: Normattiva) -> None:
        originale = client.dettaglio(f"{L241}~art1", vigenza="originale")
        assert originale.testo

    def test_la_finestra_resa_copre_sempre_la_data_chiesta(self, client: Normattiva) -> None:
        """La verifica che protegge da `ValidityMismatchError` non deve mai scattare.

        Quell'errore è una rete di sicurezza contro un servizio che risponda con
        la versione sbagliata: finché non lo fa, il modo di provarla è verificare
        che non serva.
        """
        for giorno in (date(1975, 1, 1), date(1990, 1, 1), date(2010, 1, 1)):
            atto = client.dettaglio("urn:nir:stato:legge:1970-12-01;898~art5", vigenza=giorno)
            assert atto.finestra is not None
            assert atto.finestra.contiene(giorno)

    def test_un_articolo_non_ancora_nato(self, client: Normattiva) -> None:
        with pytest.raises(NotYetInForceError) as errore:
            client.dettaglio(codici.CODICE_PENALE.articolo("416bis"), vigenza=date(1975, 1, 1))
        assert errore.value.vigente_dal is None or errore.value.vigente_dal.year >= 1975

    def test_percorro_tutta_la_storia_di_un_articolo(self, client: Normattiva) -> None:
        versioni = list(client.cronologia(f"{L241}~art19"))
        assert len(versioni) > 5, "l'articolo più emendato della 241 ha più di cinque versioni"
        finestre = [v.finestra for v in versioni if v.finestra]
        assert len(finestre) == len(versioni)
        for prima, dopo in pairwise(finestre):
            assert prima.fine is not None
            assert dopo.inizio == prima.fine + timedelta(days=1), "le finestre non si incastrano"
        assert finestre[-1].aperta


class TestTrappole:
    def test_il_troncamento_si_puo_far_esplodere(self, client: Normattiva) -> None:
        troncabile = "urn:nir:stato:legge:2016-12-11;232~art1"
        assert client.dettaglio(troncabile).possibile_troncamento
        with pytest.raises(TruncationError):
            client.dettaglio(troncabile, se_troncato="solleva")

    def test_l_ambiguita_arriva_coi_candidati_distinguibili(self, client: Normattiva) -> None:
        with pytest.raises(AmbiguityError) as errore:
            client.dettaglio("urn:nir:stato:legge:2001-12-28;448~art2")
        candidati = errore.value.candidati
        assert len(candidati) >= 2
        assert len({c.gazzetta.data for c in candidati}) == len(candidati)

    def test_il_comma_viene_tolto_dall_urn(self, client: Normattiva) -> None:
        """Un URN col comma è rifiutato dal servizio; la libreria lo spoglia e chiede l'articolo.

        L'atto qui usato ha due pubblicazioni: che risponda con l'ambiguità invece
        che con un 400 è già la prova che il comma non è arrivato al servizio.
        """
        citazione = Urn.parse("urn:nir:stato:legge:2007-12-24;244~art2-com428")
        assert citazione.comma == "428"
        with pytest.raises(AmbiguityError):
            client.dettaglio(citazione)

    def test_il_testo_arriva_gia_separato(self, client: Normattiva) -> None:
        """Le note redazionali, il preambolo e i commi: tre cose diverse, tenute distinte."""
        articolo = client.dettaglio(f"{L241}~art19")
        assert articolo.testo
        assert articolo.note_aggiornamento, "l'art. 19 porta note di aggiornamento"
        assert "AGGIORNAMENTO" not in articolo.testo
        assert articolo.commi, "l'articolo è marcato per commi"
        assert articolo.commi_presenti == len(articolo.commi)
        assert articolo.commi[0].numero == "1"

    def test_la_formula_di_promulgazione_resta_fuori_dal_testo(self, client: Normattiva) -> None:
        atto = client.dettaglio(L241)
        assert atto.preambolo, "l'atto intero porta la formula di promulgazione"
        assert "La Camera dei deputati" in atto.preambolo
        assert "La Camera dei deputati" not in atto.testo

    def test_l_html_interattivo_porta_gli_accenti_veri(self, client: Normattiva) -> None:
        """Sul percorso interattivo gli accenti arrivano come entità HTML, già corretti."""
        testo = client.dettaglio(f"{L241}~art1").testo
        assert "attività" in testo
        assert "&agrave;" not in testo


class TestLimitiDelServizio:
    def test_oltre_dodici_mesi_l_intervallo_viene_spezzato(self, client: Normattiva) -> None:
        oggi = date.today()
        atti = list(client.atti_aggiornati(oggi - timedelta(days=400), oggi - timedelta(days=1)))
        assert isinstance(atti, list)

    def test_le_date_invertite_non_partono_nemmeno(self, client: Normattiva) -> None:
        oggi = date.today()
        with pytest.raises(RuleViolationError) as errore:
            list(client.atti_aggiornati(oggi, oggi - timedelta(days=30)))
        assert errore.value.regola is RuleCode.DATE_INVERTITE

    def test_il_feed_degli_aggiornati_porta_le_sue_coordinate(self, client: Normattiva) -> None:
        oggi = date.today()
        atti = list(client.atti_aggiornati(oggi - timedelta(days=60), oggi - timedelta(days=1)))
        if not atti:
            pytest.skip("nessun atto modificato negli ultimi due mesi")
        assert any(a.ultima_modifica for a in atti)


class TestLimitiCheNonCiSono:
    def test_un_anno_prima_dell_unita_risponde_vuoto(self, client: Normattiva) -> None:
        """Non inventiamo limiti: il servizio accetta la domanda e dice che non c'è nulla."""
        assert client.ricerca_avanzata(anno=1848).totale == 0


class TestDizionari:
    def test_i_tre_dizionari_e_le_ricerche_predefinite(self, client: Normattiva) -> None:
        assert client.denominazioni()
        assert client.classi_provvedimento()
        assert client.export_formats()
        assert client.ricerche_predefinite()

    def test_la_cache_non_ripete_la_richiesta(self, client: Normattiva) -> None:
        assert client.denominazioni() is client.denominazioni()
        assert client.denominazioni(reload=True) == client.denominazioni()


class TestCollezioni:
    def test_il_catalogo_elenca_gli_archivi_pronti(self, client: Normattiva) -> None:
        collezioni = client.collections()
        assert collezioni
        assert all(c.name and c.total_atti >= 0 for c in collezioni)

    def test_un_formato_illeggibile_lo_dice_prima_di_scaricare(self, client: Normattiva) -> None:
        with pytest.raises(ValueError, match="save_collection"):
            client.download_collection("Leggi di delegazione europea", format=Format.AKN)

    def test_salvo_una_collezione_in_akn(self, client: Normattiva, tmp_path) -> None:
        piccola = min(client.collections(), key=lambda c: c.total_atti)
        percorso = client.save_collection(
            piccola.nome, tmp_path / "collezione.zip", format=Format.AKN
        )
        if percorso.stat().st_size == 0:
            pytest.skip("lo scarico sincrono delle collezioni restituisce un archivio vuoto")
        assert percorso.stat().st_size > 0

    def test_scarico_la_collezione_piu_piccola(self, client: Normattiva) -> None:
        piccola = min(client.collections(), key=lambda c: c.total_atti)
        try:
            corpus = client.download_collection(piccola.nome, mode=ExportMode.ORIGINALE)
        except Exception as guasto:
            pytest.skip(f"lo scarico sincrono delle collezioni non funziona: {guasto}")
        assert corpus.atti


@pytest.fixture(scope="session")
def esportazione_conclusa(client: Normattiva):
    """Un export vero, fatto una volta sola: costa un minuto e mezzo.

    Senza conteggio preventivo di proposito: l'atto è uno solo e noto, e legare
    tutte le prove dell'export alla disponibilità della ricerca avanzata
    trasformerebbe un guasto di quell'endpoint in una decina di errori altrove.
    Il conteggio ha la sua prova a parte.
    """
    try:
        esportazione = client.start_export(
            denominazione="LEGGE",
            anno=1990,
            numero=241,
            mode=ExportMode.MULTIVIGENTE,
            massimo_atti=None,
        )
        esportazione.wait()
    except (ConnectionError, ExportFailedError, OverloadedError) as guasto:
        pytest.skip(f"l'esportazione non è disponibile: {guasto}")
    return esportazione


@pytest.mark.slow
class TestEsportazione:
    def test_l_export_si_conclude(self, esportazione_conclusa) -> None:
        assert esportazione_conclusa.status is ExportStatus.COMPLETED

    def test_il_corpus_porta_l_atto_con_la_sua_storia(self, esportazione_conclusa) -> None:
        corpus = esportazione_conclusa.download()
        assert len(corpus) == 1
        atto = corpus.atti[0]
        assert str(atto.urn) == L241
        assert len(atto.versioni) > 30, "il multivigente deve portare tutte le versioni"
        assert atto.aggiornamenti

    def test_i_file_dichiarano_ancora_la_vigenza_nel_nome(self, esportazione_conclusa) -> None:
        """La data di vigenza sta solo nel nome del file, e va guardata come un campo.

        Nessun campo del documento la porta: se IPZS cambia la convenzione, ogni
        versione diventa indistinguibile dall'originale e `alla_data` risponde il
        testo di partenza per qualunque data. Da quando `_versione` rifiuta un
        nome che non la dichiara il guasto è rumoroso, ma è qui che si vede
        arrivare: dal monitoraggio, non da chi usa la libreria.
        """
        archivio = zipfile.ZipFile(io.BytesIO(esportazione_conclusa.download().archive))
        documenti = [n for n in archivio.namelist() if n.lower().endswith(".json")]
        assert documenti
        senza_versione = [n for n in documenti if not _VERSIONE_FILE.search(n)]
        assert senza_versione == [], (
            "l'archivio non segue più la convenzione da cui si legge la data di vigenza: "
            f"per esempio {senza_versione[0]!r}"
        )
        assert sum(1 for n in documenti if "ORIGINALE" in n.upper()) == 1

    def test_la_versione_a_una_data_esce_dal_corpus(self, esportazione_conclusa) -> None:
        atto = esportazione_conclusa.download().atti[0]
        versione = atto.alla_data(date(2005, 1, 1))
        assert versione.vigente_dal is not None
        assert versione.vigente_dal <= date(2005, 1, 1)
        articoli = list(versione.articoli())
        assert articoli
        assert all(a.tipo == ARTICOLO for a in articoli)

    def test_l_atto_sa_da_quando_esiste(self, esportazione_conclusa) -> None:
        atto = esportazione_conclusa.download().atti[0]
        assert atto.pubblicato_il == date(1990, 8, 18)
        assert atto.alla_data(atto.pubblicato_il).originale

    def test_il_corpus_distingue_originale_e_vigente(self, esportazione_conclusa) -> None:
        atto = esportazione_conclusa.download().atti[0]
        assert atto.originale is not None
        assert atto.originale.vigente_dal is None
        assert atto.vigente is not None
        assert atto.vigente.vigente_dal is not None
        assert atto.attribuzione

    def test_le_finestre_degli_articoli_sono_ordinate_e_non_si_accavallano(
        self, esportazione_conclusa
    ) -> None:
        atto = esportazione_conclusa.download().atti[0]
        articoli = [a for a in atto.versioni[-1].articoli() if a.finestre]
        assert articoli, "la versione vigente deve portare le finestre dei suoi articoli"
        for articolo in articoli:
            for prima, dopo in pairwise(articolo.finestre):
                assert prima.fine is not None, f"art. {articolo.numero}: finestra aperta a metà"
                assert prima.fine < dopo.inizio, f"art. {articolo.numero}: finestre accavallate"
            assert articolo.finestre[-1].aperta, (
                f"art. {articolo.numero}: nessuna versione in vigore"
            )

    def test_gli_accenti_dell_export_si_normalizzano(self, esportazione_conclusa) -> None:
        """Nell'export il testo è piano e gli accenti sono vocale+apostrofo."""
        articolo = next(
            a for a in esportazione_conclusa.download().atti[0].versioni[-1].articoli() if a.testo
        )
        assert "'" in articolo.testo
        assert normalize_accents(articolo.testo) is not None

    def test_salvo_e_riapro_senza_rete(self, esportazione_conclusa, tmp_path) -> None:
        percorso = esportazione_conclusa.save(tmp_path / "241.zip")
        riaperto = Corpus.from_zip(percorso)
        assert str(riaperto.atti[0].urn) == L241
        assert riaperto.attribuzione

    def test_mi_riaggancio_all_export_dal_token(
        self, client: Normattiva, esportazione_conclusa
    ) -> None:
        ripreso = client.export_from_token(esportazione_conclusa.token)
        assert ripreso.token == esportazione_conclusa.token
        assert ripreso.status is ExportStatus.COMPLETED
        assert len(ripreso.download()) == 1

    def test_l_export_in_akn_si_salva_ma_non_si_legge(
        self, client: Normattiva, esportazione_conclusa, tmp_path
    ) -> None:
        akn = client.export_from_token(esportazione_conclusa.token, format=Format.AKN)
        with pytest.raises(ValueError, match="salva"):
            akn.download()


@pytest.mark.anyio
class TestAsincrono:
    """La stessa superficie, awaited: se diverge, chi la usa se ne accorge tardi."""

    async def test_dettaglio_e_ricerca(self, cliente_async) -> None:
        async with cliente_async as normattiva:
            atto = await normattiva.dettaglio(f"{L241}~art2")
            assert atto.testo
            esito = await normattiva.ricerca("divorzio", per_pagina=3)
            assert esito.totale > 0

    async def test_iteratori_asincroni(self, cliente_async) -> None:
        async with cliente_async as normattiva:
            versioni = [v async for v in normattiva.cronologia(f"{L241}~art19", massimo=5)]
            assert versioni
            atti = [a async for a in normattiva.ricerca_completa("divorzio", massimo=10)]
            assert atti

    async def test_stesso_esito_del_sincrono(self, cliente_async, client: Normattiva) -> None:
        async with cliente_async as normattiva:
            asincrono = await normattiva.dettaglio(f"{L241}~art2")
        sincrono = client.dettaglio(f"{L241}~art2")
        assert asincrono.testo == sincrono.testo
        assert asincrono.finestra == sincrono.finestra
