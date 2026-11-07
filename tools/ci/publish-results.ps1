# Commits CI outputs to the ci-results branch, under runs/<short sha>[/<Sub>].
# Several jobs publish into the same run folder: each replaces only its own
# subfolder (or, with no -Sub, overwrites only the files it brings).
param(
    [Parameter(Mandatory)] [string]$Source,
    [string]$Sub = "",
    [string]$Message = "CI results"
)
$short = $env:GITHUB_SHA.Substring(0, 7)
git config user.name "ci-results bot"
git config user.email "ci-results@users.noreply.github.com"
$wt = Join-Path $env:RUNNER_TEMP "results"
git fetch origin ci-results --depth 1 2>$null
if ($LASTEXITCODE -eq 0) {
    git worktree add $wt origin/ci-results
} else {
    git worktree add --detach $wt
    Push-Location $wt
    git checkout --orphan tmp-results
    git rm -rfq .
    Pop-Location
}
$dest = Join-Path $wt "runs/$short"
if ($Sub) {
    $dest = Join-Path $dest $Sub
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
}
New-Item -ItemType Directory -Force $dest | Out-Null
Copy-Item -Recurse -Force (Join-Path $Source "*") $dest
Set-Content (Join-Path $wt "LATEST") $short
Push-Location $wt
git add -A
git commit -qm "$Message ($short)"
for ($i = 0; $i -lt 5; $i++) {
    git push origin HEAD:ci-results
    if ($LASTEXITCODE -eq 0) { break }
    git fetch origin ci-results --depth 1
    git rebase origin/ci-results
}
Pop-Location
