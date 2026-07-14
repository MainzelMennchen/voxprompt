"""Modell-Verwaltung für die verteilbare App (Phase 2, Schritt 2).

- prüft, ob die benötigten Modelle im Hugging-Face-Cache liegen,
- lädt fehlende beim ersten Start herunter (mit Fortschritts-Callback),
- sorgt dafür, dass geladene Modelle für die Session im Speicher bleiben
  (Whisper-Loader wird gecacht; das LLM hält InProcessLLM bereits selbst).

Welche Modelle nötig sind, hängt vom Backend ab: Whisper immer; das Sprachmodell
nur im "inprocess"-Backend (im "endpoint"-Betrieb lädt es der Server selbst).
"""

from __future__ import annotations

import functools
import importlib
import os
import threading
from typing import Callable

from huggingface_hub import HfApi, snapshot_download
from huggingface_hub.constants import HF_HUB_CACHE

DEFAULT_WHISPER = "mlx-community/whisper-large-v3-mlx"

# Callback: (label, done_bytes, total_bytes). total kann 0 sein (unbekannt).
ProgressCb = Callable[[str, int, int], None]


def required_models(config: dict) -> dict[str, str]:
    """Liefert {Anzeigename: HF-Repo} der für das aktuelle Setup nötigen Modelle.

    Im inprocess-Backend zählen auch die per-Modus-Modelle (cleanup_model/
    prompt_model) dazu — die App lädt sie beim Moduswechsel und braucht sie
    daher lokal. Doppelte Repos werden nur einmal aufgeführt.
    """
    transcription = config.get("transcription", {})
    llm = config.get("llm", {})
    models = {"Spracherkennung": transcription.get("whisper_model", DEFAULT_WHISPER)}
    if llm.get("llm_backend", "endpoint") == "inprocess":
        seen: set[str] = set()
        for label, repo in (
            ("Sprachmodell", llm.get("llm_model")),
            ("Sprachmodell (Bereinigen)", llm.get("cleanup_model")),
            ("Sprachmodell (Prompt)", llm.get("prompt_model")),
        ):
            if repo and repo not in seen:
                models[label] = repo
                seen.add(repo)
    return models


def is_cached(repo: str) -> bool:
    """True, wenn der vollständige Snapshot lokal im HF-Cache liegt (kein Netz)."""
    try:
        snapshot_download(repo, local_files_only=True)
        return True
    except Exception:
        return False


def missing_models(config: dict) -> list[tuple[str, str]]:
    """[(Anzeigename, Repo)] der Modelle, die noch nicht lokal vorhanden sind."""
    return [(name, repo) for name, repo in required_models(config).items() if not is_cached(repo)]


def _total_size(repo: str) -> int:
    """Gesamtgröße des Repos in Bytes (für die Fortschrittsanzeige), 0 wenn unbekannt."""
    try:
        info = HfApi().model_info(repo, files_metadata=True)
        return sum((s.size or 0) for s in (info.siblings or []))
    except Exception:
        return 0


def _repo_cache_dir(repo: str) -> str:
    """Cache-Verzeichnis eines Repos: <HF_HUB_CACHE>/models--org--name."""
    return os.path.join(HF_HUB_CACHE, "models--" + repo.replace("/", "--"))


def _blobs_size(repo: str) -> int:
    """Bisher heruntergeladene Bytes = Größe des blobs/-Verzeichnisses (echte Daten,
    keine Symlinks). Erfasst auch *.incomplete-Teildateien während des Downloads."""
    blobs = os.path.join(_repo_cache_dir(repo), "blobs")
    total = 0
    for root, _dirs, files in os.walk(blobs):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def download_model(name: str, repo: str, on_progress: ProgressCb) -> None:
    """Lädt ein Modell von Hugging Face und meldet den Fortschritt über on_progress.

    Backend-unabhängig: ein Poller misst die wachsende blobs/-Größe gegen die
    Gesamtgröße (funktioniert auch mit dem Xet-Downloader, der tqdm-Hooks umgeht).
    """
    total = _total_size(repo)
    stop = threading.Event()

    def poll() -> None:
        while not stop.is_set():
            done = _blobs_size(repo)
            on_progress(name, min(done, total) if total else done, total)
            stop.wait(0.5)

    poller = threading.Thread(target=poll, daemon=True)
    poller.start()
    try:
        snapshot_download(repo)
    finally:
        stop.set()
        poller.join(timeout=1)
    final = total or _blobs_size(repo)
    on_progress(name, final, final)  # sicher 100 %


def download_models(models: list[tuple[str, str]], on_progress: ProgressCb) -> None:
    """Lädt mehrere Modelle nacheinander herunter."""
    for name, repo in models:
        download_model(name, repo, on_progress)


_session_caches_installed = False


def install_session_caches() -> None:
    """Hält das Whisper-Modell über mehrere transcribe-Aufrufe im Speicher.

    mlx_whisper lädt das Modell sonst bei JEDEM Aufruf neu. Wir wrappen den Loader
    einmalig mit lru_cache (lazy: lädt beim ersten Diktat, danach gecacht).
    Das LLM hält InProcessLLM bereits selbst im Speicher.
    """
    global _session_caches_installed
    if _session_caches_installed:
        return
    mod = importlib.import_module("mlx_whisper.transcribe")
    mod.load_model = functools.lru_cache(maxsize=2)(mod.load_model)
    _session_caches_installed = True
