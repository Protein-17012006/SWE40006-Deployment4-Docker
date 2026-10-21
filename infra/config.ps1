# Shared settings and helpers for the infra scripts (Windows PowerShell 5.1).
# Dot-source it at the top of a script:   . "$PSScriptRoot\config.ps1"
Set-StrictMode -Version 3
$ErrorActionPreference = 'Stop'

$Project     = 'swe40006-a4'
$Region      = 'ap-southeast-1'
$AwsProfile  = 'swe40006-a2'            # the student's account (IAM user Ha_Tran); never default or admin
$AwsArgs     = @('--profile', $AwsProfile, '--region', $Region)
$StackName   = "$Project-docker-host"
$Template    = 'infra/cfn/docker-host.yaml'
$RepoRoot    = Split-Path -Parent $PSScriptRoot
$CfnLint     = Join-Path $RepoRoot '.venv-tools\Scripts\cfn-lint.exe'
$ListingsDir = Join-Path $RepoRoot 'report\listings'

$script:Log = New-Object 'System.Collections.Generic.List[string]'

function Write-Step {
    # Print a line and remember it for the listing file.
    param([AllowEmptyString()][string]$Text = '')
    Write-Host $Text
    $script:Log.Add($Text)
}

function Format-Command {
    param([string]$FilePath, [string[]]$ArgumentList)
    $parts = @([IO.Path]::GetFileNameWithoutExtension($FilePath)) + @($ArgumentList | ForEach-Object {
        if ($_ -match '\s') { '"' + $_ + '"' } else { $_ }
    })
    $parts -join ' '
}

function Invoke-Native {
    # Run a native command, print and log "PS> command" and its output, and return the exit code.
    # Windows PowerShell 5.1 turns native stderr into errors under 'Stop', so it is relaxed around the call.
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [switch]$AllowFailure
    )
    Write-Step ('PS> ' + (Format-Command $FilePath $ArgumentList))
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $lines = @(& $FilePath @ArgumentList 2>&1 | ForEach-Object { "$_" })
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $saved
    }
    foreach ($line in $lines) { Write-Step $line }
    if ($code -ne 0 -and -not $AllowFailure) {
        throw "Command failed with exit code ${code}: $(Format-Command $FilePath $ArgumentList)"
    }
    return $code
}

function Invoke-AwsJson {
    # Run an AWS CLI command quietly and return its JSON output as objects ($null on failure with -AllowFailure).
    param([Parameter(Mandatory)][string[]]$ArgumentList, [switch]$AllowFailure)
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $text = (& aws @ArgumentList @AwsArgs --output json 2>$null) -join "`n"
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $saved
    }
    if ($code -ne 0) {
        if ($AllowFailure) { return $null }
        throw "aws $($ArgumentList -join ' ') failed with exit code $code (if the session expired: aws login --profile $AwsProfile)"
    }
    if ([string]::IsNullOrWhiteSpace($text)) { return $null }
    return ($text | ConvertFrom-Json)
}

function Get-StackOutputs {
    param([string]$Name = $StackName)
    $described = Invoke-AwsJson @('cloudformation', 'describe-stacks', '--stack-name', $Name)
    $map = @{}
    $stack = $described.Stacks[0]
    if ($stack.PSObject.Properties['Outputs']) {
        foreach ($output in @($stack.Outputs)) { $map[$output.OutputKey] = $output.OutputValue }
    }
    return $map
}

function Get-PublicIp {
    # The Elastic IP from the Docker host stack, or $null if the stack does not exist yet.
    $described = Invoke-AwsJson @('cloudformation', 'describe-stacks', '--stack-name', $StackName) -AllowFailure
    if (-not $described) { return $null }
    $stack = $described.Stacks[0]
    if (-not $stack.PSObject.Properties['Outputs']) { return $null }
    $ip = @($stack.Outputs | Where-Object { $_.OutputKey -eq 'PublicIp' })
    if ($ip.Count) { return $ip[0].OutputValue }
    return $null
}

function Get-LocalConfig {
    $path = Join-Path $PSScriptRoot 'a4.local.json'
    if (-not (Test-Path $path)) {
        throw "Missing $path. Create it with dockerHubUser (Task 2)."
    }
    return (Get-Content $path -Raw | ConvertFrom-Json)
}

function ConvertTo-SsmCommands {
    # Wrap a bash script for AWS-RunShellScript. It travels base64-encoded in short lines, so quotes,
    # '$' and non-ASCII text arrive unchanged and no single command line gets long.
    param([Parameter(Mandatory)][string]$Script)
    $text = ($Script -replace "`r`n", "`n").TrimEnd() + "`n"
    $b64 = [Convert]::ToBase64String((New-Object System.Text.UTF8Encoding($false)).GetBytes($text))
    $chunks = for ($i = 0; $i -lt $b64.Length; $i += 1000) { $b64.Substring($i, [Math]::Min(1000, $b64.Length - $i)) }
    return @('f=$(mktemp)', 'base64 -d > "$f" <<''B64''') + @($chunks) + @('B64', 'bash "$f"; rc=$?; rm -f "$f"; exit $rc')
}

function Hide-PublicIp {
    # Mask public IPv4 addresses except the Elastic IP (which the report publishes anyway).
    param([string]$Text, [string]$KeepIp)
    $evaluator = {
        param($match)
        $a = [int]$match.Groups[1].Value
        $b = [int]$match.Groups[2].Value
        $private = ($a -eq 10) -or ($a -eq 127) -or ($a -eq 172 -and $b -ge 16 -and $b -le 31) -or
                   ($a -eq 192 -and $b -eq 168) -or ($a -eq 169 -and $b -eq 254) -or ($a -eq 0)
        if ($private -or $match.Value -eq $KeepIp) { return $match.Value }
        return 'x.x.x.x'
    }
    return [regex]::Replace($Text, '\b(\d{1,3})\.(\d{1,3})\.\d{1,3}\.\d{1,3}\b', $evaluator)
}

function Save-Listing {
    # Append everything logged so far to report\listings\<Name> (UTF-8, public IPs masked), so that
    # several runs (change set, then -Execute) build one listing. Delete the file to start afresh.
    param([string]$Name, [string]$KeepIp)
    if (-not $Name) { return }
    New-Item -ItemType Directory -Force $ListingsDir | Out-Null
    $path = Join-Path $ListingsDir $Name
    $text = Hide-PublicIp (($script:Log -join "`r`n") + "`r`n") $KeepIp
    if (Test-Path $path) { $text = "`r`n" + $text }
    [IO.File]::AppendAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "listing saved: $path"
}
