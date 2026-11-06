# Batch-converts every .3mm under a folder into video files.
#
#   render-folder.ps1 -InputDir D:\3mm-archive -OutputDir D:\3mm-videos [-Stereo]
#
# For each movie (recursively; the folder structure is mirrored):
#   1. 3dmm-render plays it headlessly into a scratch folder
#   2. encode-movie.ps1 builds the soundtrack and encodes the videos
#   3. the scratch folder is deleted (unless -KeepFrames)
# Movies whose videos are already newer than the .3mm are skipped, so an
# interrupted run picks up where it left off (-Force redoes everything).
# Every movie gets a row in <OutputDir>\report.csv.
#
# Needs: 3dmm-render.exe (built from this repo), ffmpeg on PATH, a 3D
# Movie Maker content install (-Root), and for music, FluidSynth plus a
# General MIDI SoundFont (-SoundFont, or the SOUNDFONT environment variable).
# Works in Windows PowerShell 5.1 and PowerShell 7.
param(
    [Parameter(Mandatory)] [string]$InputDir,
    [Parameter(Mandatory)] [string]$OutputDir,
    [string]$Root = "C:\Program Files (x86)\Microsoft Kids",
    [string]$Renderer,
    [switch]$Stereo,
    [double]$Depth = 2.5,
    [string[]]$Formats,
    [string]$SoundFont = $env:SOUNDFONT,
    [string]$FluidSynth = "fluidsynth",
    [double]$ClickPause = 3,
    [int]$TimeoutMinutes = 30,
    [int]$Scale = 2,
    [switch]$KeepFrames,
    [switch]$Force
)
$ErrorActionPreference = "Stop"

if (-not $Renderer) {
    $candidates = @(
        (Join-Path $PSScriptRoot "3dmm-render.exe"),
        (Join-Path $PSScriptRoot "..\..\build\3dmm-render.exe"),
        (Join-Path $PSScriptRoot "..\..\dist\3dmm-render.exe"))
    $Renderer = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $Renderer) {
        $cmd = Get-Command 3dmm-render.exe -ErrorAction SilentlyContinue
        if ($cmd) { $Renderer = $cmd.Source }
    }
}
if (-not $Renderer -or -not (Test-Path $Renderer)) { throw "can't find 3dmm-render.exe; pass -Renderer" }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { throw "ffmpeg isn't on PATH" }
if (-not (Test-Path (Join-Path $Root "3D Movie Maker"))) { throw "no '3D Movie Maker' folder under $Root; pass -Root" }
if (-not $Formats) { $Formats = if ($Stereo) { @("sbs", "anaglyph", "2d") } else { @("2d") } }

$InputDir = (Resolve-Path $InputDir).Path.TrimEnd('\')
New-Item -ItemType Directory -Force $OutputDir | Out-Null
$OutputDir = (Resolve-Path $OutputDir).Path
$scratch = Join-Path $OutputDir ".render-scratch"
$report = Join-Path $OutputDir "report.csv"
$encoder = Join-Path $PSScriptRoot "encode-movie.ps1"

$statusByExit = @{ 0 = "ok"; 1 = "usage"; 2 = "init-failed"; 3 = "load-failed"; 4 = "missing-content";
                   5 = "render-failed"; 6 = "movie-timeout" }

$movies = @(Get-ChildItem -Recurse -File $InputDir | Where-Object { $_.Extension -ieq ".3mm" } | Sort-Object FullName)
Write-Host "$($movies.Count) movies under $InputDir"
$rows = @()
$n = 0

foreach ($movie in $movies) {
    $n++
    $rel = $movie.FullName.Substring($InputDir.Length + 1)
    $relBase = [IO.Path]::ChangeExtension($rel, $null).TrimEnd('.')
    $outBase = Join-Path $OutputDir $relBase
    $outputs = $Formats | ForEach-Object { "$outBase.$_.mp4" }
    $row = [ordered]@{ movie = $rel; status = ""; exit = ""; frames = ""; seconds = ""; missing = ""; outputs = "" }

    $upToDate = -not $Force -and @($outputs | Where-Object {
            -not (Test-Path $_) -or (Get-Item $_).LastWriteTime -lt $movie.LastWriteTime }).Count -eq 0
    if ($upToDate) {
        Write-Host "[$n/$($movies.Count)] $rel - up to date"
        $row.status = "skipped"
        $rows += [pscustomobject]$row
        continue
    }

    Write-Host "[$n/$($movies.Count)] $rel"
    $work = Join-Path $scratch ("{0:D5}" -f $n)
    if (Test-Path $work) { Remove-Item -Recurse -Force $work }
    New-Item -ItemType Directory -Force $work | Out-Null

    $rargs = @("`"$($movie.FullName)`"", "`"$work`"", "--root", "`"$Root`"", "--click-pause", "$ClickPause")
    if ($Stereo) { $rargs += @("--stereo", "--depth", "$Depth") }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $proc = Start-Process -FilePath $Renderer -ArgumentList $rargs -PassThru -NoNewWindow `
        -RedirectStandardOutput (Join-Path $work "stdout.txt") -RedirectStandardError (Join-Path $work "stderr.txt")
    if (-not $proc.WaitForExit($TimeoutMinutes * 60 * 1000)) {
        $proc.Kill()
        $row.status = "timeout"
    } else {
        $row.exit = $proc.ExitCode
        $row.status = if ($statusByExit.ContainsKey($proc.ExitCode)) { $statusByExit[$proc.ExitCode] } else { "crashed" }
    }
    $sw.Stop()
    $row.seconds = [Math]::Round($sw.Elapsed.TotalSeconds, 1)
    $row.frames = @(Get-ChildItem (Join-Path $work "frames") -Filter *.bmp -ErrorAction SilentlyContinue).Count
    $events = Join-Path $work "events.txt"
    if (Test-Path $events) {
        $row.missing = (Select-String -Path $events -Pattern "missing-content (.*)$" |
                ForEach-Object { $_.Matches[0].Groups[1].Value } | Sort-Object -Unique) -join "; "
    }

    if ($row.status -eq "ok") {
        New-Item -ItemType Directory -Force (Split-Path -Parent $outBase) | Out-Null
        & $encoder -RenderDir $work -OutBase $outBase -Formats $Formats -SoundFont $SoundFont `
            -FluidSynth $FluidSynth -Scale $Scale
        if ($LASTEXITCODE -ne 0) { $row.status = "encode-failed" }
        $row.outputs = ($outputs | Where-Object { Test-Path $_ } | ForEach-Object { Split-Path -Leaf $_ }) -join "; "
    } else {
        Write-Warning "$rel - $($row.status)$(if ($row.missing) { " (needs: $($row.missing))" })"
        # keep the log next to where the video would have gone
        New-Item -ItemType Directory -Force (Split-Path -Parent $outBase) | Out-Null
        if (Test-Path (Join-Path $work "render.log")) { Copy-Item (Join-Path $work "render.log") "$outBase.render.log" }
    }

    if (-not $KeepFrames) { Remove-Item -Recurse -Force $work }
    $rows += [pscustomobject]$row
    $rows | Export-Csv -NoTypeInformation $report   # rewrite as we go, so a crash leaves a report
}

if (-not $KeepFrames -and (Test-Path $scratch)) { Remove-Item -Recurse -Force $scratch -ErrorAction SilentlyContinue }
$rows | Export-Csv -NoTypeInformation $report
$rows | Group-Object status | ForEach-Object { Write-Host ("{0,-16} {1}" -f $_.Name, $_.Count) }
$missing = $rows | Where-Object { $_.missing } | ForEach-Object { $_.missing -split "; " } | Group-Object |
    Sort-Object Count -Descending
if ($missing) {
    Write-Host "`nContent packs that would unlock more movies:"
    $missing | ForEach-Object { Write-Host ("  {0,4}  {1}" -f $_.Count, $_.Name) }
}
Write-Host "`nReport: $report"
