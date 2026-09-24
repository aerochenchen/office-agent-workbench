# Sign the shell and sidecar after they are built and before NSIS packs them.
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Release = Join-Path $Root "apps\desktop\src-tauri\target\release"
$files = @()
foreach ($name in @("文书通.exe", "desktop.exe")) {
    $path = Join-Path $Release $name
    if (Test-Path -LiteralPath $path) { $files += $path }
}
$runtime = Join-Path $Root "apps\desktop\src-tauri\resources\runtime\office-agent-runtime.exe"
if (Test-Path -LiteralPath $runtime) { $files += $runtime }
if ($files.Count -eq 0) {
    throw "No Windows binaries found to sign before bundling."
}
& (Join-Path $PSScriptRoot "sign-windows.ps1") -Files $files
exit $LASTEXITCODE
