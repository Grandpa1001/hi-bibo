"""bibo-tryby — tryby Bibo w Telegram Mini App (Bibotektyw).

Wtyczka dotyka Bibo w trzech miejscach, wszystkie opcjonalne:
- `pre_gateway_dispatch` — zapamiętuje źródło rozmowy; jedyne, co przechwytuje, to
  stuknięcia w siatkę stanu dnia właściciela (`siatka.py`, bez udziału modelu),
- `pre_llm_call` — dokleja zaległą notatkę z Mini App (fallback) i krótkie
  podsumowanie karty bieżącej sprawy oraz tryb dnia (`tryb.py`; przy okazji liczy turę
  do zaangażowania, same czasy bez treści),
- `post_llm_call` — raz dziennie, po pierwszej turze, pokazuje siatkę stanu dnia;
  wykrywa znacznik propozycji `[[tryb:detektyw]]`
  (znacznik z tekstu usuwa `bibo-podpis`; `transform_llm_output` bierze tylko
  pierwszą podmianę, więc nie konkurujemy z podpisem).

Serwer API, tunel Cloudflare i Bot API żyją w osobnym wątku (`uslugi.py`),
który startuje tylko w procesie gatewaya.
"""
from __future__ import annotations

import logging

from . import czat, gateway_most, karta, karta_narzedzie, kontakt, siatka, stan, tryb, uslugi

log = logging.getLogger("bibo-tryby")
ZNACZNIK = "[[tryb:detektyw]]"
_siatka_dzien: dict[str, object] = {}


def _stan_wlasciciela(user_id: str) -> str | None:
    """Id właściciela, gdy stan dnia jest włączony i dotyczy tego usera; inaczej None."""
    w = karta.wlasciciel()
    return w if w and str(user_id) == w and siatka.wlaczone() else None


def _na_wiadomosc(event=None, **_):
    try:
        src = getattr(event, "source", None)
        platforma = getattr(getattr(src, "platform", None), "value", "")
        if src is not None and platforma == "telegram":
            gateway_most.zapamietaj_zrodlo(src)
            tekst = getattr(event, "text", "") or ""
            w = _stan_wlasciciela(getattr(src, "user_id", "")) if siatka.rozpoznaj(tekst) else None
            u = uslugi.aktywne()
            if w and u and u.bot and getattr(src, "chat_type", "dm") == "dm":
                odp = siatka.obsluz(w, tekst)
                if odp:
                    u.zleć(siatka.wyslij(w, u, odp))
                    return {"action": "skip", "reason": "bibo-stan: obsłużone przez siatkę"}
    except Exception:
        log.debug("bibo-tryby: pre_gateway_dispatch", exc_info=True)
    return None


def _pokaz_siatke_gdy_pierwsza_tura(platform: str) -> None:
    """FR-1: raz dziennie, gdy dziś nie ma wpisu. Dzień już załatwiony pamiętamy w pamięci procesu,
    więc kolejne tury tego dnia nie dotykają bazy."""
    w = karta.wlasciciel()
    if platform != "telegram" or not w or not siatka.wlaczone() or gateway_most.ostatni_user() != w:
        return
    dzien = kontakt.teraz().astimezone(kontakt.strefa()).date()
    if _siatka_dzien.get(w) == dzien:
        return
    u = uslugi.aktywne()
    if not (u and u.bot):
        return   # usługi jeszcze wstają: spróbujemy przy następnej turze
    _siatka_dzien[w] = dzien
    if stan.czy_pokazac_siatke(w):
        u.zleć(siatka.wyslij(w, u))


def _komenda_stan(raw_args: str = "") -> str | None:
    """FR-7: `/stan` pokazuje siatkę; nowy wpis zastępuje tryb z poprzedniego."""
    w = karta.wlasciciel()
    u = uslugi.aktywne()
    if not w or not siatka.wlaczone():
        return "Stan dnia jest niedostępny w tej instancji."
    if not (u and u.bot):
        return "Teraz nie mogę pokazać siatki — spróbuj za chwilę."
    u.zleć(siatka.wyslij(w, u))
    return None


def _tryb_dnia(sender_id: str) -> str | None:
    """FR-3/FR-10: zlicza turę (czasy, bez treści) i zwraca wytyczne trybu dnia — jedno połączenie z bazą."""
    w = _stan_wlasciciela(sender_id)
    if not w:
        return None
    try:
        return tryb.kontekst(stan.rejestruj_ture(w))
    except Exception:
        log.debug("bibo-tryby: tryb dnia", exc_info=True)
        return None


def _przed_tura(platform: str = "", sender_id: str = "", **_):
    try:
        if platform == "telegram":
            czesci = [gateway_most.odbierz_notatki(), karta_narzedzie.podsumowanie(sender_id), _tryb_dnia(sender_id)]
            czesci = [c for c in czesci if c]
            if czesci:
                return {"context": "\n\n".join(czesci)}
    except Exception:
        log.debug("bibo-tryby: pre_llm_call", exc_info=True)
    return None


def _po_turze(assistant_response: str = "", platform: str = "", **_):
    try:
        _pokaz_siatke_gdy_pierwsza_tura(platform)
    except Exception:
        log.debug("bibo-tryby: siatka po turze", exc_info=True)
    try:
        if platform != "telegram" or ZNACZNIK not in (assistant_response or ""):
            return
        u = uslugi.aktywne()
        uid = gateway_most.ostatni_user()
        if u and uid:
            u.zleć(czat.wyslij_propozycje(uid, u))
        else:
            log.info("bibo-tryby: znacznik propozycji wykryty, ale usługi/user niedostępne")
    except Exception:
        log.debug("bibo-tryby: post_llm_call", exc_info=True)


def _komenda_diagnostyka(raw_args: str = "") -> str:
    u = uslugi.aktywne()
    d = gateway_most.diagnostyka()
    if u is None:
        return "bibo-tryby: usługi nie działają w tym procesie (czy gateway jest uruchomiony?)."
    return (f"bibo-tryby {u.ust.get('port')} · tunel: {u.url or 'brak (sprawdź cloudflared)'}\n"
            f"gateway: runner={d['runner']} pętla={d['petla']} telegram={d['adapter_telegram']}\n"
            f"Otwórz Mini App przyciskiem „🎲 Tryby” obok pola wiadomości.")


def register(ctx):
    try:
        ctx.register_auxiliary_task(
            "bibo_tryby", display_name="Bibo — tryby",
            description="Krótkie wywołania gier Bibo (Bibotektyw): pytanie śledczego i werdykt.",
            defaults={"provider": "anthropic", "model": "claude-haiku-4-5"})
    except Exception as e:
        log.warning("bibo-tryby: nie zarejestrowano zadania auxiliary: %s", e)
    try:
        karta_narzedzie.zarejestruj(ctx)
    except Exception as e:
        log.warning("bibo-tryby: nie zarejestrowano narzędzia bibo_karta: %s", e)
    ctx.register_hook("pre_gateway_dispatch", _na_wiadomosc)
    ctx.register_hook("pre_llm_call", _przed_tura)
    ctx.register_hook("post_llm_call", _po_turze)
    ctx.register_command("stan", _komenda_stan, description="Bibo: jak się dziś czujesz (siatka stanu)")
    ctx.register_command("bt_diag", _komenda_diagnostyka, description="Bibotektyw: diagnostyka wtyczki")
    uslugi.uruchom_gdy_gateway()
