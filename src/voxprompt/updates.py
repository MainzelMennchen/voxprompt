"""Update-Check gegen die GitHub-Releases-API.

Option 1 der Update-Strategie (siehe CLAUDE.md): ein reiner HINWEIS, kein
Self-Update. Die App fragt das neueste Release ab, vergleicht dessen Tag mit
`__version__` und meldet, ob eine neuere Version verfügbar ist. Der Nutzer lädt
das DMG dann selbst von der Release-Seite und ersetzt die App in /Applications —
die App ersetzt sich NICHT selbst (kein Sparkle nötig, keine Signatur-Fallen).

Alle Funktionen sind fehler-tolerant: kein Netz, 404, kaputtes JSON → None,
niemals eine Exception (der Update-Check darf das Diktieren nie stören).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from voxprompt import __version__

# GitHub-REST-API: neuestes veröffentlichtes Release (ohne Drafts/Prereleases).
GITHUB_LATEST = "https://api.github.com/repos/{repo}/releases/latest"


@dataclass(frozen=True)
class UpdateInfo:
    """Ein verfügbares Update, das neuer ist als die laufende Version."""

    version: str  # normalisierte Version des Release ("1.2.0")
    tag: str      # Original-Tag aus GitHub ("v1.2.0")
    url: str      # HTML-URL der Release-Seite (im Browser zu öffnen)


def _parse_version(text: str) -> tuple[int, ...] | None:
    """'v1.2.3' / '1.2' -> (1, 2, 3) / (1, 2). None, wenn keine Zahl gefunden."""
    match = re.search(r"(\d+(?:\.\d+)*)", text or "")
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(latest: str, current: str) -> bool:
    """True, wenn `latest` eine höhere Version als `current` ist (semver-artig).

    Vergleicht die Zahl-Tupel komponentenweise, auf gleiche Länge aufgefüllt
    ('1.2' == '1.2.0'). Nicht parsebare Eingaben -> False (kein Update melden).
    """
    lv, cv = _parse_version(latest), _parse_version(current)
    if lv is None or cv is None:
        return False
    length = max(len(lv), len(cv))
    lv += (0,) * (length - len(lv))
    cv += (0,) * (length - len(cv))
    return lv > cv


def check_for_update(
    repo: str,
    current: str = __version__,
    *,
    timeout: float = 8.0,
    transport: httpx.BaseTransport | None = None,
) -> UpdateInfo | None:
    """Fragt GitHub nach dem neuesten Release von `repo` ("owner/name").

    Gibt UpdateInfo zurück, wenn das Release neuer ist als `current`, sonst None.
    Leeres `repo`, Netz-/HTTP-/Parsefehler und Drafts/Prereleases -> None.
    `transport` nur für Tests (httpx.MockTransport).
    """
    if not repo:
        return None
    try:
        with httpx.Client(
            timeout=timeout,
            transport=transport,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "voxprompt-updater",
            },
        ) as client:
            resp = client.get(GITHUB_LATEST.format(repo=repo))
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("draft") or data.get("prerelease"):
            return None
        tag = data.get("tag_name") or ""
        if not tag or not is_newer(tag, current):
            return None
        parsed = _parse_version(tag)
        version = ".".join(str(p) for p in parsed) if parsed else tag
        url = data.get("html_url") or f"https://github.com/{repo}/releases/latest"
        return UpdateInfo(version=version, tag=tag, url=url)
    except Exception:
        return None
