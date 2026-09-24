# Sign Windows release binaries with an Authenticode certificate.
# Requires a PFX that chains to the Microsoft Trusted Root Program.
# A Microsoft Store MSIX test certificate cannot be used here.
param(
    [Parameter(Mandatory = $true)]
    [string[]]$Files
)

$ErrorActionPreference = "Stop"

$pfx = $env:WENSHUTONG_SIGN_PFX
if ([string]::IsNullOrWhiteSpace($pfx)) {
    Write-Host "WENSHUTONG_SIGN_PFX is not set; leaving binaries unsigned."
    exit 0
}
if (-not (Test-Path -LiteralPath $pfx)) {
    throw "Signing certificate not found: $pfx"
}

$signtoolPath = $null
$signtoolCmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
if ($signtoolCmd) { $signtoolPath = $signtoolCmd.Source }
if (-not $signtoolPath) {
    $kits = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Select-Object -First 1
    if ($kits) { $signtoolPath = $kits.FullName }
}
if (-not $signtoolPath) {
    throw "signtool.exe was not found. Install the Windows SDK signing tools."
}

$password = $env:WENSHUTONG_SIGN_PASSWORD
$existing = @()
foreach ($file in $Files) {
    if (Test-Path -LiteralPath $file) { $existing += $file }
}
if ($existing.Count -eq 0) {
    throw "No files to sign."
}

$args = @(
    "sign",
    "/fd", "SHA256",
    "/td", "SHA256",
    "/tr", "http://timestamp.digicert.com",
    "/f", $pfx
)
if (-not [string]::IsNullOrWhiteSpace($password)) {
    $args += @("/p", $password)
}
$args += $existing

& $signtoolPath @args
if ($LASTEXITCODE -ne 0) {
    throw "signtool failed with exit $LASTEXITCODE"
}
Write-Host "Signed $($existing.Count) file(s)."
