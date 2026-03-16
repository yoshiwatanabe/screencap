# screencap

Windows Task Scheduler-triggered screenshot monitor. Every 2 minutes it scans
a folder for screenshots, analyzes each new one via GitHub Copilot CLI,
categorizes it (main/sub category), creates a sidecar `.md` file with a
description and preview-ready image link, and moves the image+sidecar pair
into an organized output directory.

No console window. No always-on process. Uses your GitHub Copilot subscription
— no Azure keys, no Anthropic tokens.

## Quick Start

```powershell
git clone <repo-url>
cd screencap
powershell -ExecutionPolicy Bypass -File setup.ps1
```

`setup.ps1` auto-detects Python and Copilot CLI, prompts for your folder
paths, writes `config.json`, and registers the scheduled task. Done.

## Prerequisites

- Windows 11
- Python 3.11+ (with `pythonw.exe` — included in standard install)
- [GitHub Copilot CLI](https://www.npmjs.com/package/@github/copilot) via npm:
  ```powershell
  npm install -g @github/copilot
  copilot login
  ```

## Output Structure

```
output_dir/
├── development/
│   ├── python/
│   │   ├── Screenshot_2026-03-15_143022.png
│   │   └── Screenshot_2026-03-15_143022.md   ← opens with image preview
│   └── vscode/
├── communication/
│   └── teams/
├── social-media/
│   └── facebook/
└── others/                                   ← ambiguous / unclear images
```

Each `.md` sidecar renders the image when opened in VS Code, Obsidian, or GitHub.

## Configuration

`config.json` is created by `setup.ps1` and is gitignored (machine-specific).
See `config.example.json` for all available options.

Key settings:

| Key | Default | Description |
|-----|---------|-------------|
| `watch_dir` | `...\Screenshots` | Folder to monitor |
| `output_dir` | `...\Organized` | Where categorized files go |
| `max_age_minutes` | `5` | Files younger than this stay untouched |
| `copilot_model` | `gpt-5.4` | Model for image analysis |

## Daily Use

The task runs silently every 2 minutes. Files less than 5 minutes old stay in
`watch_dir` so you can still drag-and-drop from it. Older files are analyzed
and moved automatically.

## Check Logs

```powershell
# Live tail
Get-Content logs\screencap.log -Wait -Tail 20

# Last 10 lines
Get-Content logs\screencap.log -Tail 10
```

## Manual Test (no Task Scheduler)

```powershell
# See what would be processed — no files moved, no API calls
python main.py --dry-run

# Run for real
python main.py
```

## Pause / Resume

```powershell
# Pause (files accumulate, nothing processed)
Disable-ScheduledTask -TaskName "ScreencapMonitor"

# Resume
Enable-ScheduledTask -TaskName "ScreencapMonitor"
```

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File remove_task.ps1
```

Removes the scheduled task only. Your `config.json`, `state.json`, logs, and
all organized screenshots are preserved.

## Fresh Start

If you want to reprocess everything from scratch:

```powershell
Disable-ScheduledTask -TaskName "ScreencapMonitor"
Remove-Item state.json -ErrorAction SilentlyContinue
Remove-Item metadata\categories.json -ErrorAction SilentlyContinue
Enable-ScheduledTask -TaskName "ScreencapMonitor"
```

## Category Dictionary

Categories grow automatically as new screenshots are analyzed. The dictionary
lives at `metadata\categories.json` (gitignored). `others` is the implicit
catch-all and is never written to the file.

## Run Tests

```powershell
python -m unittest discover -s tests -v
```
