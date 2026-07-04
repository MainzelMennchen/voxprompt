"""Lebenszyklus des lokalen LLM-Servers (mlx_lm.server).

Startet den Server beim App-Start (falls nicht schon erreichbar) und stoppt ihn
beim Beenden — wodurch auch das geladene Modell aus dem RAM entladen wird.

Wichtig: Nur ein Server, den WIR gestartet haben, wird beim Beenden gestoppt
(`_owned`). Einen bereits laufenden Server (vom User manuell gestartet) lassen
wir unangetastet.
"""

from __future__ import annotations

import subprocess
import time
from urllib.parse import urlparse

import httpx


def build_command(template: list[str], endpoint: str) -> list[str]:
    """Ersetzt {host}/{port} im Befehls-Template anhand des Endpoints."""
    parsed = urlparse(endpoint)
    host = parsed.hostname or "127.0.0.1"
    port = str(parsed.port or 8080)
    return [arg.replace("{host}", host).replace("{port}", port) for arg in template]


class LLMServerManager:
    """Startet/stoppt den lokalen LLM-Server passend zum konfigurierten Endpoint."""

    def __init__(
        self,
        endpoint: str,
        command: list[str],
        startup_timeout: float = 30.0,
        log_path: str = "/tmp/voxprompt-mlx.log",
    ) -> None:
        self.models_url = endpoint.rstrip("/") + "/models"
        self.command = command
        self.startup_timeout = startup_timeout
        self.log_path = log_path
        self._process: subprocess.Popen | None = None
        self._owned = False

    @property
    def owned(self) -> bool:
        """True, wenn dieser Manager den Server gestartet hat (und ihn stoppen darf)."""
        return self._owned

    def is_up(self) -> bool:
        """True, wenn der Endpoint antwortet (Server läuft bereits)."""
        try:
            httpx.get(self.models_url, timeout=2.0)
            return True
        except httpx.HTTPError:
            return False

    def ensure_running(self) -> str:
        """Sorgt dafür, dass der Server läuft. Gibt 'reused' oder 'started' zurück.

        Läuft schon einer -> übernehmen (nicht ownen). Sonst starten und warten,
        bis der Endpoint antwortet. Wirft RuntimeError/TimeoutError bei Fehlschlag.
        """
        if self.is_up():
            self._owned = False
            return "reused"

        log = open(self.log_path, "ab", buffering=0)  # noqa: SIM115 (Lebensdauer = Prozess)
        self._process = subprocess.Popen(self.command, stdout=log, stderr=log)
        self._owned = True

        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise RuntimeError(
                    f"LLM-Server endete sofort (Code {self._process.returncode}), "
                    f"siehe {self.log_path}"
                )
            if self.is_up():
                return "started"
            time.sleep(0.5)
        raise TimeoutError(
            f"LLM-Server nicht erreichbar nach {self.startup_timeout:.0f}s "
            f"({self.models_url})"
        )

    def shutdown(self) -> None:
        """Stoppt den Server — aber nur, wenn wir ihn gestartet haben (entlädt das Modell)."""
        if not self._owned or self._process is None:
            return
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)
        self._process = None
        self._owned = False
