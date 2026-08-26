"""La riga di comando è una superficie pubblica come le altre.

Qui viene provato quello che chi la usa può notare: che cosa esce, come esce, e
con quale codice il programma termina. I comandi vengono invocati da `main`,
cioè dal punto esatto in cui li invoca il terminale, così nessuna prova passa
attraverso una scorciatoia che il terminale non ha.
"""

from __future__ import annotations

import argparse
import json
import logging
import runpy
import shlex
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest
import respx

from normattiva import cli
from normattiva._http import PRODUZIONE
from normattiva.client import Normattiva
from normattiva.errori import (
    ConnectionError,
    InvalidArgumentError,
    InvalidUrnError,
    NormattivaError,
    NotFoundError,
    OverloadedError,
    TooManyResultsError,
)
from normattiva.modelli import ATTRIBUZIONE
from tests.dati import FIXTURES, carica

if TYPE_CHECKING:
    from collections.abc import Iterator

URN = "atto/dettaglio-atto-urn"
TOKEN = "802ecf87-b3bf-43f3-9d85-c0851d7d5021"
ARCHIVIO = (FIXTURES / "export_multivigente.zip").read_bytes()


@pytest.fixture
def api() -> Iterator[respx.Router]:
    """Il servizio, finto, all'indirizzo vero: la CLI non sa di essere in prova."""
    with respx.mock(base_url=PRODUZIONE, assert_all_called=False) as router:
        yield router


class Orologio:
    """Un tempo che scorre solo quando qualcuno dice di aver atteso."""

    def __init__(self) -> None:
        self.adesso = 0.0

    def tempo(self) -> float:
        return self.adesso

    def attendi(self, quanto: float) -> None:
        self.adesso += quanto


@pytest.fixture(autouse=True)
def senza_attese(monkeypatch: pytest.MonkeyPatch) -> None:
    """Toglie dal cliente il limitatore e le attese, che qui rallenterebbero e basta.

    È l'unica scorciatoia di questo file, e vale solo per come il cliente viene
    costruito: tutto il resto passa da `main` come nel terminale.
    """
    orologio = Orologio()
    monkeypatch.setattr(
        cli,
        "_cliente",
        lambda argomenti: Normattiva(
            requests_per_second=0,
            timeout=argomenti.timeout,
            sleep=orologio.attendi,
            clock=orologio.tempo,
        ),
    )


def esegui(riga: str) -> int:
    """Un comando come lo si scriverebbe nel terminale, senza il nome del programma."""
    return cli.main(shlex.split(riga))


def sottocomandi() -> dict[str, argparse.ArgumentParser]:
    """I sottoparser, presi dall'azione che li tiene.

    argparse non offre un modo pubblico per rileggerli, e girarci intorno
    vorrebbe dire tenere altrove un elenco dei comandi che invecchierebbe.
    """
    azione = next(a for a in cli.parser()._actions if isinstance(a, argparse._SubParsersAction))
    return dict(azione.choices)


COMANDI = sorted(sottocomandi())


class TestIComandiSenzaRete:
    """`urn` e `codici` non toccano il servizio: devono funzionare anche staccati."""

    def test_urn_smontato(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert esegui("urn urn:nir:stato:legge:1990-08-07;241~art19") == cli.Uscita.OK
        uscita = capsys.readouterr().out
        assert "urn:nir:stato:legge:1990-08-07;241~art19" in uscita
        assert "1990-08-07" in uscita

    def test_urn_composto_da_un_atto_noto(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Il codice penale risponde attraverso l'allegato 1: la CLI lo sa da sé."""
        assert esegui("urn codice-penale --articolo 416bis") == cli.Uscita.OK
        assert ";1398:1~art416bis" in capsys.readouterr().out

    def test_urn_arricchito(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert esegui("urn codice-civile --articolo 2043 --comma 1 --vigenza 2010-01-01") == 0
        uscita = capsys.readouterr().out
        assert "~art2043-com1!vig=2010-01-01" in uscita

    def test_codici_elenca_tutti_quelli_noti(self, capsys: pytest.CaptureFixture[str]) -> None:
        from normattiva import codici

        assert esegui("codici") == cli.Uscita.OK
        uscita = capsys.readouterr().out
        assert all(noto.nome in uscita for noto in codici.tutti())

    def test_i_nomi_elencati_sono_quelli_che_i_comandi_accettano(self) -> None:
        """L'elenco che «codici» stampa deve essere utilizzabile così com'è."""
        for nome in cli._noti():
            assert cli._risolvi_atto(nome, None) is not None


class TestIlBersaglio:
    def test_un_atto_noto_per_nome(self) -> None:
        assert str(cli._risolvi_atto("codice-civile", "2043")).endswith(":2~art2043")

    def test_il_nome_e_indulgente(self) -> None:
        """Maiuscole, trattini bassi e spazi sono modi diversi di scrivere lo stesso nome."""
        atteso = cli._risolvi_atto("codice-civile", None)
        for scritto in ("CODICE_CIVILE", "Codice Civile", " codice-civile "):
            assert cli._risolvi_atto(scritto, None) == atteso

    def test_un_urn_resta_un_urn(self) -> None:
        urn = cli._risolvi_atto("urn:nir:stato:legge:1990-08-07;241", "19")
        assert urn.articolo == "19"

    def test_un_nome_sconosciuto_rimanda_ai_codici(self) -> None:
        with pytest.raises(InvalidArgumentError, match="codici"):
            cli._risolvi_atto("codice-fiscale", None)

    def test_un_urn_malformato_e_un_urn_malformato(self) -> None:
        with pytest.raises(InvalidUrnError):
            cli._risolvi_atto("urn:nir:stato:legge:1990-99-99;241", None)


class TestICodiciDiUscita:
    """Chi mette il comando in uno script legge il codice, non il messaggio."""

    @pytest.mark.parametrize(
        ("errore", "atteso"),
        [
            (NotFoundError("niente"), cli.Uscita.NON_TROVATO),
            (ConnectionError("giù"), cli.Uscita.SERVIZIO),
            (OverloadedError(), cli.Uscita.SERVIZIO),
            (TooManyResultsError(9000, 100), cli.Uscita.RICHIESTA),
            (InvalidUrnError("boh"), cli.Uscita.RICHIESTA),
            (NormattivaError("altro"), cli.Uscita.RICHIESTA),
        ],
    )
    def test_ogni_errore_cade_nella_sua_famiglia(
        self, errore: NormattivaError, atteso: cli.Uscita
    ) -> None:
        assert cli._famiglia(errore) == atteso

    def test_un_atto_che_non_c_e(self, api: respx.Router, capsys) -> None:
        api.post(f"/{URN}").respond(404, json=carica("errore_404_business"))
        assert esegui("testo urn:nir:stato:legge:1990-08-07;241") == cli.Uscita.NON_TROVATO
        assert capsys.readouterr().err.startswith("normattiva: ")

    def test_una_richiesta_sbagliata_non_arriva_alla_rete(self, api: respx.Router) -> None:
        assert esegui("testo codice-fiscale") == cli.Uscita.RICHIESTA
        assert not api.calls

    def test_argomenti_in_contraddizione(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert esegui("testo codice-civile --gazzetta 042U0262") == cli.Uscita.USO
        assert "non tutti e due" in capsys.readouterr().err

    def test_gazzetta_senza_data(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert esegui("testo --gazzetta 042U0262") == cli.Uscita.USO
        assert "--data" in capsys.readouterr().err

    def test_nessun_atto(self) -> None:
        assert esegui("testo") == cli.Uscita.USO

    def test_un_argomento_che_argparse_rifiuta(self) -> None:
        """Quelli che il parser sa rifiutare da solo escono con lo stesso codice."""
        with pytest.raises(SystemExit) as uscita:
            esegui("cerca qualcosa --pagina zero")
        assert uscita.value.code == cli.Uscita.USO


class TestIlTestoDiUnAtto:
    def test_l_atto_e_scritto_per_intero(self, api: respx.Router, capsys) -> None:
        api.post(f"/{URN}").respond(200, json=carica("urn_articolo_con_commi"))
        assert esegui("testo urn:nir:stato:legge:2007-12-24;244 --articolo 2") == cli.Uscita.OK
        uscita = capsys.readouterr().out
        assert "Citazione" in uscita
        assert "Permalink" in uscita
        assert ATTRIBUZIONE.split(".")[0] in uscita

    def test_la_vigenza_arriva_al_servizio(self, api: respx.Router) -> None:
        rotta = api.post(f"/{URN}").respond(200, json=carica("urn_vigenza_finestra"))
        esegui("testo urn:nir:stato:legge:1970-12-01;898 --articolo 5 --vigenza 2005-01-01")
        assert json.loads(rotta.calls.last.request.content)["urn"].endswith("!vig=2005-01-01")

    def test_il_troncamento_e_dichiarato_su_stderr(self, api: respx.Router, capsys) -> None:
        """Il sospetto va su stderr, così chi incanala il testo lo vede lo stesso."""
        api.post(f"/{URN}").respond(200, json=carica("urn_troncato_100_commi"))
        assert esegui("testo urn:nir:stato:legge:2007-12-24;244 --articolo 1") == cli.Uscita.OK
        catturato = capsys.readouterr()
        assert "potrebbe essere tagliato" in catturato.err
        assert "potrebbe essere tagliato" not in catturato.out

    def test_il_troncamento_puo_diventare_un_errore(self, api: respx.Router) -> None:
        api.post(f"/{URN}").respond(200, json=carica("urn_troncato_100_commi"))
        uscita = esegui(
            "testo urn:nir:stato:legge:2007-12-24;244 --articolo 1 --se-troncato solleva"
        )
        assert uscita == cli.Uscita.RICHIESTA

    def test_la_strada_di_gazzetta(self, api: respx.Router) -> None:
        rotta = api.post("/atto/dettaglio-atto").respond(200, json=carica("urn_atto_intero"))
        assert esegui("testo --gazzetta 042U0262 --data 1942-04-04") == cli.Uscita.OK
        assert json.loads(rotta.calls.last.request.content)["codiceRedazionale"] == "042U0262"

    def test_l_ambiguita_mostra_i_candidati(self, api: respx.Router, capsys) -> None:
        """L'eccezione porta i candidati: buttarli via costringerebbe a ricercarli."""
        api.post(f"/{URN}").respond(200, json=carica("urn_ambiguo"))
        assert esegui("testo urn:nir:stato:legge:1865-03-20;2248") == cli.Uscita.RICHIESTA
        errori = capsys.readouterr().err
        assert "--gazzetta" in errori
        assert errori.count("\n") >= 3


class TestLaRicerca:
    def test_una_pagina_di_risultati(self, api: respx.Router, capsys) -> None:
        api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        assert esegui("cerca procedimento amministrativo") == cli.Uscita.OK
        assert "atti trovati" in capsys.readouterr().out

    def test_le_parole_arrivano_unite(self, api: respx.Router) -> None:
        rotta = api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        esegui("cerca procedimento amministrativo")
        assert "procedimento amministrativo" in rotta.calls.last.request.content.decode()

    def test_le_faccette_solo_se_chieste(self, api: respx.Router, capsys) -> None:
        api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        esegui("cerca trasparenza")
        assert "--tipo" not in capsys.readouterr().out
        esegui("cerca trasparenza --faccette")
        assert "--tipo" in capsys.readouterr().out

    def test_la_numerazione_continua_di_pagina_in_pagina(self, api: respx.Router, capsys) -> None:
        """Il primo atto della terza pagina è il ventunesimo, non di nuovo il primo."""
        dati = carica("ricerca_semplice") | {"paginaCorrente": 3}
        api.post("/ricerca/semplice").respond(200, json=dati)
        esegui("cerca trasparenza --pagina 3 --per-pagina 10")
        assert "  21  " in capsys.readouterr().out

    def test_la_ricerca_per_coordinate(self, api: respx.Router) -> None:
        rotta = api.post("/ricerca/avanzata").respond(200, json=carica("ricerca_avanzata"))
        assert esegui("cerca-avanzata --denominazione LEGGE --anno 1990 --numero 241") == 0
        corpo = json.loads(rotta.calls.last.request.content)
        assert corpo["annoProvvedimento"] == 1990
        assert corpo["numeroProvvedimento"] == 241


class TestLaCronologia:
    def test_le_versioni_sono_numerate(self, api: respx.Router, capsys) -> None:
        """Una sola versione si dice al singolare: «1 versioni» non lo scrive nessuno."""
        api.post(f"/{URN}").respond(200, json=carica("urn_atto_intero"))
        assert esegui("cronologia urn:nir:stato:regio.decreto:1942-03-16;262") == cli.Uscita.OK
        uscita = capsys.readouterr().out
        assert uscita.startswith("1 versione di urn:nir:stato:regio.decreto:1942-03-16;262")
        assert "   1  " in uscita

    def test_in_json_ogni_versione_porta_l_urn_da_cui_rileggerla(
        self, api: respx.Router, capsys
    ) -> None:
        api.post(f"/{URN}").respond(200, json=carica("urn_vigenza_finestra"))
        esegui("cronologia urn:nir:stato:legge:1970-12-01;898 --articolo 5 --massimo 2 --json")
        dati = json.loads(capsys.readouterr().out)
        assert len(dati["versioni"]) == 2
        assert [v["urn"] for v in dati["versioni"]] == [
            "urn:nir:stato:legge:1970-12-01;898~art5!vig=1987-03-12"
        ] * 2


class TestGliArchivi:
    def test_le_collezioni_avvisano_di_che_formato_si_parla(
        self, api: respx.Router, capsys
    ) -> None:
        api.get("/collections/collection-predefinite").respond(
            200, json=[{"nomeCollezione": "Codici", "formatoCollezione": "V", "numeroAtti": 40}]
        )
        assert esegui("collezioni") == cli.Uscita.OK
        assert "--modalita" in capsys.readouterr().out

    def test_un_token_non_convive_con_i_criteri(self, capsys: pytest.CaptureFixture[str]) -> None:
        uscita = esegui("esporta --token abc --anno 1990 --archivio /dev/null")
        assert uscita == cli.Uscita.USO
        assert "--token" in capsys.readouterr().err

    def test_il_tetto_e_l_assenza_di_tetto_si_escludono(self) -> None:
        with pytest.raises(SystemExit) as uscita:
            esegui("esporta --massimo-atti 10 --senza-conteggio --archivio /dev/null")
        assert uscita.value.code == cli.Uscita.USO


class TestL_UscitaInJson:
    """Il JSON è un contratto: chi ci costruisce sopra uno script se lo aspetta fermo."""

    @pytest.mark.parametrize(
        "riga",
        [
            "urn codice-civile --articolo 2043 --json",
            "codici --json",
        ],
    )
    def test_e_json_valido(self, riga: str, capsys: pytest.CaptureFixture[str]) -> None:
        assert esegui(riga) == cli.Uscita.OK
        assert isinstance(json.loads(capsys.readouterr().out), dict)

    def test_l_atto_porta_le_chiavi_promesse(self, api: respx.Router, capsys) -> None:
        api.post(f"/{URN}").respond(200, json=carica("urn_articolo_con_commi"))
        esegui("testo urn:nir:stato:legge:2007-12-24;244 --articolo 2 --json")
        dati = json.loads(capsys.readouterr().out)
        attese = {"citazione", "titolo", "urn", "testo", "commi", "vigenza", "fonte"}
        assert attese <= set(dati)

    def test_il_testo_in_json_non_e_mandato_a_capo(self, api: respx.Router, capsys) -> None:
        """La resa per il terminale impagina; quella per i programmi no."""
        api.post(f"/{URN}").respond(200, json=carica("urn_articolo_con_commi"))
        esegui("testo urn:nir:stato:legge:2007-12-24;244 --articolo 2 --json")
        in_json = json.loads(capsys.readouterr().out)["testo"]
        esegui("testo urn:nir:stato:legge:2007-12-24;244 --articolo 2")
        a_terminale = capsys.readouterr().out
        assert max(len(r) for r in in_json.splitlines()) >= max(
            len(r) for r in a_terminale.splitlines()
        )

    def test_niente_colori_dentro_il_json(self, api: respx.Router, capsys) -> None:
        api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        esegui("cerca trasparenza --json --colore sempre")
        assert "\x1b[" not in capsys.readouterr().out


class TestIColori:
    def test_su_richiesta_ci_sono(self, capsys: pytest.CaptureFixture[str]) -> None:
        esegui("codici --colore sempre")
        assert "\x1b[" in capsys.readouterr().out

    def test_su_richiesta_non_ci_sono(self, capsys: pytest.CaptureFixture[str]) -> None:
        esegui("codici --colore mai")
        assert "\x1b[" not in capsys.readouterr().out

    def test_di_norma_non_ci_sono_fuori_da_un_terminale(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """capsys non è un terminale, ed è la stessa cosa che vede una pipe."""
        esegui("codici")
        assert "\x1b[" not in capsys.readouterr().out

    def test_no_color_ha_l_ultima_parola_su_auto(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        assert cli._a_colori("auto") is False


class TestL_Attribuzione:
    """La licenza dei dati obbliga a portarsela dietro, anche fuori da Python."""

    @pytest.mark.parametrize(
        ("riga", "rotta", "fixture"),
        [
            ("testo urn:nir:stato:regio.decreto:1942-03-16;262", URN, "urn_atto_intero"),
            ("cerca trasparenza", "ricerca/semplice", "ricerca_semplice"),
            ("cerca-avanzata --anno 1990", "ricerca/avanzata", "ricerca_avanzata"),
            (
                "aggiornati --dal 2026-01-01 --al 2026-01-31",
                "ricerca/aggiornati",
                "ricerca_aggiornati",
            ),
        ],
    )
    def test_ogni_comando_che_rende_atti_la_mostra(
        self, api: respx.Router, capsys, riga: str, rotta: str, fixture: str
    ) -> None:
        api.post(f"/{rotta}").respond(200, json=carica(fixture))
        assert esegui(riga) == cli.Uscita.OK
        assert "Fonte: Normattiva" in capsys.readouterr().out

    @pytest.mark.parametrize(
        ("riga", "rotta", "fixture"),
        [
            ("testo urn:nir:stato:regio.decreto:1942-03-16;262 --json", URN, "urn_atto_intero"),
            ("cerca trasparenza --json", "ricerca/semplice", "ricerca_semplice"),
            ("cerca-avanzata --anno 1990 --json", "ricerca/avanzata", "ricerca_avanzata"),
            (
                "aggiornati --dal 2026-01-01 --al 2026-01-31 --json",
                "ricerca/aggiornati",
                "ricerca_aggiornati",
            ),
        ],
    )
    def test_anche_in_json_e_un_campo(
        self, api: respx.Router, capsys, riga: str, rotta: str, fixture: str
    ) -> None:
        api.post(f"/{rotta}").respond(200, json=carica(fixture))
        esegui(riga)
        assert json.loads(capsys.readouterr().out)["fonte"] == ATTRIBUZIONE


class TestIlParser:
    """Il parser è la documentazione che chi usa il comando legge per prima."""

    def test_ci_sono_comandi_da_controllare(self) -> None:
        assert len(COMANDI) >= 10

    @pytest.mark.parametrize("nome", COMANDI)
    def test_ogni_comando_sa_che_cosa_eseguire(self, nome: str) -> None:
        assert callable(sottocomandi()[nome].get_default("esegui"))

    @pytest.mark.parametrize("nome", COMANDI)
    def test_ogni_comando_si_presenta(self, nome: str) -> None:
        sotto = sottocomandi()[nome]
        assert sotto.description, f"{nome} non dice che cosa fa"
        assert sotto.description.rstrip().endswith("."), f"{nome} non è una frase compiuta"

    @pytest.mark.parametrize("nome", COMANDI)
    def test_ogni_opzione_e_spiegata(self, nome: str) -> None:
        senza = [
            azione.option_strings or azione.dest
            for azione in sottocomandi()[nome]._actions
            if not azione.help and azione.help is not argparse.SUPPRESS
        ]
        assert senza == [], f"{nome} ha opzioni senza spiegazione: {senza}"

    @pytest.mark.parametrize("nome", COMANDI)
    def test_gli_esempi_dell_aiuto_sono_comandi_veri(self, nome: str) -> None:
        """Un esempio che non si può incollare è peggio di nessun esempio."""
        for esempio in _esempi(sottocomandi()[nome].epilog):
            pezzi = shlex.split(esempio)
            assert pezzi[0] == cli.PROGRAMMA, f"{nome}: l'esempio non invoca il programma"
            cli.parser().parse_args(pezzi[1:])

    @pytest.mark.parametrize("nome", COMANDI)
    def test_l_aiuto_non_rimescola_gli_esempi(self, nome: str) -> None:
        """La prosa va mandata a capo, i comandi da incollare no."""
        sotto = sottocomandi()[nome]
        for esempio in _esempi(sotto.epilog):
            assert esempio in sotto.format_help()

    def test_ci_sono_esempi_da_controllare(self) -> None:
        quanti = sum(len(_esempi(sottocomandi()[n].epilog)) for n in COMANDI)
        assert quanti >= 8


def _esempi(epilogo: str | None) -> list[str]:
    """Le righe di un epilogo che sono comandi, cioè quelle rientrate."""
    if not epilogo:
        return []
    return [riga.strip() for riga in epilogo.splitlines() if riga.startswith("  ")]


class TestIlClienteVero:
    """La scorciatoia delle altre prove salta `_cliente`: qui viene guardato."""

    def test_parla_con_la_produzione(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.undo()
        with cli._cliente(argparse.Namespace(timeout=7.0)) as cliente:
            assert cliente.base_url == PRODUZIONE

    def test_si_presenta_come_riga_di_comando(self) -> None:
        """IPZS deve poter distinguere il traffico del terminale da quello di uno script."""
        assert "cli" in cli.USER_AGENT


class TestGliArchiviSuDisco:
    """L'esportazione è l'unico comando che scrive un file: qui viene guardato."""

    @pytest.fixture
    def esportazione(self, api: respx.Router) -> respx.Router:
        api.post("/ricerca/avanzata").respond(200, json=carica("ricerca_avanzata"))
        api.post("/ricerca-asincrona/nuova-ricerca").respond(202, text=TOKEN)
        api.put("/ricerca-asincrona/conferma-ricerca").respond(200, json={"stato": 1})
        api.get(f"/ricerca-asincrona/check-status/{TOKEN}").respond(200, json={"stato": 3})
        api.get(f"/collections/download/collection-asincrona/{TOKEN}").respond(
            200, content=ARCHIVIO
        )
        return api

    def test_l_archivio_finisce_dove_e_stato_chiesto(self, esportazione, tmp_path, capsys) -> None:
        destinazione = tmp_path / "241.zip"
        assert esegui(f"esporta --anno 1990 --numero 241 --archivio {destinazione}") == 0
        assert destinazione.read_bytes() == ARCHIVIO
        assert TOKEN in capsys.readouterr().out

    def test_il_token_viene_detto_su_stderr_prima_dell_attesa(
        self, esportazione, tmp_path, capsys
    ) -> None:
        """Un'esportazione dura minuti: chi la interrompe deve poterla riprendere."""
        esegui(f"esporta --anno 1990 --archivio {tmp_path / 'a.zip'}")
        assert TOKEN in capsys.readouterr().err

    def test_senza_conteggio_non_conta(self, esportazione: respx.Router, tmp_path) -> None:
        """Il conteggio preventivo è una richiesta in più: chi non la vuole la salta."""
        esegui(f"esporta --anno 1990 --senza-conteggio --archivio {tmp_path / 'a.zip'}")
        assert esportazione.routes[0].call_count == 0

    def test_con_il_tetto_conta_prima(self, esportazione: respx.Router, tmp_path) -> None:
        esegui(f"esporta --anno 1990 --archivio {tmp_path / 'a.zip'}")
        assert esportazione.routes[0].call_count == 1

    def test_un_token_riprende_senza_ricominciare(
        self, esportazione: respx.Router, tmp_path
    ) -> None:
        assert esegui(f"esporta --token {TOKEN} --archivio {tmp_path / 'a.zip'}") == cli.Uscita.OK
        assert esportazione.routes[1].call_count == 0

    def test_in_json_dice_dove_ha_scritto(self, esportazione, tmp_path, capsys) -> None:
        destinazione = tmp_path / "241.zip"
        esegui(f"esporta --anno 1990 --archivio {destinazione} --json")
        dati = json.loads(capsys.readouterr().out)
        assert dati["archivio"] == str(destinazione)
        assert dati["byte"] == len(ARCHIVIO)

    def test_in_json_anche_la_collezione_dice_dove_ha_scritto(
        self, api: respx.Router, tmp_path, capsys
    ) -> None:
        api.get("/collections/download/collection-preconfezionata").respond(200, content=ARCHIVIO)
        destinazione = tmp_path / "codici.zip"
        esegui(f"scarica-collezione Codici --archivio {destinazione} --json")
        assert json.loads(capsys.readouterr().out)["archivio"] == str(destinazione)

    def test_le_collezioni_in_json_sono_una_lista(self, api: respx.Router, capsys) -> None:
        api.get("/collections/collection-predefinite").respond(
            200, json=[{"nomeCollezione": "Codici", "formatoCollezione": "V", "numeroAtti": 40}]
        )
        esegui("collezioni --json")
        assert len(json.loads(capsys.readouterr().out)["collezioni"]) == 1

    def test_un_percorso_che_non_esiste_non_stampa_una_traccia(
        self, esportazione, tmp_path, capsys
    ) -> None:
        """Scrivere il file è l'unico modo di fallire che non riguarda Normattiva."""
        uscita = esegui(f"esporta --anno 1990 --archivio {tmp_path / 'manca' / 'a.zip'}")
        assert uscita == cli.Uscita.ERRORE
        assert "normattiva: " in capsys.readouterr().err

    def test_una_collezione_gia_pronta(self, api: respx.Router, tmp_path) -> None:
        api.get("/collections/download/collection-preconfezionata").respond(200, content=ARCHIVIO)
        destinazione = tmp_path / "codici.zip"
        assert esegui(f"scarica-collezione Codici --archivio {destinazione}") == cli.Uscita.OK
        assert destinazione.read_bytes() == ARCHIVIO


class TestIDizionari:
    @pytest.mark.parametrize(
        ("quale", "percorso", "fixture"),
        [
            ("denominazioni", "tipologiche/denominazione-atto", "tipologiche_denominazione_atto"),
            ("classi", "tipologiche/classe-provvedimento", "tipologiche_classe_provvedimento"),
            ("formati", "tipologiche/estensioni", "tipologiche_estensioni"),
        ],
    )
    def test_ognuno_rende_codici_e_descrizioni(
        self, api: respx.Router, capsys, quale: str, percorso: str, fixture: str
    ) -> None:
        api.get(f"/{percorso}").respond(200, json=carica(fixture))
        assert esegui(f"dizionario {quale}") == cli.Uscita.OK
        uscita = capsys.readouterr().out
        assert uscita.startswith("codice")
        assert uscita.count("\n") >= 2

    def test_in_json_e_una_lista_sotto_il_suo_nome(self, api: respx.Router, capsys) -> None:
        api.get("/tipologiche/estensioni").respond(200, json=carica("tipologiche_estensioni"))
        esegui("dizionario formati --json")
        assert isinstance(json.loads(capsys.readouterr().out)["formati"], list)


class TestLoScorrimento:
    def test_massimo_scorre_le_pagine(self, api: respx.Router, capsys) -> None:
        """La pagina registrata ne porta cinque: per averne dodici ne servono tre."""
        rotta = api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        assert esegui("cerca trasparenza --massimo 12") == cli.Uscita.OK
        assert rotta.call_count == 3
        assert "12 atti" in capsys.readouterr().out

    def test_massimo_si_ferma_dove_gli_e_stato_detto(self, api: respx.Router, capsys) -> None:
        api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        esegui("cerca trasparenza --massimo 2")
        assert "2 atti" in capsys.readouterr().out

    def test_massimo_in_json_rende_solo_gli_atti(self, api: respx.Router, capsys) -> None:
        api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        esegui("cerca trasparenza --massimo 1 --json")
        dati = json.loads(capsys.readouterr().out)
        assert set(dati) == {"atti", "fonte"}


class TestGliArgomentiMalScritti:
    """Quello che il parser sa rifiutare da solo, con un messaggio in italiano."""

    @pytest.mark.parametrize(
        "riga",
        [
            "testo codice-civile --vigenza ieri",
            "cerca-avanzata --classe fantasia",
            "esporta --formato pergamena --archivio /dev/null",
            "esporta --modalita retroattiva --archivio /dev/null",
            "cerca trasparenza --per-pagina 0",
            "aggiornati --dal 2026-13-01 --al 2026-01-01",
        ],
    )
    def test_esce_con_il_codice_d_uso(self, riga: str, capsys) -> None:
        with pytest.raises(SystemExit) as uscita:
            esegui(riga)
        assert uscita.value.code == cli.Uscita.USO
        assert "non è" in capsys.readouterr().err


class TestQuandoQualcunoSmetteDiAscoltare:
    """I due modi in cui il comando finisce senza che nessuno abbia sbagliato."""

    def test_ctrl_c_non_stampa_una_traccia(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        monkeypatch.setattr(cli, "_esegui_codici", _scoppia(KeyboardInterrupt))
        assert esegui("codici") == cli.Uscita.INTERROTTO
        assert capsys.readouterr().err.strip() == "normattiva: interrotto"

    def test_una_pipe_chiusa_non_e_un_errore_di_chi_legge(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`| head` chiude il flusso a metà: non è colpa di nessuno."""
        monkeypatch.setattr(cli, "_esegui_codici", _scoppia(BrokenPipeError))
        monkeypatch.setattr(cli, "_zittisci_uscita", lambda: None)
        assert esegui("codici") == cli.Uscita.LETTURA_INTERROTTA

    def test_zittire_l_uscita_la_zittisce_davvero(self) -> None:
        """Va provato in un processo a parte: qui stdout è quello che cattura le prove."""
        codice = "from normattiva import cli\ncli._zittisci_uscita()\nprint('non si vede')\n"
        esito = subprocess.run(
            [sys.executable, "-c", codice], capture_output=True, text=True, check=False
        )
        assert esito.returncode == 0
        assert esito.stdout == ""


def _scoppia(quale: type[BaseException]):
    """Un comando che fallisce nel modo indicato, per provare come viene raccolto."""

    def esegui_e_scoppia(_: argparse.Namespace) -> cli.Uscita:
        raise quale

    return esegui_e_scoppia


class TestIlRacconto:
    def test_verboso_manda_su_stderr_quello_che_la_libreria_dice(
        self, api: respx.Router, capsys
    ) -> None:
        api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        registro = logging.getLogger("normattiva")
        quanti = len(registro.handlers)
        try:
            esegui("cerca trasparenza --verboso")
            assert len(registro.handlers) == quanti + 1
        finally:
            del registro.handlers[quanti:]

    def test_senza_verboso_nessuno_si_attacca_al_registro(self, api: respx.Router) -> None:
        api.post("/ricerca/semplice").respond(200, json=carica("ricerca_semplice"))
        quanti = len(logging.getLogger("normattiva").handlers)
        esegui("cerca trasparenza")
        assert len(logging.getLogger("normattiva").handlers) == quanti


class TestI_ModiDiInvocarlo:
    def test_python_meno_emme_vale_quanto_il_comando(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", [cli.PROGRAMMA, "codici"])
        with pytest.raises(SystemExit) as uscita:
            runpy.run_module("normattiva", run_name="__main__")
        assert uscita.value.code == cli.Uscita.OK

    def test_lo_script_termina_con_il_codice_del_comando(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "argv", [cli.PROGRAMMA, "testo", "codice-fiscale"])
        with pytest.raises(SystemExit) as uscita:
            cli._da_terminale()
        assert uscita.value.code == cli.Uscita.RICHIESTA
