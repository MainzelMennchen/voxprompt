"""Build-Metadaten für das py2app-Bundle (Phase 2).

Hier liegen die Info.plist-Werte und der Icon-Pfad zentral, damit setup.py
(Schritt 4) sie nur noch einbindet. Einzige Quelle für Bundle-ID, Version,
Mikrofon-Hinweis, LSUIElement und das .icns.
"""

from __future__ import annotations

from voxprompt import __version__

APP_NAME = "voxprompt"
BUNDLE_ID = "de.erik.voxprompt"
VERSION = __version__

# Klartext-Begründung für den Mikrofonzugriff (erscheint im macOS-Dialog).
MIC_USAGE = (
    "voxprompt nimmt über das Mikrofon dein Diktat auf und wandelt es lokal in "
    "Text um. Es werden keine Audiodaten ins Internet gesendet."
)

# Relativer Pfad zum App-Icon (von make_icons.sh erzeugt).
ICNS_PATH = "assets/voxprompt.icns"

# Info.plist-Werte für das Bundle (py2app: options={"py2app": {"plist": INFO_PLIST}}).
INFO_PLIST = {
    "CFBundleName": APP_NAME,
    "CFBundleDisplayName": APP_NAME,
    "CFBundleIdentifier": BUNDLE_ID,
    "CFBundleShortVersionString": VERSION,
    "CFBundleVersion": VERSION,
    "NSMicrophoneUsageDescription": MIC_USAGE,
    # Reine Menüleisten-App: kein Dock-Icon, kein App-Name in der Menüleiste.
    "LSUIElement": True,
    # SMAppService (Login-Item, Schritt 5) braucht Ventura+.
    "LSMinimumSystemVersion": "13.0",
}
