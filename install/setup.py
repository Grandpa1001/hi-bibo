#!/usr/bin/env python3
"""Hi-Bibo installer + first-run wizard.

Stawia profil Hermes, Telegram, TTS (Edge Neural, nie wbudowany głos Telegrama),
imię partnera, język, cel i cron oddechu.

    python3 install/setup.py
    python3 install/setup.py --yes --language pl --name Mira --goal "dowozić sprint"
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

NAMES = (
    "Mira", "Nox", "Olek", "Iga", "Remi", "Lila", "Pio", "Nala",
    "Sage", "Tori", "Bibo", "Kora", "Juno", "Ash", "Vega", "Leo",
)

VOICES = {
    "pl": {
        "zofia": ("pl-PL-ZofiaNeural", "Zofia — spokojny głos żeński, dobry do partnera"),
        "marek": ("pl-PL-MarekNeural", "Marek — głos męski, bardziej bezpośredni"),
    },
    "en": {
        "aria": ("en-US-AriaNeural", "Aria — clear, calm US English"),
        "andrew": ("en-US-AndrewNeural", "Andrew — warmer US English male"),
    },
}

DEFAULT_VOICE_KEY = {"pl": "zofia", "en": "aria"}

FREQ_LABELS = {
    "1": ("rarely", "rzadko — max 1 wiadomość dziennie"),
    "2": ("normal", "normalnie — kilka razy dziennie (rekomendowane)"),
    "3": ("often", "często — jak kumpel, bez ścisłego limitu (max 6/dzień)"),
}


def _prompt(question: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{question}{suffix}: ").strip()
    except EOFError:
        answer = ""
    return answer or (default or "")


def _pick(question: str, options: Sequence[Tuple[str, str]], default: str) -> str:
    print(question)
    for key, label in options:
        mark = " ←" if key == default else ""
        print(f"  {key}) {label}{mark}")
    choice = _prompt("Wybór", default)
    valid = {key for key, _ in options}
    return choice if choice in valid else default


def detect_bibo_dir() -> str:
    env = os.environ.get("BIBO_DIR")
    if env:
        return os.path.abspath(env)
    if os.path.isfile(os.path.join(REPO_ROOT, "brain.template.json")):
        return REPO_ROOT
    if os.path.isdir("/opt/data/hi-bibo"):
        return "/opt/data/hi-bibo"
    return REPO_ROOT


def detect_hermes_home() -> str:
    env = os.environ.get("HERMES_HOME")
    if env:
        return os.path.abspath(env)
    if os.path.isdir("/opt/data") and os.path.isdir("/opt/data/profiles"):
        return "/opt/data"
    return os.path.expanduser("~/.hermes")


def hermes_bin() -> Optional[str]:
    return shutil.which("hermes")


def run_hermes(args: Sequence[str], hermes_home: str, check: bool = False) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["HERMES_HOME"] = hermes_home
    return subprocess.run(
        [hermes_bin() or "hermes", *args],
        env=env,
        check=check,
        capture_output=True,
        text=True,
    )


def suggest_names(k: int = 3) -> List[str]:
    return random.sample(list(NAMES), k=min(k, len(NAMES)))


def voice_id(language: str, key: str) -> str:
    pack = VOICES.get(language) or VOICES["pl"]
    if key in pack:
        return pack[key][0]
    first = next(iter(pack.values()))
    return first[0]


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not an object")
    return data


def write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def merge_env(path: str, updates: Dict[str, str]) -> None:
    rows: List[str] = []
    existing: Dict[str, str] = {}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                raw = line.rstrip("\n")
                if "=" in raw and not raw.strip().startswith("#"):
                    key, val = raw.split("=", 1)
                    existing[key] = val
                rows.append(raw)
    for key, val in updates.items():
        existing[key] = val
    out = []
    seen = set()
    for raw in rows:
        if "=" in raw and not raw.strip().startswith("#"):
            key, _ = raw.split("=", 1)
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(raw)
    for key, val in updates.items():
        if key not in seen:
            out.append(f"{key}={val}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out).rstrip() + "\n")


def upsert_yaml_block(path: str, marker: str, block: str) -> None:
    """Replace a tagged block or append it. Avoids a PyYAML dependency."""
    start = f"# BEGIN {marker}"
    end = f"# END {marker}"
    payload = f"{start}\n{block.rstrip()}\n{end}\n"
    existing = ""
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            existing = fh.read()
    if start in existing and end in existing:
        pre = existing.split(start, 1)[0]
        post = existing.split(end, 1)[1]
        text = pre.rstrip() + "\n\n" + payload + post.lstrip("\n")
    else:
        text = existing.rstrip() + "\n\n" + payload
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.lstrip("\n") if not existing else text)


def copy_tree(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)


def build_brain(template: Dict[str, Any], *, name: str, language: str, goal: str,
                voice: str, tts_on: bool, frequency: str) -> Dict[str, Any]:
    brain = json.loads(json.dumps(template))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    brain["partner"] = {
        "name": name,
        "language": language,
        "goal": goal,
        "role": "partner",
        "tts": {
            "enabled": tts_on,
            "provider": "edge",
            "voice": voice,
            "mode": "on" if tts_on else "off",
        },
        "contact": {
            "frequency": frequency,
            "initiative": "balanced" if frequency == "normal" else ("agent" if frequency == "often" else "user"),
            "length": "short",
        },
    }
    brain["setup"] = {
        "complete": bool(name and language),
        "completed_at": now if name and language else None,
        "installer": "install/setup.py",
    }
    if goal:
        cele = brain.setdefault("cele_i_kierunek", {})
        deklaracje = list(cele.get("deklaracje") or [])
        if goal not in deklaracje:
            deklaracje.insert(0, goal)
        cele["deklaracje"] = deklaracje
        cele["last_updated"] = now
    brain.setdefault("wnioski", {
        "description": "Wnioski Bibo z dowodem — nie vibe",
        "entries": [],
        "last_updated": None,
    })
    return brain


def write_cron(path: str, *, user_id: str, workdir: str, name: str, language: str) -> None:
    lang_line = "Pisz po polsku." if language == "pl" else "Write in English."
    job = {
        "jobs": [
            {
                "id": str(uuid.uuid4()),
                "name": "bibo-breath",
                "prompt": (
                    f"Jesteś {name}. To jest Twój oddech.\n"
                    "Odczytaj prompt.md, knowledge.md i brain.json.\n"
                    "Slot decyzji (MUST_WRITE / MAY_WRITE / SILENT) jest już policzony — nie głosuj nad nim.\n"
                    "MUST_WRITE → wiadomość. SILENT → dokładnie [SILENT]. MAY_WRITE → pisz tylko gdy masz wniosek.\n"
                    f"Zaczynaj 'Hi', kończ ',{name.lower()}'. {lang_line}"
                ),
                "script": "breath.py",
                "no_agent": False,
                "attach_to_session": True,
                "origin": {
                    "platform": "telegram",
                    "chat_id": user_id,
                    "user_id": user_id,
                    "chat_type": "private",
                },
                "continuity": True,
                "schedule": {"kind": "interval", "minutes": 60, "display": "every 60m"},
                "enabled": True,
                "deliver": f"telegram:{user_id}",
                "workdir": workdir,
            }
        ],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(path, job)


def collect_interactive(args: argparse.Namespace) -> Dict[str, Any]:
    print()
    print("Hi-Bibo — kreator instalacji")
    print("Partner, nie chatbot. Kod decyduje kiedy pisać, model — co powiedzieć.")
    print()

    language = args.language
    if not language:
        language = {"1": "pl", "2": "en"}.get(
            _pick("Język partnera", [("1", "polski"), ("2", "English")], "1"),
            "pl",
        )

    suggestions = suggest_names()
    print(f"Propozycje imienia: {', '.join(suggestions)}")
    name = args.name or _prompt("Imię partnera", suggestions[0])

    goal = args.goal or _prompt(
        "Cel tej relacji (jedno zdanie — kontrakt partnera)",
        "dowozić to co sam deklaruję, bez nowego chaosu",
    )

    freq_key = args.frequency
    if not freq_key:
        picked = _pick("Jak często ma zagadywać?", list(FREQ_LABELS.items()), "2")
        freq_key = FREQ_LABELS[picked][0]
    elif freq_key in FREQ_LABELS:
        freq_key = FREQ_LABELS[freq_key][0]

    voice_key = args.tts or DEFAULT_VOICE_KEY[language]
    if not args.tts:
        voice_opts = [(k, v[1]) for k, v in VOICES[language].items()] + [("off", "bez głosu — tylko tekst")]
        voice_key = _pick("TTS (Edge Neural, nie głos Telegrama)", voice_opts, DEFAULT_VOICE_KEY[language])

    tts_on = voice_key != "off"
    voice = voice_id(language, voice_key) if tts_on else VOICES[language][DEFAULT_VOICE_KEY[language]][0]

    token = args.telegram_token or _prompt("Token bota od @BotFather")
    user_id = args.telegram_user_id or _prompt("Twoje Telegram user ID (@userinfobot)")

    return {
        "language": language,
        "name": name.strip() or suggestions[0],
        "goal": goal.strip(),
        "frequency": freq_key,
        "tts_on": tts_on,
        "voice": voice,
        "token": token.strip(),
        "user_id": user_id.strip(),
    }


def apply_install(cfg: Dict[str, Any], args: argparse.Namespace) -> int:
    bibo_dir = os.path.abspath(args.bibo_dir or detect_bibo_dir())
    hermes_root = os.path.abspath(args.hermes_home or detect_hermes_home())
    profile = args.profile
    profile_home = os.path.join(hermes_root, "profiles", profile)

    print()
    print(f"BIBO_DIR     {bibo_dir}")
    print(f"HERMES_HOME  {hermes_root}")
    print(f"profil       {profile} → {profile_home}")
    print(f"imię         {cfg['name']}")
    print(f"język        {cfg['language']}")
    print(f"TTS          {cfg['voice'] if cfg['tts_on'] else 'off'}")
    print()

    if not args.yes:
        ok = _prompt("Instalować? [Y/n]", "Y")
        if ok.lower() not in ("y", "yes", "t", "tak", ""):
            print("Anulowano.")
            return 1

    if not hermes_bin():
        print("Brak `hermes` w PATH. Zainstaluj Hermes Agent i spróbuj ponownie.")
        return 1

    if shutil.which("ffmpeg") is None and cfg["tts_on"]:
        print("Uwaga: brak ffmpeg — Edge TTS na Telegramie pójdzie jako plik, nie bańka głosowa.")
        print("  macOS: brew install ffmpeg    Debian/Ubuntu: sudo apt install ffmpeg")

    os.makedirs(bibo_dir, exist_ok=True)
    os.makedirs(os.path.join(bibo_dir, "logs"), exist_ok=True)

    template_path = os.path.join(bibo_dir, "brain.template.json")
    if not os.path.isfile(template_path):
        template_path = os.path.join(REPO_ROOT, "brain.template.json")
    template = load_json(template_path)
    brain = build_brain(
        template,
        name=cfg["name"],
        language=cfg["language"],
        goal=cfg["goal"],
        voice=cfg["voice"],
        tts_on=cfg["tts_on"],
        frequency=cfg["frequency"],
    )
    write_json(os.path.join(bibo_dir, "brain.json"), brain)

    created = run_hermes(
        ["profile", "create", profile, "--no-skills", "--description",
         f"Hi-Bibo: partner {cfg['name']}"],
        hermes_root,
    )
    if created.returncode != 0 and "already" not in (created.stderr or "").lower() and "exists" not in (created.stderr or created.stdout or "").lower():
        print((created.stderr or created.stdout or "profile create failed").strip())

    os.makedirs(profile_home, exist_ok=True)
    copy_tree(os.path.join(REPO_ROOT, "install", "SOUL.md"), os.path.join(profile_home, "SOUL.md"))
    copy_tree(
        os.path.join(REPO_ROOT, "install", "plugins", "bibo-clean-output"),
        os.path.join(profile_home, "plugins", "bibo-clean-output"),
    )
    os.makedirs(os.path.join(profile_home, "scripts"), exist_ok=True)
    for script in ("breath.py", "analytics.py", "decision.py"):
        src = os.path.join(REPO_ROOT, "scripts", script)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(profile_home, "scripts", script))

    env_updates = {}
    if cfg["token"]:
        env_updates["TELEGRAM_BOT_TOKEN"] = cfg["token"]
    if cfg["user_id"]:
        env_updates["TELEGRAM_ALLOWED_USERS"] = cfg["user_id"]
    env_updates["BIBO_DIR"] = bibo_dir
    if env_updates:
        merge_env(os.path.join(profile_home, ".env"), env_updates)

    uid = cfg["user_id"] or "0"
    tts_block = f"""tts:
  provider: edge
  speed: 1.0
  edge:
    voice: {cfg['voice']}
    speed: 1.0
stt:
  enabled: true
  provider: local
  local:
    model: small
agent:
  max_turns: 50
  reasoning_effort: medium
gateway:
  telegram:
    - hermes-telegram
platforms:
  telegram:
    enabled: true
    home_channel:
      platform: telegram
      chat_id: '{uid}'
      name: {cfg['name']}
      user_id: '{uid}'
"""
    upsert_yaml_block(os.path.join(profile_home, "config.yaml"), "HI-BIBO", tts_block)

    run_hermes(["config", "set", "plugins.enabled", '["bibo-clean-output"]'], profile_home)
    run_hermes(["config", "set", "display.memory_notifications", "off"], profile_home)
    run_hermes(["config", "set", "auxiliary.background_review.enabled", "false"], profile_home)
    run_hermes(["config", "set", "tts.provider", "edge"], profile_home)
    run_hermes(["config", "set", "tts.edge.voice", cfg["voice"]], profile_home)
    run_hermes(["config", "set", "stt.provider", "local"], profile_home)
    run_hermes(["config", "set", "stt.local.model", "small"], profile_home)

    write_cron(
        os.path.join(profile_home, "cron", "jobs.json"),
        user_id=uid,
        workdir=bibo_dir,
        name=cfg["name"],
        language=cfg["language"],
    )

    if args.start_gateway:
        run_hermes(["gateway", "stop", "--profile", profile], hermes_root)
        started = run_hermes(["gateway", "start", "--profile", profile], hermes_root)
        if started.returncode != 0:
            print((started.stderr or started.stdout or "gateway start failed").strip())
        else:
            print("Gateway uruchomiony.")

    print()
    print("Gotowe.")
    print(f"  1. Otwórz Telegram → bot → /start")
    print(f"  2. Dopnij resztę w czacie: /bibo-setup")
    print(f"  3. Głos (bańka, nie TTS Telegrama): /voice tts")
    print(f"  4. Karta partnera: /bibo-profile")
    if not cfg["token"] or not cfg["user_id"]:
        print("  Brak tokenu lub user ID — uzupełnij .env profilu i odpal setup jeszcze raz.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Hi-Bibo installer")
    p.add_argument("--yes", action="store_true", help="Bez pytań potwierdzających")
    p.add_argument("--bibo-dir", default=os.environ.get("BIBO_DIR"))
    p.add_argument("--hermes-home", default=os.environ.get("HERMES_HOME"))
    p.add_argument("--profile", default="bibo")
    p.add_argument("--language", choices=("pl", "en"))
    p.add_argument("--name")
    p.add_argument("--goal")
    p.add_argument("--frequency", choices=("rarely", "normal", "often", "1", "2", "3"))
    p.add_argument("--tts", help="zofia|marek|aria|andrew|off")
    p.add_argument("--telegram-token")
    p.add_argument("--telegram-user-id")
    p.add_argument("--start-gateway", action="store_true", default=True)
    p.add_argument("--no-start-gateway", action="store_false", dest="start_gateway")
    p.add_argument("--suggest-names", action="store_true")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.suggest_names:
        print(" ".join(suggest_names()))
        return 0
    if args.yes:
        language = args.language or "pl"
        tts_key = args.tts or DEFAULT_VOICE_KEY[language]
        cfg = {
            "language": language,
            "name": args.name or suggest_names(1)[0],
            "goal": args.goal or "",
            "frequency": {"1": "rarely", "2": "normal", "3": "often"}.get(args.frequency or "2", args.frequency or "normal"),
            "tts_on": tts_key != "off",
            "voice": voice_id(language, tts_key) if tts_key != "off" else voice_id(language, DEFAULT_VOICE_KEY[language]),
            "token": args.telegram_token or "",
            "user_id": args.telegram_user_id or "",
        }
        if cfg["frequency"] in FREQ_LABELS:
            cfg["frequency"] = FREQ_LABELS[cfg["frequency"]][0]
    else:
        cfg = collect_interactive(args)
    return apply_install(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
