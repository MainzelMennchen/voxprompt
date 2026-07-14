"""Trainingsdaten-Logging für zukünftiges Finetuning des Prompt-Tuners.

Nach jedem ERFOLGREICHEN Optimierungs-Call (Prompt-Modus) wird ein Paar
(rohes Diktat, Modell-Output) als JSONL-Zeile angehängt. Fallback-Fälle
(LLM down/Timeout) werden bewusst NICHT geloggt — kein Trainingssignal.

Das Feld "final" bleibt null; es ist für manuell korrigierte Endfassungen
reserviert (die App hat kein Editier-UI, das befüllt es also nie).

Logging-Fehler dürfen den Diktat-Flow niemals stören: append_pair() wirft
nie, sondern loggt Fehler nur auf die Konsole und meldet False zurück.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def append_pair(path: str | Path, model_label: str, raw: str, output: str) -> bool:
    """Hängt ein Trainingspaar als eine JSONL-Zeile an (Verzeichnis wird angelegt).

    Rückgabe: True wenn geschrieben, False bei jedem Fehler (nie eine Exception).
    """
    try:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                "model": model_label,
                "raw": raw,
                "output": output,
                "final": None,
            },
            ensure_ascii=False,
        )
        with target.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return True
    except Exception as exc:  # noqa: BLE001 — Logging darf den Hauptflow nie stören
        print(f"[voxprompt] Trainingslog fehlgeschlagen (ignoriert): {exc}", flush=True)
        return False
