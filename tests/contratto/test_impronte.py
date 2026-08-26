"""La forma delle risposte è cambiata?

Un campo che sparisce o cambia tipo rompe chi lo leggeva: è un fallimento. Un
campo che compare è una notizia: viene segnalato e basta. Un endpoint che non
risponde è un guasto del servizio, non un cambio di contratto: si salta, e lo
dice il referto.
"""

from __future__ import annotations

import warnings

import pytest

from tests.contratto import interroga as rete
from tests.contratto.campioni import TUTTI, Campione
from tests.contratto.impronta import confronta

pytestmark = [pytest.mark.rete, pytest.mark.timeout(600)]


@pytest.mark.parametrize("campione", TUTTI, ids=lambda c: c.nome)
def test_la_forma_e_quella_registrata(campione: Campione, grezzo, impronte) -> None:
    try:
        esito = rete.interroga(campione, grezzo)
    except rete.Indisponibile as guasto:
        pytest.skip(f"il servizio non risponde su {campione.gruppo}: {guasto}")

    registrata = impronte.get(campione.nome)
    if registrata is None:
        pytest.fail(
            f"{campione.nome} non è nel dataset: eseguire "
            f"`uv run python -m tests.contratto.registra {campione.nome}`"
        )

    derive = confronta(registrata, rete.impronta_di(campione, esito))
    rotture = [d for d in derive if d.rompe]
    novita = [d for d in derive if not d.rompe]

    if novita:
        warnings.warn(
            f"{campione.nome}: {len(novita)} campi nuovi. " + "; ".join(str(d) for d in novita),
            stacklevel=1,
        )
    assert not rotture, (
        f"il contratto di {campione.gruppo} è cambiato ({campione.perche}):\n  "
        + "\n  ".join(str(d) for d in rotture)
    )


def test_il_servizio_risponde(grezzo) -> None:
    """Se non risponde più niente, il guasto è generale e va detto una volta sola."""
    risposte = 0
    for campione in TUTTI[:4]:
        try:
            rete.interroga(campione, grezzo, retries=1)
        except rete.Indisponibile:
            continue
        risposte += 1
    assert risposte, "nessuno degli endpoint di base ha risposto: servizio giù o rete assente"


def test_il_dataset_copre_tutti_gli_endpoint(impronte) -> None:
    """Ogni endpoint pubblicato ha almeno un campione registrato."""
    coperti = {c.gruppo for c in TUTTI if c.nome in impronte}
    mancanti = {c.gruppo for c in TUTTI} - coperti
    assert not mancanti, f"endpoint senza dataset: {', '.join(sorted(mancanti))}"
