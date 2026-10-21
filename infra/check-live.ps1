<#
.SYNOPSIS
  Check the public endpoints of the three apps on the Docker host. Exit code 1 if any check fails.
.DESCRIPTION
  Used for listing 23, on the evening before the live grading and on its morning.
.EXAMPLE
  .\infra\check-live.ps1 -Listing 23-url-checks.txt
#>
param([string]$Listing)
. "$PSScriptRoot\config.ps1"

function Test-Url {
    param([string]$Url, [string]$Expect, [int]$Lines = 12)
    Write-Step "PS> curl.exe -si $Url"
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $out = @(& curl.exe -si --max-time 15 $Url 2>&1 | ForEach-Object { "$_" }) } finally { $ErrorActionPreference = $saved }
    $out | Select-Object -First $Lines | ForEach-Object { Write-Step $_ }
    if ($out.Count -gt $Lines) { Write-Step "... ($($out.Count - $Lines) more lines)" }
    $ok = ($out.Count -gt 0) -and ($out[0] -match '^HTTP/\S+ 200') -and (($out -join "`n").Contains($Expect))
    Write-Step $(if ($ok) { 'check: OK' } else { "check: FAILED (expected 200 and '$Expect')" })
    Write-Step ''
    return $ok
}

function Test-Banner {
    param([string]$HostName, [int]$Port)
    Write-Step "PS> first line from ${HostName}:$Port (TCP)"
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.ReceiveTimeout = 10000
        $client.Connect($HostName, $Port)
        $reader = New-Object System.IO.StreamReader($client.GetStream(), (New-Object System.Text.UTF8Encoding($false)))
        $line = $reader.ReadLine()
        $client.Close()
    } catch {
        $line = "error: $($_.Exception.Message)"
    }
    Write-Step $line
    $ok = "$line".StartsWith('CONNECT FOUR')
    Write-Step $(if ($ok) { 'check: OK' } else { "check: FAILED (expected a line starting with 'CONNECT FOUR')" })
    Write-Step ''
    return $ok
}

$ip = $null
$failed = 0
try {
    $ip = Get-PublicIp
    if (-not $ip) { throw "$StackName has no PublicIp output." }
    Write-Step ("Endpoint checks, {0:yyyy-MM-dd HH:mm} UTC" -f (Get-Date).ToUniversalTime())
    Write-Step ''
    $results = @(
        (Test-Url "http://${ip}:4000/" 'Hello'),
        (Test-Url "http://${ip}/" 'Quick Poll'),
        (Test-Url "http://${ip}/readyz" '"status":"ok"'),
        (Test-Banner $ip 2323)
    )
    $failed = @($results | Where-Object { -not $_ }).Count
    Write-Step ("{0} of {1} checks passed" -f ($results.Count - $failed), $results.Count)
}
finally {
    Save-Listing $Listing $ip
}
if ($failed) { exit 1 }
