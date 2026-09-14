"""bibo-clean-output — enforce Bibo's output cleanliness AND brain schema.

This plugin wires two hooks to keep the Bibo agent honest:

1. ``transform_llm_output`` — strip Bibo's internal thoughts from the LLM's
   response before it reaches the user, controlled by ``debug_mode`` in
   ``brain.json``.

2. ``post_tool_call`` — after any tool writes to ``/opt/data/hi-bibo/brain.json``,
   validate the file against the template schema. If required top-level keys
   are missing (Bibo dropped them during a rewrite), restore them from
   ``brain.template.json`` WITHOUT touching keys Bibo did set. This keeps
   Bibo's persistent memory structurally intact across turns.

Both hooks are scoped to the ``bibo`` profile — the plugin lives under
``/opt/data/profiles/bibo/plugins/`` and is opt-in via ``plugins.enabled``
in the profile's config.yaml. Other profiles never see it.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

BIBO_DIR = "/opt/data/hi-bibo"
BRAIN_PATH = os.path.join(BIBO_DIR, "brain.json")
BRAIN_TEMPLATE_PATH = os.path.join(BIBO_DIR, "brain.template.json")
THOUGHTS_LOG = os.path.join(BIBO_DIR, "logs", "thoughts.log")

# Match ',bibo' / ', bibo' / ' bibo' / '\nbibo' — optional leading punctuation
# and whitespace, then 'bibo' as a word. Everything matched here is stripped
# from the user-facing message (including the punctuation), so the message
# reads cleanly without a trailing ',bibo'.
TERMINATOR_RE = re.compile(r"[,\s]*\bbibo\b", re.IGNORECASE)


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

    # SILENT protocol — cron jobs return exactly "[SILENT]" to suppress
    # delivery entirely. Hermes gateway handles this natively; the plugin
    # must NOT touch it. Also accept the bare word (belt-and-braces).
    stripped = response_text.strip()
    if stripped == "[SILENT]" or stripped == "SILENT":
        return None

    match = TERMINATOR_RE.search(response_text)
    if match is None:
        # No 'bibo' terminator found — this is Bibo's second, "thinking"
        # message that leaked out after a tool call. Replace the entire
        # content with the bare marker 'bibo' so the user sees only that
        # short signal on Telegram instead of a paragraph of internal
        # reasoning. The full original text is preserved in thoughts.log.
        _append_thoughts(
            f"[FULL RESPONSE HAD NO 'bibo' TERMINATOR — replaced with marker]\n{response_text}"
        )
        logger.info(
            "bibo-clean-output: no 'bibo' terminator (len=%d) — replacing with marker "
            "(session=%s platform=%s)",
            len(response_text), session_id, platform,
        )
        return "bibo"

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


def _repair_brain_schema() -> None:
    """Ensure brain.json has every top-level key from template.

    Only ADDS missing keys — never overwrites keys Bibo has set. Also runs
    a soft check that the JSON is valid; if not, we log loudly and back off
    (do NOT clobber a corrupted file — Kamil can inspect it).
    """
    template = _load_template()
    if template is None:
        return

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
        except OSError as exc:
            logger.error("bibo-clean-output: cannot restore brain.json: %s", exc)
        return
    except (OSError, ValueError) as exc:
        # Corrupted or unreadable — do NOT touch it. Log for human inspection.
        logger.error(
            "bibo-clean-output: brain.json is corrupted or unreadable (%s) — leaving as-is for inspection",
            exc,
        )
        return

    if not isinstance(brain, dict):
        logger.error(
            "bibo-clean-output: brain.json root is not an object (type=%s) — leaving as-is",
            type(brain).__name__,
        )
        return

    # Find missing top-level keys
    missing = [k for k in template.keys() if k not in brain]
    if not missing:
        return

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
    except OSError as exc:
        logger.error("bibo-clean-output: cannot write repaired brain.json: %s", exc)


def _on_post_tool_call(
    tool_name: str = "",
    args: Optional[Dict[str, Any]] = None,
    result: Any = None,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    **_kwargs: Any,
) -> None:
    """After Bibo writes brain.json, verify schema integrity."""
    if _touches_brain_json(tool_name, args):
        _repair_brain_schema()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(ctx) -> None:
    ctx.register_hook("transform_llm_output", _on_transform_llm_output)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
