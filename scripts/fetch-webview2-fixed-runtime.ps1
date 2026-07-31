<#
.SYNOPSIS
  Download and extract Microsoft Edge WebView2 Fixed Version Runtime (x64)
  into apps/desktop/src-tauri/webview2-fixed for Tauri fixedRuntime bundling.

.NOTES
  Pin version/url/hash below when bumping. Cab is ~280MB; extracted folder is larger.
  On Windows use expand.exe; this script also runs on GitHub Actions windows-latest.
#>
[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Pinned Fixed Version (x64). Bump together when updating.
$RuntimeVersion = "150.0.4078.105"
$CabUrl = "https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/b401c036-cfb8-4dc4-a58e-8766441df4ac/Microsoft.WebView2.FixedVersionRuntime.150.0.4078.105.x64.cab"
$CabSha256 = "26c07cad95615a672cde8c1843a326e18ad25d691f004347544e5e099bff9b92"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$SrcTauri = Join-Path $RepoRoot "apps\desktop\src-tauri"
$DestDir = Join-Path $SrcTauri "webview2-fixed"
$Marker = Join-Path $DestDir ".webview2-fixed-version"
$WorkDir = Join-Path $RepoRoot "packaging\webview2-fixed-download"
$CabPath = Join-Path $WorkDir "Microsoft.WebView2.FixedVersionRuntime.$RuntimeVersion.x64.cab"
$ExpandDir = Join-Path $WorkDir "expand"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

if ((Test-Path $Marker) -and -not $Force) {
    $existing = (Get-Content -Path $Marker -Raw).Trim()
    if ($existing -eq $RuntimeVersion) {
        $exe = Get-ChildItem -Path $DestDir -Filter "msedgewebview2.exe" -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($exe) {
            Write-Host "WebView2 Fixed Runtime $RuntimeVersion already present at $DestDir"
            exit 0
        }
    }
}

Write-Step "Preparing WebView2 Fixed Runtime $RuntimeVersion"
New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null
if (Test-Path $ExpandDir) {
    Remove-Item -Recurse -Force $ExpandDir
}
New-Item -ItemType Directory -Path $ExpandDir -Force | Out-Null

if (-not (Test-Path $CabPath) -or $Force) {
    Write-Step "Downloading Fixed Version cab (~280MB)"
    # BITS / Invoke-WebRequest can be slow; curl.exe is available on windows-latest.
    & curl.exe -L --fail --retry 3 --retry-delay 5 -o $CabPath $CabUrl
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to download WebView2 Fixed Runtime cab (exit $LASTEXITCODE)"
    }
}

Write-Step "Verifying SHA256"
$actual = (Get-FileHash -Path $CabPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $CabSha256.ToLowerInvariant()) {
    throw "SHA256 mismatch for WebView2 cab. Expected $CabSha256, got $actual"
}

Write-Step "Expanding cab with expand.exe"
& expand.exe -F:* $CabPath $ExpandDir | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "expand.exe failed with exit $LASTEXITCODE"
}

$inner = Get-ChildItem -Path $ExpandDir -Directory |
    Where-Object { $_.Name -like "Microsoft.WebView2.FixedVersionRuntime.*" } |
    Select-Object -First 1
if (-not $inner) {
    # Some cabs expand files flat or under a single root without the expected name.
    $probe = Get-ChildItem -Path $ExpandDir -Filter "msedgewebview2.exe" -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $probe) {
        throw "Expanded cab missing msedgewebview2.exe under $ExpandDir"
    }
    $sourceRoot = $probe.Directory.FullName
}
else {
    $sourceRoot = $inner.FullName
    $probe = Get-ChildItem -Path $sourceRoot -Filter "msedgewebview2.exe" -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $probe) {
        throw "Fixed Runtime folder missing msedgewebview2.exe: $sourceRoot"
    }
}

Write-Step "Staging to $DestDir"
if (Test-Path $DestDir) {
    Remove-Item -Recurse -Force $DestDir
}
New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
Copy-Item -Path (Join-Path $sourceRoot "*") -Destination $DestDir -Recurse -Force
Set-Content -Path $Marker -Value $RuntimeVersion -NoNewline

$finalExe = Get-ChildItem -Path $DestDir -Filter "msedgewebview2.exe" -Recurse |
    Select-Object -First 1
if (-not $finalExe) {
    throw "Staging failed: msedgewebview2.exe not found in $DestDir"
}

Write-Host ("WebView2 Fixed Runtime ready: {0} ({1})" -f $DestDir, $RuntimeVersion) -ForegroundColor Green
