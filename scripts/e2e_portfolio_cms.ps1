# v1.0 P2 Portfolio CMS e2e smoke pass (PowerShell)
$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:8000'
$pass = 0; $fail = 0
function Check($name, $condition) {
  if ($condition) { $script:pass++; Write-Output "PASS  $name" }
  else { $script:fail++; Write-Output "FAIL  $name" }
}

# --- health -------------------------------------------------------------------
$health = Invoke-RestMethod "$base/health"
Check "backend health" ($health.status -eq 'ok')

# --- auth ---------------------------------------------------------------------
$suffix = Get-Random -Maximum 99999
$aliceName = "cms_alice_$suffix"
$eveName = "cms_eve_$suffix"
$alice = Invoke-RestMethod "$base/api/auth/register" -Method POST -ContentType 'application/json' -Body (@{username=$aliceName; email="$aliceName@t.io"; password='password-12345'} | ConvertTo-Json)
$h1 = @{ Authorization = "Bearer $($alice.access_token)" }
$eve = Invoke-RestMethod "$base/api/auth/register" -Method POST -ContentType 'application/json' -Body (@{username=$eveName; email="$eveName@t.io"; password='password-12345'} | ConvertTo-Json)
$h2 = @{ Authorization = "Bearer $($eve.access_token)" }

# --- CMS profile --------------------------------------------------------------
# auth guard
try {
  Invoke-RestMethod "$base/api/portfolio-cms/profile" | Out-Null
  Check "cms profile requires auth" $false
} catch { Check "cms profile requires auth" ($_.Exception.Response.StatusCode.value__ -eq 401) }

# auto-created profile, default unpublished
$profile = Invoke-RestMethod "$base/api/portfolio-cms/profile" -Headers $h1
Check "profile auto-created" ($profile.username -eq $aliceName)
Check "profile default unpublished" ($profile.is_published -eq $false)

# unpublished → public view serves the legacy static shape
$publicLegacy = Invoke-RestMethod "$base/api/portfolio/$aliceName"
Check "unpublished serves legacy" ($null -eq $publicLegacy.cms)
Check "unpublished legacy title" ($publicLegacy.title -eq 'AI / Agent Engineer')

# update profile fields (still unpublished)
$profileBody = @{
  display_name = 'Alice CMS'
  headline = 'Agent Infra Engineer'
  summary = 'Building reliable agents.'
  skills = @('Python', 'FastAPI', 'LangGraph')
  resume_url = 'https://example.com/cv.pdf'
  social_links = @{ github = 'https://github.com/alice'; blog = 'https://alice.dev' }
  is_published = $false
}
$updated = Invoke-RestMethod "$base/api/portfolio-cms/profile" -Method PUT -ContentType 'application/json' -Headers $h1 -Body ($profileBody | ConvertTo-Json)
Check "profile fields saved" ($updated.display_name -eq 'Alice CMS' -and $updated.headline -eq 'Agent Infra Engineer')
Check "profile skills saved" (($updated.skills -join ',') -eq 'Python,FastAPI,LangGraph')
Check "profile social saved" ($updated.social_links.github -eq 'https://github.com/alice')

# still unpublished → legacy
$publicLegacy2 = Invoke-RestMethod "$base/api/portfolio/$aliceName"
Check "unpublished still legacy" ($null -eq $publicLegacy2.cms)

# publish
$publishBody = $profileBody
$publishBody.is_published = $true
$published = Invoke-RestMethod "$base/api/portfolio-cms/profile" -Method PUT -ContentType 'application/json' -Headers $h1 -Body ($publishBody | ConvertTo-Json)
Check "published flag" ($published.is_published -eq $true)

$publicCms = Invoke-RestMethod "$base/api/portfolio/$aliceName"
Check "public cms flag" ($publicCms.cms -eq $true)
Check "public cms headline" ($publicCms.title -eq 'Agent Infra Engineer')
Check "public cms name" ($publicCms.name -eq 'Alice CMS')
Check "public cms skills" (($publicCms.skills -join ',') -eq 'Python,FastAPI,LangGraph')
Check "public cms resume" ($publicCms.resume_url -eq 'https://example.com/cv.pdf')
Check "public cms social" ($publicCms.social.blog -eq 'https://alice.dev')

# --- projects -----------------------------------------------------------------
$mkBody = @{
  title = 'MindTrip'
  subtitle = 'Structured travel-planning Agent'
  description = 'Retrieve, plan, validate, repair.'
  architecture = 'Plan -> Validate -> Executor'
  decisions = 'LLM proposes, deterministic executor disposes.'
  tech_tags = @('LangGraph', 'FastAPI')
  link = 'https://example.com/mindtrip'
  repository_id = $null
  is_visible = $true
}
$p1 = Invoke-RestMethod "$base/api/portfolio-cms/projects" -Method POST -ContentType 'application/json' -Headers $h1 -Body ($mkBody | ConvertTo-Json)
Check "project created" ($p1.title -eq 'MindTrip')
Check "project visible default" ($p1.is_visible -eq $true)
Check "project order 1" ($p1.order_index -eq 1)

$mkBody2 = $mkBody
$mkBody2.title = 'AtlasSplit'
$mkBody2.subtitle = 'Safe deterministic execution'
$p2 = Invoke-RestMethod "$base/api/portfolio-cms/projects" -Method POST -ContentType 'application/json' -Headers $h1 -Body ($mkBody2 | ConvertTo-Json)
Check "second project order 2" ($p2.order_index -eq 2)

# public view shows both, in order
$publicProjects = Invoke-RestMethod "$base/api/portfolio/$aliceName"
Check "public projects count" ($publicProjects.projects.Count -eq 2)
Check "public first project" ($publicProjects.projects[0].name -eq 'MindTrip')
Check "public project tech tags" (($publicProjects.projects[0].tech_tags -join ',') -eq 'LangGraph,FastAPI')
Check "public project repo null" ($null -eq $publicProjects.projects[0].repository)

# repository binding validation: unknown repo id → 404
try {
  $mkBad = $mkBody
  $mkBad.title = 'BadBinding'
  $mkBad.repository_id = 999999
  Invoke-RestMethod "$base/api/portfolio-cms/projects" -Method POST -ContentType 'application/json' -Headers $h1 -Body ($mkBad | ConvertTo-Json) | Out-Null
  Check "foreign repo id rejected" $false
} catch { Check "foreign repo id rejected" ($_.Exception.Response.StatusCode.value__ -eq 404) }

# reorder: swap p2 first
$reordered = Invoke-RestMethod "$base/api/portfolio-cms/projects/order" -Method PUT -ContentType 'application/json' -Headers $h1 -Body (@{ids=@($p2.id, $p1.id)} | ConvertTo-Json)
Check "reorder swaps order" ($reordered[0].title -eq 'AtlasSplit' -and $reordered[0].order_index -eq 1)

# hide p2 via update
$hideBody = @{
  title = 'AtlasSplit'
  subtitle = 'Safe deterministic execution'
  description = 'Retrieve, plan, validate, repair.'
  architecture = 'Plan -> Validate -> Executor'
  decisions = 'LLM proposes, deterministic executor disposes.'
  tech_tags = @('LangGraph', 'FastAPI')
  link = 'https://example.com/mindtrip'
  repository_id = $null
  is_visible = $false
}
$hidden = Invoke-RestMethod "$base/api/portfolio-cms/projects/$($p2.id)" -Method PUT -ContentType 'application/json' -Headers $h1 -Body ($hideBody | ConvertTo-Json)
Check "project hidden" ($hidden.is_visible -eq $false)

$publicHidden = Invoke-RestMethod "$base/api/portfolio/$aliceName"
Check "hidden project excluded from public" ($publicHidden.projects.Count -eq 1)
Check "remaining project is MindTrip" ($publicHidden.projects[0].name -eq 'MindTrip')

# --- tenant isolation ---------------------------------------------------------
try {
  Invoke-RestMethod "$base/api/portfolio-cms/projects/$($p1.id)" -Method PUT -ContentType 'application/json' -Headers $h2 -Body ($mkBody | ConvertTo-Json) | Out-Null
  Check "cross-user update 404" $false
} catch { Check "cross-user update 404" ($_.Exception.Response.StatusCode.value__ -eq 404) }

try {
  Invoke-RestMethod "$base/api/portfolio-cms/projects/$($p1.id)" -Method DELETE -Headers $h2 | Out-Null
  Check "cross-user delete 404" $false
} catch { Check "cross-user delete 404" ($_.Exception.Response.StatusCode.value__ -eq 404) }

# eve sees only her own (empty) list
$eveProjects = Invoke-RestMethod "$base/api/portfolio-cms/projects" -Headers $h2
Check "eve list empty" ($eveProjects.Count -eq 0)

# eve's portfolio stays legacy (independent publish state)
$publicEve = Invoke-RestMethod "$base/api/portfolio/$eveName"
Check "eve portfolio legacy" ($null -eq $publicEve.cms)

# unknown username → 404
try {
  Invoke-RestMethod "$base/api/portfolio/nobody_here_$suffix" | Out-Null
  Check "unknown portfolio 404" $false
} catch { Check "unknown portfolio 404" ($_.Exception.Response.StatusCode.value__ -eq 404) }

# --- delete + unpublish -------------------------------------------------------
$deleted = Invoke-RestMethod "$base/api/portfolio-cms/projects/$($p1.id)" -Method DELETE -Headers $h1
Check "project deleted" ($deleted.deleted -eq $p1.id)
$aliceList = Invoke-RestMethod "$base/api/portfolio-cms/projects" -Headers $h1
Check "list after delete" ($aliceList.Count -eq 1)

$unpublishBody = $publishBody
$unpublishBody.is_published = $false
$unpublished = Invoke-RestMethod "$base/api/portfolio-cms/profile" -Method PUT -ContentType 'application/json' -Headers $h1 -Body ($unpublishBody | ConvertTo-Json)
Check "unpublished flag" ($unpublished.is_published -eq $false)
$publicFinal = Invoke-RestMethod "$base/api/portfolio/$aliceName"
Check "unpublish restores legacy" ($null -eq $publicFinal.cms)

Write-Output ""
Write-Output "RESULT: $pass passed, $fail failed"
if ($fail -gt 0) { exit 1 } else { exit 0 }
