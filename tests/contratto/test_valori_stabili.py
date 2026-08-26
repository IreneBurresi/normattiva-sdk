"""I valori su cui la libreria ha cablato delle scelte.

Le enum, le abbreviazioni delle citazioni e la mappa degli allegati non sono
dati che passano: sono decisioni prese guardando il servizio una volta. Se il
servizio cambia idea, qui si rompe.
"""

from __future__ import annotations

from contextlib import suppress

import pytest

from normattiva import Normattiva, codici
from normattiva.errori import AmbiguityError
from normattiva.modelli import (
    ABBREVIAZIONI,
    DENOMINAZIONI_URN,
    ClasseProvvedimento,
    Format,
)

pytestmark = [pytest.mark.rete, pytest.mark.timeout(600)]


class TestEnumerazioni:
    def test_ogni_formato_esiste_ancora(self, client: Normattiva) -> None:
        disponibili = {v.codice for v in client.export_formats()}
        assert {f.value for f in Format} <= disponibili

    def test_ogni_classe_esiste_ancora(self, client: Normattiva) -> None:
        disponibili = {v.codice for v in client.classi_provvedimento()}
        assert {str(int(c)) for c in ClasseProvvedimento} <= disponibili

    def test_le_denominazioni_abbreviate_esistono_ancora(self, client: Normattiva) -> None:
        disponibili = {v.descrizione.upper() for v in client.denominazioni()}
        assert set(ABBREVIAZIONI) <= disponibili


class TestPonteFraRicercaEDettaglio:
    def test_l_urn_derivato_da_una_ricerca_risolve(self, client: Normattiva) -> None:
        """`AttoTrovato.urn` compone l'URN dai campi della ricerca: deve risolvere."""
        esito = client.ricerca("procedimento amministrativo", per_pagina=5)
        assert esito.atti, "la ricerca non ha restituito nulla su cui provare il ponte"
        mappati = [a for a in esito.atti if a.estremi.denominazione in DENOMINAZIONI_URN][:3]
        if not mappati:
            pytest.skip("nessun risultato di un tipo di atto con forma URN verificata")
        for trovato in mappati:
            with suppress(AmbiguityError):
                assert client.dettaglio(trovato.urn).testo

    @pytest.mark.parametrize("denominazione", sorted(DENOMINAZIONI_URN))
    def test_ogni_denominazione_mappata_e_ancora_giusta(
        self, client: Normattiva, denominazione: str
    ) -> None:
        """La mappa è stata verificata una volta: qui si verifica che regga ancora."""
        esito = client.ricerca_avanzata(denominazione=denominazione, per_pagina=1)
        if not esito.atti:
            pytest.skip(f"il servizio non ha atti di tipo {denominazione}")
        with suppress(AmbiguityError):
            assert client.dettaglio(esito.atti[0].urn).testo


class TestMappaDegliAllegati:
    @pytest.mark.parametrize(
        ("atto", "articolo"),
        [
            (codici.CODICE_CIVILE, "2043"),
            (codici.CODICE_PENALE, "575"),
            (codici.CODICE_PROCEDURA_CIVILE, "99"),
        ],
        ids=lambda x: getattr(x, "nome", x),
    )
    def test_l_articolo_risponde_solo_dall_allegato(
        self, client: Normattiva, atto, articolo: str
    ) -> None:
        assert client.dettaglio(atto.articolo(articolo)).testo
