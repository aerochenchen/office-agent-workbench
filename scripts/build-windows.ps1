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
  -MsixStore creates a Store-identity MSIX from Package.store.appxmanifest.

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
    [switch]$Msix,
    [switch]$MsixStore,
    [string]$StorePackageName = "",
    [string]$StorePublisher = "",
    [string]$StorePublisherDisplayName = "",
    [string]$StoreVersion = "0.1.0.0"
)

if ($MicrosoftStore -and $Msix) {
    throw "-Msix cannot be combined with -MicrosoftStore"
}
if ($MsixStore -and $Msix) {
    throw "-MsixStore cannot be combined with -Msix"
}
if ($MsixStore -and $MicrosoftStore) {
    throw "-MsixStore cannot be combined with -MicrosoftStore"
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

function Stage-MsixPayload {
    Write-Step "Stage MSIX payload"

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

    # Nest under App\ so package-root "resources/" does not collide with
    # MakeAppx-generated resources.pri (common 0x8007007b failure mode).
    # MakeAppx also rejects non-ASCII filenames — stage as Wenshutong.exe.
    $appDir = Join-Path $MsixPayloadDir "App"
    New-Item -ItemType Directory -Path $appDir -Force | Out-Null
    $stagedMainExe = Join-Path $appDir "Wenshutong.exe"
    Copy-Item -Path $mainExe -Destination $stagedMainExe -Force
    Write-Host "Staged main exe as App\Wenshutong.exe (from $mainExe)"

    # Copy the full staged resources tree next to the exe (runtime/ + bundled/).
    Copy-Item -Path $ResourcesDir -Destination (Join-Path $appDir "resources") -Recurse -Force

    # MakeAppx rejects non-ASCII payload paths (0x8007007b). Skill fixture
    # samples use Chinese filenames; strip fixtures/ from the MSIX payload
    # (not needed at runtime — only for skill self-tests).
    $bundledRoot = Join-Path $appDir "resources\bundled"
    if (Test-Path $bundledRoot) {
        Get-ChildItem -Path $bundledRoot -Recurse -Directory -Filter "fixtures" -ErrorAction SilentlyContinue |
            ForEach-Object {
                Write-Host "Removing MSIX-incompatible fixtures: $($_.FullName)"
                Remove-Item -LiteralPath $_.FullName -Recurse -Force
            }
    }

    # MakeAppx 0x8007007b: payload filenames must not contain OPC/Appx-illegal
    # characters. PyInstaller ships python-docx's unpacked template with
    # "[Content_Types].xml" — brackets collide with package OPC rules.
    # Prefer dropping the unpacked template when default.docx is present.
    $docxTemplates = Join-Path $appDir "resources\runtime\_internal\docx\templates"
    $unpackedTpl = Join-Path $docxTemplates "default-docx-template"
    $defaultDocx = Join-Path $docxTemplates "default.docx"
    if ((Test-Path $unpackedTpl) -and (Test-Path $defaultDocx)) {
        Write-Host "Removing unpacked docx template (default.docx present): $unpackedTpl"
        Remove-Item -LiteralPath $unpackedTpl -Recurse -Force
    }
    Get-ChildItem -LiteralPath $appDir -Recurse -Force -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '[\[\]<>:"|?*]' } |
        ForEach-Object {
            Write-Host "Removing MSIX-illegal filename: $($_.FullName)"
            Remove-Item -LiteralPath $_.FullName -Force
        }
    # Unused agent skill packs / placeholders under site-packages.
    Get-ChildItem -LiteralPath $appDir -Recurse -Force -Directory -Filter ".agents" -ErrorAction SilentlyContinue |
        ForEach-Object {
            Write-Host "Removing MSIX-unused dir: $($_.FullName)"
            Remove-Item -LiteralPath $_.FullName -Recurse -Force
        }
    Get-ChildItem -LiteralPath $appDir -Recurse -Force -File -Filter ".keep" -ErrorAction SilentlyContinue |
        ForEach-Object {
            Write-Host "Removing MSIX-unused file: $($_.FullName)"
            Remove-Item -LiteralPath $_.FullName -Force
        }

    # Assets stay at package root (winapp / MakeAppx convention).
    Copy-Item -Path $assetsDir -Destination (Join-Path $MsixPayloadDir "Assets") -Recurse -Force

    $stagedRuntimeExe = Join-Path $appDir "resources\runtime\office-agent-runtime.exe"
    if (-not (Test-Path $stagedRuntimeExe)) {
        throw "MSIX payload missing sidecar: $stagedRuntimeExe"
    }
}

function Invoke-WinappPack([string]$DevCert, [string]$MsixOutFile) {
    Write-Step "winapp pack"
    # Explicit ASCII --output avoids DisplayName-derived paths; collect into msix-out/.
    Push-Location $MsixPayloadDir
    try {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & winapp pack . --cert $DevCert --output $MsixOutFile
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
}

function Build-Msix {
    Write-Step "Build MSIX sideload spike"

    $winapp = Get-Command winapp -ErrorAction SilentlyContinue
    if (-not $winapp) {
        throw "winapp CLI not found on PATH. Install it with: winget install microsoft.winappcli"
    }

    $manifest = Join-Path $SrcTauri "Package.appxmanifest"
    if (-not (Test-Path $manifest)) {
        throw "Package.appxmanifest missing at $manifest"
    }
    Stage-MsixPayload

    # Manifest stays at package root (winapp / MakeAppx convention).
    Copy-Item -Path $manifest -Destination (Join-Path $MsixPayloadDir "Package.appxmanifest") -Force

    $devCert = Join-Path $MsixOutDir "devcert.pfx"
    $msixOutFile = Join-Path $MsixOutDir "Wenshutong_0.1.0.0_x64.msix"

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

    Invoke-WinappPack $devCert $msixOutFile
    Write-Host ("Dev cert: " + $devCert) -ForegroundColor Green
}

function Build-MsixStore {
    Write-Step "Build Store-identity MSIX"

    foreach ($field in @(
        @{ Name = "StorePackageName"; Value = $StorePackageName },
        @{ Name = "StorePublisher"; Value = $StorePublisher },
        @{ Name = "StorePublisherDisplayName"; Value = $StorePublisherDisplayName },
        @{ Name = "StoreVersion"; Value = $StoreVersion }
    )) {
        if ([string]::IsNullOrWhiteSpace($field.Value)) {
            throw "$($field.Name) must not be empty when using -MsixStore"
        }
    }
    if ($StoreVersion -notmatch '^\d+\.\d+\.\d+\.0$') {
        throw "StoreVersion must match x.y.z.0 (for example 0.1.0.0)"
    }

    $winapp = Get-Command winapp -ErrorAction SilentlyContinue
    if (-not $winapp) {
        throw "winapp CLI not found on PATH. Install it with: winget install microsoft.winappcli"
    }

    $storeManifest = Join-Path $SrcTauri "Package.store.appxmanifest"
    if (-not (Test-Path $storeManifest)) {
        throw "Package.store.appxmanifest missing at $storeManifest"
    }
    Stage-MsixPayload

    $manifestText = Get-Content -Path $storeManifest -Raw
    $manifestText = $manifestText.
        Replace("__STORE_PACKAGE_NAME__", $StorePackageName).
        Replace("__STORE_PUBLISHER__", $StorePublisher).
        Replace("__STORE_PUBLISHER_DISPLAY_NAME__", $StorePublisherDisplayName).
        Replace("__STORE_VERSION__", $StoreVersion)
    if ($manifestText.Contains("__STORE_")) {
        throw "Store manifest still contains unresolved __STORE_ placeholder(s)"
    }
    Set-Content -Path (Join-Path $MsixPayloadDir "Package.appxmanifest") -Value $manifestText -Encoding utf8

    Write-Host "Store Identity Name: $StorePackageName"
    Write-Host "Store Identity Publisher: $StorePublisher"
    Write-Host "Store Identity Version: $StoreVersion"

    $devCert = Join-Path $MsixOutDir "store-devcert.pfx"
    $msixOutFile = Join-Path $MsixOutDir ("Wenshutong_{0}_x64.msix" -f $StoreVersion)

    # Generate from the substituted manifest, allowing winapp to derive the
    # exact Store Publisher instead of using the spike certificate subject.
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

    Invoke-WinappPack $devCert $msixOutFile
    Write-Host ("Store dev cert: " + $devCert) -ForegroundColor Green
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
if ($MsixStore) {
    Build-MsixStore
}
