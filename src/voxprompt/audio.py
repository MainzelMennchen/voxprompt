"""Audioaufnahme (Schritt 2) + Sprachaktivitätserkennung (Schritt 7).

Nimmt über sounddevice in einen Puffer auf, solange Push-to-Talk aktiv ist,
und schreibt die Aufnahme beim Stoppen als temporäre WAV-Datei (soundfile).
16 kHz mono genügt für Whisper. `contains_speech()` filtert leere/stille
Aufnahmen, damit Whisper bei Stille keinen Geistertext halluziniert.
"""

from __future__ import annotations

import tempfile
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf

try:
    import webrtcvad
except Exception:  # pragma: no cover - optionale Abhängigkeit
    webrtcvad = None

SAMPLE_RATE = 16_000
VAD_FRAME_MS = 30
DEFAULT_MIN_SPEECH_MS = 200
ENERGY_RMS_THRESHOLD = 0.01  # Fallback-VAD, RMS auf [-1,1]-Audio


def contains_speech(
    wav_path: str,
    aggressiveness: int = 2,
    min_speech_ms: int = DEFAULT_MIN_SPEECH_MS,
) -> bool:
    """True, wenn die Aufnahme genug Sprache enthält (>= min_speech_ms).

    Nutzt webrtcvad (stimmhafte 30-ms-Frames); fällt ohne webrtcvad oder bei
    unpassender Samplerate auf eine RMS-Energie-Schwelle zurück. Bei jedem
    internen Fehler: fail-open (True) — lieber transkribieren als Audio verwerfen.
    """
    try:
        audio, sample_rate = sf.read(wav_path, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        frame_len = int(sample_rate * VAD_FRAME_MS / 1000)
        if frame_len == 0 or len(audio) < frame_len:
            return False  # zu kurz für überhaupt eine Frame -> leer

        if webrtcvad is not None and sample_rate in (8000, 16000, 32000, 48000):
            voiced_ms = _webrtc_voiced_ms(audio, sample_rate, frame_len, aggressiveness)
        else:
            voiced_ms = _energy_voiced_ms(audio, frame_len)
        return voiced_ms >= min_speech_ms
    except Exception as exc:
        print(f"[audio] VAD übersprungen ({exc}) — transkribiere trotzdem", flush=True)
        return True


def _webrtc_voiced_ms(audio: np.ndarray, sample_rate: int, frame_len: int, aggressiveness: int) -> int:
    vad = webrtcvad.Vad(aggressiveness)
    pcm16 = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16).tobytes()
    bytes_per_frame = frame_len * 2
    voiced = 0
    for i in range(0, len(pcm16) - bytes_per_frame + 1, bytes_per_frame):
        if vad.is_speech(pcm16[i : i + bytes_per_frame], sample_rate):
            voiced += 1
    return voiced * VAD_FRAME_MS


def _energy_voiced_ms(audio: np.ndarray, frame_len: int) -> int:
    voiced = 0
    for i in range(0, len(audio) - frame_len + 1, frame_len):
        seg = audio[i : i + frame_len]
        if float(np.sqrt(np.mean(seg**2))) > ENERGY_RMS_THRESHOLD:
            voiced += 1
    return voiced * VAD_FRAME_MS
CHANNELS = 1


class Recorder:
    """Sammelt Audio-Frames zwischen Start und Stop der Aufnahme.

    Thread-sicher: start()/stop() werden aus dem Hotkey-Listener-Thread
    aufgerufen, der sounddevice-Callback läuft im PortAudio-Thread.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._recording = False
        self._last_duration = 0.0
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            print(f"[audio] stream status: {status}", flush=True)
        with self._lock:
            if self._recording:
                self._frames.append(indata.copy())

    def start(self) -> None:
        """Beginnt das Streaming vom Mikrofon in den Puffer."""
        with self._lock:
            if self._recording:
                return
            self._frames = []
            self._recording = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> str | None:
        """Stoppt die Aufnahme, schreibt eine temporäre WAV-Datei, gibt deren Pfad zurück.

        Gibt None zurück, wenn nicht aufgenommen wurde oder kein Audio anfiel.
        """
        with self._lock:
            if not self._recording:
                return None
            self._recording = False

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            frames = self._frames
            self._frames = []

        if not frames:
            self._last_duration = 0.0
            return None

        audio = np.concatenate(frames, axis=0)
        self._last_duration = len(audio) / self.sample_rate

        tmp = tempfile.NamedTemporaryFile(prefix="voxprompt_", suffix=".wav", delete=False)
        tmp.close()
        sf.write(tmp.name, audio, self.sample_rate, subtype="PCM_16")
        return tmp.name

    @property
    def is_recording(self) -> bool:
        """Ob gerade aufgenommen wird."""
        with self._lock:
            return self._recording

    @property
    def last_duration(self) -> float:
        """Dauer der zuletzt gestoppten Aufnahme in Sekunden."""
        return self._last_duration
