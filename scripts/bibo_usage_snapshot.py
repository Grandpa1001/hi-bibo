#!/usr/bin/env python3
"""Dzienne zdjęcie licznika zużycia (cron `bibo-usage`, tryb bez modelu, 0 tokenów).

Nic nie wypisuje, więc Hermes nic nie wysyła na Telegram. Z różnic między
kolejnymi zdjęciami raport (bibo_raport.py) liczy zużycie na dzień.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bibo_raport  # noqa: E402

if bibo_raport.DB.exists():
    bibo_raport.snapshot(bibo_raport.usage_rows(bibo_raport.db()))
