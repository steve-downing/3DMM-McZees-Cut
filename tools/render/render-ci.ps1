# Renders every .3mm in -MovieDir with 3dmm-render and collects small,
# reviewable outputs (logs, contact sheet, sample frames, preview mp4) in
# -OutDir. Used by CI; also handy locally after a build.
param(
    [string]$BuildDir = "build",
    [string]$MovieDir = "test-movies",
    [string]$OutDir = "ci-out/render",
    [int]$TimeoutSeconds = 900,
    # stereo pass is capped so CI stays quick; 0 = whole movie
    [int]$StereoMaxFrames = 300
)
$ErrorActionPreference = "Stop"

$repo = Resolve-Path "$PSScriptRoot/../.."
$build = Resolve-Path $BuildDir
New-Item -ItemType Directory -Force $OutDir | Out-Null
$OutDir = Resolve-Path $OutDir

# Stage a content root: <stage>\3D Movie Maker\{*.3cn, *.3th, 3DMovie.chk}
$stage = Join-Path $build "stage"
$product = Join-Path $stage "3D Movie Maker"
New-Item -ItemType Directory -Force $product | Out-Null
Copy-Item "$repo/content-files/*.3cn", "$repo/content-files/*.3th" $product
$chk = Get-ChildItem -Recurse "$build/chomp/studio" -Filter "utest.chk" | Select-Object -First 1
if (-not $chk) { throw "utest.chk (3DMovie.chk) was not built" }
Copy-Item $chk.FullName (Join-Path $product "3DMovie.chk")
$exe = Get-ChildItem -Recurse $build -Filter "3dmm-render.exe" | Select-Object -First 1
if (-not $exe) { throw "3dmm-render.exe was not built" }

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    choco install ffmpeg -y --no-progress | Out-Null
    $env:PATH = "C:\ProgramData\chocolatey\bin;$env:PATH"
}

# FluidSynth + a General MIDI SoundFont, for the music
$tools = Join-Path $build "tools"
New-Item -ItemType Directory -Force $tools | Out-Null
$soundFont = Join-Path $tools "GeneralUser-GS.sf2"
if (-not (Test-Path $soundFont)) {
    Invoke-WebRequest -UseBasicParsing -OutFile $soundFont `
        "https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/main/GeneralUser-GS.sf2"
}
$fluid = Get-ChildItem -Recurse $tools -Filter fluidsynth.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $fluid -and $env:GH_TOKEN) {
    gh release download --repo FluidSynth/fluidsynth --pattern "*win10-x64*.zip" --dir $tools --clobber
    Get-ChildItem $tools -Filter *.zip | ForEach-Object { Expand-Archive -Force $_.FullName (Join-Path $tools "fluidsynth") }
    $fluid = Get-ChildItem -Recurse $tools -Filter fluidsynth.exe | Select-Object -First 1
}
$fluidPath = if ($fluid) { $fluid.FullName } else { "fluidsynth" }
Write-Host "fluidsynth: $fluidPath"

$work = Join-Path $env:RUNNER_TEMP "render-work"
if (-not $env:RUNNER_TEMP) { $work = Join-Path $build "render-work" }
$summary = @()

foreach ($movie in Get-ChildItem $MovieDir -Filter *.3mm) {
    $name = $movie.BaseName -replace '[^A-Za-z0-9]+', '-'
    $raw = Join-Path $work $name
    $keep = Join-Path $OutDir $name

    foreach ($mode in "mono", "stereo") {
    $rawMode = Join-Path $raw $mode
    $keepMode = Join-Path $keep $mode
    New-Item -ItemType Directory -Force $rawMode, $keepMode | Out-Null
    $rargs = @("`"$($movie.FullName)`"", "`"$rawMode`"", "--root", "`"$stage`"")
    if ($mode -eq "stereo") {
        $rargs += "--stereo"
        if ($StereoMaxFrames -gt 0) { $rargs += @("--max-frames", "$StereoMaxFrames") }
    }

    $sw = [Diagnostics.Stopwatch]::StartNew()
    $proc = Start-Process -FilePath $exe.FullName -PassThru -NoNewWindow -ArgumentList $rargs `
        -RedirectStandardOutput (Join-Path $keepMode "stdout.txt") `
        -RedirectStandardError (Join-Path $keepMode "stderr.txt")
    if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
        $proc.Kill()
        $code = "timeout"
    } else {
        $code = $proc.ExitCode
    }
    $sw.Stop()

    foreach ($f in "render.log", "events.txt", "timeline.ffconcat") {
        if (Test-Path "$rawMode/$f") { Copy-Item "$rawMode/$f" $keepMode }
    }
    $frames = @(Get-ChildItem "$rawMode/frames" -Filter *.bmp -ErrorAction SilentlyContinue)

    if ($frames.Count -gt 0 -and (Test-Path "$rawMode/timeline.ffconcat")) {
        $look = if ($mode -eq "stereo") { "stereo3d=sbsl:arcd," } else { "" }
        $fmts = if ($mode -eq "stereo") { @("anaglyph") } else { @("2d") }
        & "$PSScriptRoot/encode-movie.ps1" -RenderDir $rawMode -OutBase (Join-Path $keepMode "preview") `
            -Formats $fmts -SoundFont $soundFont -FluidSynth $fluidPath -Scale 1 -Crf 28
        foreach ($f in "audio.ffscript") {
            if (Test-Path "$rawMode/$f") { Copy-Item "$rawMode/$f" $keepMode }
        }
        # contact sheet of 16 evenly spaced distinct frames, plus 3 full-size samples
        $step = [int][Math]::Max(1, [Math]::Floor($frames.Count / 16))
        $pick = for ($i = 0; $i -lt 16 -and $i * $step -lt $frames.Count; $i++) { $frames[$i * $step] }
        $list = Join-Path $rawMode "contact.txt"
        ($pick | ForEach-Object { "file '$($_.FullName -replace '\\','/')'" }) | Set-Content $list
        ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i $list `
            -vf "${look}scale=272:153,tile=4x4" -frames:v 1 (Join-Path $keepMode "contact.png")
        foreach ($i in @(0, [int][Math]::Floor($frames.Count / 2), ($frames.Count - 1))) {
            ffmpeg -hide_banner -loglevel error -y -i $frames[$i].FullName (Join-Path $keepMode ("frame-{0:D6}.png" -f $i))
        }
        # stereo depth diagnostics (16-bit PGM -> PNG)
        foreach ($pgm in Get-ChildItem $rawMode -Filter "depth-*.pgm" -ErrorAction SilentlyContinue) {
            ffmpeg -hide_banner -loglevel error -y -i $pgm.FullName (Join-Path $keepMode ($pgm.BaseName + ".png"))
        }
    }

    $summary += [pscustomobject]@{
        movie = $movie.Name
        mode = $mode
        exit = $code
        frames = $frames.Count
        seconds = [Math]::Round($sw.Elapsed.TotalSeconds, 1)
    }
    }
}

$summary | Export-Csv -NoTypeInformation (Join-Path $OutDir "summary.csv")
$summary | Format-Table | Out-String | Write-Host
