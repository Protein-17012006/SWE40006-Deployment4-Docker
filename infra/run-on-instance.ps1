<#
.SYNOPSIS
  Run a bash script on the Docker host through SSM Run Command (no SSH) and print its output.
.DESCRIPTION
  Each script line is echoed first, prefixed with "$ ", like a terminal session. -HideScript skips that,
  for scripts that echo their own commands (deploy-app.ps1).
.EXAMPLE
  .\infra\run-on-instance.ps1 -Command "sudo docker ps" -Listing 09-ec2-manual-docker.txt
#>
param(
    [Parameter(Mandatory)][string]$Command,
    [string]$Listing,
    [int]$TimeoutSeconds = 600,
    [switch]$HideScript
)
. "$PSScriptRoot\config.ps1"

$paramFile = Join-Path ([IO.Path]::GetTempPath()) ("a4-ssm-" + [guid]::NewGuid().ToString() + '.json')
$keepIp = $null
try {
    $outputs = Get-StackOutputs
    $instanceId = $outputs['InstanceId']
    $keepIp = $outputs['PublicIp']

    # The parameters go through a file: Windows PowerShell 5.1 mangles quotes in native arguments.
    $payload = @{ commands = @(ConvertTo-SsmCommands $Command); executionTimeout = @("$TimeoutSeconds") }
    [IO.File]::WriteAllText($paramFile, (ConvertTo-Json -InputObject $payload -Depth 3),
                            (New-Object System.Text.UTF8Encoding($false)))

    Write-Step "Session on $instanceId (Amazon Linux 2023 Docker host), via SSM Run Command:"
    if (-not $HideScript) {
        foreach ($line in ($Command -split "`r?`n" | Where-Object { $_.Trim() })) { Write-Step "`$ $line" }
    }
    $sent = Invoke-AwsJson @('ssm', 'send-command', '--instance-ids', $instanceId, '--document-name', 'AWS-RunShellScript',
                             '--comment', 'SWE40006 Assignment 4', '--parameters', "file://$paramFile")
    $commandId = $sent.Command.CommandId

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds + 60)
    do {
        Start-Sleep -Seconds 3
        $result = Invoke-AwsJson @('ssm', 'get-command-invocation', '--command-id', $commandId,
                                   '--instance-id', $instanceId) -AllowFailure
    } while ((-not $result -or $result.Status -in @('Pending', 'InProgress', 'Delayed')) -and (Get-Date) -lt $deadline)

    Write-Step ''
    foreach ($line in ($result.StandardOutputContent -split "`n")) { Write-Step $line.TrimEnd() }
    if ($result.StandardErrorContent) {
        Write-Step '--- stderr'
        foreach ($line in ($result.StandardErrorContent -split "`n")) { Write-Step $line.TrimEnd() }
    }
    Write-Step "--- status: $($result.Status), exit code $($result.ResponseCode)"
    if ($result.Status -ne 'Success') { throw "The command did not succeed on $instanceId ($($result.Status))." }
}
finally {
    Remove-Item $paramFile -ErrorAction SilentlyContinue
    Save-Listing $Listing $keepIp
}
