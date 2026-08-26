"""Nessun metodo pubblico deve restare senza una prova contro il servizio vero.

I test unitari girano su risposte registrate: dicono che sappiamo leggere quel
che il servizio diceva ieri. Solo le prove di rete dicono che il servizio lo
dice ancora. Questa guardia legge il sorgente della suite di contratto e
fallisce se qualcosa della superficie pubblica non compare mai.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import normattiva
from normattiva import AsyncNormattiva, Corpus, Export, Normattiva
from normattiva.esporta import AsyncExport

CONTRATTO = Path(__file__).parent / "contratto"
SORGENTE = "\n".join(f.read_text(encoding="utf-8") for f in sorted(CONTRATTO.glob("test_*.py")))

MOTIVI = {
    "close": "la esercita ogni context manager della suite",
    "from_data": "la esercita ogni scarico che costruisce un Corpus",
    "from_token": "ci si arriva da Normattiva.export_from_token, che è provato",
    "refresh": "ci si arriva da wait(), che è provato",
}
"""I metodi coperti per via indiretta, ciascuno con la ragione per cui lo è."""

SENZA_PROVA_DI_RETE = set(MOTIVI)


def esercitato(nome: str) -> bool:
    """Se il nome compare nella suite come chiamata o come callable passato a un aiuto."""
    return any(f".{nome}{coda}" in SORGENTE for coda in ("(", ",", ")", "\n"))


def metodi_pubblici(cosa: type) -> set[str]:
    return {
        nome
        for nome, _ in inspect.getmembers(cosa, callable)
        if not nome.startswith("_") and nome in vars(cosa)
    }


def proprieta_pubbliche(cosa: type) -> set[str]:
    return {
        nome
        for nome, valore in vars(cosa).items()
        if not nome.startswith("_") and isinstance(valore, property)
    }


class TestMetodiDelClient:
    @pytest.mark.parametrize("nome", sorted(metodi_pubblici(Normattiva) - SENZA_PROVA_DI_RETE))
    def test_ogni_metodo_sincrono_e_provato_dal_vivo(self, nome: str) -> None:
        assert esercitato(nome), (
            f"Normattiva.{nome} non è mai chiamato nelle prove di contratto: "
            "aggiungerne una in tests/contratto/test_percorsi.py"
        )

    @pytest.mark.parametrize("nome", sorted(metodi_pubblici(AsyncNormattiva) - SENZA_PROVA_DI_RETE))
    def test_ogni_metodo_asincrono_esiste_anche_nel_sincrono(self, nome: str) -> None:
        assert nome in metodi_pubblici(Normattiva)


class TestEsportazioneECorpus:
    @pytest.mark.parametrize("nome", sorted(metodi_pubblici(Export) - SENZA_PROVA_DI_RETE))
    def test_ogni_metodo_dell_esportazione_e_provato(self, nome: str) -> None:
        assert esercitato(nome)

    @pytest.mark.parametrize("nome", sorted(metodi_pubblici(Corpus) - SENZA_PROVA_DI_RETE))
    def test_ogni_metodo_del_corpus_e_provato(self, nome: str) -> None:
        assert esercitato(nome) or f"{nome}(" in SORGENTE

    def test_l_esportazione_asincrona_rispecchia_quella_sincrona(self) -> None:
        assert metodi_pubblici(AsyncExport) == metodi_pubblici(Export)


ERRORI_DAL_SERVIZIO = {
    "NotYetInForceError",
    "TruncationError",
    "AmbiguityError",
    "NotFoundError",
    "RuleViolationError",
    "TooManyResultsError",
}
"""Errori che il servizio, così com'è oggi, produce davvero: e quindi si provano."""

RETI_DI_SICUREZZA = {
    "ValidityMismatchError": (
        "scatta solo se il servizio rispondesse con una versione che non copre la data "
        "chiesta: oggi non lo fa, e la prova di rete verifica che non serva"
    ),
    "UnexpectedResponseError": "scatta su una risposta malformata, che il servizio oggi non manda",
    "OverloadedError": "dipende dal carico di IPZS, non provocabile a comando",
    "ExportFailedError": "dipende da un guasto interno dell'esportazione",
    "ConnectionError": "dipende dalla rete, non dal contratto",
    "RequestBlockedError": "provata sul campione WAF, che passa dal client grezzo",
    "InvalidUrnError": "nasce da noi prima di toccare la rete",
    "InvalidArgumentError": (
        "nasce da noi prima di toccare la rete: dice che un argomento non ha senso, "
        "e chiederlo al servizio sarebbe solo un giro di rete sprecato"
    ),
    "VersionNotFoundError": "nasce da noi leggendo un corpus già scaricato",
    "NormattivaError": "è la radice della gerarchia: non viene mai sollevata direttamente",
}
"""Errori che non si provocano dal vivo, ciascuno col motivo per cui non si può."""


class TestErrori:
    @pytest.mark.parametrize("nome", sorted(ERRORI_DAL_SERVIZIO))
    def test_ogni_errore_del_servizio_e_provocato_dal_vivo(self, nome: str) -> None:
        assert nome in SORGENTE, (
            f"{nome} non viene mai provocato contro il servizio reale: "
            "senza una prova non sappiamo se il servizio lo produce ancora"
        )

    def test_ogni_errore_e_classificato(self) -> None:
        """Nessun errore pubblico può restare senza prova né senza una ragione scritta."""
        tutti = {nome for nome in normattiva.__all__ if nome.endswith("Error")}
        assert tutti == ERRORI_DAL_SERVIZIO | set(RETI_DI_SICUREZZA)

    @pytest.mark.parametrize("nome", sorted(RETI_DI_SICUREZZA))
    def test_ogni_rete_di_sicurezza_spiega_perche_non_si_prova(self, nome: str) -> None:
        assert len(RETI_DI_SICUREZZA[nome].strip()) > 30


class TestModelli:
    @pytest.mark.parametrize(
        "proprieta",
        sorted(proprieta_pubbliche(normattiva.DettaglioAtto)),
    )
    def test_ogni_lettura_del_dettaglio_e_provata(self, proprieta: str) -> None:
        assert f".{proprieta}" in SORGENTE

    @pytest.mark.parametrize("proprieta", sorted(proprieta_pubbliche(normattiva.AttoStorico)))
    def test_ogni_lettura_dell_atto_storico_e_provata(self, proprieta: str) -> None:
        assert f".{proprieta}" in SORGENTE


class TestLaGuardiaFunziona:
    def test_il_sorgente_e_stato_letto(self) -> None:
        assert len(SORGENTE) > 5000

    def test_un_nome_inventato_non_risulta_provato(self) -> None:
        assert ".metodo_che_non_esiste(" not in SORGENTE

    def test_ogni_file_di_contratto_e_incluso(self) -> None:
        attesi = {f.stem for f in CONTRATTO.glob("test_*.py")}
        assert attesi == {
            "test_comportamenti",
            "test_impronte",
            "test_percorsi",
            "test_valori_stabili",
        }

    def test_ogni_esclusione_porta_la_sua_ragione(self) -> None:
        senza_ragione = [nome for nome, motivo in MOTIVI.items() if len(motivo.strip()) < 20]
        assert senza_ragione == []

    def test_le_esclusioni_esistono_davvero(self) -> None:
        superficie = (
            metodi_pubblici(Normattiva)
            | metodi_pubblici(Export)
            | metodi_pubblici(Corpus)
            | metodi_pubblici(AsyncNormattiva)
        )
        assert superficie >= SENZA_PROVA_DI_RETE
