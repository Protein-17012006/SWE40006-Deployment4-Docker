<#
.SYNOPSIS
  Deploy or update one Compose project on the Docker host: hello (4.2), quickpoll (4.3) or connect4 (4.4).
.DESCRIPTION
  Copies the app's compose.deploy.yaml to /opt/swe40006-a4/<project>/compose.yaml, sets the .env keys that
  are given (the others keep their previous values), then runs on the host, echoing every command:
    docker compose config --quiet
    docker compose pull --policy missing
    docker compose up -d --dry-run          (only when the project already exists)
    docker compose up -d --wait
    docker compose ps -a / images           (and the migrate log for quickpoll)
  Quick Poll's database password is generated on the host at the first deploy and never leaves it.
.EXAMPLE
  .\infra\deploy-app.ps1 -App quickpoll -Tag 1.0.0 -ProxyTag 1.0.0 -Listing 14-poll-deploy-ec2.txt
  .\infra\deploy-app.ps1 -App quickpoll -Tag 1.1.0 -Listing 15-poll-v110-upgrade.txt
#>
param(
    [Parameter(Mandatory)][ValidateSet('hello', 'quickpoll', 'connect4')][string]$App,
    [ValidatePattern('^[0-9A-Za-z._-]+$')][string]$Tag,
    [ValidatePattern('^[0-9A-Za-z._-]+$')][string]$ProxyTag,
    [string]$Listing,
    [string]$SaveScript      # write the bash script to this file instead of running it (for testing)
)
. "$PSScriptRoot\config.ps1"
if ($ProxyTag -and $App -ne 'quickpoll') { throw '-ProxyTag applies to quickpoll only.' }
$config = Get-LocalConfig
$folders = @{ hello = 'task4.2-python-hello'; quickpoll = 'task4.3-quickpoll'; connect4 = 'task4.4-connect4' }
$composeFile = Join-Path $RepoRoot "$($folders[$App])\compose.deploy.yaml"
if (-not (Test-Path $composeFile)) { throw "Missing $composeFile." }
$deployTarget = "AWS EC2 $([char]0x00B7) Docker Compose"     # the middle dot, built here so the .ps1 stays ASCII

# The .env keys to set on the host. A tag that is not given keeps its value from the previous deploy.
$settings = [ordered]@{ DOCKERHUB_USER = $config.dockerHubUser }
if ($App -eq 'quickpoll') {
    if ($Tag) { $settings['WEB_TAG'] = $Tag }
    if ($ProxyTag) { $settings['PROXY_TAG'] = $ProxyTag }
} elseif ($Tag) {
    $settings['TAG'] = $Tag
}
if ($App -ne 'connect4') { $settings['DEPLOY_TARGET'] = $deployTarget }

$utf8 = New-Object System.Text.UTF8Encoding($false)
$composeText = ([IO.File]::ReadAllText($composeFile, $utf8) -replace "`r`n", "`n")
$composeB64 = [Convert]::ToBase64String($utf8.GetBytes($composeText))
$pairs = @($settings.GetEnumerator() | ForEach-Object { "'" + $_.Key + '=' + $_.Value + "'" }) -join ' '

$header = @(
    'set -euo pipefail'
    'exec 2>&1                 # Compose reports progress on stderr: keep it in order with the commands'
    "project='$App'"
    "dir='/opt/$Project/$App'"
    "compose_b64='$composeB64'"
    'mkdir -p "$dir"'
    "set -- $pairs"
) -join "`n"

# Runs on the host as root. Tested against Docker Engine 25 with Compose v5.6.0.
$body = @'
cd "$dir"
run() { printf '\n# %s\n' "$*"; "$@"; }
mask() { sed -E 's/^(POSTGRES_PASSWORD=).*/\1******** (masked)/' .env; }
pull_missing() {  # pull only images that are not on this host yet; print one line per image
  printf '\n# %s\n' 'docker compose pull --policy missing'
  local out rc=0
  out=$(docker compose --progress plain pull --policy missing 2>&1) || rc=$?
  printf '%s\n' "$out" | grep -E '^ ?Image |rror' || echo '(every image is already on this host)'
  return $rc
}
set_env() {  # replace KEY=... in .env, or append it
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else printf '%s=%s\n' "$1" "$2" >> .env; fi
}
existing=$(docker ps -aq --filter "label=com.docker.compose.project=$project" | wc -l)
printf '%s' "$compose_b64" | base64 -d > compose.yaml
touch .env
chmod 600 .env
printf '# cd %s\n# cat .env   (before)\n' "$dir"; mask
for pair in "$@"; do set_env "${pair%%=*}" "${pair#*=}"; done
if [ "$project" = quickpoll ] && ! grep -q '^POSTGRES_PASSWORD=' .env; then
  set_env POSTGRES_PASSWORD "$(openssl rand -hex 16)"
  echo '# POSTGRES_PASSWORD generated on this host (openssl rand -hex 16); it never leaves it'
fi
printf '\n# cat .env   (after)\n'; mask
run docker compose config --quiet
pull_missing
if [ "$existing" -gt 0 ]; then run docker compose up -d --dry-run; fi
run docker compose up -d --wait --wait-timeout 300
run docker compose ps -a --format 'table {{.Service}}\t{{.Image}}\t{{.State}}\t{{.Status}}\t{{.Ports}}'
run docker compose images
if [ "$project" = quickpoll ]; then run docker compose logs --no-log-prefix migrate; fi
'@

$script = $header + "`n" + ($body -replace "`r`n", "`n")
if ($SaveScript) {
    [IO.File]::WriteAllText($SaveScript, $script, $utf8)
    Write-Host "script saved: $SaveScript"
    return
}
& "$PSScriptRoot\run-on-instance.ps1" -Command $script -HideScript -TimeoutSeconds 900 -Listing $Listing
