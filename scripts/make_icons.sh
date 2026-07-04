#!/usr/bin/env bash
# Baut die Icon-Assets für voxprompt (Phase 2, Schritt 3):
#   - assets/voxprompt.icns aus assets/icon.png (über ein .iconset + iconutil)
#   - assets/menubar_template.png (+@2x) als monochromes Menüleisten-Template
#
# Bei fehlendem assets/icon.png wird ein Platzhalter erzeugt. Eigenes Icon
# einfach als assets/icon.png (1024x1024) ablegen und dieses Skript neu laufen lassen.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ASSETS="$ROOT/assets"
ICON="$ASSETS/icon.png"
ICONSET="$ASSETS/voxprompt.iconset"
ICNS="$ASSETS/voxprompt.icns"

mkdir -p "$ASSETS"

# 1) App-Icon sicherstellen (sonst Platzhalter erzeugen)
if [[ ! -f "$ICON" ]]; then
  echo "Kein assets/icon.png gefunden — erzeuge Platzhalter."
  uv run python "$ROOT/scripts/gen_assets.py" placeholder
fi

# 2) .iconset mit allen benötigten Größen aus icon.png
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
sizes=(16 32 32 64 128 256 256 512 512 1024)
names=(
  icon_16x16.png icon_16x16@2x.png icon_32x32.png icon_32x32@2x.png
  icon_128x128.png icon_128x128@2x.png icon_256x256.png icon_256x256@2x.png
  icon_512x512.png icon_512x512@2x.png
)
for i in "${!sizes[@]}"; do
  sips -z "${sizes[$i]}" "${sizes[$i]}" "$ICON" --out "$ICONSET/${names[$i]}" >/dev/null
done

# 3) .icns bauen
iconutil -c icns "$ICONSET" -o "$ICNS"
rm -rf "$ICONSET"
echo "Erstellt: $ICNS"

# 4) Menüleisten-Template (immer neu, unabhängig vom App-Icon)
uv run python "$ROOT/scripts/gen_assets.py" template

echo "Fertig."
