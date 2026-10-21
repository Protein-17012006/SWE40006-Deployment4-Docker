<#
.SYNOPSIS
  Lint, validate and deploy the Docker host stack (swe40006-a4-docker-host) through a change set.
.DESCRIPTION
  Without -Execute: cfn-lint, validate-template, create a change set and print it for review.
  With -Execute:    execute the newest change set waiting for review, wait, print events and outputs.
.EXAMPLE
  .\infra\deploy-stack.ps1 -Listing 06-docker-host-stack.txt
  .\infra\deploy-stack.ps1 -Execute -Listing 06-docker-host-stack.txt
#>
param(
    [ValidateSet('t3.micro', 't3.small')][string]$InstanceType,
    [switch]$Execute,
    [string]$Listing
)
. "$PSScriptRoot\config.ps1"
Set-Location $RepoRoot

function Show-StackEvents {
    param([int]$Count = 30)
    $events = Invoke-AwsJson @('cloudformation', 'describe-stack-events', '--stack-name', $StackName, '--max-items', "$Count")
    Write-Step ''
    Write-Step ('{0,-19}  {1,-28}  {2,-26}  {3}' -f 'Time (UTC)', 'Logical ID', 'Status', 'Reason')
    foreach ($event in @($events.StackEvents | Sort-Object { [datetime]$_.Timestamp })) {
        $time = ([datetime]$event.Timestamp).ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss')
        $reason = if ($event.PSObject.Properties['ResourceStatusReason']) { $event.ResourceStatusReason } else { '' }
        Write-Step ('{0,-19}  {1,-28}  {2,-26}  {3}' -f $time, $event.LogicalResourceId, $event.ResourceStatus, $reason)
    }
}

$keepIp = $null
try {
    if ($Execute) {
        $sets = Invoke-AwsJson @('cloudformation', 'list-change-sets', '--stack-name', $StackName)
        $pending = @($sets.Summaries | Where-Object { $_.ExecutionStatus -eq 'AVAILABLE' } |
                     Sort-Object { [datetime]$_.CreationTime } -Descending)
        if ($pending.Count -eq 0) { throw "No change set is waiting for $StackName. Run without -Execute first." }
        $changeSet = $pending[0].ChangeSetName
        $status = (Invoke-AwsJson @('cloudformation', 'describe-stacks', '--stack-name', $StackName)).Stacks[0].StackStatus
        $waiter = if ($status -eq 'REVIEW_IN_PROGRESS') { 'stack-create-complete' } else { 'stack-update-complete' }
        Invoke-Native aws (@('cloudformation', 'execute-change-set', '--stack-name', $StackName,
                             '--change-set-name', $changeSet) + $AwsArgs) | Out-Null
        $code = Invoke-Native aws (@('cloudformation', 'wait', $waiter, '--stack-name', $StackName) + $AwsArgs) -AllowFailure
        Show-StackEvents
        $final = (Invoke-AwsJson @('cloudformation', 'describe-stacks', '--stack-name', $StackName)).Stacks[0]
        Write-Step ''
        Write-Step "Stack status: $($final.StackStatus)"
        if ($code -ne 0) { throw "$StackName did not finish: $($final.StackStatus). See the events above." }
        Write-Step 'Outputs:'
        if ($final.PSObject.Properties['Outputs']) {
            foreach ($output in @($final.Outputs)) { Write-Step ('  {0,-16} {1}' -f $output.OutputKey, $output.OutputValue) }
        }
        $keepIp = Get-PublicIp
        return
    }

    # 1. Lint and validate the template.
    if (-not (Test-Path $CfnLint)) { throw "cfn-lint not found at $CfnLint (Task 1 creates .venv-tools)." }
    $lint = Invoke-Native $CfnLint @('--regions', $Region, '--', $Template) -AllowFailure
    if ($lint -band 2) { throw "cfn-lint found errors in $Template." }
    Invoke-Native aws (@('cloudformation', 'validate-template', '--template-body', "file://$Template",
                         '--query', 'Description', '--output', 'text') + $AwsArgs) | Out-Null

    # 2. Create the change set.
    $existing = Invoke-AwsJson @('cloudformation', 'describe-stacks', '--stack-name', $StackName) -AllowFailure
    $status = if ($existing) { $existing.Stacks[0].StackStatus } else { $null }
    if ($status -in @('ROLLBACK_COMPLETE', 'ROLLBACK_FAILED', 'DELETE_FAILED')) {
        throw "$StackName is $status. Delete it (aws cloudformation delete-stack --stack-name $StackName) and run again."
    }
    $type = if ($status -and $status -ne 'REVIEW_IN_PROGRESS') { 'UPDATE' } else { 'CREATE' }
    $parameters = @()
    if ($InstanceType) { $parameters += "ParameterKey=InstanceType,ParameterValue=$InstanceType" }
    elseif ($type -eq 'UPDATE') { $parameters += 'ParameterKey=InstanceType,UsePreviousValue=true' }
    $changeSet = "$StackName-" + (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
    $createArgs = @('cloudformation', 'create-change-set', '--stack-name', $StackName, '--change-set-name', $changeSet,
                    '--change-set-type', $type, '--template-body', "file://$Template", '--capabilities', 'CAPABILITY_IAM',
                    '--tags', "Key=Project,Value=$Project")
    if ($parameters.Count) { $createArgs += @('--parameters') + $parameters }
    Invoke-Native aws ($createArgs + $AwsArgs) | Out-Null
    $ready = Invoke-Native aws (@('cloudformation', 'wait', 'change-set-create-complete', '--stack-name', $StackName,
                                  '--change-set-name', $changeSet) + $AwsArgs) -AllowFailure
    $described = Invoke-AwsJson @('cloudformation', 'describe-change-set', '--stack-name', $StackName,
                                  '--change-set-name', $changeSet)
    if ($ready -ne 0) {
        Write-Step "Change set status: $($described.Status) - $($described.StatusReason)"
        if ("$($described.StatusReason)" -match "didn't contain changes|No updates") {
            Invoke-Native aws (@('cloudformation', 'delete-change-set', '--stack-name', $StackName,
                                 '--change-set-name', $changeSet) + $AwsArgs) | Out-Null
            Write-Step 'Nothing to deploy: the stack already matches this template and these parameters.'
            return
        }
        throw "Change set $changeSet failed."
    }
    Write-Step ''
    Write-Step "Change set $changeSet ($type) is ready for review:"
    Write-Step ('{0,-8}  {1,-24}  {2,-38}  {3}' -f 'Action', 'Logical ID', 'Resource type', 'Replacement')
    foreach ($change in @($described.Changes)) {
        $resource = $change.ResourceChange
        $replacement = if ($resource.PSObject.Properties['Replacement']) { $resource.Replacement } else { '' }
        Write-Step ('{0,-8}  {1,-24}  {2,-38}  {3}' -f $resource.Action, $resource.LogicalResourceId,
                    $resource.ResourceType, $replacement)
    }
    Write-Step ''
    Write-Step 'Next: .\infra\deploy-stack.ps1 -Execute'
    $keepIp = Get-PublicIp
}
finally {
    Save-Listing $Listing $keepIp
}
