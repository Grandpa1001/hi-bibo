"""Komendy Bibo w CLI Hermesa.

    hermes bibo update    — pobiera i uruchamia update.sh z GitHuba (nic nie robi, gdy wersja aktualna)
    hermes bibo update --force — wgrywa ponownie, nawet gdy wersja aktualna
    hermes bibo version   — wersje wgranych wtyczek i adres Mini App

Skrypt pobieramy z sieci, a nie z lokalnego repo, żeby aktualizacja działała
także wtedy, gdy repo na serwerze zniknęło albo jest stare.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SKRYPT = "https://raw.githubusercontent.com/Grandpa1001/hi-bibo/{galaz}/update.sh"


def _home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def _aktualizuj(args) -> int:
    url = SKRYPT.format(galaz=args.galaz)
    env = {**os.environ, "BIBO_GALAZ": args.galaz, "HERMES_HOME": str(_home())}
    flagi = " --force" if args.force else ""
    return subprocess.call(["bash", "-c", f'set -o pipefail; curl -fsSL "{url}" | bash -s --{flagi}'], env=env)


def _wersja(args) -> int:
    h = _home()
    try:
        print(f"{'wersja':12} {(h / 'local' / 'bibo_wersja').read_text().strip()[:7]}")
    except Exception:
        print(f"{'wersja':12} nieznana (przed pierwszym `hermes bibo update`)")
    for n in ("bibo-podpis", "bibo-cli", "bibo-tryby"):
        y = h / "plugins" / n / "plugin.yaml"
        wersja = "brak"
        if y.is_file():
            for linia in y.read_text(encoding="utf-8").splitlines():
                if linia.startswith("version:"):
                    wersja = linia.split(":", 1)[1].strip().strip('"')
        print(f"{n:12} {wersja}")
    try:
        stan = json.loads((h / "local" / "bibo_tryby" / "stan_tunelu.json").read_text(encoding="utf-8"))
        print(f"Mini App     {stan.get('url')}  (od {stan.get('od')})")
    except Exception:
        pass
    return 0


def _setup(parser) -> None:
    sub = parser.add_subparsers(dest="bibo_cmd")
    a = sub.add_parser("update", help="Update Bibo to the latest version from GitHub (no git, no questions)")
    a.add_argument("--branch", dest="galaz", default="main", help="repo branch (default: main)")
    a.add_argument("--force", action="store_true", help="reinstall even if already up to date")
    a.set_defaults(bibo_func=_aktualizuj)
    w = sub.add_parser("version", help="Installed Bibo plugin versions and Mini App URL")
    w.set_defaults(bibo_func=_wersja)
    parser.set_defaults(bibo_func=lambda a: (parser.print_help(), 0)[1])


def _handler(args) -> int:
    # Hermes ustawia `func=_handler` na parserze komendy; podkomendy mają własne `bibo_func`.
    func = getattr(args, "bibo_func", None)
    rc = func(args) if func else 0
    sys.stdout.flush()
    return rc or 0


def register(ctx):
    ctx.register_cli_command("bibo", help="Bibo: update and version", setup_fn=_setup,
                             handler_fn=_handler, description="Komendy Bibo (hi-bibo)")
