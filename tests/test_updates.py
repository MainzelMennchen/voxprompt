"""Tests für den Update-Check (Option 1: Hinweis, kein Self-Update).

Deterministisch über httpx.MockTransport — kein Netz, kein GitHub nötig.
"""

from __future__ import annotations

import httpx
import pytest

from voxprompt import updates
from voxprompt.updates import UpdateInfo, check_for_update, is_newer


@pytest.mark.parametrize(
    "latest, current, expected",
    [
        ("v1.2.0", "1.1.0", True),
        ("1.1.0", "1.1.0", False),
        ("v1.0.0", "1.1.0", False),
        ("1.2", "1.2.0", False),      # gleich, nur andere Länge
        ("1.2.1", "1.2", True),       # 1.2.1 > 1.2(.0)
        ("2.0", "1.9.9", True),
        ("kaputt", "1.0.0", False),   # nicht parsebar -> kein Update
        ("1.0.0", "kaputt", False),
    ],
)
def test_is_newer(latest, current, expected) -> None:
    assert is_newer(latest, current) is expected


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def _release(tag: str, *, draft: bool = False, prerelease: bool = False) -> dict:
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "html_url": f"https://github.com/o/r/releases/tag/{tag}",
    }


def test_neuere_version_liefert_updateinfo() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/o/r/releases/latest"
        return httpx.Response(200, json=_release("v1.5.0"))

    info = check_for_update("o/r", current="1.0.0", transport=_transport(handler))
    assert isinstance(info, UpdateInfo)
    assert info.version == "1.5.0"
    assert info.tag == "v1.5.0"
    assert info.url.endswith("/v1.5.0")


def test_gleiche_version_kein_update() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_release("v1.0.0"))

    assert check_for_update("o/r", current="1.0.0", transport=_transport(handler)) is None


def test_prerelease_und_draft_werden_ignoriert() -> None:
    def draft(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_release("v2.0.0", draft=True))

    def pre(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_release("v2.0.0", prerelease=True))

    assert check_for_update("o/r", current="1.0.0", transport=_transport(draft)) is None
    assert check_for_update("o/r", current="1.0.0", transport=_transport(pre)) is None


def test_http_404_liefert_none() -> None:
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    assert check_for_update("o/r", current="1.0.0", transport=_transport(handler)) is None


def test_netzwerkfehler_liefert_none_statt_werfen() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    assert check_for_update("o/r", current="1.0.0", transport=_transport(handler)) is None


def test_leeres_repo_liefert_none() -> None:
    assert check_for_update("", current="1.0.0") is None


def test_kaputtes_json_liefert_none() -> None:
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="kein-json")

    assert check_for_update("o/r", current="1.0.0", transport=_transport(handler)) is None


def test_default_current_ist_paketversion() -> None:
    """Ohne current-Arg wird __version__ verwendet (gleiche Version -> None)."""
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_release(f"v{updates.__version__}"))

    assert check_for_update("o/r", transport=_transport(handler)) is None
