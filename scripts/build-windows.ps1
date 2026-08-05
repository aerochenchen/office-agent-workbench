<#
.SYNOPSIS
  Build the Windows NSIS installer (文书通-setup.exe).
  App / installer / desktop shortcut icons come from apps/desktop/src-tauri/icons
  (generated from apps/desktop/branding/app-icon.png via scripts/generate-app-icons.sh).

.DESCRIPTION
  1. Create/reuse a packaging venv under packaging/.venv
  2. PyInstaller onedir -> packaging/dist/office-agent-runtime
  3. Stage into apps/desktop/src-tauri/resources/{runtime,bundled}
  4. npm + tauri build (NSIS only)
  -MicrosoftStore merges tauri.microsoftstore.conf.json for store packaging.
  -Msix stages a payload (exe + resources + Package.appxmanifest + Assets)
  under packaging/msix-payload and runs `winapp cert generate` + `winapp pack`
  to produce packaging/msix-out/*.msix for the sideload spike. Mutually
  exclusive with -MicrosoftStore.

.NOTES
  Requires: Python 3.11+, Node.js/npm, Rust toolchain, WebView2 SDK bits via Tauri.
  -Msix additionally requires the `winapp` CLI on PATH (winget install microsoft.winappcli).
  Run from anywhere; script resolves the repo root from its own path.
#>
[CmdletBinding()]
param(
    [switch]$SkipSidecar,
    [switch]$SkipTauri,
    [switch]$Clean,
    [switch]$MicrosoftStore,
    [switch]$Msix
)

if ($MicrosoftStore -and $Msix) {
    throw "-Msix cannot be combined with -MicrosoftStore"
}

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
$MsixPayloadDir = Join-Path $PackagingDir "msix-payload"
$MsixOutDir = Join-Path $PackagingDir "msix-out"

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

    $noticeSrc = Join-Path $RepoRoot "NOTICE"
    if (-not (Test-Path $noticeSrc)) {
        throw "NOTICE missing at $noticeSrc — run scripts/generate_notice.sh before packaging"
    }
    Copy-Item -Path $noticeSrc -Destination (Join-Path $ResourcesDir "NOTICE") -Force

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
        $tauriArgs = @("tauri", "build")
        if ($MicrosoftStore) {
            $storeConf = Join-Path $SrcTauri "tauri.microsoftstore.conf.json"
            if (-not (Test-Path $storeConf)) {
                $ErrorActionPreference = $prevEap
                throw "Microsoft Store config missing: $storeConf"
            }
            Write-Host "Microsoft Store mode: merging $storeConf"
            $tauriArgs += @("--config", "src-tauri/tauri.microsoftstore.conf.json")
        }
        & npx --yes @tauriArgs
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

function Build-Msix {
    Write-Step "Stage MSIX payload + winapp pack"

    $winapp = Get-Command winapp -ErrorAction SilentlyContinue
    if (-not $winapp) {
        throw "winapp CLI not found on PATH. Install it with: winget install microsoft.winappcli"
    }

    $manifest = Join-Path $SrcTauri "Package.appxmanifest"
    if (-not (Test-Path $manifest)) {
        throw "Package.appxmanifest missing at $manifest"
    }
    $assetsDir = Join-Path $SrcTauri "Assets"
    if (-not (Test-Path $assetsDir)) {
        throw "Assets directory missing at $assetsDir"
    }
    if (-not (Test-Path $ResourcesDir)) {
        throw "Staged resources missing at $ResourcesDir — run without -SkipSidecar first."
    }

    # Recreate payload + out dirs from scratch for a reproducible spike build.
    foreach ($dir in @($MsixPayloadDir, $MsixOutDir)) {
        if (Test-Path $dir) {
            Remove-Item -Recurse -Force $dir
        }
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    # Locate the main product exe. Prefer the well-known productName path;
    # fall back to scanning target/release for the exe that isn't the sidecar.
    $mainExe = Join-Path $SrcTauri "target\release\文书通.exe"
    if (-not (Test-Path $mainExe)) {
        $releaseDir = Join-Path $SrcTauri "target\release"
        $candidate = Get-ChildItem -Path $releaseDir -Filter "*.exe" -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -ne "office-agent-runtime.exe" } |
            Select-Object -First 1
        if (-not $candidate) {
            throw "Could not locate main product exe under $releaseDir. Run tauri build first (drop -SkipTauri)."
        }
        $mainExe = $candidate.FullName
        Write-Host "Using fallback main exe: $mainExe"
    }

    # MakeAppx rejects non-ASCII payload filenames (文书通.exe becomes ???.exe).
    # Stage as ASCII Wenshutong.exe to match Package.appxmanifest Executable.
    $stagedMainExe = Join-Path $MsixPayloadDir "Wenshutong.exe"
    Copy-Item -Path $mainExe -Destination $stagedMainExe -Force
    Write-Host "Staged main exe as Wenshutong.exe (from $mainExe)"

    # Copy the full staged resources tree (runtime/ + bundled/), required by
    # the app at runtime — not just the single exe.
    Copy-Item -Path $ResourcesDir -Destination (Join-Path $MsixPayloadDir "resources") -Recurse -Force

    # Copy manifest + Assets alongside the payload so winapp pack can read
    # them from the same directory it packs.
    Copy-Item -Path $manifest -Destination (Join-Path $MsixPayloadDir "Package.appxmanifest") -Force
    Copy-Item -Path $assetsDir -Destination (Join-Path $MsixPayloadDir "Assets") -Recurse -Force

    $stagedRuntimeExe = Join-Path $MsixPayloadDir "resources\runtime\office-agent-runtime.exe"
    if (-not (Test-Path $stagedRuntimeExe)) {
        throw "MSIX payload missing sidecar: $stagedRuntimeExe"
    }

    $devCert = Join-Path $MsixOutDir "devcert.pfx"

    # Same stderr-vs-Stop trap as Build-Sidecar / Build-Tauri: preview CLIs
    # often write progress to stderr; with $ErrorActionPreference=Stop that
    # becomes a terminating NativeCommandError even on success.
    Write-Step "winapp cert generate"
    Push-Location $MsixPayloadDir
    try {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & winapp cert generate --if-exists skip --output $devCert
        $certExit = $LASTEXITCODE
        $ErrorActionPreference = $prevEap
        if ($certExit -ne 0) { throw "winapp cert generate failed with exit $certExit" }
    }
    finally {
        Pop-Location
    }

    Write-Step "winapp pack"
    # winapp pack --output expects an MSIX filename, not a directory. Omit it,
    # run from the payload dir, then collect any new *.msix into msix-out/.
    Push-Location $MsixPayloadDir
    try {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & winapp pack . --cert $devCert
        $packExit = $LASTEXITCODE
        $ErrorActionPreference = $prevEap
        if ($packExit -ne 0) { throw "winapp pack failed with exit $packExit" }

        Get-ChildItem -Path . -Filter "*.msix" -ErrorAction SilentlyContinue | ForEach-Object {
            Move-Item -Path $_.FullName -Destination $MsixOutDir -Force
        }
    }
    finally {
        Pop-Location
    }

    $msixFiles = Get-ChildItem -Path $MsixOutDir -Filter "*.msix" -ErrorAction SilentlyContinue
    if (-not $msixFiles) {
        throw "winapp pack reported success but no .msix found in $MsixOutDir"
    }
    foreach ($f in $msixFiles) {
        Write-Host ("MSIX package: " + $f.FullName) -ForegroundColor Green
    }
    Write-Host ("Dev cert: " + $devCert) -ForegroundColor Green
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

if ($Msix) {
    Build-Msix
}
