"""Komendy Bibo w CLI Hermesa.

    hermes bibo update    — pobiera i uruchamia update.sh z GitHuba (nic nie robi, gdy wersja aktualna)
    hermes bibo update --force — wgrywa ponownie, nawet gdy wersja aktualna
    hermes bibo version   — wersje wgranych wtyczek i adres Mini App
    hermes bibo dry-run   — test promptów Bibotektywa na prawdziwym modelu, raport do oceny

Skrypt pobieramy z sieci, a nie z lokalnego repo, żeby aktualizacja działała
także wtedy, gdy repo na serwerze zniknęło albo jest stare.
"""
from __future__ import annotations

import importlib
import importlib.util
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


def _modul_trybow(nazwa: str):
    """Moduł wtyczki bibo-tryby — ten, który Hermes już załadował, albo świeżo z katalogu wtyczek."""
    katalog = _home() / "plugins" / "bibo-tryby"
    for mod in list(sys.modules.values()):
        plik = getattr(mod, "__file__", None) or ""
        if plik and Path(plik).resolve() == (katalog / "__init__.py").resolve():
            return importlib.import_module(f"{mod.__name__}.{nazwa}")
    if not (katalog / "__init__.py").is_file():
        return None
    spec = importlib.util.spec_from_file_location("bibo_tryby_cli", katalog / "__init__.py",
                                                  submodule_search_locations=[str(katalog)])
    m = importlib.util.module_from_spec(spec)
    sys.modules["bibo_tryby_cli"] = m
    spec.loader.exec_module(m)
    return importlib.import_module(f"bibo_tryby_cli.{nazwa}")


def _dry_run(args) -> int:
    sucho = _modul_trybow("sucho")
    if sucho is None:
        print("Brak wtyczki bibo-tryby — najpierw ją zainstaluj.")
        return 1
    raport = _home() / "local" / "bibo_tryby" / "raport_dry_run.md"
    print("Bibotektyw · test na sucho (prawdziwe Haiku, ~15 spraw, ok. 1–2 min)\n", flush=True)
    sucho.uruchom(raport=raport, wypisz=lambda s: print(s, flush=True))
    print(f"\nRaport: {raport}")
    print(f"Podgląd: cat {raport}")
    return 0


def _setup(parser) -> None:
    sub = parser.add_subparsers(dest="bibo_cmd")
    a = sub.add_parser("update", help="Update Bibo to the latest version from GitHub (no git, no questions)")
    a.add_argument("--branch", dest="galaz", default="main", help="repo branch (default: main)")
    a.add_argument("--force", action="store_true", help="reinstall even if already up to date")
    a.set_defaults(bibo_func=_aktualizuj)
    w = sub.add_parser("version", help="Installed Bibo plugin versions and Mini App URL")
    w.set_defaults(bibo_func=_wersja)
    d = sub.add_parser("dry-run", help="Test Bibotektyw prompts against the real model and write a report")
    d.set_defaults(bibo_func=_dry_run)
    parser.set_defaults(bibo_func=lambda a: (parser.print_help(), 0)[1])


def _handler(args) -> int:
    # Hermes ustawia `func=_handler` na parserze komendy; podkomendy mają własne `bibo_func`.
    func = getattr(args, "bibo_func", None)
    rc = func(args) if func else 0
    sys.stdout.flush()
    return rc or 0


def register(ctx):
    ctx.register_cli_command("bibo", help="Bibo: update, version, dry-run", setup_fn=_setup,
                             handler_fn=_handler, description="Komendy Bibo (hi-bibo)")
