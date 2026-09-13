$ErrorActionPreference = 'Stop'
$tmp = New-TemporaryFile

# register fresh user
@{ username = "e2e_replay_$(Get-Date -Format HHmmss)"; email = "replay@e2e.local"; password = 'e2e-replay-pass-123' } | ConvertTo-Json | Set-Content -Path $tmp -Encoding ascii
$reg = curl.exe -s -X POST http://127.0.0.1:8000/api/auth/register -H 'Content-Type: application/json' -d "@$tmp"
$token = ($reg | ConvertFrom-Json).access_token
Write-Host "token length: $($token.Length)"

# authorize github
'{}' | Set-Content -Path $tmp -Encoding ascii
$auth = curl.exe -s -X POST http://127.0.0.1:8000/api/git/github/authorize -H "Authorization: Bearer $token" -H 'Content-Type: application/json' -d "@$tmp"
$state = ($auth | ConvertFrom-Json).state
Write-Host "state: $state"

# callback #1: fake code -> 502 (provider rejects), state gets consumed
@{ code = 'e2e-fake-auth-code'; state = $state } | ConvertTo-Json | Set-Content -Path $tmp -Encoding ascii
Write-Host "--- callback #1 ---"
curl.exe -s -w "`nHTTP %{http_code}`n" -X POST http://127.0.0.1:8000/api/git/callback -H "Authorization: Bearer $token" -H 'Content-Type: application/json' -d "@$tmp"

# callback #2: replay same state -> 400 already completed
Write-Host "--- callback #2 (replay) ---"
curl.exe -s -w "`nHTTP %{http_code}`n" -X POST http://127.0.0.1:8000/api/git/callback -H "Authorization: Bearer $token" -H 'Content-Type: application/json' -d "@$tmp"

Remove-Item $tmp -Force
