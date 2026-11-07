# Batch-converts every .3mm under a folder into video files.
#
#   render-folder.ps1 -InputDir D:\3mm-archive -OutputDir D:\3mm-videos [-Smooth] [-Formats 2d,sbs,...]
#
# -Formats picks the outputs (default 2d, the plain Movie.mp4); asking for
# sbs or anaglyph renders the movie in 3D. See README.md for every option.
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
    [string]$Root,
    [string]$Renderer,
    [switch]$Smooth,
    [double]$Depth = 2.5,
    [string[]]$Formats,
    [string]$SoundFont = $env:SOUNDFONT,
    [string]$FluidSynth,
    [double]$MidiGain = 0.6,
    [ValidateSet("auto", "original")] [string]$AudioLevel = "auto",
    [switch]$Duck,
    [ValidateSet("both", "stereo", "5.1")] [string]$Channels = "both",
    [double]$ClickPause = 3,
    [double]$EndHold = 3,
    [string]$Fonts,
    [int]$TimeoutMinutes = 30,
    [int]$Scale = 2,
    [ValidateSet("pc", "trinitron", "tv", "hdr")] [string]$CrtPreset = "pc",
    [ValidateSet("", "shadow", "grille", "slot", "none")] [string]$CrtMask = "",
    [double]$CrtScanlines = -1,
    [double]$CrtGlow = -1,
    [double]$CrtCurvature = -1,
    [ValidateSet("420", "444")] [string]$CrtChroma = "420",
    [switch]$ExtractSounds,
    [switch]$IncludeLibrarySounds,
    [switch]$KeepFrames,
    [switch]$Force,
    # for Movie Exporter's progress bar: prints "@progress render <percent>"
    # while a movie renders and "@duration_ms <n>" after, and has the video
    # encode write ffmpeg's -progress reports to -ProgressFile
    [switch]$Progress,
    [string]$ProgressFile
)
$ErrorActionPreference = "Stop"

# regex matches in a file another process is still writing
function Read-Matches([string]$Path, [string]$Pattern) {
    try {
        $fs = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        try { $text = (New-Object IO.StreamReader($fs)).ReadToEnd() } finally { $fs.Dispose() }
        return ,([regex]::Matches($text, $Pattern))
    } catch { return @() }
}
# "-Formats a,b" arrives as one string when run with powershell -File
if ($Formats) { $Formats = @($Formats | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }

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

# content: McZee's Cut ships "Microsoft Kids\3D Movie Maker" next to the
# renderer (older packages: just "3D Movie Maker"); otherwise fall back to a
# regular 3DMM install
if (-not $Root) {
    $here = Split-Path -Parent (Resolve-Path $Renderer)
    $Root = @($here, (Join-Path $here "Microsoft Kids"), "C:\Program Files (x86)\Microsoft Kids",
        "C:\Program Files\Microsoft Kids") | Where-Object { Test-Path (Join-Path $_ "3D Movie Maker") } |
        Select-Object -First 1
}

# music tools: get-tools.ps1 puts them in .\tools
$toolsDir = Join-Path $PSScriptRoot "tools"
if (-not $FluidSynth) {
    $fs = Get-ChildItem -Recurse $toolsDir -Filter fluidsynth.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    $FluidSynth = if ($fs) { $fs.FullName } else { "fluidsynth" }
}
if ($SoundFont -eq "windows") { $SoundFont = Join-Path $env:WINDIR "System32\drivers\gm.dls" }
if ($SoundFont -and -not (Test-Path $SoundFont)) { throw "SoundFont not found: $SoundFont" }
if (-not $SoundFont -and (Test-Path (Join-Path $toolsDir "GeneralUser-GS.sf2"))) {
    $SoundFont = Join-Path $toolsDir "GeneralUser-GS.sf2"
}
if (-not $SoundFont -or -not (Get-Command $FluidSynth -ErrorAction SilentlyContinue)) {
    Write-Warning "No FluidSynth/SoundFont: MIDI music will be silent. Run get-tools.ps1 to fetch them."
}
# ffmpeg: on PATH, or fetched into .\tools by get-tools.ps1
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    $ffLocal = Get-ChildItem -Recurse (Join-Path $PSScriptRoot "tools") -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($ffLocal) { $env:PATH = "$($ffLocal.DirectoryName);$env:PATH" }
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { throw "can't find ffmpeg: run get-tools.ps1, or install it (winget install Gyan.FFmpeg)" }
if (-not $Root -or -not (Test-Path (Join-Path $Root "3D Movie Maker"))) {
    throw "can't find a '3D Movie Maker' content folder; pass -Root (the folder that contains it)"
}
if (-not $Formats) { $Formats = @("2d") }
$known = "2d", "sbs", "anaglyph", "crt", "avi", "none"
$unknown = @($Formats | Where-Object { $known -notcontains $_ })
if ($unknown) { throw "unknown format(s): $($unknown -join ', ') (use $($known -join ', '))" }
# 3D formats need the movie rendered from two cameras; everything else uses the 2-D view
$Stereo = ($Formats -contains "sbs") -or ($Formats -contains "anaglyph")

$InputDir = (Resolve-Path $InputDir).Path.TrimEnd('\')
if ($Fonts) { $Fonts = (Resolve-Path $Fonts).Path.TrimEnd('\') }
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
    $relBase = $rel.Substring(0, $rel.Length - $movie.Extension.Length)
    $outBase = Join-Path $OutputDir $relBase
    $outputs = @($Formats | ForEach-Object {
            switch ($_) { "2d" { "$outBase.mp4" } "avi" { "$outBase.avi" } "none" { } default { "$outBase.$_.mp4" } } })
    if ($ExtractSounds) { $outputs += "$outBase.sounds.zip" }
    $row = [ordered]@{ movie = $rel; status = ""; exit = ""; frames = ""; seconds = ""; missing = ""; missingFonts = ""; outputs = "" }

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

    $rargs = @("`"$($movie.FullName)`"", "`"$work`"", "--root", "`"$Root`"", "--click-pause", "$ClickPause", "--end-hold", "$EndHold")
    if ($Stereo) { $rargs += @("--stereo", "--depth", "$Depth") }
    if ($Smooth) { $rargs += "--smooth" }
    if ($Progress) { $rargs += "--progress" }
    if ($Fonts) { $rargs += @("--fonts", "`"$Fonts`"") }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $proc = Start-Process -FilePath $Renderer -ArgumentList $rargs -PassThru -NoNewWindow `
        -RedirectStandardOutput (Join-Path $work "stdout.txt") -RedirectStandardError (Join-Path $work "stderr.txt")
    $null = $proc.Handle   # without this, ExitCode can come back empty
    $stdout = Join-Path $work "stdout.txt"
    $deadline = [DateTime]::Now.AddMinutes($TimeoutMinutes)
    $lastPct = -1
    $finished = $false
    while (-not $finished -and [DateTime]::Now -lt $deadline) {
        $finished = $proc.WaitForExit(500)
        if ($Progress) {
            $m = Read-Matches $stdout 'progress (\d+)'
            if ($m.Count -and [int]$m[$m.Count - 1].Groups[1].Value -ne $lastPct) {
                $lastPct = [int]$m[$m.Count - 1].Groups[1].Value
                Write-Host "@progress render $lastPct"
            }
        }
    }
    if ($Progress) {
        $m = Read-Matches $stdout 'duration_ms (\d+)'
        if ($m.Count) { Write-Host "@duration_ms $($m[0].Groups[1].Value)" }
    }
    if (-not $finished) {
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
        $row.missingFonts = (Select-String -Path $events -Pattern "missing-font (.*)$" |
                ForEach-Object { $_.Matches[0].Groups[1].Value } | Sort-Object -Unique) -join "; "
    }

    if ($row.status -eq "ok") {
        New-Item -ItemType Directory -Force (Split-Path -Parent $outBase) | Out-Null
        & $encoder -RenderDir $work -OutBase $outBase -Formats $Formats -SoundFont $SoundFont -ProgressFile $ProgressFile `
            -FluidSynth $FluidSynth -MidiGain $MidiGain -AudioLevel $AudioLevel -Duck:$Duck -Channels $Channels -Scale $Scale `
            -CrtPreset $CrtPreset -CrtMask $CrtMask -CrtScanlines $CrtScanlines -CrtGlow $CrtGlow `
            -CrtCurvature $CrtCurvature -CrtChroma $CrtChroma -ExtractSounds:$ExtractSounds `
            -IncludeLibrarySounds:$IncludeLibrarySounds
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
$missingFonts = $rows | Where-Object { $_.missingFonts } | ForEach-Object { $_.missingFonts -split "; " } |
    Group-Object | Sort-Object Count -Descending
if ($missingFonts) {
    Write-Host "`nFonts that weren't available (text fell back to the system font):"
    $missingFonts | ForEach-Object { Write-Host ("  {0,4}  {1}" -f $_.Count, $_.Name) }
    Write-Host "Put the font files in a folder and pass -Fonts <folder>."
}
Write-Host "`nReport: $report"
