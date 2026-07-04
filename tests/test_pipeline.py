"""Pipeline-Tests. Wird schrittweise gefüllt (LLM-Roundtrip in Schritt 4,
Modus-Verdrahtung in Schritt 5/6).
"""

from __future__ import annotations


def test_package_importierbar() -> None:
    import voxprompt

    assert voxprompt.__version__
