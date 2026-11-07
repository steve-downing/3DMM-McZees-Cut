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
$first = $true
# Another job may push first: then start again from its commit and redo our
# copy (a rebase can't work on the shallow history).
for ($i = 0; $i -lt 6; $i++) {
    git fetch origin ci-results --depth 1 2>$null
    $have = $LASTEXITCODE -eq 0
    if ($first) {
        if ($have) { git worktree add --detach $wt origin/ci-results }
        else {
            git worktree add --detach $wt
            Push-Location $wt; git checkout --orphan tmp-results; git rm -rfq .; Pop-Location
        }
        $first = $false
    } elseif ($have) {
        Push-Location $wt; git reset -q --hard origin/ci-results; git clean -qfd; Pop-Location
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
    git push origin HEAD:ci-results
    $ok = $LASTEXITCODE -eq 0
    Pop-Location
    if ($ok) { exit 0 }
    Start-Sleep -Seconds (3 + 2 * $i)
}
Write-Warning "couldn't publish to ci-results"
