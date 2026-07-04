"""Tests für die Modell-Verwaltung (Phase 2, Schritt 2)."""

from __future__ import annotations

import importlib

import voxprompt.models as models


def test_required_models_ist_backend_abhaengig() -> None:
    base = {"transcription": {"whisper_model": "w"}, "llm": {"llm_model": "l"}}
    ep = {**base, "llm": {"llm_backend": "endpoint", "llm_model": "l"}}
    ip = {**base, "llm": {"llm_backend": "inprocess", "llm_model": "l"}}
    # endpoint: nur Whisper (LLM lädt der Server)
    assert models.required_models(ep) == {"Spracherkennung": "w"}
    # inprocess: Whisper + Sprachmodell
    assert models.required_models(ip) == {"Spracherkennung": "w", "Sprachmodell": "l"}


def test_is_cached_und_missing(monkeypatch) -> None:
    def fake_snapshot(repo, local_files_only=False, **kw):
        if repo == "present":
            return "/cache/present"
        raise FileNotFoundError(repo)

    monkeypatch.setattr(models, "snapshot_download", fake_snapshot)
    assert models.is_cached("present") is True
    assert models.is_cached("absent") is False

    cfg = {
        "transcription": {"whisper_model": "present"},
        "llm": {"llm_backend": "inprocess", "llm_model": "absent"},
    }
    assert models.missing_models(cfg) == [("Sprachmodell", "absent")]


def test_repo_cache_dir() -> None:
    d = models._repo_cache_dir("mlx-community/Qwen3.5-9B-MLX-4bit")
    assert d.endswith("models--mlx-community--Qwen3.5-9B-MLX-4bit")


def test_blobs_size_summiert_dateien(tmp_path, monkeypatch) -> None:
    # blobs/-Verzeichnis mit zwei „heruntergeladenen" Dateien simulieren
    repo = "org/model"
    blobs = tmp_path / "models--org--model" / "blobs"
    blobs.mkdir(parents=True)
    (blobs / "a").write_bytes(b"x" * 100)
    (blobs / "b.incomplete").write_bytes(b"y" * 50)
    monkeypatch.setattr(models, "HF_HUB_CACHE", str(tmp_path))
    assert models._blobs_size(repo) == 150


def test_install_session_caches_cached_und_idempotent() -> None:
    models.install_session_caches()
    mod = importlib.import_module("mlx_whisper.transcribe")
    assert hasattr(mod.load_model, "cache_info")  # ist jetzt lru_cache
    loader = mod.load_model
    models.install_session_caches()  # zweiter Aufruf darf nicht erneut wrappen
    assert mod.load_model is loader
