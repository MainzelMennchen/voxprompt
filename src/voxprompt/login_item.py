"""Login-Item-Verwaltung über SMAppService (ServiceManagement, macOS 13+).

Registriert die laufende .app als Login-Item (Start beim Anmelden) — der moderne
Ersatz für den von Hand installierten LaunchAgent aus Phase 1.

Funktioniert nur aus einem echten .app-Bundle heraus: SMAppService.mainAppService()
bezieht sich auf das Haupt-App-Bundle. Im Dev-Betrieb (`uv run`, kein Bundle) ist der
Status 'not found' und Registrieren schlägt fehl — das ist erwartet.
"""

from __future__ import annotations

# SMAppServiceStatus-Werte
STATUS_NOT_REGISTERED = 0
STATUS_ENABLED = 1
STATUS_REQUIRES_APPROVAL = 2
STATUS_NOT_FOUND = 3


def available() -> bool:
    """Ob das ServiceManagement-Framework importierbar ist (macOS 13+)."""
    try:
        import ServiceManagement  # noqa: F401

        return True
    except Exception:
        return False


def _service():
    from ServiceManagement import SMAppService

    return SMAppService.mainAppService()


def status() -> int:
    """Aktueller SMAppServiceStatus (oder NOT_FOUND, wenn nicht ermittelbar)."""
    try:
        return int(_service().status())
    except Exception:
        return STATUS_NOT_FOUND


def is_enabled() -> bool:
    """True, wenn die App als Login-Item registriert/aktiv ist."""
    return status() == STATUS_ENABLED


def usable() -> bool:
    """True, wenn Login-Item-Schalten sinnvoll möglich ist (echtes .app-Bundle).

    Bewusst NICHT am Status festgemacht (der ist anfangs auch im Bundle 'not found'),
    sondern am Haupt-Bundle: im Dev-Betrieb hat es keine Bundle-ID und keinen
    .app-Pfad — dort würde register sonst ein kaputtes Login-Item (auf das venv-
    Python) anlegen.
    """
    if not available():
        return False
    try:
        from Foundation import NSBundle

        bundle = NSBundle.mainBundle()
        return bool(bundle.bundleIdentifier()) and str(bundle.bundlePath()).endswith(".app")
    except Exception:
        return False


def set_enabled(enabled: bool) -> None:
    """Registriert (enabled=True) bzw. deregistriert die App als Login-Item.

    Idempotent; wirft RuntimeError bei Fehlschlag (z. B. außerhalb eines Bundles).
    """
    if not usable():
        raise RuntimeError(
            "Login-Item lässt sich nur aus der installierten voxprompt.app schalten."
        )
    svc = _service()
    current = int(svc.status())
    if enabled and current == STATUS_ENABLED:
        return
    if not enabled and current in (STATUS_NOT_REGISTERED, STATUS_NOT_FOUND):
        return

    result = (
        svc.registerAndReturnError_(None)
        if enabled
        else svc.unregisterAndReturnError_(None)
    )
    # pyobjc gibt für (BOOL)…AndReturnError: ein (ok, error)-Tupel zurück.
    if isinstance(result, tuple):
        ok, err = result
    else:
        ok, err = result, None
    if not ok:
        raise RuntimeError(str(err) if err else "SMAppService-Aufruf fehlgeschlagen")
