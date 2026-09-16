"""bibo-clean-output — enforce Bibo's output cleanliness AND brain schema.

This plugin wires three hooks to keep the Bibo agent honest:

1. ``transform_llm_output`` — strip Bibo's internal thoughts from the LLM's
   response before it reaches the user, controlled by ``debug_mode`` in
   ``brain.json``.

2. ``post_tool_call`` — after any tool writes to ``/opt/data/hi-bibo/brain.json``,
   validate the file against the template schema. If required top-level keys
   are missing (Bibo dropped them during a rewrite), restore them from
   ``brain.template.json`` WITHOUT touching keys Bibo did set. This keeps
   Bibo's persistent memory structurally intact across turns.

3. ``post_llm_call`` — append quality telemetry (no message bodies) to
   ``logs/analytics.jsonl``. The ``/bibo-analytics`` slash command scores
   week-over-week proxies. Bibo itself must not read this report.

Hooks are scoped to the ``bibo`` profile — the plugin lives under
``/opt/data/profiles/bibo/plugins/`` and is opt-in via ``plugins.enabled``
in the profile's config.yaml. Other profiles never see it.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BIBO_DIR = os.environ.get("BIBO_DIR", "/opt/data/hi-bibo")
BRAIN_PATH = os.path.join(BIBO_DIR, "brain.json")
BRAIN_TEMPLATE_PATH = os.path.join(BIBO_DIR, "brain.template.json")
THOUGHTS_LOG = os.path.join(BIBO_DIR, "logs", "thoughts.log")

# Default terminator; rebuilt from partner.name when brain.json is available.
TERMINATOR_RE = re.compile(r"[,\s]*\bbibo\b", re.IGNORECASE)


def _load_brain() -> Dict[str, Any]:
    try:
        with open(BRAIN_PATH, "r", encoding="utf-8") as f:
            brain = json.load(f)
        return brain if isinstance(brain, dict) else {}
    except (OSError, ValueError):
        return {}


def _partner_name(brain: Optional[Dict[str, Any]] = None) -> str:
    brain = brain if brain is not None else _load_brain()
    partner = brain.get("partner") or {}
    name = str(partner.get("name") or "Bibo").strip() or "Bibo"
    return name


def _terminator_re() -> re.Pattern:
    name = re.escape(_partner_name())
    return re.compile(rf"[,\s]*\b(?:{name}|bibo)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# transform_llm_output — strip trailing thoughts from user-facing message
# ---------------------------------------------------------------------------

def _read_debug_mode() -> bool:
    """Return brain.json's debug_mode flag; default False on any failure."""
    try:
        with open(BRAIN_PATH, "r", encoding="utf-8") as f:
            brain = json.load(f)
        return bool(brain.get("debug_mode", False))
    except (OSError, ValueError) as exc:
        logger.debug("bibo-clean-output: cannot read debug_mode from %s: %s", BRAIN_PATH, exc)
        return False


def _append_thoughts(cut_tail: str) -> None:
    """Append cut thoughts to thoughts.log with timestamp. Never raises."""
    try:
        os.makedirs(os.path.dirname(THOUGHTS_LOG), exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"\n[{ts}] [bibo-clean-output] Cut trailing thoughts from LLM response:\n"
            f"{cut_tail.strip()}\n"
        )
        with open(THOUGHTS_LOG, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError as exc:
        logger.warning("bibo-clean-output: cannot append to %s: %s", THOUGHTS_LOG, exc)


def _enforce_decision_slot(response_text: str) -> Optional[str]:
    """If the last breath slot is SILENT and still fresh, do not deliver a message."""
    scripts = os.path.join(BIBO_DIR, "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        from decision import load_decision  # type: ignore
    except Exception:
        return None
    decision = load_decision()
    if not decision or decision.get("slot") != "SILENT":
        return None
    ts_raw = decision.get("ts")
    try:
        ts = datetime.fromisoformat(str(ts_raw))
    except (TypeError, ValueError):
        return None
    now = datetime.now().astimezone()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=now.tzinfo)
    age = (now - ts).total_seconds()
    if age < 0 or age > 20 * 60:
        return None
    stripped = (response_text or "").strip()
    if stripped in ("[SILENT]", "SILENT"):
        return None
    _append_thoughts(
        f"[SLOT SILENT — swallowed outbound]\n{response_text}"
    )
    logger.info("bibo-clean-output: slot SILENT enforced, dropped %d chars", len(response_text or ""))
    return "[SILENT]"


def _on_transform_llm_output(
    response_text: str = "",
    session_id: str = "",
    model: str = "",
    platform: str = "",
    **_kwargs: Any,
) -> Optional[str]:
    """Strip everything after the first ',bibo' terminator.

    Returns:
        - New string (cleaned message) → replaces the response
        - None → leave response unchanged (debug mode, no terminator, empty)
    """
    if not response_text:
        return None

    if _read_debug_mode():
        return None

    enforced = _enforce_decision_slot(response_text)
    if enforced is not None:
        return enforced

    # SILENT protocol — cron jobs return exactly "[SILENT]" to suppress
    # delivery entirely. Hermes gateway handles this natively; the plugin
    # must NOT touch it. Also accept the bare word (belt-and-braces).
    stripped = response_text.strip()
    if stripped == "[SILENT]" or stripped == "SILENT":
        return None

    match = _terminator_re().search(response_text)
    marker = _partner_name().lower()
    if match is None:
        # No 'bibo' terminator found — this is Bibo's second, "thinking"
        # message that leaked out after a tool call. Replace the entire
        # content with the bare marker 'bibo' so the user sees only that
        # short signal on Telegram instead of a paragraph of internal
        # reasoning. The full original text is preserved in thoughts.log.
        _append_thoughts(
            f"[FULL RESPONSE HAD NO '{marker}' TERMINATOR — replaced with marker]\n{response_text}"
        )
        logger.info(
            "bibo-clean-output: no terminator (len=%d) — replacing with marker "
            "(session=%s platform=%s)",
            len(response_text), session_id, platform,
        )
        return marker

    cut_at = match.start()  # cut BEFORE the ',bibo' — strip terminator itself
    message = response_text[:cut_at].rstrip(" ,\t\n")
    tail = response_text[match.end():]

    if not tail.strip():
        return None

    _append_thoughts(tail)
    logger.info(
        "bibo-clean-output: stripped %d chars of trailing thoughts (session=%s platform=%s)",
        len(tail), session_id, platform,
    )
    return message


# ---------------------------------------------------------------------------
# post_tool_call — enforce brain.json schema after every write
# ---------------------------------------------------------------------------

# Cache the template in memory; reload it if the file changes on disk.
_template_cache: Dict[str, Any] = {"mtime": 0.0, "data": None}


def _load_template() -> Optional[Dict[str, Any]]:
    """Load brain.template.json, cached by mtime. Returns None on failure."""
    try:
        st = os.stat(BRAIN_TEMPLATE_PATH)
        if _template_cache["data"] is None or st.st_mtime != _template_cache["mtime"]:
            with open(BRAIN_TEMPLATE_PATH, "r", encoding="utf-8") as f:
                _template_cache["data"] = json.load(f)
            _template_cache["mtime"] = st.st_mtime
        return _template_cache["data"]
    except (OSError, ValueError) as exc:
        logger.warning("bibo-clean-output: cannot load template %s: %s", BRAIN_TEMPLATE_PATH, exc)
        return None


def _touches_brain_json(tool_name: str, args: Optional[Dict[str, Any]]) -> bool:
    """True if this tool call likely wrote to brain.json."""
    if not isinstance(args, dict):
        return False
    if tool_name not in ("write_file", "patch"):
        return False
    path = args.get("path") or ""
    if not isinstance(path, str):
        return False
    # Normalize — accept absolute path or any suffix match
    try:
        return os.path.realpath(path) == os.path.realpath(BRAIN_PATH)
    except OSError:
        return path.endswith("hi-bibo/brain.json")


def _repair_brain_schema() -> List[str]:
    """Ensure brain.json has every top-level key from template.

    Only ADDS missing keys — never overwrites keys Bibo has set. Also runs
    a soft check that the JSON is valid; if not, we log loudly and back off
    (do NOT clobber a corrupted file — Kamil can inspect it).

    Returns the list of restored keys (empty if nothing changed).
    """
    template = _load_template()
    if template is None:
        return []

    try:
        with open(BRAIN_PATH, "r", encoding="utf-8") as f:
            brain = json.load(f)
    except FileNotFoundError:
        # Bibo (or something) deleted brain.json entirely — restore from template
        logger.warning("bibo-clean-output: %s missing, restoring from template", BRAIN_PATH)
        try:
            with open(BRAIN_PATH, "w", encoding="utf-8") as f:
                json.dump(template, f, indent=2, ensure_ascii=False)
                f.write("\n")
            return ["__restored__"]
        except OSError as exc:
            logger.error("bibo-clean-output: cannot restore brain.json: %s", exc)
            return []
    except (OSError, ValueError) as exc:
        # Corrupted or unreadable — do NOT touch it. Log for human inspection.
        logger.error(
            "bibo-clean-output: brain.json is corrupted or unreadable (%s) — leaving as-is for inspection",
            exc,
        )
        return []

    if not isinstance(brain, dict):
        logger.error(
            "bibo-clean-output: brain.json root is not an object (type=%s) — leaving as-is",
            type(brain).__name__,
        )
        return []

    # Find missing top-level keys
    missing = [k for k in template.keys() if k not in brain]
    if not missing:
        return []

    # Restore missing keys from template, preserve everything Bibo set
    for key in missing:
        brain[key] = template[key]

    try:
        with open(BRAIN_PATH, "w", encoding="utf-8") as f:
            json.dump(brain, f, indent=2, ensure_ascii=False)
            f.write("\n")
        logger.info(
            "bibo-clean-output: restored missing brain.json keys: %s",
            ", ".join(missing),
        )
        # Log the repair for Kamil to see
        try:
            os.makedirs(os.path.dirname(THOUGHTS_LOG), exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(THOUGHTS_LOG, "a", encoding="utf-8") as f:
                f.write(
                    f"\n[{ts}] [bibo-clean-output] SCHEMA REPAIR — Bibo dropped these "
                    f"top-level keys from brain.json, restored from template: {', '.join(missing)}\n"
                )
        except OSError:
            pass
        return missing
    except OSError as exc:
        logger.error("bibo-clean-output: cannot write repaired brain.json: %s", exc)
        return []


def _on_post_tool_call(
    tool_name: str = "",
    args: Optional[Dict[str, Any]] = None,
    result: Any = None,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    **_kwargs: Any,
) -> None:
    """After Bibo writes brain.json, verify schema integrity and log the write."""
    if not _touches_brain_json(tool_name, args):
        return
    repaired = _repair_brain_schema()
    analytics = _analytics_mod()
    if analytics is None:
        return
    try:
        analytics.emit_brain_write(repaired_keys=repaired)
    except Exception as exc:
        logger.debug("bibo-clean-output: analytics emit_brain_write failed: %s", exc)


# ---------------------------------------------------------------------------
# /bibo-profile — slash command showing the agent's self-state
# ---------------------------------------------------------------------------

# Character parameter descriptions used in the profile card.
_CHAR_DESCRIPTIONS = {
    "bezposredniosc": "bezpośredniość — jak wprost formułuje obserwacje",
    "cierpliwosc": "cierpliwość — jak długo czeka na Twoje tempo",
    "humor": "humor — ile luzu w tonie",
    "prowokacyjnosc": "prowokacyjność — jak mocno stawia lustro",
    "emocjonalnosc": "emocjonalność — ile pozwala sobie na ton uczuciowy",
    "ciekawosc": "ciekawość — jak głęboko drąży to co mówisz",
}

_PHASE_DESCRIPTIONS = {
    "adaptation": "adaptacja — obserwuje, buduje model, mało pisze",
    "partnership": "partnerstwo — inicjuje, konfrontuje, aktywny",
    "silence": "cisza — user zniknął, tylko sygnały życia",
}


def _bar(value: float, width: int = 10) -> str:
    """Render a 0-1 value as a text bar. Handles non-numeric input gracefully."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "?" * width
    v = max(0.0, min(1.0, v))
    filled = int(round(v * width))
    return "█" * filled + "░" * (width - filled)


def _handle_bibo_profile(raw_args: str) -> Optional[str]:
    """Render Bibo's self-state as a compact card.

    Shows ONLY data about the agent itself (phase, breath count, character
    parameters, what forms of communication worked/didn't). Does NOT include
    anything about the user (profile / preferences / habits stay private and
    are not surfaced through this command — Kamil asked for 'jakiego bibo
    stworzyliśmy', not for a summary of himself).
    """
    try:
        with open(BRAIN_PATH, "r", encoding="utf-8") as f:
            brain = json.load(f)
    except (OSError, ValueError) as exc:
        return f"❌ Nie mogę odczytać brain.json: {exc}"

    lines = ["🫧 *Bibo — karta partnera*", ""]

    phase = brain.get("phase", "?")
    phase_desc = _PHASE_DESCRIPTIONS.get(phase, phase)
    lines.append(f"*Faza:* {phase_desc}")

    breath = brain.get("breath_count", 0)
    lines.append(f"*Oddechy:* {breath}")

    last_updated = brain.get("last_updated") or "—"
    lines.append(f"*Ostatnia aktualizacja:* {last_updated}")

    debug = brain.get("debug_mode", False)
    lines.append(f"*Tryb debug:* {'włączony (myśli lecą do Ciebie)' if debug else 'wyłączony'}")

    lines.append("")
    lines.append("*Charakter (ewoluuje z rozmowy):*")
    char = brain.get("charakter_bibo") or {}
    for key, desc in _CHAR_DESCRIPTIONS.items():
        val = char.get(key)
        bar = _bar(val)
        if isinstance(val, (int, float)):
            val_str = f"{val:.2f}"
        else:
            val_str = "?"
        lines.append(f"  `{bar}` {val_str}  {desc}")

    co_dziala = brain.get("co_dziala") or {}
    skuteczne = co_dziala.get("skuteczne") or []
    nieskuteczne = co_dziala.get("nieskuteczne") or []

    lines.append("")
    lines.append(f"*Co Bibo już wie że na Ciebie działa* ({len(skuteczne)}):")
    if skuteczne:
        for item in skuteczne:
            lines.append(f"  ✓ {item}")
    else:
        lines.append("  — jeszcze nic potwierdzonego —")

    lines.append("")
    lines.append(f"*Co się nie sprawdziło* ({len(nieskuteczne)}):")
    if nieskuteczne:
        for item in nieskuteczne:
            lines.append(f"  ✗ {item}")
    else:
        lines.append("  — jeszcze nic negatywnego —")

    lines.append("")
    lines.append(
        f"_Dane z {BRAIN_PATH}. Nic tu nie idzie do modelu językowego — czysty odczyt pliku._"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Analytics — quality telemetry (operator-only, never fed back to the LLM)
# ---------------------------------------------------------------------------

def _analytics_mod():
    """Import scripts/analytics.py from BIBO_DIR. Fail open."""
    scripts = os.path.join(BIBO_DIR, "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        import analytics as analytics_mod  # type: ignore
        return analytics_mod
    except Exception as exc:
        logger.debug("bibo-clean-output: cannot import analytics: %s", exc)
        return None


def _on_post_llm_call(
    user_message: str = "",
    assistant_response: str = "",
    session_id: str = "",
    platform: str = "",
    **_kwargs: Any,
) -> None:
    """Record inbound/outbound turns into analytics.jsonl. No message bodies."""
    analytics = _analytics_mod()
    if analytics is None:
        return
    try:
        if user_message:
            analytics.emit_inbound(
                user_message,
                session_id=session_id or "",
                platform=platform or "",
            )
        if assistant_response:
            leak = assistant_response.strip().lower() == "bibo"
            analytics.emit_outbound(
                assistant_response,
                session_id=session_id or "",
                platform=platform or "",
                thought_leak=leak,
            )
    except Exception as exc:
        logger.debug("bibo-clean-output: analytics turn emit failed: %s", exc)


def _handle_bibo_analytics(raw_args: str) -> Optional[str]:
    """Telegram card: quality index vs previous window. Pure file read + math."""
    analytics = _analytics_mod()
    if analytics is None:
        return "Nie mogę załadować scripts/analytics.py — skopiuj plik do $BIBO_DIR/scripts/."
    try:
        days = 7
        token = (raw_args or "").strip().split()
        if token and token[0].isdigit():
            days = max(1, min(30, int(token[0])))
        report = analytics.build_report(days=days)
        return analytics.format_telegram_report(report)
    except Exception as exc:
        return f"Błąd analityki: {exc}"


SETUP_VOICES = {
    "zofia": "pl-PL-ZofiaNeural",
    "marek": "pl-PL-MarekNeural",
    "aria": "en-US-AriaNeural",
    "andrew": "en-US-AndrewNeural",
}

SETUP_NAMES = ("Mira", "Nox", "Olek", "Iga", "Remi", "Lila", "Pio", "Nala", "Sage", "Tori", "Bibo")


def _save_brain(brain: Dict[str, Any]) -> None:
    with open(BRAIN_PATH, "w", encoding="utf-8") as f:
        json.dump(brain, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _handle_bibo_setup(raw_args: str) -> Optional[str]:
    """Deterministic partner wizard — no LLM. Imię, cel, język, TTS, częstość."""
    import random

    brain = _load_brain()
    if not brain:
        return "Nie mogę odczytać brain.json."
    partner = brain.setdefault("partner", {})
    tts = partner.setdefault("tts", {})
    contact = partner.setdefault("contact", {})
    args = (raw_args or "").strip()

    if not args or args in ("status", "stan"):
        suggestions = ", ".join(random.sample(SETUP_NAMES, 3))
        complete = bool((brain.get("setup") or {}).get("complete"))
        lines = [
            f"*Kreator partnera* ({'gotowe' if complete else 'do dokończenia'})",
            "",
            f"Imię: `{partner.get('name') or '—'}`",
            f"Język: `{partner.get('language') or 'pl'}`",
            f"Cel: {partner.get('goal') or '—'}",
            f"TTS: `{tts.get('voice') or '—'}` ({'on' if tts.get('enabled') else 'off'})",
            f"Częstość: `{contact.get('frequency') or 'normal'}`",
            "",
            "Ustawienia (wpisz dokładnie):",
            f"`/bibo-setup imię {suggestions.split(', ')[0]}`",
            "`/bibo-setup cel dowozić sprint bez nowych projektów`",
            "`/bibo-setup język pl` albo `en`",
            "`/bibo-setup tts zofia` · `marek` · `aria` · `andrew` · `off`",
            "`/bibo-setup częstość rzadko|normalnie|często`",
            "`/bibo-setup losuj` — nowe imiona",
            "`/bibo-setup gotowe`",
            "",
            "Głos na Telegramie (bańka Edge Neural, nie TTS Telegrama): `/voice tts`",
        ]
        return "\n".join(lines)

    lower = args.lower()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    if lower in ("losuj", "random"):
        picks = ", ".join(random.sample(SETUP_NAMES, 3))
        return f"Propozycje imienia: {picks}\nUstaw: `/bibo-setup imię {picks.split(', ')[0]}`"

    def _rest(prefix: str) -> str:
        return args[len(prefix):].strip()

    changed = None
    if lower.startswith("imię ") or lower.startswith("imie ") or lower.startswith("name "):
        partner["name"] = _rest(args.split()[0] + " ")
        changed = f"Imię: {partner['name']}"
    elif lower.startswith("cel ") or lower.startswith("goal "):
        partner["goal"] = _rest(args.split()[0] + " ")
        cele = brain.setdefault("cele_i_kierunek", {})
        deklaracje = list(cele.get("deklaracje") or [])
        if partner["goal"] and partner["goal"] not in deklaracje:
            deklaracje.insert(0, partner["goal"])
        cele["deklaracje"] = deklaracje
        cele["last_updated"] = now
        changed = f"Cel: {partner['goal']}"
    elif lower.startswith("język ") or lower.startswith("jezyk ") or lower.startswith("lang "):
        lang = _rest(args.split()[0] + " ").lower()
        partner["language"] = "en" if lang.startswith("en") else "pl"
        if partner["language"] == "en" and not tts.get("voice", "").startswith("en-"):
            tts["voice"] = SETUP_VOICES["aria"]
        if partner["language"] == "pl" and not str(tts.get("voice") or "").startswith("pl-"):
            tts["voice"] = SETUP_VOICES["zofia"]
        changed = f"Język: {partner['language']}"
    elif lower.startswith("tts "):
        key = _rest("tts ").lower()
        if key in ("off", "wyłącz", "wylacz"):
            tts["enabled"] = False
            tts["mode"] = "off"
            changed = "TTS wyłączony"
        elif key in SETUP_VOICES:
            tts["enabled"] = True
            tts["mode"] = "on"
            tts["provider"] = "edge"
            tts["voice"] = SETUP_VOICES[key]
            changed = f"TTS: {tts['voice']} — na czacie wpisz /voice tts"
        else:
            return "TTS: `zofia` `marek` `aria` `andrew` albo `off`."
    elif lower.startswith("częstość ") or lower.startswith("czestosc ") or lower.startswith("freq "):
        raw = _rest(args.split()[0] + " ").lower()
        mapping = {
            "rzadko": "rarely", "rarely": "rarely", "1": "rarely",
            "normalnie": "normal", "normal": "normal", "2": "normal",
            "często": "often", "czesto": "often", "often": "often", "3": "often",
        }
        if raw not in mapping:
            return "Częstość: `rzadko` `normalnie` `często`."
        contact["frequency"] = mapping[raw]
        changed = f"Częstość: {contact['frequency']}"
    elif lower in ("gotowe", "done", "ok"):
        brain.setdefault("setup", {})["complete"] = True
        brain["setup"]["completed_at"] = now
        changed = "Kreator zamknięty. Partner gotowy."
    else:
        return "Nie rozumiem. Wpisz `/bibo-setup` żeby zobaczyć komendy."

    brain.setdefault("setup", {})
    if partner.get("name") and partner.get("language"):
        brain["setup"]["complete"] = True
        brain["setup"]["completed_at"] = now
    try:
        _save_brain(brain)
    except OSError as exc:
        return f"Nie mogę zapisać brain.json: {exc}"
    return f"{changed}\nKonfiguracja zapisana. `/bibo-setup` pokaże stan."


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(ctx) -> None:
    ctx.register_hook("transform_llm_output", _on_transform_llm_output)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("post_llm_call", _on_post_llm_call)
    ctx.register_command(
        "bibo-profile",
        handler=_handle_bibo_profile,
        description="Pokaż aktualny stan Bibo: faza, charakter, co działa.",
    )
    ctx.register_command(
        "bibo-analytics",
        handler=_handle_bibo_analytics,
        description="Pokaż indeks jakości partnera vs poprzednie okno.",
    )
    ctx.register_command(
        "bibo-setup",
        handler=_handle_bibo_setup,
        description="Kreator partnera: imię, cel, język, TTS, częstość.",
    )
