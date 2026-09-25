"""Podpis Bibo dopisywany kodem, nie przez model.

Hook `transform_llm_output` dostaje gotową odpowiedź tuż przed wysłaniem
i dokleja na końcu " bibo". Model nie musi o podpisie pamiętać (mniej
instrukcji w prompcie, zero wiadomości bez podpisu).

Nie podpisujemy:
- odpowiedzi „ciszy” ([SILENT], NO_REPLY...) — inaczej cron uznałby
  „[SILENT] bibo” za treść i wysłał pustą zaczepkę;
- niczego poza Telegramem i cronem (np. `./raport.sh --opinia` w terminalu).

Przed podpisem usuwamy znaczniki sterujące innych wtyczek (np. `[[tryb:detektyw]]`
z `bibo-tryby`). `transform_llm_output` bierze tylko pierwszą podmianę tekstu,
więc sprzątanie musi być tutaj, a nie w drugiej wtyczce.
"""
from __future__ import annotations

import re

SIGNATURE = "bibo"
SEPARATOR = " "  # "\n\n" = podpis w osobnej linii
PLATFORMS = {"telegram", "cron"}

# Podpis, który model mógł dopisać z przyzwyczajenia (",bibo", " bibo") — usuwamy, by nie było dwóch.
_OWN_TAIL = re.compile(r"\s*,?\s*bibo[\s.!]*$")
# Znaczniki sterujące wtyczek: [[nazwa:wartosc]] — nigdy nie trafiają do usera.
_MARKERS = re.compile(r"[ \t]*\[\[[a-z_]+:[a-z0-9_-]+\]\]")


def _is_silence(text: str) -> bool:
    try:
        from gateway.response_filters import is_autonomous_silence_response  # ten sam test co cron Hermesa
        return bool(is_autonomous_silence_response(text))
    except Exception:
        lines = [l.strip().upper() for l in text.strip().splitlines() if l.strip()]
        markers = {"[SILENT]", "SILENT", "NO_REPLY", "[NO_REPLY]", "NO REPLY"}
        return not lines or lines[0] in markers or lines[-1] in markers


def sign(response_text=None, platform=None, **_):
    if not isinstance(response_text, str) or not response_text.strip():
        return None
    if str(platform or "").lower() not in PLATFORMS or _is_silence(response_text):
        return None
    text = _MARKERS.sub("", response_text).rstrip()
    text = _OWN_TAIL.sub("", text).rstrip()
    return f"{text}{SEPARATOR}{SIGNATURE}" if text else None


def register(ctx):
    ctx.register_hook("transform_llm_output", sign)
