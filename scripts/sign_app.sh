#!/usr/bin/env bash
#
# sign_app.sh — signiert dist/voxprompt.app mit Developer ID + Hardened Runtime.
#
# Voraussetzung:
#   - Apple Developer Program (99 USD/Jahr)
#   - "Developer ID Application"-Zertifikat im Schlüsselbund
#   - Identität als Umgebungsvariable setzen, z. B.:
#       export VOXPROMPT_SIGN_IDENTITY="Developer ID Application: Dein Name (ABCDE12345)"
#     (verfügbare Identitäten:  security find-identity -v -p codesigning)
#
# Ablauf: erst ALLE verschachtelten Mach-O-Dateien (Dylibs, .so, gebündeltes
# Python) einzeln mit Hardened Runtime signieren, DANN das App-Bundle mit den
# Entitlements (nur die Haupt-Binary braucht die Entitlements). --deep ist
# bewusst NICHT benutzt (unzuverlässig bei vielen nativen Libs).
#
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APP="${1:-$HERE/../dist/voxprompt.app}"
ENTITLEMENTS="$HERE/../packaging/entitlements.plist"
IDENTITY="${VOXPROMPT_SIGN_IDENTITY:-}"

if [[ -z "$IDENTITY" ]]; then
  echo "FEHLER: VOXPROMPT_SIGN_IDENTITY ist nicht gesetzt." >&2
  echo '  export VOXPROMPT_SIGN_IDENTITY="Developer ID Application: Dein Name (TEAMID)"' >&2
  echo "Im Schlüsselbund vorhandene Signier-Identitäten:" >&2
  security find-identity -v -p codesigning >&2 || true
  exit 1
fi
[[ -d "$APP" ]] || { echo "FEHLER: $APP nicht gefunden — erst ./scripts/build_app.sh laufen lassen." >&2; exit 1; }
[[ -f "$ENTITLEMENTS" ]] || { echo "FEHLER: $ENTITLEMENTS fehlt." >&2; exit 1; }

echo "==> Signiere verschachtelte Binaries in $(basename "$APP") (innen → außen) …"
# Jede reguläre Datei prüfen; Mach-O-Dateien einzeln signieren (Runtime + Zeitstempel,
# OHNE Entitlements — die gehören nur an die Haupt-Binary).
count=0
while IFS= read -r -d '' f; do
  if file -b "$f" | grep -q "Mach-O"; then
    codesign --force --options runtime --timestamp --sign "$IDENTITY" "$f"
    count=$((count + 1))
  fi
done < <(find "$APP" -type f -print0)
echo "    $count native Binärdateien signiert."

echo "==> Signiere das App-Bundle mit Entitlements …"
codesign --force --options runtime --timestamp \
  --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" "$APP"

echo "==> Prüfe Signatur …"
codesign --verify --deep --strict --verbose=2 "$APP"
echo "OK: $APP ist signiert (Developer ID + Hardened Runtime)."
echo "    Nächster Schritt: ./scripts/make_dmg.sh  und dann  ./scripts/notarize.sh"
