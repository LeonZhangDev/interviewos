$ErrorActionPreference = 'Continue'
$base = 'http://127.0.0.1:8000'
$results = @()

function Add-Result($name, $ok, $detail) {
  $script:results += [pscustomobject]@{ Name = $name; Ok = $ok; Detail = $detail }
  Write-Host ("[{0}] {1} :: {2}" -f ($(if ($ok) {'PASS'} else {'FAIL'})), $name, $detail)
}

function Request($method, $path, $body, $token) {
  $headers = @{}
  if ($token) { $headers['Authorization'] = "Bearer $token" }
  try {
    if ($body) {
      $json = $body | ConvertTo-Json -Depth 5
      $response = Invoke-WebRequest -Uri "$base$path" -Method $method -Body $json -ContentType 'application/json' -Headers $headers -UseBasicParsing -TimeoutSec 30
    } else {
      $response = Invoke-WebRequest -Uri "$base$path" -Method $method -Headers $headers -UseBasicParsing -TimeoutSec 30
    }
    return @{ Status = [int]$response.StatusCode; Body = $response.Content }
  } catch {
    $stream = $_.Exception.Response.GetResponseStream()
    if ($stream) {
      $reader = New-Object System.IO.StreamReader($stream)
      $content = $reader.ReadToEnd()
    } else { $content = $_.Exception.Message }
    $status = try { [int]$_.Exception.Response.StatusCode } catch { 0 }
    return @{ Status = $status; Body = $content }
  }
}

# 1. register a fresh e2e user
$username = "e2e_git_" + (Get-Date -Format 'HHmmss')
$reg = Request 'POST' '/api/auth/register' @{ username = $username; email = "$username@e2e.local"; password = 'e2e-git-pass-123'; display_name = 'E2E Git' }
if ($reg.Status -ne 200) { Add-Result 'register' $false $reg.Body; exit 1 }
$token = ($reg.Body | ConvertFrom-Json).access_token
Add-Result 'register + token' $true $username

# 2. provider status: github configured (fake creds), gitee not
$providers = Request 'GET' '/api/git/providers' $null $token
$plist = if ($providers.Status -eq 200) { $providers.Body | ConvertFrom-Json } else { @() }
$gh = $plist | Where-Object { $_.provider -eq 'github' }
$gt = $plist | Where-Object { $_.provider -eq 'gitee' }
Add-Result 'providers list 200, github configured' ($providers.Status -eq 200 -and $gh.configured -eq $true -and $gh.connected -eq $false) $providers.Body
Add-Result 'providers list, gitee unconfigured' ($gt.configured -eq $false) $providers.Body

# 3. authorize github -> 200 with state + url
$auth = Request 'POST' '/api/git/github/authorize' @{} $token
$authBody = if ($auth.Status -eq 200) { $auth.Body | ConvertFrom-Json } else { $null }
Add-Result 'authorize github 200 + state + url' ($auth.Status -eq 200 -and $authBody.state -and $authBody.authorize_url.StartsWith('https://github.com/login/oauth/authorize')) $auth.Body

# 4. authorize gitee (unconfigured) -> 400
$authGitee = Request 'POST' '/api/git/gitee/authorize' @{} $token
Add-Result 'authorize gitee unconfigured 400' ($authGitee.Status -eq 400 -and $authGitee.Body -match 'not configured') $authGitee.Body

# 5. authorize unknown provider -> 404
$authBad = Request 'POST' '/api/git/gitlab/authorize' @{} $token
Add-Result 'authorize unknown provider 404' ($authBad.Status -eq 404) $authBad.Body

# 6. callback with valid state + fake code -> 502 (provider rejects fake credentials)
$cb = Request 'POST' '/api/git/callback' @{ code = 'e2e-fake-auth-code'; state = $authBody.state } $token
Add-Result 'callback fake code -> 502 provider error' ($cb.Status -eq 502 -and $cb.Body -notmatch 'e2e-fake-client-secret') $cb.Body

# 7. replay same state -> 400 already consumed
$cb2 = Request 'POST' '/api/git/callback' @{ code = 'e2e-fake-auth-code'; state = $authBody.state } $token
Add-Result 'replay state -> 400 consumed' ($cb2.Status -eq 400 -and $cb2.Body -match 'already been completed') $cb2.Body

# 8. unknown state -> 400
$cb3 = Request 'POST' '/api/git/callback' @{ code = 'x'; state = 'unknown-state-value-12345678' } $token
Add-Result 'unknown state -> 400' ($cb3.Status -eq 400) $cb3.Body

# 9. repos without connection -> 404
$repos = Request 'GET' '/api/git/github/repos' $null $token
Add-Result 'provider repos without connection 404' ($repos.Status -eq 404) $repos.Body

# 10. disconnect without connection -> 404
$disc = Request 'DELETE' '/api/git/github' $null $token
Add-Result 'disconnect without connection 404' ($disc.Status -eq 404) $disc.Body

# 11. still not connected + old repo sync path intact
$providers2 = Request 'GET' '/api/git/providers' $null $token
$p2 = $providers2.Body | ConvertFrom-Json
Add-Result 'still not connected after failures' (($p2 | Where-Object { $_.provider -eq 'github' }).connected -eq $false) $providers2.Body
$repoList = Request 'GET' '/api/repos' $null $token
Add-Result 'legacy /api/repos path intact 200' ($repoList.Status -eq 200) ($repoList.Status)

# 12. unauthenticated access -> 401
$anon = Request 'GET' '/api/git/providers' $null $null
Add-Result 'unauthenticated providers 401' ($anon.Status -eq 401) $anon.Body

$failed = $results | Where-Object { -not $_.Ok }
Write-Host ""
Write-Host ("SUMMARY: {0}/{1} passed" -f ($results.Count - $failed.Count), $results.Count)
if ($failed) { exit 1 } else { exit 0 }
