# voxprompt

[Deutsch](README.md) · **English**

[![License: CC BY-NC-ND 4.0](https://img.shields.io/badge/License-CC%20BY--NC--ND%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-nd/4.0/)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![macOS 13+](https://img.shields.io/badge/macOS-13%2B-black.svg)](https://www.apple.com/macos/)

Local push-to-talk dictation tool for macOS. German-primary with English
code-switching: local speech recognition (mlx-whisper) and local LLM post-processing
in three modes: Raw, Cleaned, Prompt-optimized.

## Start

```bash
uv run voxprompt
```

A 🎙 icon appears in the menu bar; use **Quit** to exit.

## Push-to-talk

Default key: **right option key (right ⌥ / `<alt_r>`)**. Hold to record,
release to stop. The icon shows the status: 🎙 ready · 🔴 recording · 💭 transcribing.
Key and behavior (`hold`/`toggle`) are configurable in [config.toml](config.toml) under
`[hotkeys]`.

After releasing, the recording is transcribed (mlx-whisper, German enforced), post-processed
depending on the mode, and the result is placed **on the clipboard**; a notification says
"Text ready". Then paste it with ⌘V (or via auto-paste, see below).

> On the **first** run, mlx-whisper downloads the `whisper-large-v3-mlx` model (~3 GB) from
> Hugging Face. This takes a few minutes once, after which it is cached. A
> smaller/faster model can be set in [config.toml](config.toml) (`whisper_model`),
> e.g. `mlx-community/whisper-tiny-mlx` for a quick try.

### macOS permissions (required, otherwise nothing happens)

On the first run macOS does not always ask by itself. Grant the permissions manually under
*System Settings → Privacy & Security*:

- **Input Monitoring:** for the global push-to-talk key (pynput).
  Without this, the console reports "This process is not trusted!" and the key
  does not fire.
- **Microphone:** for recording (otherwise the app only records silence).
- **Accessibility:** for the optional auto-paste (simulating ⌘V).

You must grant these to the app that starts it (in dev: your terminal;
as a service: see the note under "Run as a service"). Restart the app after granting.

## Build the .app (py2app)

```bash
./scripts/build_app.sh        # -> dist/voxprompt.app (~600 MB, without models)
```

The `.app` is self-contained (its own Python + all native MLX libs) and needs neither a
uv environment nor a running server; it uses the `inprocess` backend. It downloads models
on first launch. A double-click starts the menu bar app; signing for
distribution to other Macs comes last (see the Phase 2 plan, step 7/8).

### Distributable DMG

```bash
brew install create-dmg     # once
./scripts/make_dmg.sh        # -> dist/voxprompt.dmg (drag-to-Applications)
```

Open the DMG, **drag voxprompt.app into the Applications folder**, done. (Note: create-dmg
drives the Finder via AppleScript for the window layout; on an `AppleEvent timed out`
just run the script again.)

## Replace the app icon

The bundled `assets/icon.png` is only a **placeholder**. Just put your own icon (1024×1024 PNG)
at `assets/icon.png` and regenerate:

```bash
./scripts/make_icons.sh   # rebuilds assets/voxprompt.icns + menu bar template
```

The menu bar icon is a monochrome **template** (adapts to a light/dark menu bar);
the app icon (`.icns`) later goes into the `.app` bundle.

## First launch: downloading models

On the very first launch, voxprompt downloads the required models (speech recognition, plus
the language model with `inprocess`; several GB) from Hugging Face. A dialog
explains this, progress appears as `⬇ %` in the menu bar icon, and afterwards a
notification says "Models ready". The app launch itself stays fast: the models are loaded
**lazily** into memory on the first dictation and kept there. If the models are
already in the HF cache, the download is skipped.

## LLM backend: endpoint vs. inprocess

`[llm] llm_backend` in [config.toml](config.toml):
- **`endpoint`** (default, development): HTTP against a local MLX server
  (`llm_endpoint`). Can start the server automatically (see below).
- **`inprocess`** (for the distributable app): loads the model via `mlx_lm` directly into the
  process. **No server, no port** needed. The model is loaded on first use
  and kept for the session.

Both produce identical results; the rest of the app is unaware of the backend.

## Start/stop the LLM server automatically

With `[llm] manage_server = true` (default), voxprompt starts the local
LLM server itself on launch and shuts it down again on exit (the loaded model is
unloaded in the process). The start command is in `[llm] server_command` ({host}/{port} come
from `llm_endpoint`). If a server is already running at `llm_endpoint` on launch (e.g. started
manually), it is **adopted and not** stopped on exit.

So this is enough:

```bash
uv run voxprompt          # also starts the mlx_lm.server
# … dictate …
# Quit in the menu (or Ctrl-C / kill the process) -> server is stopped, model unloaded
```

Server log: `/tmp/voxprompt-mlx.log`.

> Note: If you run voxprompt as an always-on **LaunchAgent** (see below), the
> server is effectively always on (KeepAlive restarts the app after Quit). The automatic
> stop on exit mainly matters in standalone operation (`uv run voxprompt`). For pure
> on-demand operation, unload the LaunchAgent.

## Run as a service (LaunchAgent, autostart at login)

voxprompt runs as a **LaunchAgent** (not as a system LaunchDaemon; a menu bar app
with global hotkeys needs the logged-in GUI session). This way it starts automatically at
login, is restarted after a crash/exit, and survives logout/login and reboot.

```bash
# 1) copy the plist into the LaunchAgents folder
cp ~/dev/voxprompt/scripts/com.erik.voxprompt.plist ~/Library/LaunchAgents/

# 2) load it (starts the app immediately; RunAtLoad=true)
launchctl load ~/Library/LaunchAgents/com.erik.voxprompt.plist

# status / logs
launchctl list | grep voxprompt
tail -f /tmp/voxprompt.err.log   # incl. the pynput permission message

# stop / unload (needed, because KeepAlive otherwise restarts it)
launchctl unload ~/Library/LaunchAgents/com.erik.voxprompt.plist

# After a plist change: first unload, then load
```

**Important, permissions for the service:** Microphone, Input Monitoring and (for
auto-paste) Accessibility must be granted to the process that now starts; that is
no longer your terminal, but the Python process started via launchd
(`…/voxprompt/.venv/bin/python3`). macOS asks on the first keypress/first microphone access;
if not, add the entries manually under *System Settings → Privacy & Security*
(list via "+" and the Python path). After granting, run
`launchctl unload`/`load` once.

> KeepAlive=true means: "Quit" in the menu immediately restarts the service. To really exit,
> use `launchctl unload`. Adjust the paths in the plist (uv at `~/.local/bin/uv`,
> project `~/dev/voxprompt`) if you move the project.

## Status

Built strictly step by step, **all 8 steps done** (scaffold → audio/hotkey →
STT+clipboard → LLM client → mode 2 → mode 3+switching → hardening → LaunchAgent).
Recording → transcription (mlx-whisper, German) → mode post-processing via the local LLM →
clipboard/auto-paste, with VAD, hallucination guard and error notifications. For the
LLM modes the server must be running (`[llm] llm_endpoint` in [config.toml](config.toml)).

### Auto-paste (optional)

`[output] auto_paste = true` in [config.toml](config.toml) pastes the result right after
copying via ⌘V into the focused field. Additionally needs the macOS permission
**Accessibility** for the starting process.

## Modes

Via the menu bar menu (current mode checked) or by hotkey:

| Mode | Hotkey | what it does |
|------|--------|--------------|
| **Raw** | ⌘⇧1 | raw transcript, no LLM |
| **Cleaned** | ⌘⇧2 | clean up the transcript (punctuation, filler words, correct English spelling); default |
| **Prompt** | ⌘⇧3 | turn a spoken thought-dump into a ready-to-use prompt (does NOT answer it) |

The selected mode applies to the next recording. Hotkeys are configurable in
[config.toml](config.toml) under `[hotkeys]`.

## Requirements (for later steps)

- Python 3.12, [uv](https://docs.astral.sh/uv/)
- Local OpenAI-compatible LLM endpoint, e.g.:
  `uv run mlx_lm.server --model mlx-community/Qwen3-4B-Instruct-4bit --port 8080`

## License

© 2026 Erik ([github.com/MainzelMennchen](https://github.com/MainzelMennchen)).

**CC BY-NC-ND 4.0** ([Creative Commons Attribution-NonCommercial-NoDerivatives 4.0
International](https://creativecommons.org/licenses/by-nc-nd/4.0/)). See
[LICENSE](LICENSE).

In short: you may **use and redistribute voxprompt unchanged**, with
attribution. **Not permitted** are commercial use/profit and the
redistribution of **modified versions or derivative works** (including
modified forks). For anything beyond that, please ask.
