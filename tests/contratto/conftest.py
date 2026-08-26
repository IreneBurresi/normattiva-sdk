from collections.abc import Callable

import httpx
import pytest

from normattiva import AsyncNormattiva, ConnectionError, Normattiva
from tests.contratto import interroga as rete


@pytest.fixture(scope="session")
def grezzo() -> httpx.Client:
    """Un client nudo, per le richieste che la libreria non manderebbe mai."""
    with rete.nuovo_client() as client:
        yield client


@pytest.fixture(scope="session")
def client() -> Normattiva:
    """La libreria vera, per verificare che le sue astrazioni reggano ancora."""
    with Normattiva(user_agent=rete.USER_AGENT) as normattiva:
        yield normattiva


@pytest.fixture(scope="session")
def impronte() -> dict[str, dict[str, list[str]]]:
    """Il dataset di riferimento."""
    return rete.impronte_registrate()


@pytest.fixture
async def cliente_async() -> AsyncNormattiva:
    """Il client asincrono: stessa superficie, stesso servizio."""
    async with AsyncNormattiva(user_agent=rete.USER_AGENT) as normattiva:
        yield normattiva


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item):
    """Un servizio irraggiungibile fa saltare la prova, non fallire.

    Vale per tutta la suite di contratto, non caso per caso: quando IPZS
    rallenta o si ferma, decine di prove cadono insieme, e un referto con trenta
    fallimenti per un solo guasto è un referto che si impara a ignorare. Uno
    scostamento del contratto è un'altra cosa, e continua a fallire.
    """
    try:
        return (yield)
    except ConnectionError as guasto:
        pytest.skip(f"il servizio non risponde: {guasto}")


@pytest.fixture
def nonostante_i_guasti() -> Callable[..., object]:
    """Esegue qualcosa lasciando passare i guasti al gestore di cui sopra."""

    def esegui(cosa: Callable[..., object], *argomenti: object, **parametri: object) -> object:
        return cosa(*argomenti, **parametri)

    return esegui
