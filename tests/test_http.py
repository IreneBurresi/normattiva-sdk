import httpx
import pytest
import respx

from normattiva._http import Limitatore, PoliticaRitentativi, Trasporto
from normattiva.errori import (
    ConnectionError,
    RequestBlockedError,
    RuleViolationError,
    UnexpectedResponseError,
)

BASE = "https://esempio.invalid/api"


class Orologio:
    """A clock that never really waits."""

    def __init__(self) -> None:
        self.adesso = 0.0
        self.attese: list[float] = []

    def tempo(self) -> float:
        return self.adesso

    def attendi(self, quanto: float) -> None:
        self.attese.append(quanto)
        self.adesso += quanto


@pytest.fixture
def orologio() -> Orologio:
    return Orologio()


@pytest.fixture
def api():
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        yield router


@pytest.fixture
def trasporto(orologio: Orologio) -> Trasporto:
    return Trasporto(
        base_url=BASE,
        retries=3,
        requests_per_second=0,
        sleep=orologio.attendi,
        clock=orologio.tempo,
    )


class TestPoliticaRitentativi:
    @pytest.mark.parametrize("stato", [400, 500, 502, 503, 504])
    def test_stati_ritentabili(self, stato: int) -> None:
        assert PoliticaRitentativi().ritentabile(stato)

    @pytest.mark.parametrize("stato", [200, 202, 303, 404, 409, 422])
    def test_stati_non_ritentabili(self, stato: int) -> None:
        assert not PoliticaRitentativi().ritentabile(stato)

    def test_il_waf_non_si_ritenta_mai(self) -> None:
        assert not PoliticaRitentativi().ritentabile(409)

    def test_attesa_cresce(self) -> None:
        politica = PoliticaRitentativi(base=1.0, jitter=0.0)
        assert [politica.attesa(n) for n in range(3)] == [1.0, 2.0, 4.0]

    def test_attesa_ha_un_tetto(self) -> None:
        politica = PoliticaRitentativi(base=1.0, jitter=0.0, tetto=3.0)
        assert politica.attesa(10) == 3.0

    def test_jitter_entro_i_limiti(self) -> None:
        politica = PoliticaRitentativi(base=1.0, jitter=0.5)
        attese = [politica.attesa(0) for _ in range(50)]
        assert all(1.0 <= a <= 1.5 for a in attese)


class TestLimitatore:
    def test_nessun_limite_se_disattivato(self, orologio: Orologio) -> None:
        limitatore = Limitatore(0, sleep=orologio.attendi, clock=orologio.tempo)
        for _ in range(5):
            limitatore.attendi_turno()
        assert orologio.attese == []

    def test_spaziatura_fra_richieste(self, orologio: Orologio) -> None:
        limitatore = Limitatore(2, sleep=orologio.attendi, clock=orologio.tempo)
        limitatore.attendi_turno()
        limitatore.attendi_turno()
        limitatore.attendi_turno()
        assert orologio.attese == pytest.approx([0.5, 0.5])

    def test_non_attende_se_e_gia_passato_tempo(self, orologio: Orologio) -> None:
        limitatore = Limitatore(2, sleep=orologio.attendi, clock=orologio.tempo)
        limitatore.attendi_turno()
        orologio.adesso += 10
        limitatore.attendi_turno()
        assert orologio.attese == []


class TestDisciplinaDegliHeader:
    def test_get_senza_content_type(self, api, trasporto: Trasporto) -> None:
        rotta = api.get("/prova").respond(200, json={})
        trasporto.get("/prova")
        assert "content-type" not in rotta.calls.last.request.headers

    def test_post_con_content_type(self, api, trasporto: Trasporto) -> None:
        rotta = api.post("/prova").respond(200, json={})
        trasporto.post("/prova", {"a": 1})
        assert rotta.calls.last.request.headers["content-type"] == "application/json"

    def test_user_agent_identificante(self, api, trasporto: Trasporto) -> None:
        rotta = api.get("/prova").respond(200, json={})
        trasporto.get("/prova")
        agente = rotta.calls.last.request.headers["user-agent"]
        assert "normattiva" in agente.lower()
        assert "github.com" in agente

    def test_user_agent_personalizzato(self, api, orologio: Orologio) -> None:
        rotta = api.get("/prova").respond(200, json={})
        with Trasporto(base_url=BASE, user_agent="mio/1.0", requests_per_second=0) as t:
            t.get("/prova")
        assert rotta.calls.last.request.headers["user-agent"] == "mio/1.0"

    def test_accetta_json(self, api, trasporto: Trasporto) -> None:
        rotta = api.get("/prova").respond(200, json={})
        trasporto.get("/prova")
        assert "application/json" in rotta.calls.last.request.headers["accept"]


class TestRitentativi:
    def test_ritenta_il_500(self, api, trasporto: Trasporto) -> None:
        rotta = api.get("/prova").mock(
            side_effect=[httpx.Response(500), httpx.Response(200, json={"ok": True})]
        )
        assert trasporto.get("/prova").json() == {"ok": True}
        assert rotta.call_count == 2

    def test_ritenta_il_400(self, api, trasporto: Trasporto) -> None:
        rotta = api.get("/prova").mock(
            side_effect=[httpx.Response(400), httpx.Response(200, json={})]
        )
        trasporto.get("/prova")
        assert rotta.call_count == 2

    def test_ritenta_gli_errori_di_trasporto(self, api, trasporto: Trasporto) -> None:
        rotta = api.get("/prova").mock(
            side_effect=[httpx.ConnectError("giù"), httpx.Response(200, json={})]
        )
        trasporto.get("/prova")
        assert rotta.call_count == 2

    def test_non_ritenta_il_409(self, api, trasporto: Trasporto) -> None:
        rotta = api.get("/prova").respond(409, json={"supportId": "1"})
        with pytest.raises(RequestBlockedError):
            trasporto.get("/prova")
        assert rotta.call_count == 1

    def test_non_ritenta_una_regola_di_business(self, api, trasporto: Trasporto) -> None:
        rotta = api.get("/prova").respond(400, json={"code": "1501", "message": "no"})
        with pytest.raises(RuleViolationError):
            trasporto.get("/prova")
        assert rotta.call_count == 1

    def test_un_codice_ignoto_segue_lo_stato(self, api, trasporto: Trasporto) -> None:
        """Il servizio ha errori transitori che chiedono di riprovare: non sono regole."""
        rotta = api.get("/prova").mock(
            side_effect=[
                httpx.Response(500, json={"code": "9999", "message": "riprovare più tardi"}),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        assert trasporto.get("/prova").json() == {"ok": True}
        assert rotta.call_count == 2

    def test_un_cinquecento_persistente_e_un_guasto_non_una_regola(
        self, api, trasporto: Trasporto
    ) -> None:
        """Un `5xx` parla del servizio, non della richiesta, qualunque codice porti.

        Presentarlo come regola violata manderebbe chi lo riceve a correggere una
        richiesta che era già giusta: il 1000 arriva così anche per un URN valido.
        """
        rotta = api.get("/prova").respond(500, json={"code": "1000", "message": "riprovare"})
        with pytest.raises(ConnectionError, match="riprovare"):
            trasporto.get("/prova")
        assert rotta.call_count == 3

    def test_una_regola_su_un_quattrocento_resta_una_regola(
        self, api, trasporto: Trasporto
    ) -> None:
        rotta = api.get("/prova").respond(400, json={"code": "9999", "message": "boh"})
        with pytest.raises(RuleViolationError) as errore:
            trasporto.get("/prova")
        assert errore.value.codice == 9999
        assert errore.value.regola is None
        assert rotta.call_count == 3

    def test_esaurisce_i_tentativi_e_fallisce(self, api, trasporto: Trasporto) -> None:
        rotta = api.get("/prova").respond(500, json={"error": "rotto"})
        with pytest.raises(UnexpectedResponseError):
            trasporto.get("/prova")
        assert rotta.call_count == 3

    def test_errore_di_rete_persistente(self, api, trasporto: Trasporto) -> None:
        api.get("/prova").mock(side_effect=httpx.ConnectError("giù"))
        with pytest.raises(ConnectionError):
            trasporto.get("/prova")

    def test_attende_fra_un_tentativo_e_l_altro(
        self, api, trasporto: Trasporto, orologio: Orologio
    ) -> None:
        api.get("/prova").mock(side_effect=[httpx.Response(500), httpx.Response(200, json={})])
        trasporto.get("/prova")
        assert len(orologio.attese) == 1
        assert orologio.attese[0] > 0


class TestRisposte:
    def test_stato_atteso_diverso(self, api, trasporto: Trasporto) -> None:
        api.get("/prova").respond(303, headers={"x-ipzs-location": "http://qui"})
        risposta = trasporto.get("/prova", attesi=(200, 303))
        assert risposta.status == 303
        assert risposta.intestazioni["x-ipzs-location"] == "http://qui"

    def test_corpo_di_testo(self, api, trasporto: Trasporto) -> None:
        api.post("/prova").respond(202, text="un-token")
        risposta = trasporto.post("/prova", {}, attesi=(202,))
        assert risposta.testo == "un-token"

    def test_corpo_binario(self, api, trasporto: Trasporto) -> None:
        api.get("/prova").respond(200, content=b"PK\x03\x04")
        assert trasporto.get("/prova").contenuto == b"PK\x03\x04"

    def test_json_non_valido(self, api, trasporto: Trasporto) -> None:
        api.get("/prova").respond(200, text="non json")
        with pytest.raises(UnexpectedResponseError):
            trasporto.get("/prova").json()

    def test_parametri_in_query(self, api, trasporto: Trasporto) -> None:
        rotta = api.get("/prova").respond(200, json={})
        trasporto.get("/prova", parametri={"nome": "un valore", "n": 3})
        assert rotta.calls.last.request.url.params["nome"] == "un valore"

    def test_parametri_vuoti_omessi(self, api, trasporto: Trasporto) -> None:
        rotta = api.get("/prova").respond(200, json={})
        trasporto.get("/prova", parametri={"nome": "x", "vuoto": None})
        assert "vuoto" not in rotta.calls.last.request.url.params


class TestRedirect:
    def test_non_seguiti_per_impostazione(self, api, trasporto: Trasporto) -> None:
        api.get("/prova").respond(303, headers={"location": f"{BASE}/altrove"})
        risposta = trasporto.get("/prova", attesi=(303,))
        assert risposta.status == 303

    def test_seguiti_su_richiesta(self, api, trasporto: Trasporto) -> None:
        api.get("/prova").respond(302, headers={"location": f"{BASE}/altrove"})
        altrove = api.get("/altrove").respond(200, content=b"PK\x03\x04")
        risposta = trasporto.get("/prova", segui_redirect=True)
        assert risposta.contenuto == b"PK\x03\x04"
        assert altrove.call_count == 1


class TestCicloDiVita:
    def test_context_manager(self, api, orologio: Orologio) -> None:
        api.get("/prova").respond(200, json={})
        with Trasporto(base_url=BASE, requests_per_second=0) as t:
            t.get("/prova")
        assert t.closed

    def test_client_iniettato_non_viene_chiuso(self, api) -> None:
        api.get("/prova").respond(200, json={})
        mio = httpx.Client()
        with Trasporto(base_url=BASE, requests_per_second=0, http_client=mio) as t:
            t.get("/prova")
        assert not mio.is_closed
        mio.close()
