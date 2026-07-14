#!/usr/bin/env bash
#
# notarize.sh — notarisiert ein signiertes Artefakt bei Apple und stapelt das
#               Ticket an (staple), sodass es OFFLINE ohne Warnung startet.
#
# Funktioniert mit .app oder .dmg (Default: dist/voxprompt.dmg).
#
# Einmalige Vorbereitung (legt die Zugangsdaten sicher im Schlüsselbund ab,
# KEIN Passwort im Skript/Repo):
#   xcrun notarytool store-credentials voxprompt-notary \
#     --apple-id "du@example.com" \
#     --team-id  "ABCDE12345" \
#     --password "app-spezifisches-passwort"   # appleid.apple.com -> App-spez. Passwörter
#
# Empfohlene Reihenfolge für ein Release:
#   1) ./scripts/build_app.sh
#   2) ./scripts/sign_app.sh
#   3) ./scripts/notarize.sh dist/voxprompt.app   # notarisiert + stapelt die App
#   4) ./scripts/make_dmg.sh                       # DMG mit der gestapelten App
#   5) ./scripts/notarize.sh dist/voxprompt.dmg   # notarisiert + stapelt das DMG
#
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ARTIFACT="${1:-$HERE/../dist/voxprompt.dmg}"
PROFILE="${VOXPROMPT_NOTARY_PROFILE:-voxprompt-notary}"
IDENTITY="${VOXPROMPT_SIGN_IDENTITY:-}"

[[ -e "$ARTIFACT" ]] || { echo "FEHLER: $ARTIFACT nicht gefunden." >&2; exit 1; }

submit() {
  echo "==> Lade $(basename "$1") zu Apple hoch (Scan dauert meist 1–15 Min) …"
  xcrun notarytool submit "$1" --keychain-profile "$PROFILE" --wait
}

case "$ARTIFACT" in
  *.app)
    ZIP="${ARTIFACT%.app}-notarize.zip"
    echo "==> Packe App für den Upload (ditto) …"
    /usr/bin/ditto -c -k --keepParent "$ARTIFACT" "$ZIP"
    submit "$ZIP"
    rm -f "$ZIP"
    echo "==> Stapel das Ticket an die App …"
    xcrun stapler staple "$ARTIFACT"
    echo "==> Gatekeeper-Bewertung:"
    spctl -a -t exec -vvv "$ARTIFACT" || true
    ;;

  *.dmg)
    # DMG vor der Notarisierung signieren (empfohlen), falls Identität gesetzt ist.
    if [[ -n "$IDENTITY" ]]; then
      echo "==> Signiere das DMG …"
      codesign --force --timestamp --sign "$IDENTITY" "$ARTIFACT"
    else
      echo "Hinweis: VOXPROMPT_SIGN_IDENTITY nicht gesetzt — DMG wird nicht signiert."
    fi
    submit "$ARTIFACT"
    echo "==> Stapel das Ticket an das DMG …"
    xcrun stapler staple "$ARTIFACT"
    echo "==> Gatekeeper-Bewertung:"
    spctl -a -t open --context context:primary-signature -vvv "$ARTIFACT" || true
    ;;

  *)
    echo "FEHLER: nur .app oder .dmg werden unterstützt." >&2
    exit 1
    ;;
esac

echo "Fertig: $(basename "$ARTIFACT") ist notarisiert und gestapelt."
