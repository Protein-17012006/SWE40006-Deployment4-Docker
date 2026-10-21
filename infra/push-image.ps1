<#
.SYNOPSIS
  Tag a locally built image and push it to Docker Hub as <dockerid>/<app>:<tag> and :latest.
.EXAMPLE
  .\infra\push-image.ps1 -App friendlyhello -Tag 1.0.0 -Listing 07-push-hello.txt
#>
param(
    [Parameter(Mandatory)][ValidateSet('friendlyhello', 'quickpoll', 'quickpoll-proxy', 'connect4')][string]$App,
    [Parameter(Mandatory)][ValidatePattern('^[0-9A-Za-z._-]+$')][string]$Tag,
    [string]$Listing
)
. "$PSScriptRoot\config.ps1"
$config = Get-LocalConfig
$localImage = "${App}:$Tag"
$hub = "$($config.dockerHubUser)/$App"

try {
    Invoke-Native docker @('image', 'inspect', '--format', '{{.Id}}  {{.Size}} bytes', $localImage) | Out-Null
    foreach ($hubTag in @($Tag, 'latest')) {
        Invoke-Native docker @('tag', $localImage, "${hub}:$hubTag") | Out-Null
        Invoke-Native docker @('push', "${hub}:$hubTag") | Out-Null
    }
    Invoke-Native docker @('image', 'inspect', '--format', '{{json .RepoDigests}}', "${hub}:$Tag") | Out-Null
}
finally {
    Save-Listing $Listing
}
