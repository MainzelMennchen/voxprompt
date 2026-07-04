"""voxprompt — lokales Push-to-Talk-Diktiertool für macOS.

Push-to-Talk-Aufnahme -> mlx-whisper Transkription -> lokale LLM-Nachbearbeitung
in drei Modi (Roh / Bereinigt / Prompt-optimiert) -> Zwischenablage.

Siehe CLAUDE.md für den schrittweisen Bauplan.
"""

import os

# Xet-Downloader von Hugging Face deaktivieren: er stagt Dateien außerhalb des
# blobs/-Caches, wodurch unsere Download-Fortschrittsanzeige (Schritt 2) bis kurz
# vor Schluss bei 0 % hängt. Klassischer Download schreibt inkrementell -> sichtbarer
# Fortschritt. Muss VOR dem ersten huggingface_hub-Import gesetzt werden.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

__version__ = "0.1.0"
