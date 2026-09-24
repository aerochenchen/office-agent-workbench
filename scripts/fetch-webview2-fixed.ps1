<#
.SYNOPSIS
  Download and extract WebView2 Fixed Version Runtime for LocalDeploy builds.

.DESCRIPTION
  Evergreen offlineInstaller still goes through Edge Update and can fail on
  intranet Win10 with HRESULT 0xA043050D (-1606220531). Fixed Version ships
  the runtime beside the app and never runs the system WebView2 installer.
#>
[CmdletBinding()]
param(
    [string]$Version = "151.0.4129.107",
    [string]$OutRoot = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if ([string]::IsNullOrWhiteSpace($OutRoot)) {
    $OutRoot = Join-Path $RepoRoot "apps\desktop\src-tauri\webview2-runtime"
}

$FolderName = "Microsoft.WebView2.FixedVersionRuntime.$Version.x64"
$DestDir = Join-Path $OutRoot $FolderName
$Marker = Join-Path $DestDir "msedgewebview2.exe"
if (Test-Path $Marker) {
    Write-Host "WebView2 Fixed Runtime already present: $DestDir"
    return
}

$NupkgName = "webview2.runtime.x64.$Version.nupkg"
$NupkgPath = Join-Path $env:TEMP $NupkgName
$Url = "https://api.nuget.org/v3-flatcontainer/webview2.runtime.x64/$Version/webview2.runtime.x64.$Version.nupkg"

Write-Host "Downloading WebView2 Fixed Runtime $Version ..."
Write-Host "  $Url"
Invoke-WebRequest -Uri $Url -OutFile $NupkgPath -UseBasicParsing

if (Test-Path $OutRoot) {
    Remove-Item -Recurse -Force $OutRoot
}
New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

$ExtractTmp = Join-Path $env:TEMP ("webview2-fixed-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $ExtractTmp -Force | Out-Null
try {
    Write-Host "Extracting nupkg -> $ExtractTmp"
    Copy-Item -Path $NupkgPath -Destination (Join-Path $ExtractTmp "runtime.zip")
    Expand-Archive -Path (Join-Path $ExtractTmp "runtime.zip") -DestinationPath $ExtractTmp -Force

    $found = Get-ChildItem -Path $ExtractTmp -Recurse -Filter "msedgewebview2.exe" |
        Select-Object -First 1
    if (-not $found) {
        throw "msedgewebview2.exe not found after extracting $NupkgName"
    }
    $runtimeRoot = $found.Directory.FullName
    New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
    Copy-Item -Path (Join-Path $runtimeRoot "*") -Destination $DestDir -Recurse -Force
}
finally {
    Remove-Item -Recurse -Force $ExtractTmp -ErrorAction SilentlyContinue
    Remove-Item -Force $NupkgPath -ErrorAction SilentlyContinue
}

if (-not (Test-Path $Marker)) {
    throw "Fixed Runtime staging failed: missing $Marker"
}
Write-Host "Staged Fixed Runtime -> $DestDir"
