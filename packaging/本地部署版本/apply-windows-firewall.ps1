# Optional: block outbound traffic from script helper processes.
# The desktop runtime itself must still reach the intranet model host.
# Run in an elevated PowerShell. Adjust -Program if the install path differs.

$ErrorActionPreference = "Stop"
$program = Join-Path ${env:LOCALAPPDATA} "文书通\resources\runtime\office-agent-runtime.exe"
if (-not (Test-Path $program)) {
    $program = Join-Path ${env:ProgramFiles} "文书通\resources\runtime\office-agent-runtime.exe"
}
if (-not (Test-Path $program)) {
    throw "Cannot find office-agent-runtime.exe. Pass -Program explicitly after editing this script."
}

# Block all outbound from the sidecar, then allow loopback/private ranges.
# Review before applying on a machine that also uses the same exe for model HTTP.
New-NetFirewallRule -DisplayName "文书通-本地部署-脚本出站默认拒绝" `
    -Direction Outbound -Program $program -Action Block -Profile Any -ErrorAction SilentlyContinue | Out-Null

Write-Host "Added outbound block for $program"
Write-Host "If chat cannot reach the local model, delete this rule or add an allow rule for the model host."
