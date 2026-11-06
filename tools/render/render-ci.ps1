# Renders every .3mm in -MovieDir with 3dmm-render and collects small,
# reviewable outputs (logs, contact sheet, sample frames, preview mp4) in
# -OutDir. Used by CI; also handy locally after a build.
param(
    [string]$BuildDir = "build",
    [string]$MovieDir = "test-movies",
    [string]$OutDir = "ci-out/render",
    [int]$TimeoutSeconds = 900
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

$work = Join-Path $env:RUNNER_TEMP "render-work"
if (-not $env:RUNNER_TEMP) { $work = Join-Path $build "render-work" }
$summary = @()

foreach ($movie in Get-ChildItem $MovieDir -Filter *.3mm) {
    $name = $movie.BaseName -replace '[^A-Za-z0-9]+', '-'
    $raw = Join-Path $work $name
    $keep = Join-Path $OutDir $name
    New-Item -ItemType Directory -Force $raw, $keep | Out-Null

    $sw = [Diagnostics.Stopwatch]::StartNew()
    $proc = Start-Process -FilePath $exe.FullName -PassThru -NoNewWindow `
        -ArgumentList @("`"$($movie.FullName)`"", "`"$raw`"", "--root", "`"$stage`"") `
        -RedirectStandardOutput (Join-Path $keep "stdout.txt") `
        -RedirectStandardError (Join-Path $keep "stderr.txt")
    if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
        $proc.Kill()
        $code = "timeout"
    } else {
        $code = $proc.ExitCode
    }
    $sw.Stop()

    foreach ($f in "render.log", "events.txt", "timeline.ffconcat") {
        if (Test-Path "$raw/$f") { Copy-Item "$raw/$f" $keep }
    }
    $frames = @(Get-ChildItem "$raw/frames" -Filter *.bmp -ErrorAction SilentlyContinue)

    if ($frames.Count -gt 0 -and (Test-Path "$raw/timeline.ffconcat")) {
        Push-Location $raw
        ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i timeline.ffconcat `
            -vf "fps=30,format=yuv420p" -c:v libx264 -crf 26 -preset veryfast (Join-Path $keep "preview.mp4")
        Pop-Location
        # contact sheet of 16 evenly spaced distinct frames, plus 3 full-size samples
        $step = [Math]::Max(1, [Math]::Floor($frames.Count / 16))
        $pick = for ($i = 0; $i -lt 16 -and $i * $step -lt $frames.Count; $i++) { $frames[$i * $step] }
        $list = Join-Path $raw "contact.txt"
        ($pick | ForEach-Object { "file '$($_.FullName -replace '\\','/')'" }) | Set-Content $list
        ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i $list `
            -vf "scale=272:153,tile=4x4" -frames:v 1 (Join-Path $keep "contact.png")
        foreach ($i in 0, [Math]::Floor($frames.Count / 2), ($frames.Count - 1)) {
            ffmpeg -hide_banner -loglevel error -y -i $frames[$i].FullName (Join-Path $keep ("frame-{0:D6}.png" -f $i))
        }
    }

    $summary += [pscustomobject]@{
        movie = $movie.Name
        exit = $code
        frames = $frames.Count
        seconds = [Math]::Round($sw.Elapsed.TotalSeconds, 1)
    }
}

$summary | Export-Csv -NoTypeInformation (Join-Path $OutDir "summary.csv")
$summary | Format-Table | Out-String | Write-Host
