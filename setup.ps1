#Requires -Version 5.1
<#
.SYNOPSIS
    First-time setup for screencap — configures config.json and registers
    the Windows Task Scheduler task.
.DESCRIPTION
    Run once after git clone. Safe to re-run (idempotent).
    Does NOT require Administrator — registers task for current user only.
#>

$ErrorActionPreference = "Stop"
$RepoDir = $PSScriptRoot

Write-Host ""
Write-Host "=== screencap setup ===" -ForegroundColor Cyan
Write-Host ""

# ── 1. Locate pythonw.exe ─────────────────────────────────────────────────────
$pythonw = $null

# Try common install locations
$candidates = @(
    "$env:LOCALAPPDATA\Programs\Python\Python313\pythonw.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\pythonw.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\pythonw.exe"
)
foreach ($c in $candidates) {
    if (Test-Path $c) { $pythonw = $c; break }
}

# Try PATH
if (-not $pythonw) {
    $found = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($found) { $pythonw = $found.Source }
}

if (-not $pythonw) {
    $pythonw = Read-Host "pythonw.exe not found automatically. Enter full path"
}

if (-not (Test-Path $pythonw)) {
    Write-Error "pythonw.exe not found at: $pythonw"
    exit 1
}
Write-Host "  pythonw.exe : $pythonw" -ForegroundColor Green

# ── 2. Locate Copilot CLI npm-loader.js ──────────────────────────────────────
$loader = "$env:APPDATA\npm\node_modules\@github\copilot\npm-loader.js"
if (-not (Test-Path $loader)) {
    $loader = Read-Host "Copilot npm-loader.js not found at default path. Enter full path"
}
if (-not (Test-Path $loader)) {
    Write-Error "Copilot npm-loader.js not found at: $loader"
    exit 1
}
Write-Host "  copilot     : $loader" -ForegroundColor Green

# ── 3. Prompt for paths ───────────────────────────────────────────────────────
Write-Host ""
Write-Host "Configure paths (press Enter to accept default):" -ForegroundColor Yellow

$defaultWatch = "C:\Users\$env:USERNAME\OneDrive\Pictures\Screenshots"
$input = Read-Host "  Screenshot watch folder [$defaultWatch]"
$watchDir = if ($input) { $input } else { $defaultWatch }

$defaultOut = "$watchDir\Organized"
$input = Read-Host "  Organized output folder [$defaultOut]"
$outputDir = if ($input) { $input } else { $defaultOut }

# ── 4. Choose model ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Available models:" -ForegroundColor Yellow
Write-Host "    gpt-5.4              (default — uses GitHub Copilot subscription)"
Write-Host "    gemini-3-pro-preview"
Write-Host "    claude-haiku-4.5"
Write-Host "    claude-sonnet-4.6"
$input = Read-Host "  Model [gpt-5.4]"
$model = if ($input) { $input } else { "gpt-5.4" }

# ── 5. Write config.json ──────────────────────────────────────────────────────
$config = [ordered]@{
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

$configJson = $config | ConvertTo-Json -Depth 3
$configPath = "$RepoDir\config.json"
$configJson | Set-Content -Path $configPath -Encoding UTF8
Write-Host ""
Write-Host "  config.json written to: $configPath" -ForegroundColor Green

# ── 6. Create directories ─────────────────────────────────────────────────────
$dirs = @(
    $watchDir,
    $outputDir,
    "$RepoDir\metadata",
    "$RepoDir\logs"
)
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
        Write-Host "  created: $d" -ForegroundColor DarkGray
    }
}

# ── 7. Register scheduled task ────────────────────────────────────────────────
Write-Host ""
Write-Host "Registering scheduled task..." -ForegroundColor Yellow

# Use XML registration to avoid PowerShell 5.1 vs 7 trigger serialization differences.
# Omitting <Duration> inside <Repetition> means the task repeats indefinitely.
$startTime = (Get-Date).AddMinutes(1).ToString("yyyy-MM-ddTHH:mm:ss")
$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>screencap: monitors screenshots, analyzes via Copilot CLI, organizes by category</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <Repetition>
        <Interval>PT2M</Interval>
      </Repetition>
      <StartBoundary>$startTime</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$pythonw</Command>
      <Arguments>"$RepoDir\main.py"</Arguments>
      <WorkingDirectory>$RepoDir</WorkingDirectory>
    </Exec>
  </Actions>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
</Task>
"@

Register-ScheduledTask -TaskName "ScreencapMonitor" -Xml $taskXml -Force | Out-Null

if (Get-ScheduledTask -TaskName "ScreencapMonitor" -ErrorAction SilentlyContinue) {
    Write-Host "  task registered: ScreencapMonitor (every 2 minutes)" -ForegroundColor Green
} else {
    Write-Error "Failed to register scheduled task."
    exit 1
}

# ── 8. Dry-run verification ───────────────────────────────────────────────────
Write-Host ""
Write-Host "Running dry-run to verify config..." -ForegroundColor Yellow
& $pythonw "$RepoDir\main.py" --dry-run

$logFile = "$RepoDir\logs\screencap.log"
if (Test-Path $logFile) {
    Write-Host ""
    Write-Host "Last log entry:" -ForegroundColor DarkGray
    Get-Content $logFile | Select-Object -Last 3 | ForEach-Object {
        Write-Host "  $_" -ForegroundColor DarkGray
    }
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Setup complete." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Watch folder  : $watchDir"
Write-Host "  Output folder : $outputDir"
Write-Host "  Model         : $model"
Write-Host "  Logs          : $RepoDir\logs\screencap.log"
Write-Host ""
Write-Host "The task runs every 2 minutes silently in the background."
Write-Host "To check status:  Get-ScheduledTask -TaskName ScreencapMonitor"
Write-Host "To pause:         Disable-ScheduledTask -TaskName ScreencapMonitor"
Write-Host "To uninstall:     powershell -File remove_task.ps1"
Write-Host "To test manually: python main.py --dry-run"
Write-Host ""
