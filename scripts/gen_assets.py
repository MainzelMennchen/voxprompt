"""Erzeugt Icon-Assets für voxprompt (Phase 2, Schritt 3).

- `placeholder`: ein 1024x1024 App-Icon (weißes Mikrofon auf farbigem Rounded-Square),
  nur als Platzhalter, falls noch kein eigenes assets/icon.png existiert.
- `template`: das monochrome Menüleisten-Template-Icon (schwarzes Mikrofon + Alpha,
  transparenter Hintergrund) als assets/menubar_template.png (+ @2x).

Nutzt Pillow (Dev-Abhängigkeit). Aufruf: `python scripts/gen_assets.py <placeholder|template>`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def _draw_microphone(img: Image.Image, color: tuple[int, int, int, int]) -> None:
    """Zeichnet ein zentriertes Mikrofon-Glyph in der Bildmitte (skaliert mit der Größe)."""
    w, h = img.size
    s = min(w, h)
    cx = w / 2
    d = ImageDraw.Draw(img)
    lw = max(2, round(s * 0.045))

    # Mikrofonkörper (Kapsel)
    body_w = s * 0.26
    body_h = s * 0.42
    top = h * 0.16
    d.rounded_rectangle(
        [cx - body_w / 2, top, cx + body_w / 2, top + body_h],
        radius=body_w / 2,
        fill=color,
    )

    # Bügel (U-Bogen) um den unteren Teil des Körpers
    arc_w = s * 0.46
    arc_top = top + body_h * 0.18
    arc_bot = top + body_h * 1.06
    d.arc(
        [cx - arc_w / 2, arc_top, cx + arc_w / 2, arc_bot],
        start=20,
        end=160,
        fill=color,
        width=lw,
    )

    # Ständer (Linie nach unten) + Fuß
    stem_top = arc_bot - lw / 2
    stem_bot = stem_top + s * 0.13
    d.line([cx, stem_top, cx, stem_bot], fill=color, width=lw)
    foot_w = s * 0.24
    d.line([cx - foot_w / 2, stem_bot, cx + foot_w / 2, stem_bot], fill=color, width=lw)


def make_placeholder() -> None:
    size = 1024
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Vertikaler Verlauf (Indigo -> Violett) auf abgerundetem Quadrat.
    top_c = (99, 102, 241)   # indigo-500
    bot_c = (139, 92, 246)   # violet-500
    grad = Image.new("RGBA", (1, size))
    for y in range(size):
        t = y / (size - 1)
        grad.putpixel(
            (0, y),
            (
                round(top_c[0] + (bot_c[0] - top_c[0]) * t),
                round(top_c[1] + (bot_c[1] - top_c[1]) * t),
                round(top_c[2] + (bot_c[2] - top_c[2]) * t),
                255,
            ),
        )
    grad = grad.resize((size, size))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=round(size * 0.225), fill=255
    )
    img.paste(grad, (0, 0), mask)
    _draw_microphone(img, (255, 255, 255, 255))
    out = ASSETS / "icon.png"
    img.save(out)
    print(f"Platzhalter-App-Icon: {out}")


def make_template() -> None:
    # Schwarzes Glyph + Alpha; macOS färbt Template-Bilder selbst um.
    for name, size in (("menubar_template.png", 22), ("menubar_template@2x.png", 44)):
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        _draw_microphone(img, (0, 0, 0, 255))
        out = ASSETS / name
        img.save(out)
        print(f"Menüleisten-Template ({size}px): {out}")


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    if what == "placeholder":
        make_placeholder()
    elif what == "template":
        make_template()
    else:
        sys.exit("Aufruf: gen_assets.py <placeholder|template>")


if __name__ == "__main__":
    main()
