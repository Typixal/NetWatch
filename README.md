# NetWatch

Per-app network monitor for Windows. Shows which processes are making network
connections, where they're connecting to, and lets you block them via Windows
Firewall.

No cloud, no account, no telemetry. All user data lives in
`%LOCALAPPDATA%\NetWatch\`.

## Requirements

- Windows 10/11
- Python 3.11+ (managed by [uv](https://docs.astral.sh/uv/) — you don't need to install it yourself)

## Setup

```powershell
uv sync
```

Everything installs into `.venv\` inside this folder. Nothing touches system
Python or `C:\` root.

## Run

```powershell
uv run netwatch
```

The app runs unelevated. Monitoring works without admin, though some system
processes won't report a PID. Blocking a process needs admin — NetWatch asks
for elevation the first time you block something, once per session.

## Test

```powershell
uv run pytest
```

## Build a standalone exe

```powershell
uv run pyinstaller netwatch.spec
```

Output: `dist\NetWatch.exe`. No installer, no registry entries beyond the
firewall rules NetWatch writes (which it cleans up) and the optional
run-on-startup key.

## Layout

```
src/netwatch/
├── app.py        entry point
├── core/         polling, DNS, flagging, firewall, elevation, history
├── ui/           frameless window, sidebar, detail pane, tray
└── utils/        paths (%LOCALAPPDATA%) and startup registry key
docs/
├── netwatch-handoff.md   architecture handoff
└── design/               Claude Design UI handoff bundle
```

## Where NetWatch writes

| What | Where |
|---|---|
| Packages | `.venv\` (this folder) |
| App data, logs, DNS cache | `%LOCALAPPDATA%\NetWatch\` |
| Firewall rules | Windows Firewall, prefixed `NetWatch_block_` |
| Run-on-startup (optional) | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\NetWatch` |
| Built exe | `dist\` (this folder) |
