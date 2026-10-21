<#
.SYNOPSIS
  Delete the Docker host stack after grading. The instance, its disk (with every Docker volume) and the
  Elastic IP all belong to the stack, so nothing billable remains. Run with -DryRun first.
.EXAMPLE
  .\infra\teardown.ps1 -DryRun -Listing 25-teardown-dryrun.txt
#>
param([switch]$DryRun, [string]$Listing)
. "$PSScriptRoot\config.ps1"

try {
    Write-Step ("Teardown of {0} in {1} (profile {2}){3}" -f $StackName, $Region, $AwsProfile, $(if ($DryRun) { ' - DRY RUN' } else { '' }))
    $stack = Invoke-AwsJson @('cloudformation', 'describe-stacks', '--stack-name', $StackName) -AllowFailure
    if (-not $stack) {
        Write-Step "skip          $StackName (not found)"
    } elseif ($DryRun) {
        Write-Step "would delete  $StackName ($($stack.Stacks[0].StackStatus)) and its resources:"
        $resources = Invoke-AwsJson @('cloudformation', 'describe-stack-resources', '--stack-name', $StackName)
        foreach ($r in @($resources.StackResources)) {
            Write-Step ('  {0,-24} {1,-38} {2}' -f $r.LogicalResourceId, $r.ResourceType, $r.PhysicalResourceId)
        }
    } else {
        Invoke-Native aws (@('cloudformation', 'delete-stack', '--stack-name', $StackName) + $AwsArgs) | Out-Null
        Invoke-Native aws (@('cloudformation', 'wait', 'stack-delete-complete', '--stack-name', $StackName) + $AwsArgs) | Out-Null
        Write-Step "deleted       $StackName"
    }
    $arns = @(@(Invoke-AwsJson @('resourcegroupstaggingapi', 'get-resources', '--tag-filters', "Key=Project,Values=$Project",
                                 '--query', 'ResourceTagMappingList[].ResourceARN')) | Where-Object { $_ })
    Write-Step ("Resources tagged Project={0}: {1} (a terminated instance can stay listed for up to an hour)" -f $Project, $arns.Count)
    foreach ($arn in $arns) { Write-Step "  $arn" }
    if (-not $DryRun) { Write-Step 'The Docker Hub repositories stay public; delete them on hub.docker.com when no longer needed.' }
}
finally {
    Save-Listing $Listing
}
