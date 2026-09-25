"""Jedyne miejsca, w których wtyczka dotyka gatewaya Hermesa.

1. Zapamiętanie źródła rozmowy (SessionSource) z `pre_gateway_dispatch`.
2. Wstrzyknięcie wiadomości wewnętrznej (`MessageEvent(internal=True)`) do
   prawdziwej sesji Bibo — tak Hermes sam budzi sesje po zadaniach w tle.
   Wywoływane z wątku usług, wykonywane na pętli gatewaya.
3. Fallback: gdy wstrzyknięcie się nie uda, notatka czeka na następną turę
   Bibo (`pre_llm_call`).
"""
from __future__ import annotations

import asyncio
import logging
import threading

from . import magazyn

log = logging.getLogger("bibo-tryby")

_zrodla: dict[str, object] = {}
_blokada = threading.Lock()


def zapamietaj_zrodlo(source) -> None:
    uid = str(getattr(source, "user_id", "") or getattr(source, "chat_id", "") or "")
    if uid and getattr(source, "chat_type", "dm") == "dm":
        with _blokada:
            _zrodla[uid] = source


def _runner():
    try:
        from gateway.run import _gateway_runner_ref
        return _gateway_runner_ref()
    except Exception:
        return None


def diagnostyka() -> dict:
    r = _runner()
    return {
        "runner": r is not None,
        "petla": getattr(r, "_gateway_loop", None) is not None if r else False,
        "adapter_telegram": _adapter(r) is not None if r else False,
        "zapamietane_zrodla": len(_zrodla),
    }


def _adapter(r):
    try:
        from gateway.config import Platform
        return (getattr(r, "adapters", None) or {}).get(Platform.TELEGRAM)
    except Exception:
        return None


def _zrodlo_dla(uid: str):
    with _blokada:
        if uid in _zrodla:
            return _zrodla[uid]
    from gateway.config import Platform
    from gateway.session import SessionSource
    return SessionSource(platform=Platform.TELEGRAM, chat_id=uid, chat_type="dm", user_id=uid)


async def wstrzyknij(uid: str, tekst: str) -> str:
    """Zwraca sposób dostarczenia: "sesja" albo "notatka" (fallback)."""
    try:
        r = _runner()
        petla = getattr(r, "_gateway_loop", None) if r else None
        adapter = _adapter(r) if r else None
        if petla is None or adapter is None:
            raise RuntimeError("brak gatewaya / pętli / adaptera Telegrama")
        from gateway.platforms.event import MessageEvent, MessageType
        evt = MessageEvent(text=tekst, message_type=MessageType.TEXT, source=_zrodlo_dla(uid), internal=True)
        fut = asyncio.run_coroutine_threadsafe(adapter.handle_message(evt), petla)
        await asyncio.wait_for(asyncio.wrap_future(fut), timeout=30)
        return "sesja"
    except Exception as e:
        log.warning("bibo-tryby: wstrzyknięcie nie powiodło się (%s) — zostawiam notatkę", e)
        zostaw_notatke(tekst)
        return "notatka"


def zostaw_notatke(tekst: str) -> None:
    stan = magazyn.czytaj("notatki.json", []) or []
    stan.append(tekst)
    magazyn.zapisz("notatki.json", stan[-5:])


def odbierz_notatki() -> str | None:
    stan = magazyn.czytaj("notatki.json", []) or []
    if not stan:
        return None
    magazyn.zapisz("notatki.json", [])
    return "\n\n".join(stan)
