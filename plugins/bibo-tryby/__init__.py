"""bibo-tryby — tryby Bibo w Telegram Mini App (Bibotektyw).

Wtyczka dotyka Bibo w trzech miejscach, wszystkie opcjonalne:
- `pre_gateway_dispatch` — zapamiętuje źródło rozmowy (nic nie przechwytuje),
- `pre_llm_call` — dokleja zaległą notatkę z Mini App (fallback),
- `post_llm_call` — wykrywa znacznik propozycji `[[tryb:detektyw]]`
  (znacznik z tekstu usuwa `bibo-podpis`; `transform_llm_output` bierze tylko
  pierwszą podmianę, więc nie konkurujemy z podpisem).

Serwer API, tunel Cloudflare i Bot API żyją w osobnym wątku (`uslugi.py`),
który startuje tylko w procesie gatewaya.
"""
from __future__ import annotations

import logging

from . import gateway_most, uslugi

log = logging.getLogger("bibo-tryby")
ZNACZNIK = "[[tryb:detektyw]]"


def _na_wiadomosc(event=None, **_):
    try:
        src = getattr(event, "source", None)
        platforma = getattr(getattr(src, "platform", None), "value", "")
        if src is not None and platforma == "telegram":
            gateway_most.zapamietaj_zrodlo(src)
    except Exception:
        log.debug("bibo-tryby: pre_gateway_dispatch", exc_info=True)
    return None


def _przed_tura(platform: str = "", **_):
    try:
        if platform == "telegram":
            notatka = gateway_most.odbierz_notatki()
            if notatka:
                return {"context": notatka}
    except Exception:
        log.debug("bibo-tryby: pre_llm_call", exc_info=True)
    return None


def _po_turze(assistant_response: str = "", platform: str = "", **_):
    try:
        if platform == "telegram" and ZNACZNIK in (assistant_response or ""):
            log.info("bibo-tryby: wykryto znacznik propozycji")   # M0.6; wysyłka propozycji w M4
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
    ctx.register_hook("pre_gateway_dispatch", _na_wiadomosc)
    ctx.register_hook("pre_llm_call", _przed_tura)
    ctx.register_hook("post_llm_call", _po_turze)
    ctx.register_command("bt_diag", _komenda_diagnostyka, description="Bibotektyw: diagnostyka wtyczki")
    uslugi.uruchom_gdy_gateway()
