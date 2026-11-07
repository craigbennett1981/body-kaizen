# Body Kaizen installer for Windows (PowerShell).
#
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/craigbennett1981/body-kaizen/main/install/install.ps1 | iex"
#
# It installs uv (a small tool that fetches its own Python, so you don't need one), installs Body Kaizen with the
# Garmin and LibreLinkUp syncs, starts the dashboard when you sign in to Windows, adds "Body Kaizen" to the Start
# menu, and opens the dashboard in your browser, signed in. Your data folder is chosen on that first page.
#
# Again later to update. To remove (your data folder and ~\.body-kaizen are left alone): set $env:BK_UNINSTALL=1 first.
# Settings, for testing: BK_SOURCE (what to install), BK_PORT (default 8765), BK_NO_SERVICE=1, BK_NO_OPEN=1
# 'Continue', not 'Stop': in Windows PowerShell 5.1 a native command writing to stderr would otherwise abort the script.
# Each step checks its own result instead.
$ErrorActionPreference = 'Continue'
$Repo = 'https://github.com/craigbennett1981/body-kaizen'
$Port = if ($env:BK_PORT) { $env:BK_PORT } else { '8765' }
$Task = 'Body Kaizen dashboard'
$Home_ = Join-Path $env:LOCALAPPDATA 'BodyKaizen'                 # launcher scripts and the icon
$StartMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'Body Kaizen.lnk'
function Say($m) { Write-Host $m -ForegroundColor Cyan }

$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"

if ($env:BK_UNINSTALL) {
  Unregister-ScheduledTask -TaskName $Task -Confirm:$false -ErrorAction SilentlyContinue
  Get-CimInstance Win32_Process -Filter "Name='body-kaizen.exe'" -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Remove-Item $StartMenu, $Home_ -Recurse -Force -ErrorAction SilentlyContinue
  if (Get-Command uv -ErrorAction SilentlyContinue) { uv tool uninstall body-kaizen 2>$null }
  Say 'Body Kaizen removed. Your data folder and ~\.body-kaizen (settings, sign-in key) are still there.'
  return
}

# ---------- 1. uv ----------
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Say 'Installing uv (it brings its own Python)...'
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" | Out-Null
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'uv was installed but is not on PATH: open a new PowerShell window and run this again.' }

# ---------- 2. Body Kaizen (PyPI when it's there, else the latest code on GitHub; Python 3.12 for the Garmin sync) ----------
Say 'Installing Body Kaizen...'
if ($env:BK_SOURCE) {
  $src = $env:BK_SOURCE
  if (Test-Path $src -PathType Container) { $src = ([Uri](Resolve-Path $src).Path).AbsoluteUri }
  uv tool install --force --python 3.12 "body-kaizen[all] @ $src"; if ($LASTEXITCODE) { throw "couldn't install from $src" }
} else {
  uv tool install --force --python 3.12 'body-kaizen[all]' 2>$null
  if ($LASTEXITCODE) { uv tool install --force --python 3.12 "body-kaizen[all] @ $Repo/archive/refs/heads/main.zip"; if ($LASTEXITCODE) { throw "couldn't install Body Kaizen" } }
}
$Bin = (uv tool dir --bin).Trim()
$Bk = Join-Path $Bin 'body-kaizen.exe'
if (-not (Test-Path $Bk)) { throw 'installed, but body-kaizen.exe was not found' }
& $Bk --version

# ---------- 3. small hidden launchers: no console window flashing up ----------
New-Item -ItemType Directory -Force $Home_ | Out-Null
@"
CreateObject("WScript.Shell").Run """$Bk"" serve --no-browser --port $Port", 0, False
"@ | Set-Content -Encoding ASCII (Join-Path $Home_ 'serve.vbs')
@"
CreateObject("WScript.Shell").Run """$Bk"" open --port $Port", 0, False
"@ | Set-Content -Encoding ASCII (Join-Path $Home_ 'open.vbs')
try { Invoke-WebRequest "$Repo/raw/main/install/icon.ico" -OutFile (Join-Path $Home_ 'icon.ico') -UseBasicParsing } catch {}

function Up { try { Invoke-WebRequest "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 2 | Out-Null; $true } catch { [bool]$_.Exception.Response } }

# ---------- 4. start at sign-in ----------
if (-not $env:BK_NO_SERVICE) {
  Unregister-ScheduledTask -TaskName $Task -Confirm:$false -ErrorAction SilentlyContinue
  Get-CimInstance Win32_Process -Filter "Name='body-kaizen.exe'" -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep 2
  if (Up) { throw "something else is already using port $Port. Stop it, or set `$env:BK_PORT=8766 and run this again." }
  $action = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument "`"$(Join-Path $Home_ 'serve.vbs')`""
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
  Register-ScheduledTask -TaskName $Task -Action $action -Trigger $trigger -Settings $settings -Description "Body Kaizen dashboard on http://127.0.0.1:$Port" -ErrorAction Stop | Out-Null
  Start-ScheduledTask -TaskName $Task -ErrorAction Stop
}

# ---------- 5. Start menu: opens the dashboard signed in (reads the key when clicked; never stores it) ----------
$sh = (New-Object -ComObject WScript.Shell).CreateShortcut($StartMenu)
$sh.TargetPath = 'wscript.exe'; $sh.Arguments = "`"$(Join-Path $Home_ 'open.vbs')`""
$sh.Description = 'Your private health dashboard'
if (Test-Path (Join-Path $Home_ 'icon.ico')) { $sh.IconLocation = Join-Path $Home_ 'icon.ico' }
$sh.Save(); if (-not (Test-Path $StartMenu)) { throw "couldn't create the Start menu shortcut" }

# ---------- 6. open it, signed in ----------
if (-not $env:BK_NO_SERVICE -and -not $env:BK_NO_OPEN) {
  for ($i = 0; $i -lt 60 -and -not (Up); $i++) { Start-Sleep -Milliseconds 500 }
  & $Bk open --port $Port
}

Say 'Body Kaizen is installed.'
Write-Host "  Dashboard:  http://127.0.0.1:$Port  (it starts when you sign in to Windows)"
Write-Host '  Launcher:   Body Kaizen in the Start menu: it opens the dashboard signed in, in any browser'
Write-Host "  Next:       set up your AI assistant: $Repo#quick-start"
