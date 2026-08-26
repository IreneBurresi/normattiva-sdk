"""Proprietà che devono valere per ogni ingresso, non solo per quelli scelti.

Gli esempi coprono i casi a cui abbiamo pensato; queste coprono quelli a cui
non abbiamo pensato. Stanno qui solo le funzioni che hanno davvero una legge:
un parser che ricompone quel che ha letto, una normalizzazione idempotente, un
confronto che non trova differenze fra una cosa e se stessa.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import date, timedelta

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from normattiva import InvalidUrnError, Urn
from normattiva._wire import leggi_data
from normattiva.errori import UnexpectedResponseError
from normattiva.modelli import EstremiAtto, FinestraVigenza
from normattiva.testo import estrai, normalize_accents
from tests.contratto.impronta import confronta, impronta_json

DENOMINAZIONI = st.sampled_from(
    ["legge", "decreto.legge", "decreto.legislativo", "regio.decreto", "costituzione"]
)
ARTICOLI = st.from_regex(r"\A[1-9][0-9]{0,3}(\.[1-9])?(bis|ter|quater)?\Z")
COMMI = st.from_regex(r"\A[1-9][0-9]{0,2}(-let[a-z])?\Z")
NUMERI = st.integers(min_value=1, max_value=99999).map(str)
ANNI = st.integers(min_value=1861, max_value=2026)
GIORNI = st.dates(min_value=date(1861, 1, 1), max_value=date(2026, 12, 31))


@st.composite
def urn(disegna: st.DrawFn, *, con_articolo: bool = False) -> Urn:
    anno = disegna(ANNI)
    ha_articolo = con_articolo or disegna(st.booleans())
    articolo = disegna(ARTICOLI) if ha_articolo else None
    return Urn(
        denominazione=disegna(DENOMINAZIONI),
        anno=anno,
        data=disegna(st.one_of(st.none(), st.dates(date(anno, 1, 1), date(anno, 12, 31)))),
        numero=disegna(st.one_of(st.none(), NUMERI)),
        allegato=disegna(st.one_of(st.none(), st.integers(1, 9).map(str))),
        articolo=articolo,
        comma=disegna(COMMI) if articolo else None,
        versione=disegna(
            st.one_of(
                st.none(), st.just("originale"), st.dates(date(1861, 1, 1), date(2026, 12, 31))
            )
        ),
    )


class TestUrn:
    @given(urn())
    def test_ricomporre_e_rileggere_torna_allo_stesso_urn(self, atteso: Urn) -> None:
        assert Urn.parse(str(atteso)) == atteso

    @given(urn())
    def test_la_forma_testuale_e_stabile(self, atteso: Urn) -> None:
        assert str(Urn.parse(str(atteso))) == str(atteso)

    @given(st.text(max_size=120))
    def test_il_parser_non_esplode_mai_in_altro_modo(self, testo: str) -> None:
        with suppress(InvalidUrnError):
            Urn.parse(testo)

    @given(urn())
    def test_senza_comma_e_idempotente(self, qualsiasi: Urn) -> None:
        assert qualsiasi.senza_comma.senza_comma == qualsiasi.senza_comma

    @given(urn())
    def test_senza_comma_non_tocca_nient_altro(self, qualsiasi: Urn) -> None:
        spogliato = qualsiasi.senza_comma
        assert spogliato.comma is None
        assert (spogliato.denominazione, spogliato.anno, spogliato.articolo) == (
            qualsiasi.denominazione,
            qualsiasi.anno,
            qualsiasi.articolo,
        )

    @given(urn(), GIORNI)
    def test_con_vigenza_sostituisce_e_basta(self, qualsiasi: Urn, giorno: date) -> None:
        datato = qualsiasi.con_vigenza(giorno)
        assert datato.versione == giorno
        assert datato.senza_comma.con_vigenza(giorno) == datato.senza_comma

    @given(urn(), ARTICOLI)
    def test_con_articolo_scarta_il_comma(self, qualsiasi: Urn, articolo: str) -> None:
        assert qualsiasi.con_articolo(articolo).comma is None

    @given(urn())
    def test_il_permalink_contiene_l_urn(self, qualsiasi: Urn) -> None:
        assert qualsiasi.permalink.endswith(str(qualsiasi))

    @given(urn())
    def test_ogni_urn_e_hashabile(self, qualsiasi: Urn) -> None:
        assert len({qualsiasi, Urn.parse(str(qualsiasi))}) == 1


class TestDate:
    @given(GIORNI)
    def test_le_tre_forme_dicono_la_stessa_data(self, giorno: date) -> None:
        compatta = giorno.strftime("%Y%m%d")
        italiana = giorno.strftime("%d/%m/%Y")
        assert leggi_data(compatta) == giorno
        assert leggi_data(giorno.isoformat()) == giorno
        assert leggi_data(italiana) == giorno

    @given(GIORNI)
    def test_l_istante_iso_perde_l_ora_e_tiene_il_giorno(self, giorno: date) -> None:
        assert leggi_data(f"{giorno.isoformat()}T00:00:00Z") == giorno

    @given(st.text(max_size=40))
    def test_una_data_illeggibile_non_esplode_in_altro_modo(self, testo: str) -> None:
        with suppress(UnexpectedResponseError):
            leggi_data(testo)


class TestFinestraVigenza:
    @given(GIORNI, st.integers(min_value=0, max_value=20000))
    def test_contiene_ogni_giorno_fra_gli_estremi(self, inizio: date, durata: int) -> None:
        fine = inizio + timedelta(days=durata)
        assume(fine.year <= 2026)
        finestra = FinestraVigenza(inizio, fine)
        assert finestra.contiene(inizio)
        assert finestra.contiene(fine)
        assert finestra.contiene(inizio + timedelta(days=durata // 2))

    @given(GIORNI, st.integers(min_value=1, max_value=5000))
    def test_non_contiene_fuori_dagli_estremi(self, inizio: date, scarto: int) -> None:
        finestra = FinestraVigenza(inizio, inizio)
        assert not finestra.contiene(inizio - timedelta(days=scarto))
        assert not finestra.contiene(inizio + timedelta(days=scarto))

    @given(GIORNI, GIORNI)
    def test_una_finestra_aperta_contiene_ogni_giorno_successivo(
        self, inizio: date, giorno: date
    ) -> None:
        assume(giorno >= inizio)
        assert FinestraVigenza(inizio).contiene(giorno)


class TestNormalizzaAccenti:
    @given(st.text(max_size=200))
    def test_e_idempotente(self, testo: str) -> None:
        una_volta = normalize_accents(testo)
        assert normalize_accents(una_volta) == una_volta

    @given(st.text(alphabet=st.characters(blacklist_characters="'"), max_size=200))
    def test_senza_apostrofi_non_tocca_nulla(self, testo: str) -> None:
        assert normalize_accents(testo) == testo

    @given(st.text(max_size=200))
    def test_non_allunga_mai_il_testo(self, testo: str) -> None:
        assert len(normalize_accents(testo)) <= len(testo)


class TestEstrazione:
    @given(st.text(max_size=300))
    def test_non_esplode_su_marcatura_qualsiasi(self, testo: str) -> None:
        contenuto = estrai(testo)
        assert isinstance(contenuto.corpo, str)

    @given(st.text(max_size=300))
    def test_il_corpo_non_contiene_mai_tag(self, testo: str) -> None:
        assert "<div" not in estrai(f"<div>{testo}</div>").corpo

    @given(st.lists(st.text(alphabet="abcdefg ", min_size=1, max_size=20), max_size=10))
    def test_ogni_comma_marcato_viene_ritrovato(self, testi: list[str]) -> None:
        commi = "".join(
            f'<div class="art-comma-div-akn">'
            f'<span class="comma-num-akn">{n}. </span>'
            f'<span class="art_text_in_comma">{t}</span></div>'
            for n, t in enumerate(testi, start=1)
        )
        estratti = estrai(f'<div class="bodyTesto">{commi}</div>').commi
        assert [c.numero for c in estratti] == [str(n) for n in range(1, len(testi) + 1)]


class TestCitazione:
    @given(DENOMINAZIONI, GIORNI, st.one_of(st.none(), NUMERI))
    def test_la_citazione_porta_sempre_l_anno(
        self, denominazione: str, giorno: date, numero: str | None
    ) -> None:
        citazione = EstremiAtto(denominazione.upper(), giorno, numero).citazione
        assert str(giorno.year) in citazione

    @given(DENOMINAZIONI, GIORNI, NUMERI)
    def test_col_numero_la_citazione_lo_mostra(
        self, denominazione: str, giorno: date, numero: str
    ) -> None:
        assert f"n. {numero}" in EstremiAtto(denominazione.upper(), giorno, numero).citazione

    @given(DENOMINAZIONI, GIORNI)
    def test_senza_numero_la_citazione_non_lo_inventa(
        self, denominazione: str, giorno: date
    ) -> None:
        assert "n. " not in EstremiAtto(denominazione.upper(), giorno, None).citazione


PAYLOAD = st.recursive(
    st.one_of(st.none(), st.booleans(), st.integers(), st.floats(allow_nan=False), st.text()),
    lambda dentro: st.one_of(
        st.lists(dentro, max_size=4),
        st.dictionaries(st.text(min_size=1, max_size=8), dentro, max_size=4),
    ),
    max_leaves=15,
)


class TestConfrontoDelleImpronte:
    @given(PAYLOAD)
    @settings(max_examples=100)
    def test_una_risposta_non_devia_da_se_stessa(self, payload: object) -> None:
        forma = impronta_json(payload)
        assert confronta(forma, forma) == []

    @given(PAYLOAD)
    @settings(max_examples=100)
    def test_i_valori_non_spostano_l_impronta(self, payload: object) -> None:
        assert impronta_json(payload).keys() == impronta_json(payload).keys()

    @given(st.dictionaries(st.text(min_size=1, max_size=6), st.integers(), min_size=1, max_size=4))
    def test_togliere_un_campo_e_sempre_una_rottura(self, payload: dict) -> None:
        chiave = next(iter(payload))
        rimasto = {k: v for k, v in payload.items() if k != chiave}
        derive = confronta(impronta_json(payload), impronta_json(rimasto))
        assert any(d.rompe for d in derive)

    @given(st.dictionaries(st.text(min_size=1, max_size=6), st.integers(), max_size=4))
    def test_aggiungere_un_campo_non_e_mai_una_rottura(self, payload: dict) -> None:
        assume("aggiunto" not in payload)
        derive = confronta(impronta_json(payload), impronta_json({**payload, "aggiunto": 1}))
        assert not any(d.rompe for d in derive)
