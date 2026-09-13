#!/usr/bin/env python3
"""Hi-Bibo breath script — outputs brain.json + context for the cron prompt."""
import json
import os
from datetime import datetime

BIBO_DIR = "/opt/data/hi-bibo"

# Load brain
brain_path = os.path.join(BIBO_DIR, "brain.json")
with open(brain_path, "r") as f:
    brain = json.load(f)

# Load knowledge (static)
knowledge_path = os.path.join(BIBO_DIR, "knowledge.md")
with open(knowledge_path, "r") as f:
    knowledge = f.read()

# Current time context
now = datetime.now()
hour = now.hour
day_name = now.strftime("%A")
timestamp = now.isoformat()

# Output context for the agent
print(f"## Aktualny czas")
print(f"Data: {now.strftime('%Y-%m-%d')} ({day_name})")
print(f"Godzina: {now.strftime('%H:%M')}")
print(f"Oddech nr: {brain['breath_count'] + 1}")
print()

print(f"## Stan brain.json")
print(f"```json")
print(json.dumps(brain, indent=2, ensure_ascii=False))
print(f"```")
print()

print(f"## Baza wiedzy")
print(knowledge)
