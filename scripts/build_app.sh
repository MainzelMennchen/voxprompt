#!/usr/bin/env bash
# Baut die eigenständige dist/voxprompt.app mit py2app (Phase 2, Schritt 4).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Icons sicherstellen (App-Icon + Menüleisten-Template).
if [[ ! -f assets/voxprompt.icns ]]; then
  echo "==> Icons fehlen, erzeuge sie ..."
  "$ROOT/scripts/make_icons.sh"
fi

echo "==> Sauberer Build (build/ und dist/ entfernen) ..."
rm -rf build dist

echo "==> py2app-Build (das dauert einige Minuten, kopiert native MLX-Libs) ..."
uv run python setup.py py2app

# mlx ist ein Namespace-Paket (kein __init__.py) und wird von modulegraph nicht
# erfasst -> hier verbatim ins Bundle kopieren (inkl. lib/*.dylib + mlx.metallib).
echo "==> Kopiere mlx (Namespace-Paket, native Libs + Metal-Shader) ins Bundle ..."
SITEPKG="$(uv run python -c 'import os,mlx_lm; print(os.path.dirname(os.path.dirname(mlx_lm.__file__)))')"
LIBDIR="$(echo "$ROOT"/dist/voxprompt.app/Contents/Resources/lib/python3.*)"
if [[ ! -d "$SITEPKG/mlx" ]]; then echo "FEHLER: mlx nicht in $SITEPKG"; exit 1; fi
if [[ ! -d "$LIBDIR" ]]; then echo "FEHLER: Bundle-lib-Verzeichnis nicht gefunden: $LIBDIR"; exit 1; fi
cp -R "$SITEPKG/mlx" "$LIBDIR/mlx"
# Metal-Shader-Datei muss vorhanden sein, sonst läuft keine GPU-Inferenz.
if [[ ! -f "$LIBDIR/mlx/lib/mlx.metallib" ]]; then
  echo "FEHLER: mlx.metallib fehlt im Bundle!"; exit 1
fi
echo "    mlx kopiert nach $LIBDIR/mlx (metallib vorhanden)."

echo
echo "==> Fertig: $ROOT/dist/voxprompt.app"
du -sh dist/voxprompt.app 2>/dev/null || true
