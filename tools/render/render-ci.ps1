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
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -and $env:GH_TOKEN) {
    # chocolatey is occasionally unavailable; fall back to a static build
    $ffDir = Join-Path $build "ffmpeg"
    gh release download latest --repo BtbN/FFmpeg-Builds --pattern "ffmpeg-master-latest-win64-gpl.zip" --dir $ffDir --clobber
    Expand-Archive -Force (Join-Path $ffDir "ffmpeg-master-latest-win64-gpl.zip") $ffDir
    $ffBin = (Get-ChildItem -Recurse $ffDir -Filter ffmpeg.exe | Select-Object -First 1).DirectoryName
    $env:PATH = "$ffBin;$env:PATH"
    if ($env:GITHUB_PATH) { Add-Content -Path $env:GITHUB_PATH -Value $ffBin }
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { throw "no ffmpeg" }
"ffmpeg: $((Get-Command ffmpeg).Source)" | Write-Host

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
    gh release download --repo FluidSynth/fluidsynth --pattern "*win10-x64-cpp11*.zip" --dir $tools --clobber
    Get-ChildItem $tools -Filter *.zip | ForEach-Object { Expand-Archive -Force $_.FullName (Join-Path $tools "fluidsynth") }
    $fluid = Get-ChildItem -Recurse $tools -Filter fluidsynth.exe | Select-Object -First 1
}
$fluidPath = if ($fluid) { $fluid.FullName } else { "fluidsynth" }
"fluidsynth: $fluidPath`nsoundfont: $soundFont $((Get-Item $soundFont -ErrorAction SilentlyContinue).Length)" |
    Tee-Object -FilePath (Join-Path $OutDir "tools.txt") | Write-Host

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
        $rargs += @("--stereo", "--debug")
        if ($StereoMaxFrames -gt 0) { $rargs += @("--max-frames", "$StereoMaxFrames") }
    }

    $sw = [Diagnostics.Stopwatch]::StartNew()
    $proc = Start-Process -FilePath $exe.FullName -PassThru -NoNewWindow -ArgumentList $rargs `
        -RedirectStandardOutput (Join-Path $keepMode "stdout.txt") `
        -RedirectStandardError (Join-Path $keepMode "stderr.txt")
    $null = $proc.Handle   # without this, ExitCode can come back empty
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
        # stereo frames are left | right | 2-D
        $look = if ($mode -eq "stereo") { "crop=iw*2/3:ih:0:0,stereo3d=sbsl:arcd," } else { "" }
        $fmts = if ($mode -eq "stereo") { @("anaglyph", "2d") } else { @("2d") }
        & "$PSScriptRoot/encode-movie.ps1" -RenderDir $rawMode -OutBase (Join-Path $keepMode "preview") `
            -Formats $fmts -SoundFont $soundFont -FluidSynth $fluidPath -Scale 1 -Crf 28 *>&1 |
            Out-File (Join-Path $keepMode "encode.txt")
        Get-ChildItem "$rawMode/sounds" -ErrorAction SilentlyContinue | Select-Object Name, Length |
            Out-File (Join-Path $keepMode "sounds.txt")
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

# --smooth: one movie with blended in-betweens; a strip of consecutive frames
# shows whether the blends look right
$dm = Get-ChildItem $MovieDir -Filter "Hospital.3mm" | Select-Object -First 1
if ($dm) {
    $raw = Join-Path $work "smooth"
    $keep = Join-Path $OutDir "smooth"
    New-Item -ItemType Directory -Force $raw, $keep | Out-Null
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process -FilePath $exe.FullName -PassThru -NoNewWindow -Wait `
        -ArgumentList @("`"$($dm.FullName)`"", "`"$raw`"", "--root", "`"$stage`"", "--smooth") `
        -RedirectStandardOutput (Join-Path $keep "stdout.txt") -RedirectStandardError (Join-Path $keep "stderr.txt")
    "exit $($p.ExitCode) in $([Math]::Round($sw.Elapsed.TotalSeconds, 1)) s" | Out-File (Join-Path $keep "smooth.txt")
    foreach ($f in "render.log", "events.txt", "timeline.ffconcat") { if (Test-Path "$raw/$f") { Copy-Item "$raw/$f" $keep } }
    $frames = @(Get-ChildItem "$raw/frames" -Filter *.bmp -ErrorAction SilentlyContinue | Sort-Object Name)
    if ($frames.Count -gt 16) {
        $list = Join-Path $raw "strip.txt"
        $mid = [int]($frames.Count / 2)
        ($frames[$mid..($mid + 7)] | ForEach-Object { "file '$($_.FullName -replace '\\','/')'" }) | Set-Content $list
        ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i $list -vf "tile=4x2" -frames:v 1 (Join-Path $keep "strip.png")
        & "$PSScriptRoot/encode-movie.ps1" -RenderDir $raw -OutBase (Join-Path $keep "preview") -Formats 2d `
            -SoundFont $soundFont -FluidSynth $fluidPath -Scale 1 -Crf 28 *>&1 | Out-File (Join-Path $keep "encode.txt")
    }
}

# CRT effects: full-res stills for each preset, and a short encode
$crtExe = Get-ChildItem -Recurse $build -Filter 3dmm-crt.exe | Select-Object -First 1
$firstMono = Get-ChildItem $work -Directory | Select-Object -First 1
if ($crtExe -and $firstMono) {
    $monoDir = Join-Path $firstMono.FullName "mono"
    $nframes = @(Get-ChildItem "$monoDir/frames" -Filter *.bmp).Count
    $pick = [int]($nframes * 0.6)
    foreach ($preset in "pc", "trinitron", "tv", "hdr") {
        & $crtExe.FullName $monoDir --preset $preset --frame $pick (Join-Path $work "crt-$preset.bmp") 2>&1 |
            Out-File -Append (Join-Path $OutDir "crt-check.txt")
        ffmpeg -hide_banner -loglevel error -y -i (Join-Path $work "crt-$preset.bmp") (Join-Path $OutDir "crt-$preset.png")
    }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    & "$PSScriptRoot/encode-movie.ps1" -RenderDir $monoDir -OutBase (Join-Path $OutDir "crt-preview") -Formats crt `
        -SoundFont $soundFont -FluidSynth $fluidPath -CrtTool $crtExe.FullName -CrtMaxFrames 90 -Crf 24 *>&1 |
        Out-File -Append (Join-Path $OutDir "crt-check.txt")
    "crt encode: $([Math]::Round($sw.Elapsed.TotalSeconds, 1)) s for 90 frames" | Out-File -Append (Join-Path $OutDir "crt-check.txt")
}

# CRT from a stereo render: CRT effects are 2-D only, so it must use the
# 2-D view (third panel), not an eye
if ($crtExe -and $firstMono) {
    $stereoDir = Join-Path $firstMono.FullName "stereo"
    & $crtExe.FullName $stereoDir --frame 40 (Join-Path $work "crt-stereo.bmp") 2>&1 |
        Out-File -Append (Join-Path $OutDir "crt-check.txt")
    ffmpeg -hide_banner -loglevel error -y -i (Join-Path $work "crt-stereo.bmp") -vf scale=1280:-1 (Join-Path $OutDir "crt-stereo.png")
}

# AVI for Windows 95/98 (Cinepak) and sound extraction
$extras = Join-Path $OutDir "extras"
New-Item -ItemType Directory -Force $extras | Out-Null
$extrasLog = Join-Path $extras "extras.txt"
foreach ($case in @(@{ dir = "City-Tour"; formats = "avi" }, @{ dir = "Hospital"; formats = "none" })) {
    $src = Join-Path $work "$($case.dir)/mono"
    if (-not (Test-Path $src)) { continue }
    $base = Join-Path $extras $case.dir
    $sw = [Diagnostics.Stopwatch]::StartNew()
    & "$PSScriptRoot/encode-movie.ps1" -RenderDir $src -OutBase $base -Formats $case.formats -ExtractSounds `
        -SoundFont $soundFont -FluidSynth $fluidPath *>&1 | Out-File -Append $extrasLog
    "$($case.dir): $([Math]::Round($sw.Elapsed.TotalSeconds, 1)) s" | Out-File -Append $extrasLog
    if (Test-Path "$base.avi") {
        ffprobe -v error -count_packets -show_entries stream=codec_name,codec_tag_string,width,height,r_frame_rate,nb_frames,nb_read_packets,sample_rate,channels:format=duration,size `
            -of compact "$base.avi" 2>&1 | Out-File -Append $extrasLog
    }
    Copy-Item (Join-Path $src "sounds/index.tsv") "$base.index.tsv" -ErrorAction SilentlyContinue
    if (Test-Path "$base.sounds.zip") {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [IO.Compression.ZipFile]::OpenRead("$base.sounds.zip")
        $zip.Entries | ForEach-Object { "  {0,9}  {1}" -f $_.Length, $_.FullName } | Out-File -Append $extrasLog
        $zip.Dispose()
    }
}

# the Windows GS synth's instruments, through FluidSynth's DLS loader
$gmdls = Join-Path $env:WINDIR "System32\drivers\gm.dls"
$first = Get-ChildItem $work -Directory | Select-Object -First 1
if ((Test-Path $gmdls) -and $first) {
    & "$PSScriptRoot/encode-movie.ps1" -RenderDir (Join-Path $first.FullName "mono") `
        -OutBase (Join-Path $OutDir "gm-dls-check") -Formats 2d -SoundFont windows -FluidSynth $fluidPath -Scale 1 -Crf 30 *>&1 |
        Out-File (Join-Path $OutDir "gm-dls-check.txt")
} else {
    "no gm.dls on this machine" | Out-File (Join-Path $OutDir "gm-dls-check.txt")
}

# font handling: a copy of a movie whose text box asks for "Courier Prime"
# (not installed on Windows), rendered without and then with -fonts
$src = Join-Path $MovieDir "Hospital.3mm"
if (Test-Path $src) {
    $ft = Join-Path $work "fonttest"
    $fontDir = Join-Path $ft "fonts"
    New-Item -ItemType Directory -Force $fontDir | Out-Null
    $latin1 = [Text.Encoding]::GetEncoding(28591)
    $text = $latin1.GetString([IO.File]::ReadAllBytes((Resolve-Path $src).Path)).Replace("Comic Sans MS", "Courier Prime")
    $movie = Join-Path $ft "FontTest.3mm"
    [IO.File]::WriteAllBytes($movie, $latin1.GetBytes($text))
    Invoke-WebRequest -UseBasicParsing -OutFile (Join-Path $fontDir "CourierPrime-Regular.ttf") `
        "https://raw.githubusercontent.com/google/fonts/main/ofl/courierprime/CourierPrime-Regular.ttf"
    $report = @()
    foreach ($case in "without", "with") {
        $out = Join-Path $ft $case
        $fargs = @("`"$movie`"", "`"$out`"", "--root", "`"$stage`"")
        if ($case -eq "with") { $fargs += @("--fonts", "`"$fontDir`"") }
        $p = Start-Process -FilePath $exe.FullName -ArgumentList $fargs -PassThru -NoNewWindow -Wait
        $report += "== $case -fonts (exit $($p.ExitCode))"
        $report += @(Select-String -Path "$out/events.txt" -Pattern "missing-font|textbox" | ForEach-Object { $_.Line })
        $report += @(Select-String -Path "$out/render.log" -Pattern "^fonts:|loaded .* font|missing font" | ForEach-Object { $_.Line })
        $last = Get-ChildItem "$out/frames" -Filter *.bmp | Sort-Object Name | Select-Object -Last 1
        if ($last) { ffmpeg -hide_banner -loglevel error -y -i $last.FullName (Join-Path $OutDir "font-$case.png") }
    }
    $report | Out-File (Join-Path $OutDir "font-check.txt")
}

$summary | Export-Csv -NoTypeInformation (Join-Path $OutDir "summary.csv")
$summary | Format-Table | Out-String | Write-Host
