# v1.0 P1 Playgrounds e2e smoke pass (PowerShell)
$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:8000'
$pass = 0; $fail = 0
function Check($name, $condition) {
  if ($condition) { $script:pass++; Write-Output "PASS  $name" }
  else { $script:fail++; Write-Output "FAIL  $name" }
}

# --- health + meta -----------------------------------------------------------
$health = Invoke-RestMethod "$base/health"
Check "backend health" ($health.status -eq 'ok')
$meta = Invoke-RestMethod "$base/api/playground/meta"
Check "meta public" ($null -ne $meta.kinds)
Check "meta kinds" (($meta.kinds -join ',') -eq 'sql,redis,fastapi')
Check "meta limits" ($meta.limits.sql_max_chars -eq 8000)
Check "meta samples" ($null -ne $meta.samples.sql.code)

# --- auth --------------------------------------------------------------------
$suffix = Get-Random -Maximum 99999
$alice = Invoke-RestMethod "$base/api/auth/register" -Method POST -ContentType 'application/json' -Body (@{username="pg_alice_$suffix"; email="pg_alice_$suffix@t.io"; password='password-12345'} | ConvertTo-Json)
$h1 = @{ Authorization = "Bearer $($alice.access_token)" }
$eve = Invoke-RestMethod "$base/api/auth/register" -Method POST -ContentType 'application/json' -Body (@{username="pg_eve_$suffix"; email="pg_eve_$suffix@t.io"; password='password-12345'} | ConvertTo-Json)
$h2 = @{ Authorization = "Bearer $($eve.access_token)" }

# --- SQL playground ----------------------------------------------------------
$s1 = Invoke-RestMethod "$base/api/playground/sessions" -Method POST -ContentType 'application/json' -Headers $h1 -Body '{"kind":"sql"}'
Check "sql session created" ($null -ne $s1.session_id)

# auth guard
try {
  Invoke-RestMethod "$base/api/playground/sql" -Method POST -ContentType 'application/json' -Body '{"session_id":1,"sql":"SELECT 1"}' | Out-Null
  Check "sql requires auth" $false
} catch { Check "sql requires auth" ($_.Exception.Response.StatusCode.value__ -eq 401) }

# multi-statement batch
$batch = "CREATE TABLE candidates (id serial PRIMARY KEY, name text, score int);`nINSERT INTO candidates (name, score) VALUES ('Alice', 88), ('Bob', 72);`nSELECT name, score FROM candidates ORDER BY score DESC;"
$r1 = Invoke-RestMethod "$base/api/playground/sql" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{session_id=$s1.session_id; sql=$batch} | ConvertTo-Json)
Check "sql batch ok" ($r1.ok -eq $true)
Check "sql batch 3 statements" ($r1.statements.Count -eq 3)
Check "sql select rows" ($r1.statements[2].rows[0][0] -eq 'Alice' -and $r1.statements[2].rows[0][1] -eq 88)

# persistence across requests
$r2 = Invoke-RestMethod "$base/api/playground/sql" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{session_id=$s1.session_id; sql='SELECT count(*) AS n FROM candidates'} | ConvertTo-Json)
Check "sql session persists" ($r2.statements[0].rows[0][0] -eq 2)

# string literal false positive protection
$r3 = Invoke-RestMethod "$base/api/playground/sql" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{session_id=$s1.session_id; sql="INSERT INTO candidates (name, score) VALUES ('drop database joke', 1)"} | ConvertTo-Json)
Check "sql literal not false-positive" ($r3.ok -eq $true)

# UPDATE ... SET allowed
$r4 = Invoke-RestMethod "$base/api/playground/sql" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{session_id=$s1.session_id; sql="UPDATE candidates SET score = 99 WHERE name = 'Alice'"} | ConvertTo-Json)
Check "sql UPDATE SET allowed" ($r4.ok -eq $true)

# dangerous statement blocked with 400
try {
  Invoke-RestMethod "$base/api/playground/sql" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{session_id=$s1.session_id; sql='DROP DATABASE sandbox'} | ConvertTo-Json) | Out-Null
  Check "sql DROP DATABASE blocked" $false
} catch {
  $body = $_.ErrorDetails.Message
  Check "sql DROP DATABASE blocked" ($_.Exception.Response.StatusCode.value__ -eq 400 -and $body -match 'sandbox policy')
}

# transactional batch: failing statement rolls back the whole batch
$r5 = Invoke-RestMethod "$base/api/playground/sql" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{session_id=$s1.session_id; sql="INSERT INTO candidates (name, score) VALUES ('Ghost', 1); SELECT * FROM missing_table;"} | ConvertTo-Json)
Check "sql failing batch ok=false" ($r5.ok -eq $false)
$r6 = Invoke-RestMethod "$base/api/playground/sql" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{session_id=$s1.session_id; sql='SELECT count(*) AS n FROM candidates'} | ConvertTo-Json)
Check "sql batch rolled back" ($r6.statements[0].rows[0][0] -eq 3)

# cross-session isolation (second session has an empty schema)
$s2 = Invoke-RestMethod "$base/api/playground/sessions" -Method POST -ContentType 'application/json' -Headers $h1 -Body '{"kind":"sql"}'
try {
  $r7 = Invoke-RestMethod "$base/api/playground/sql" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{session_id=$s2.session_id; sql='SELECT count(*) AS n FROM candidates'} | ConvertTo-Json)
  Check "sql cross-session isolated" ($r7.ok -eq $false)
} catch { Check "sql cross-session isolated" $true }

# cross-user isolation
try {
  Invoke-RestMethod "$base/api/playground/sql" -Method POST -ContentType 'application/json' -Headers $h2 -Body (@{session_id=$s1.session_id; sql='SELECT 1'} | ConvertTo-Json) | Out-Null
  Check "sql cross-user 404" $false
} catch { Check "sql cross-user 404" ($_.Exception.Response.StatusCode.value__ -eq 404) }

# reset wipes the schema
$reset = Invoke-RestMethod "$base/api/playground/reset" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{session_id=$s1.session_id} | ConvertTo-Json)
Check "sql reset ok" ($reset.ok -eq $true -and $reset.reset_sql -eq $true)
$r8 = Invoke-RestMethod "$base/api/playground/sql" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{session_id=$s1.session_id; sql='SELECT count(*) AS n FROM candidates'} | ConvertTo-Json)
Check "sql reset wiped data" ($r8.ok -eq $false)

# --- Redis playground --------------------------------------------------------
$s3 = Invoke-RestMethod "$base/api/playground/sessions" -Method POST -ContentType 'application/json' -Headers $h1 -Body '{"kind":"redis"}'
$rr1 = Invoke-RestMethod "$base/api/playground/redis" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{session_id=$s3.session_id; command="SET greeting 'hello world'"} | ConvertTo-Json)
Check "redis SET ok" ($rr1.ok -eq $true -and $rr1.result.value -eq 'OK')
$rr2 = Invoke-RestMethod "$base/api/playground/redis" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{session_id=$s3.session_id; command='GET greeting'} | ConvertTo-Json)
Check "redis GET persists" ($rr2.result.value -eq 'hello world')

# cross-session isolation (fresh redis session = fresh database index)
$s4 = Invoke-RestMethod "$base/api/playground/sessions" -Method POST -ContentType 'application/json' -Headers $h1 -Body '{"kind":"redis"}'
$rr3 = Invoke-RestMethod "$base/api/playground/redis" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{session_id=$s4.session_id; command='GET greeting'} | ConvertTo-Json)
Check "redis cross-session isolated" ($rr3.result.value -eq $null)

# dangerous command blocked
try {
  Invoke-RestMethod "$base/api/playground/redis" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{session_id=$s3.session_id; command='FLUSHALL'} | ConvertTo-Json) | Out-Null
  Check "redis FLUSHALL blocked" $false
} catch {
  Check "redis FLUSHALL blocked" ($_.Exception.Response.StatusCode.value__ -eq 400)
}

# reset wipes keys
$reset2 = Invoke-RestMethod "$base/api/playground/reset" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{session_id=$s3.session_id} | ConvertTo-Json)
Check "redis reset ok" ($reset2.reset_redis -eq $true)
$rr4 = Invoke-RestMethod "$base/api/playground/redis" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{session_id=$s3.session_id; command='GET greeting'} | ConvertTo-Json)
Check "redis reset wiped keys" ($rr4.result.value -eq $null)

# --- FastAPI playground ------------------------------------------------------
$code = 'from fastapi import FastAPI' + "`n" + 'app = FastAPI()' + "`n`n" + '@app.post("/echo")' + "`n" + 'async def echo(data: dict):' + "`n" + '    return {"received": data.get("name", ""), "ok": True}'
$fa = Invoke-RestMethod "$base/api/playground/fastapi" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{code=$code; method='POST'; path='/echo'; body='{"name":"interviewos"}'} | ConvertTo-Json)
Check "fastapi app runs" ($fa.ok -eq $true -and $fa.status -eq 200)
Check "fastapi body roundtrip" ($fa.body -match 'interviewos')

# invalid method rejected (422)
try {
  Invoke-RestMethod "$base/api/playground/fastapi" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{code=$code; method='TRACE'; path='/'} | ConvertTo-Json) | Out-Null
  Check "fastapi TRACE rejected" $false
} catch { Check "fastapi TRACE rejected" ($_.Exception.Response.StatusCode.value__ -eq 422) }

# broken app returns ok=false with the error, not a 5xx
$fa2 = Invoke-RestMethod "$base/api/playground/fastapi" -Method POST -ContentType 'application/json' -Headers $h1 -Body (@{code='x = 1'; method='GET'; path='/'} | ConvertTo-Json)
Check "fastapi no-app error" ($fa2.ok -eq $false -and $fa2.error.Length -gt 0)

Write-Output ""
Write-Output "RESULT: $pass passed, $fail failed"
if ($fail -gt 0) { exit 1 } else { exit 0 }
