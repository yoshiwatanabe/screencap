# Plan: screencap — Windows Task Scheduler Screenshot Monitor

**Objective:** Python tool triggered by Windows Task Scheduler that monitors a screenshot folder, analyzes images via GitHub Copilot CLI, categorizes them (main/sub), creates a sidecar `.md` per image (description + relative image link), and moves the image+sidecar pair into a category-organized output directory.

**Mode:** Direct (no git/GitHub CI workflow)
**Language:** Python 3.13 (`pythonw.exe` for headless execution)
**Platform:** Windows 11 only
**LLM backend:** GitHub Copilot CLI (`copilot` npm package) — uses GitHub Copilot subscription, not Anthropic tokens

---

## Architecture Overview

```
[Task Scheduler] every 1-2 min
    → pythonw.exe main.py
        1. Load config
        2. Load category tree (metadata/categories.json)
        3. Scan watch_dir → filter to files older than max_age_minutes
        4. For each ready image (not yet in state.json):
               a. Call Copilot CLI → get {main_category, sub_category, description}
               b. Auto-add any new categories to metadata/categories.json
               c. Create sidecar .md (relative image link + description)
               d. Move image + sidecar → output_dir/<main>/<sub>/
                  (or output_dir/others/ if ambiguous)
               e. Mark processed in state.json
        5. Exit
```

**Key design decisions:**
- Files under `max_age_minutes` old stay in `watch_dir` (user may still be drag-and-dropping)
- Category dictionary starts empty, grows automatically as new categories are discovered
- `others/` is a flat catch-all (no subcategory)
- Sidecar `.md` uses a relative image link — renders in VS Code preview, Obsidian, GitHub
- No separate archive_dir — the categorized output_dir IS the archive
- `metadata/categories.json` lives in repo dir (config/state, not user output)
- No external Python packages — stdlib only

---

## File Layout

```
screencap/                         ← repo root
├── main.py
├── config.py
├── processor.py
├── categories.py
├── analyzer.py
├── config.json                    ← gitignored, machine-specific
├── config.example.json            ← committed, USERNAME placeholders
├── state.json                     ← gitignored, processed file registry
├── setup.ps1
├── remove_task.ps1
├── README.md
├── .gitignore
├── metadata/
│   └── categories.json            ← gitignored, grows over time
├── logs/                          ← gitignored
│   └── screencap.log
└── plans/
    └── screencap-scheduler-monitor.md

output_dir/                        ← configured path, outside repo
├── development/
│   ├── python/
│   │   ├── Screenshot_2026-03-15_143022.png
│   │   └── Screenshot_2026-03-15_143022.md
│   └── vscode/
│       └── ...
├── communication/
│   └── email/
│       └── ...
└── others/
    ├── Screenshot_unclear.png
    └── Screenshot_unclear.md
```

---

## Skill Usage Guide

| Phase | Skill | Purpose |
|-------|-------|---------|
| **Pre-implementation** | `everything-claude-code:prompt-optimize` | Harden the Copilot CLI categorization prompt before writing `analyzer.py` |
| **Pre-implementation** | `everything-claude-code:regex-vs-llm-structured-text` | Decide JSON extraction strategy (robust parsing from LLM output) |
| **Pre-implementation** | `everything-claude-code:content-hash-cache-pattern` | Validate `state.json` SHA-256 design before writing `processor.py` |
| **Every implementation step** | `everything-claude-code:tdd-workflow` | Write tests first; test runner output automatically feeds back to model — closed agent loop |
| **Every implementation step** | `everything-claude-code:python-patterns` | Enforce Pythonic idioms, type hints, PEP 8 while writing each module |
| **Step 4 security check** | `everything-claude-code:security-review` | Subprocess call with LLM-generated category strings in file paths = path traversal risk |
| **Post-implementation** | `everything-claude-code:python-review` | Full review pass before calling each module done |
| **Post-implementation** | `simplify` (built-in) | Remove any over-engineering; enforce stdlib-only constraint |

---

## Step 1 — Project Scaffold + Configuration

**Context:** Empty project at `C:\Users\tsuyo\Repos\screencap`.

### Tasks
- [ ] Create all files and directories per the layout above (empty stubs for .py files)

- [ ] Write `config.example.json`:
  ```json
  {
    "watch_dir":         "C:\\Users\\USERNAME\\OneDrive\\Pictures\\Screenshots",
    "output_dir":        "C:\\Users\\USERNAME\\OneDrive\\Pictures\\Screenshots\\Organized",
    "max_age_minutes":   5,
    "image_extensions":  [".png", ".jpg", ".jpeg", ".bmp"],
    "copilot_loader":    "C:\\Users\\USERNAME\\AppData\\Roaming\\npm\\node_modules\\@github\\copilot\\npm-loader.js",
    "copilot_model":     "gpt-5.4",
    "copilot_timeout":   60,
    "metadata_dir":      "REPO_DIR\\metadata",
    "log_file":          "REPO_DIR\\logs\\screencap.log",
    "state_file":        "REPO_DIR\\state.json"
  }
  ```
  `REPO_DIR` is resolved at runtime to the directory containing `main.py`.

- [ ] Write `config.py`:
  - `load_config(path) → dict`
  - Resolves `REPO_DIR` tokens in all string values
  - Creates `metadata_dir`, `logs/` dir if they don't exist
  - Validates required keys; raises `ValueError` with clear message on failure

- [ ] Write `.gitignore`:
  ```
  config.json
  state.json
  metadata/
  logs/
  *.lock
  __pycache__/
  ```

### Verification
```bash
python main.py --dry-run   # after copying config.example.json → config.json and filling USERNAME
```

### Exit Criteria
- Config loads and resolves REPO_DIR tokens
- Required directories created automatically
- Clear error on missing config keys

---

## Step 2 — State Tracker

> **Skills:** Run `/content-hash-cache-pattern` before writing this module to validate the SHA-256 design. Use `/tdd-workflow` + `/python-patterns` during implementation.

**Context:** `state.json` records which files have been processed across runs. Keyed by filename (not full path) since files move after processing.

### Tasks
- [ ] Write `processor.py` with:
  - `load_state(path) → dict` — returns `{}` if not found
  - `save_state(path, state)` — atomic write via `os.replace`
  - `file_hash(path) → str` — SHA-256 of file contents
  - `get_ready(watch_dir, extensions, max_age_minutes, state) → list[Path]`
    - Scans watch_dir (top-level only, no recursion)
    - Filters to files with `(now - mtime).total_seconds() / 60 >= max_age_minutes`
    - Excludes files whose hash is already in state
    - Returns sorted list (oldest first)
  - `mark_processed(state, original_path, hash, main_cat, sub_cat, sidecar_path, dest_image_path)`
  - `prune_state(state, output_dir)` — removes entries whose dest_image_path no longer exists

- [ ] State entry format:
  ```json
  {
    "Screenshot_2026-03-15_143022.png": {
      "hash":        "abc123...",
      "processed_at":"2026-03-15T14:30:45",
      "main_category":"development",
      "sub_category": "python",
      "dest_image":  "C:\\...\\Organized\\development\\python\\Screenshot_2026-03-15_143022.png",
      "dest_sidecar":"C:\\...\\Organized\\development\\python\\Screenshot_2026-03-15_143022.md"
    }
  }
  ```

### Verification
```bash
python -c "from processor import load_state, get_ready; print('OK')"
```

### Exit Criteria
- Only files older than threshold returned by `get_ready`
- Already-processed hashes excluded
- Atomic state save

---

## Step 3 — Category Manager

> **Skills:** `/tdd-workflow` + `/python-patterns` — pure functions, very test-friendly.

**Context:** `metadata/categories.json` starts empty and grows automatically. The LLM is shown the current tree so it can pick existing categories or propose new ones.

### Tasks
- [ ] Write `categories.py` with:

  - `load_categories(path) → dict`
    Returns `{}` if file doesn't exist (empty on first run).
    Format: `{"development": ["python", "vscode"], "communication": ["email"]}`

  - `save_categories(path, cats)` — atomic write via `os.replace`

  - `format_tree(cats) → str`
    Formats dict as indented tree string for the LLM prompt:
    ```
    development
      python
      vscode
    communication
      email
    others
    ```
    Always appends `others` at the end (even if not in dict) as the fallback hint.

  - `ensure_category(cats, main, sub) -> bool`
    Adds `main` and/or `sub` if not present. Returns `True` if dict was modified.
    Special case: `main="others"` is never written to the dict (it's implicit).

### Verification
```bash
python -c "
from categories import load_categories, format_tree, ensure_category
cats = {}
ensure_category(cats, 'development', 'python')
print(format_tree(cats))
"
# Expected output:
# development
#   python
# others
```

### Exit Criteria
- Empty dict formats cleanly (just `others`)
- `ensure_category` is idempotent
- `others` never written to the file, always appended in `format_tree`

---

## Step 4 — Copilot CLI Analyzer + Categorizer

> **Skills (before writing):** `/prompt-optimize` on the prompt template; `/regex-vs-llm-structured-text` for JSON extraction strategy.
> **Skills (during):** `/tdd-workflow` + `/python-patterns`.
> **Skills (after):** `/security-review` — LLM-generated strings used in file paths (path traversal risk on `main_category`/`sub_category`).

**Context:** Core logic. For each ready image: call Copilot CLI with the current category tree embedded in the prompt, parse the JSON response, update categories if new ones proposed, create sidecar `.md`, move image+sidecar pair to target directory.

### Confirmed Copilot CLI syntax:
```bash
node <copilot-loader.js> \
    -p "<prompt>" \
    --allow-all-tools \
    --output-format text \
    --model gpt-5.4
```

### Tasks

- [ ] Write `analyzer.py` with one public function: `process_image(image_path, config, cats, log) → dict | None`

  **Prompt template** (built at call time using current `format_tree(cats)`):
  ```
  Read the screenshot at: {image_path}

  Existing categories:
  {category_tree}

  Analyze the screenshot and respond with ONLY a JSON object — no other text:
  {{
    "main_category": "<choose from list or propose new single-word lowercase>",
    "sub_category":  "<choose or propose, or null if not applicable>",
    "description":   "<2-3 sentences: what app/content is shown and what the user appears to be doing>"
  }}

  Rules:
  - Use an existing category when it fits. Propose a new one only if none fit.
  - If the image is ambiguous, too vague, or unclear, use "others" for main_category and null for sub_category.
  - main_category and sub_category must be lowercase, no spaces (use hyphens).
  - description must be plain text, no markdown.
  ```

  **Response parsing:**
  - Extract JSON from stdout using `re.search(r'\{.*?\}', text, re.DOTALL)` as fallback if needed
  - On parse failure: log the raw response, return `None` (image stays in watch_dir, retried next run)

  **Category update:**
  - Call `ensure_category(cats, main, sub)` — if modified, caller saves cats back to disk

  **Sidecar `.md` creation:**
  ```markdown
  ---
  source: Screenshot_2026-03-15_143022.png
  analyzed_at: 2026-03-15T14:30:45
  main_category: development
  sub_category: python
  model: gpt-5.4
  ---

  ![Screenshot_2026-03-15_143022](Screenshot_2026-03-15_143022.png)

  ## Description

  The user is editing a Python script in VS Code. The file open is main.py and the
  integrated terminal shows a test run in progress.
  ```
  Note: image link uses `image_path.stem` (no extension in alt text, `.png` in path) — relative, so it works after move.

  **File move:**
  - Target: `output_dir / main_category / sub_category /` (or `output_dir / "others" /` if main=others)
  - `sub_category` is omitted from path if `None`
  - Creates target dir if needed
  - If destination filename already exists: append `_1`, `_2`, etc.
  - Move image first, then sidecar (if image move fails, sidecar is not created)

  **Return value on success:**
  ```python
  {
    "main_category": "development",
    "sub_category":  "python",
    "dest_image":    Path(...),
    "dest_sidecar":  Path(...)
  }
  ```

- [ ] Handle `copilot` process errors: non-zero returncode → log stderr, return `None`
- [ ] Handle timeout (configurable, default 60s)

### Verification
```bash
python -c "
import json, logging, sys
from pathlib import Path
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
log = logging.getLogger()
cfg = json.load(open('config.json'))
from categories import load_categories
cats = load_categories(cfg['metadata_dir'] + '/categories.json')
from analyzer import process_image
result = process_image(Path('path/to/test.png'), cfg, cats, log)
print(result)
"
```

### Exit Criteria
- JSON parsed correctly from Copilot output
- New categories auto-added to dict
- Sidecar `.md` renders correctly in VS Code preview (relative image link works)
- Image+sidecar land in correct category subdirectory
- Partial failure (e.g. copilot timeout) leaves image in watch_dir for retry next run

---

## Step 5 — Main Entry Point + Logging

> **Skills:** `/tdd-workflow` + `/python-patterns` during; `/python-review` + `/simplify` after wiring all modules together.

**Context:** `main.py` is what Task Scheduler invokes via `pythonw.exe`. No console exists — all output to rotating log file.

### Tasks
- [ ] Write `main.py`:
  ```
  Invocation: pythonw.exe main.py [--dry-run] [--config path]

  1.  Parse CLI args
  2.  Load config
  3.  Set up RotatingFileHandler (10 MB, 3 backups)
  4.  Acquire lock file → if already locked by live process: log + exit 0
  5.  log.info("Run started")
  6.  Load state (processor.load_state)
  7.  Load categories (categories.load_categories)
  8.  Get ready images (processor.get_ready)
  9.  log.info(f"{len(ready)} image(s) ready for processing")
  10. cats_modified = False
      for image in ready:
          result = analyzer.process_image(image, config, cats, log)
          if result:
              if ensure_category(cats, result['main_category'], result['sub_category']):
                  cats_modified = True
              mark_processed(state, image, file_hash(image), ...)
              log.info(f"  {image.name} → {result['main_category']}/{result['sub_category']}")
          else:
              log.warning(f"  {image.name} → failed, will retry")
  11. if cats_modified: save_categories(...)
  12. prune_state(state, config['output_dir'])
  13. save_state(...)
  14. Release lock
  15. log.info("Run complete")
  ```

- [ ] `--dry-run`: logs what would happen, calls Copilot CLI (to get real categorization output), but does NOT move files or write state/categories
- [ ] Missing `watch_dir`: log warning, exit 0 cleanly

### Verification
```bash
python main.py --dry-run
# Check logs/screencap.log — should show categorization decisions without moving files
```

### Exit Criteria
- Full pipeline runs end-to-end
- `--dry-run` calls Copilot but makes no filesystem changes
- Lock prevents overlap
- All activity in log

---

## Step 6 — Setup Script + Task Scheduler Registration

**Context:** After `git clone`, a single `setup.ps1` configures the tool and registers the scheduled task. Must work on any Windows 11 machine.

### Tasks
- [ ] Write `setup.ps1`:
  ```powershell
  # Auto-detect pythonw.exe
  $pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue)?.Source
  if (-not $pythonw) { $pythonw = Read-Host "pythonw.exe not found. Enter full path" }

  # Auto-detect copilot npm-loader.js
  $npmDir = "$env:APPDATA\npm\node_modules\@github\copilot\npm-loader.js"
  $loader = if (Test-Path $npmDir) { $npmDir } else { Read-Host "copilot npm-loader.js path" }

  # Prompt for paths (with defaults)
  $defaultWatch = "C:\Users\$env:USERNAME\OneDrive\Pictures\Screenshots"
  $watchDir  = Read-Host "Screenshot watch folder [$defaultWatch]"
  if (-not $watchDir) { $watchDir = $defaultWatch }

  $defaultOut = "$watchDir\Organized"
  $outputDir = Read-Host "Output (organized) folder [$defaultOut]"
  if (-not $outputDir) { $outputDir = $defaultOut }

  # Model selection
  Write-Host "Available models: gpt-5.4, gemini-3-pro-preview, claude-haiku-4.5, claude-sonnet-4.6"
  $model = Read-Host "Model [gpt-5.4]"
  if (-not $model) { $model = "gpt-5.4" }

  # Write config.json
  $repoDir = $PSScriptRoot
  $config = @{
    watch_dir        = $watchDir
    output_dir       = $outputDir
    max_age_minutes  = 5
    image_extensions = @(".png", ".jpg", ".jpeg", ".bmp")
    copilot_loader   = $loader
    copilot_model    = $model
    copilot_timeout  = 60
    metadata_dir     = "REPO_DIR\metadata"
    log_file         = "REPO_DIR\logs\screencap.log"
    state_file       = "REPO_DIR\state.json"
  }
  $config | ConvertTo-Json | Set-Content "$repoDir\config.json"

  # Create directories
  @($watchDir, $outputDir, "$repoDir\metadata", "$repoDir\logs") | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ | Out-Null }
  }

  # Register scheduled task
  $action   = New-ScheduledTaskAction -Execute $pythonw -Argument "$repoDir\main.py" -WorkingDirectory $repoDir
  $trigger  = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 2) -Once -At (Get-Date)
  $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -StartWhenAvailable
  Register-ScheduledTask -TaskName "ScreencapMonitor" -Action $action -Trigger $trigger -Settings $settings -Force

  # Dry-run verify
  & $pythonw "$repoDir\main.py" --dry-run
  Write-Host "`nSetup complete. Logs at: $repoDir\logs\screencap.log"
  ```

- [ ] Write `remove_task.ps1`:
  ```powershell
  Unregister-ScheduledTask -TaskName "ScreencapMonitor" -Confirm:$false
  Write-Host "Task removed. config.json, state.json, and logs preserved."
  ```

- [ ] Write `README.md` with: quick start, how to check logs, pause/resume, uninstall, manual test

### Verification
```powershell
Get-ScheduledTask -TaskName "ScreencapMonitor" | Select-Object State, LastRunTime, NextRunTime
Start-ScheduledTask -TaskName "ScreencapMonitor"
# Check logs\screencap.log — silent run, no window
```

### Exit Criteria
- Fresh clone → `setup.ps1` → working task on any Win11 machine
- Task fires silently
- `--dry-run` verifies config before first real run

---

## Dependency Graph

```
Step 1 (scaffold + config)
    ├── Step 2 (state tracker)   ─┐
    ├── Step 3 (category manager) ├── Step 5 (main wiring) → Step 6 (setup)
    └── Step 4 (analyzer)        ─┘
```

Steps 2, 3, 4 are independent — implement in parallel after Step 1.

---

## Invariants (check after every step)

- [ ] No external pip packages — stdlib only
- [ ] `config.json`, `state.json`, `metadata/` are gitignored
- [ ] `others` never written to `categories.json` — always implicit
- [ ] Image moved before sidecar created — no orphaned `.md` files
- [ ] Name collision on move uses `_1`, `_2` suffix — no silent overwrites
- [ ] State writes and categories writes are atomic (`os.replace`)
- [ ] All errors logged; failed images stay in `watch_dir` for retry

---

## Open Questions — All Resolved

1. ~~Category starting state~~ → **empty, grows automatically**
2. ~~New category handling~~ → **auto-add to dict**
3. ~~Sidecar image link~~ → **relative path, confirmed**
4. ~~Watch dir location~~ → **configurable via setup.ps1, default OneDrive path**
5. ~~Output dir~~ → **output_dir/main/sub/ replaces old archive_dir**

---

## Rollback / Pause Strategy

- Pause: `Disable-ScheduledTask -TaskName "ScreencapMonitor"`
- Remove: `powershell -File remove_task.ps1`
- Fresh start: delete `state.json` + `metadata/categories.json` — safe, images already moved are unaffected
- No database, no registry edits beyond the scheduled task

---

*Plan updated: 2026-03-15 | LLM: Copilot CLI (gpt-5.4) | Mode: direct*
