# voxprompt

Lokales Push-to-Talk-Diktiertool für macOS. Deutsch-primär mit englischem
Code-Switching: lokale Spracherkennung (mlx-whisper) und lokale LLM-Nachbearbeitung
in drei Modi — Roh / Bereinigt / Prompt-optimiert.

## Start

```bash
uv run voxprompt
```

Es erscheint ein 🎙-Icon in der Menüleiste; über **Quit** lässt es sich beenden.

## Push-to-Talk

Standard-Taste: **rechte Wahltaste (right ⌥ / `<alt_r>`)** — halten zum Aufnehmen,
loslassen zum Stoppen. Das Icon zeigt den Status: 🎙 bereit · 🔴 Aufnahme · 💭 transkribiert.
Taste und Verhalten (`hold`/`toggle`) sind in [config.toml](config.toml) unter `[hotkeys]`
einstellbar.

Nach dem Loslassen wird die Aufnahme transkribiert (mlx-whisper, Deutsch erzwungen), je nach
Modus nachbearbeitet und das Ergebnis **in die Zwischenablage** gelegt — eine Notification
meldet „Text bereit". Danach mit ⌘V einfügen (oder per Auto-Paste, s. u.).

> Beim **ersten** Lauf lädt mlx-whisper das Modell `whisper-large-v3-mlx` (~3 GB) von
> Hugging Face — das dauert einmalig ein paar Minuten, danach ist es gecacht. Ein
> kleineres/schnelleres Modell lässt sich in [config.toml](config.toml) (`whisper_model`)
> setzen, z. B. `mlx-community/whisper-tiny-mlx` zum schnellen Ausprobieren.

### macOS-Berechtigungen (nötig, sonst tut sich nichts)

Beim ersten Lauf fragt macOS nicht immer von selbst — erteile manuell unter
*Systemeinstellungen → Datenschutz & Sicherheit*:

- **Eingabeüberwachung (Input Monitoring):** für die globale Push-to-Talk-Taste (pynput).
  Ohne diese Freigabe meldet die Konsole „This process is not trusted!" und die Taste
  feuert nicht.
- **Mikrofon:** für die Aufnahme (sonst nimmt die App nur Stille auf).
- **Bedienungshilfen (Accessibility):** für das optionale Auto-Paste (⌘V simulieren).

Freigeben musst du die App, von der aus gestartet wird (im Dev-Betrieb: dein Terminal;
als Dienst: siehe Hinweis unter „Als Dienst starten"). Nach dem Erteilen die App neu starten.

## Als .app bauen (py2app)

```bash
./scripts/build_app.sh        # -> dist/voxprompt.app (~600 MB, ohne Modelle)
```

Die `.app` ist eigenständig (eigenes Python + alle nativen MLX-Libs) und braucht weder ein
uv-Environment noch einen laufenden Server — sie nutzt das `inprocess`-Backend. Modelle lädt
sie beim ersten Start. Doppelklick startet die Menüleisten-App; das Signieren für die
Weitergabe an andere Macs kommt zum Schluss (siehe Phase-2-Plan, Schritt 7/8).

### Verteilbares DMG

```bash
brew install create-dmg     # einmalig
./scripts/make_dmg.sh        # -> dist/voxprompt.dmg (Drag-to-Applications)
```

DMG öffnen, **voxprompt.app in den Programme-Ordner ziehen**, fertig. (Hinweis: create-dmg
fährt für das Fensterlayout den Finder per AppleScript; bei einem `AppleEvent timed out`
einfach das Skript erneut laufen lassen.)

## App-Icon austauschen

Das mitgelieferte `assets/icon.png` ist nur ein **Platzhalter**. Eigenes Icon (1024×1024 PNG)
einfach unter `assets/icon.png` ablegen und neu generieren:

```bash
./scripts/make_icons.sh   # baut assets/voxprompt.icns + Menüleisten-Template neu
```

Das Menüleisten-Icon ist ein monochromes **Template** (passt sich an helle/dunkle Menüleiste
an); das App-Icon (`.icns`) landet später im `.app`-Bundle.

## Erster Start: Modelle laden

Beim allerersten Start lädt voxprompt die benötigten Modelle (Spracherkennung, bei
`inprocess` zusätzlich das Sprachmodell — mehrere GB) von Hugging Face. Ein Hinweisfenster
erklärt das, der Fortschritt erscheint als `⬇ %` im Menüleisten-Icon, danach meldet eine
Notification „Modelle bereit". Der App-Start selbst bleibt schnell — die Modelle werden
**lazy** beim ersten Diktat in den Speicher geladen und dort gehalten. Sind die Modelle
schon im HF-Cache, entfällt der Download.

## LLM-Backend: endpoint vs. inprocess

`[llm] llm_backend` in [config.toml](config.toml):
- **`endpoint`** (Default, Entwicklung): HTTP gegen einen lokalen MLX-Server
  (`llm_endpoint`). Kann den Server automatisch mitstarten (s. u.).
- **`inprocess`** (für die verteilbare App): lädt das Modell über `mlx_lm` direkt in den
  Prozess — **kein Server, kein Port** nötig. Das Modell wird beim ersten Gebrauch geladen
  und für die Sitzung gehalten.

Beide liefern identische Ergebnisse; der Rest der App merkt nichts vom Backend.

## LLM-Server automatisch starten/stoppen

Mit `[llm] manage_server = true` (Default) fährt voxprompt beim Start den lokalen
LLM-Server selbst hoch und beim Beenden wieder herunter (das geladene Modell wird dabei
entladen). Der Startbefehl steht in `[llm] server_command` ({host}/{port} kommen aus
`llm_endpoint`). Läuft beim Start bereits ein Server unter `llm_endpoint` (z. B. manuell
gestartet), wird er **übernommen und beim Beenden nicht** gestoppt.

So genügt:

```bash
uv run voxprompt          # startet auch den mlx_lm.server
# … diktieren …
# Quit im Menü (oder Strg-C / Prozess beenden) -> Server wird gestoppt, Modell entladen
```

Server-Log: `/tmp/voxprompt-mlx.log`.

> Hinweis: Wer voxprompt als immer laufenden **LaunchAgent** betreibt (s. u.), hat den
> Server faktisch dauerhaft an (KeepAlive startet die App nach Quit neu). Das automatische
> Stoppen beim Beenden greift v. a. im Standalone-Betrieb (`uv run voxprompt`). Für reinen
> On-Demand-Betrieb den LaunchAgent entladen.

## Als Dienst starten (LaunchAgent, Autostart beim Login)

voxprompt läuft als **LaunchAgent** (nicht als system LaunchDaemon — eine Menüleisten-App
mit globalen Hotkeys braucht die eingeloggte GUI-Session). Damit startet es automatisch beim
Login, wird nach Absturz/Beenden neu gestartet und übersteht Ab-/Anmelden und Reboot.

```bash
# 1) plist in den LaunchAgents-Ordner kopieren
cp ~/dev/voxprompt/scripts/com.erik.voxprompt.plist ~/Library/LaunchAgents/

# 2) laden (startet die App sofort; RunAtLoad=true)
launchctl load ~/Library/LaunchAgents/com.erik.voxprompt.plist

# Status / Logs
launchctl list | grep voxprompt
tail -f /tmp/voxprompt.err.log   # u. a. die pynput-Berechtigungsmeldung

# Stoppen / entladen (nötig, weil KeepAlive es sonst neu startet)
launchctl unload ~/Library/LaunchAgents/com.erik.voxprompt.plist

# Nach einer plist-Änderung: erst unload, dann load
```

**Wichtig — Berechtigungen für den Dienst:** Mikrofon, Eingabeüberwachung und (für
Auto-Paste) Bedienungshilfen müssen dem Prozess erteilt werden, der jetzt startet — das ist
nicht mehr dein Terminal, sondern der über launchd gestartete Python-Prozess
(`…/voxprompt/.venv/bin/python3`). macOS fragt beim ersten Tastendruck/ersten Mikrofonzugriff;
falls nicht, die Einträge unter *Systemeinstellungen → Datenschutz & Sicherheit* manuell
hinzufügen (Liste über „+" und den Python-Pfad). Nach dem Erteilen einmal
`launchctl unload`/`load`.

> KeepAlive=true heißt: „Quit" im Menü startet den Dienst sofort neu. Zum echten Beenden
> `launchctl unload` benutzen. Pfade in der plist (uv unter `~/.local/bin/uv`,
> Projekt `~/dev/voxprompt`) ggf. anpassen, falls du das Projekt verschiebst.

## Status

Strikt schrittweise gebaut — **alle 8 Schritte fertig** (Gerüst → Audio/Hotkey →
STT+Clipboard → LLM-Client → Modus 2 → Modus 3+Umschaltung → Hardening → LaunchAgent).
Aufnahme → Transkription (mlx-whisper, Deutsch) → Modus-Nachbearbeitung übers lokale LLM →
Zwischenablage/Auto-Paste, mit VAD, Halluzinations-Guard und Fehler-Notifications. Für die
LLM-Modi muss der Server laufen (`[llm] llm_endpoint` in [config.toml](config.toml)).
Details siehe [CLAUDE.md](CLAUDE.md).

### Auto-Paste (optional)

`[output] auto_paste = true` in [config.toml](config.toml) fügt das Ergebnis nach dem
Kopieren direkt per ⌘V ins fokussierte Feld ein. Braucht zusätzlich die macOS-Freigabe
**Bedienungshilfen (Accessibility)** für den startenden Prozess.

## Modi

Über das Menüleisten-Menü (aktueller Modus mit Häkchen) oder per Hotkey:

| Modus | Hotkey | was es macht |
|------|--------|--------------|
| **Roh** | ⌘⇧1 | Rohtranskript, kein LLM |
| **Bereinigt** | ⌘⇧2 | Transkript säubern (Interpunktion, Füllwörter, korrekte engl. Schreibweise) — Default |
| **Prompt** | ⌘⇧3 | aus gesprochenem Gedanken-Dump einen einsatzbereiten Prompt bauen (beantwortet ihn NICHT) |

Der gewählte Modus gilt für die nächste Aufnahme. Hotkeys sind in
[config.toml](config.toml) unter `[hotkeys]` einstellbar.

## Voraussetzungen (für spätere Schritte)

- Python 3.12, [uv](https://docs.astral.sh/uv/)
- Lokaler OpenAI-kompatibler LLM-Endpoint, z. B.:
  `uv run mlx_lm.server --model mlx-community/Qwen3-4B-Instruct-4bit --port 8080`

## Lizenz

© 2026 Erik ([github.com/MainzelMennchen](https://github.com/MainzelMennchen)).

**CC BY-NC-ND 4.0** ([Creative Commons Attribution-NonCommercial-NoDerivatives 4.0
International](https://creativecommons.org/licenses/by-nc-nd/4.0/)) — siehe
[LICENSE](LICENSE).

Kurz gesagt: Du darfst voxprompt **nutzen und unverändert weitergeben**, mit
Namensnennung. **Nicht erlaubt** sind kommerzielle Nutzung/Profit sowie das
Weiterverbreiten von **veränderten Versionen oder abgeleiteten Werken** (auch
geänderten Forks). Für alles darüber hinaus bitte anfragen.
