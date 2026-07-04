"""py2app-Build-Konfiguration für voxprompt (Phase 2, Schritt 4).

Baut eine eigenständige dist/voxprompt.app. Der kritische Punkt sind die nativen
MLX-Bibliotheken (mlx/lib/*.dylib + mlx.metallib) und weitere C-Extensions
(numba/llvmlite/scipy/tokenizers …): diese Pakete werden bewusst komplett über
`packages` kopiert (verbatim, inkl. Datendateien/Dylibs), statt sie dem
Modulgraph zu überlassen — sonst fehlen Metal-Shader oder lazy importierte Module.

mlx verlinkt seine Dylibs über @loader_path/lib, bleibt also portabel, solange die
Verzeichnisstruktur erhalten bleibt (das tut ein packages-Copy).

Build:  uv run python setup.py py2app   (siehe scripts/build_app.sh)
"""

import sys

from setuptools import setup

import build_metadata
from py2app.build_app import py2app as _py2app

# modulegraph scannt den (tiefen) Import-Graphen rekursiv; transformers/scipy
# sprengen sonst das Standard-Limit von 1000.
sys.setrecursionlimit(10_000)

# uv-Python (python-build-standalone) linkt zlib statisch -> zlib hat kein
# __file__. py2app will es trotzdem ins Bundle kopieren (für den Entpack-
# Bootstrap), was bei eingebautem zlib unnötig ist. Platzhalter unterschieben.
import zlib  # noqa: E402

if not hasattr(zlib, "__file__"):
    import tempfile  # noqa: E402

    _ph = tempfile.NamedTemporaryFile(prefix="voxprompt_zlib_", delete=False)
    _ph.close()
    zlib.__file__ = _ph.name


class Py2AppCommand(_py2app):
    """py2app verweigert den Build, wenn install_requires gesetzt ist — was
    setuptools aber aus den [project].dependencies der pyproject.toml befüllt.
    Wir leeren es vor finalize_options (alle Deps werden ohnehin explizit
    über `packages` gebündelt)."""

    def finalize_options(self):  # noqa: D401
        self.distribution.install_requires = None
        super().finalize_options()

APP = ["app_launcher.py"]

# In Resources: In-Process-config (kein Server) + Menüleisten-Template-Icon.
DATA_FILES = [
    ("", ["packaging/config.toml"]),
    ("assets", ["assets/menubar_template.png", "assets/menubar_template@2x.png"]),
]

# Komplett kopieren: native Extensions, Pakete mit Datendateien und solche mit
# lazy/dynamischen Importen (transformers!), die der Modulgraph nicht erfasst.
PACKAGES = [
    "voxprompt",
    # MLX-Stack. ACHTUNG: `mlx` selbst ist ein PEP-420-Namespace-Paket (kein
    # __init__.py) -> modulegraph kann es nicht auflösen. Es wird daher NICHT hier
    # gelistet, sondern in build_app.sh nach dem Build manuell ins Bundle kopiert
    # (verbatim; @loader_path/lib bleibt portabel). mlx_lm/mlx_whisper sind regulär.
    "mlx_lm", "mlx_whisper",
    # von mlx_whisper beim Import geladen (nativ)
    "numba", "llvmlite", "scipy", "numpy",
    # LLM-Tokenizer (transformers nutzt lazy imports -> zwingend verbatim)
    "transformers", "tokenizers", "sentencepiece",
    # Modell-Download/-Laden + TLS
    "huggingface_hub", "certifi", "safetensors", "regex", "tiktoken",
    "filelock", "fsspec", "requests", "tqdm", "yaml", "packaging",
    "charset_normalizer", "urllib3", "idna",
    # App-Laufzeit
    "rumps", "sounddevice", "soundfile", "pynput", "pyperclip", "webrtcvad",
    "httpx", "httpcore", "h11", "anyio", "sniffio", "cffi",
    # Login-Item (SMAppService); lazy importiert -> sicherheitshalber explizit.
    "ServiceManagement",
    # WICHTIG: native Begleit-Dylibs von soundfile/sounddevice stecken in diesen
    # _data-Paketen (libsndfile / libportaudio). Sie MÜSSEN entpackt werden — aus
    # einer .zip lässt sich keine .dylib dlopen-en. soundfile/sounddevice finden die
    # Lib über <_paket>.__file__.
    "_soundfile_data", "_sounddevice_data",
]

# Nur tatsächlich installierte Pakete listen — sonst bricht modulegraph mit
# "No module named X" ab (z. B. optionale Transitiv-Deps, die hier fehlen).
import importlib.util  # noqa: E402

PACKAGES = [p for p in PACKAGES if importlib.util.find_spec(p) is not None]

# Große/unnötige Brocken raus (torch wird zur Laufzeit nicht gebraucht!).
# `mlx` wird ausgeschlossen, damit modulegraph nicht über das Namespace-Paket
# stolpert; es wird post-build manuell kopiert (siehe build_app.sh).
EXCLUDES = [
    "mlx",
    "torch", "torchvision", "torchaudio",
    "tensorflow", "jax", "jaxlib", "flax",
    "tkinter", "_tkinter", "tcl", "tk", "turtle",
    "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
    "matplotlib", "pandas", "IPython", "jupyter", "notebook",
    "pytest", "_pytest", "py2app",
    "datasets", "accelerate", "peft", "bitsandbytes",
    "sklearn", "onnx", "onnxruntime",
]

OPTIONS = {
    "iconfile": build_metadata.ICNS_PATH,
    "plist": build_metadata.INFO_PLIST,
    "packages": PACKAGES,
    "excludes": EXCLUDES,
    "argv_emulation": False,
    "optimize": 0,
    # Modelle werden NICHT gebündelt (mehrere GB) — sie laden beim ersten Start.
}

setup(
    name="voxprompt",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    cmdclass={"py2app": Py2AppCommand},
)
