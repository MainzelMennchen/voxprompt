#!/usr/bin/env bash
# Baut ein verteilbares (vorerst unsigniertes) DMG aus dist/voxprompt.app
# (Phase 2, Schritt 6) — mit Volume-Icon, Applications-Symlink und
# Drag-to-Applications-Fensterlayout.
#
# Voraussetzung: create-dmg (brew install create-dmg) und ein fertiger Build
# (./scripts/build_app.sh).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP="dist/voxprompt.app"
DMG="dist/voxprompt.dmg"
ICNS="assets/voxprompt.icns"

if [[ ! -d "$APP" ]]; then
  echo "FEHLER: $APP fehlt — zuerst ./scripts/build_app.sh ausführen."; exit 1
fi
if ! command -v create-dmg >/dev/null 2>&1; then
  echo "FEHLER: create-dmg nicht gefunden — 'brew install create-dmg'."; exit 1
fi

# create-dmg packt den INHALT des Quellordners ins DMG -> Staging-Ordner mit nur
# der App, damit nichts anderes mit reinrutscht.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"

rm -f "$DMG"

# create-dmg liefert gelegentlich einen Nicht-Null-Exitcode trotz erfolgreichem
# DMG (AppleScript-Layout-Schritt) -> Erfolg an der erzeugten Datei festmachen.
if ! create-dmg \
  --volname "voxprompt" \
  --volicon "$ICNS" \
  --window-pos 200 120 \
  --window-size 640 400 \
  --icon-size 120 \
  --icon "voxprompt.app" 160 200 \
  --hide-extension "voxprompt.app" \
  --app-drop-link 480 200 \
  --no-internet-enable \
  "$DMG" \
  "$STAGE"; then
  echo "Hinweis: create-dmg meldete einen Fehlercode — prüfe Ergebnis ..."
fi

if [[ ! -f "$DMG" ]]; then
  echo "FEHLER: DMG wurde nicht erzeugt."; exit 1
fi

echo
echo "==> Fertig: $ROOT/$DMG"
du -sh "$DMG"
