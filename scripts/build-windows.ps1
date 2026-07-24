<#
.SYNOPSIS
  Build the Windows NSIS installer (办公智能体工作台-setup.exe).

.DESCRIPTION
  1. Create/reuse a packaging venv under packaging/.venv
  2. PyInstaller onedir -> packaging/dist/office-agent-runtime
  3. Stage into apps/desktop/src-tauri/resources/{runtime,bundled}
  4. npm + tauri build (NSIS only)

.NOTES
  Requires: Python 3.11+, Node.js/npm, Rust toolchain, WebView2 SDK bits via Tauri.
  Run from anywhere; script resolves the repo root from its own path.
#>
[CmdletBinding()]
param(
    [switch]$SkipSidecar,
    [switch]$SkipTauri,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PackagingDir = Join-Path $RepoRoot "packaging"
$RuntimeDir = Join-Path $RepoRoot "runtime"
$DesktopDir = Join-Path $RepoRoot "apps\desktop"
$SrcTauri = Join-Path $DesktopDir "src-tauri"
$ResourcesDir = Join-Path $SrcTauri "resources"
$VenvDir = Join-Path $PackagingDir ".venv"
$DistRuntime = Join-Path $PackagingDir "dist\office-agent-runtime"
$StagedRuntime = Join-Path $ResourcesDir "runtime"
$StagedBundled = Join-Path $ResourcesDir "bundled"
$BundledSrc = Join-Path $RepoRoot "bundled"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Ensure-Python {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) {
        throw "Python not found on PATH. Install Python 3.11+ and retry."
    }
    & python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.11+ required."
    }
}

function Ensure-Venv {
    if ($Clean -and (Test-Path $VenvDir)) {
        Write-Step "Removing packaging/.venv"
        Remove-Item -Recurse -Force $VenvDir
    }
    if (-not (Test-Path (Join-Path $VenvDir "Scripts\python.exe"))) {
        Write-Step "Creating packaging/.venv"
        & python -m venv $VenvDir
    }
    $script:VenvPython = Join-Path $VenvDir "Scripts\python.exe"
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -e "$RuntimeDir[packaging]"
    # python-docx is in requirements.txt for light format skill scripts
    $req = Join-Path $RuntimeDir "requirements.txt"
    if (Test-Path $req) {
        & $VenvPython -m pip install -r $req
    }
}

function Build-Sidecar {
    Write-Step "PyInstaller onedir (office-agent-runtime)"
    if ($Clean) {
        $buildDir = Join-Path $PackagingDir "build"
        $distDir = Join-Path $PackagingDir "dist"
        if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir }
        if (Test-Path $distDir) { Remove-Item -Recurse -Force $distDir }
    }
    Push-Location $PackagingDir
    try {
        # PyInstaller logs INFO to stderr; with ErrorActionPreference=Stop that
        # becomes a terminating NativeCommandError even on success.
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $VenvPython -m PyInstaller (Join-Path $PackagingDir "runtime.spec") --noconfirm --clean
        $pyiExit = $LASTEXITCODE
        $ErrorActionPreference = $prevEap
        if ($pyiExit -ne 0) { throw "PyInstaller failed with exit $pyiExit" }
    }
    finally {
        Pop-Location
    }
    $exe = Join-Path $DistRuntime "office-agent-runtime.exe"
    if (-not (Test-Path $exe)) {
        throw "Sidecar exe missing: $exe"
    }
}

function Stage-Resources {
    Write-Step "Staging Tauri resources"
    # Only replace staged trees — keep resources/README.md and .gitignore
    foreach ($dir in @($StagedRuntime, $StagedBundled)) {
        if (Test-Path $dir) {
            Remove-Item -Recurse -Force $dir
        }
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    Copy-Item -Path (Join-Path $DistRuntime "*") -Destination $StagedRuntime -Recurse -Force
    if (-not (Test-Path $BundledSrc)) {
        throw "bundled/ source missing at $BundledSrc"
    }
    Copy-Item -Path (Join-Path $BundledSrc "*") -Destination $StagedBundled -Recurse -Force

    $stagedExe = Join-Path $StagedRuntime "office-agent-runtime.exe"
    if (-not (Test-Path $stagedExe)) {
        throw "Staged sidecar missing: $stagedExe"
    }
    Write-Host "Staged runtime -> $StagedRuntime"
    Write-Host "Staged bundled -> $StagedBundled"
}

function Build-Tauri {
    Write-Step "npm install + tauri build (NSIS)"
    Push-Location $DesktopDir
    try {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        if (-not (Test-Path (Join-Path $DesktopDir "node_modules\@tauri-apps\cli"))) {
            & npm install
            if ($LASTEXITCODE -ne 0) {
                $ErrorActionPreference = $prevEap
                throw "npm install failed"
            }
        }
        & npx --yes tauri build
        $tauriExit = $LASTEXITCODE
        $ErrorActionPreference = $prevEap
        if ($tauriExit -ne 0) { throw "tauri build failed with exit $tauriExit" }
    }
    finally {
        Pop-Location
    }

    $nsisDir = Join-Path $SrcTauri "target\release\bundle\nsis"
    Write-Step "Done"
    if (Test-Path $nsisDir) {
        Get-ChildItem $nsisDir -Filter "*.exe" | ForEach-Object {
            Write-Host ("Installer: " + $_.FullName) -ForegroundColor Green
        }
    }
    else {
        Write-Host "NSIS output folder not found at $nsisDir (check tauri build logs)." -ForegroundColor Yellow
    }
}

Ensure-Python
if (-not $SkipSidecar) {
    Ensure-Venv
    Build-Sidecar
    Stage-Resources
}
elseif (-not (Test-Path (Join-Path $StagedRuntime "office-agent-runtime.exe"))) {
    throw "SkipSidecar set but staged runtime missing. Run without -SkipSidecar first."
}

if (-not $SkipTauri) {
    Build-Tauri
}
else {
    Write-Step "SkipTauri: resources staged only"
    Write-Host "Staged at $ResourcesDir"
}
