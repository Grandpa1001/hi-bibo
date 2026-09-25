"""Ładuje wtyczki z katalogu `plugins/` tak jak Hermes (pakiet z relatywnymi importami)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def wtyczka(nazwa: str):
    katalog = REPO / "plugins" / nazwa
    modul = "test_plugin_" + nazwa.replace("-", "_")
    if modul in sys.modules:
        return sys.modules[modul]
    spec = importlib.util.spec_from_file_location(
        modul, katalog / "__init__.py", submodule_search_locations=[str(katalog)])
    m = importlib.util.module_from_spec(spec)
    sys.modules[modul] = m
    spec.loader.exec_module(m)
    return m


def podmodul(nazwa: str, sub: str):
    wtyczka(nazwa)
    return importlib.import_module(f"test_plugin_{nazwa.replace('-', '_')}.{sub}")
