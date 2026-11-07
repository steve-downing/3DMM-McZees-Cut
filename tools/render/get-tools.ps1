# Downloads what render-folder.ps1 needs into .\tools next to this script:
#   * ffmpeg (video encoding), unless it's already on PATH
#   * FluidSynth (plays MIDI music) and the GeneralUser GS General MIDI SoundFont
# Run it once; it skips anything already there. The McZee's Cut app runs it
# for you the first time.
# Works in Windows PowerShell 5.1 and PowerShell 7.
param(
    [string]$ToolsDir = (Join-Path $PSScriptRoot "tools")
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Windows PowerShell's progress bar makes downloads crawl
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
New-Item -ItemType Directory -Force $ToolsDir | Out-Null

function Get-Release([string]$Repo) {
    Invoke-RestMethod -UseBasicParsing "https://api.github.com/repos/$Repo/releases/latest"
}

$haveFfmpeg = (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or
    (Get-ChildItem -Recurse $ToolsDir -Filter ffmpeg.exe -ErrorAction SilentlyContinue)
if (-not $haveFfmpeg) {
    Write-Host "Downloading ffmpeg (about 150 MB)..."
    # BtbN's Windows builds; the GPL build has the x264/x265 encoders
    $url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    try {
        $asset = (Get-Release "BtbN/FFmpeg-Builds").assets |
            Where-Object { $_.name -match '^ffmpeg-n[\d\.]+-latest-win64-gpl-[\d\.]+\.zip$' } | Select-Object -First 1
        if ($asset) { $url = $asset.browser_download_url }
    } catch { }
    $zip = Join-Path $ToolsDir "ffmpeg.zip"
    Invoke-WebRequest -UseBasicParsing -OutFile $zip $url
    Write-Host "Unpacking ffmpeg..."
    Expand-Archive -Force $zip (Join-Path $ToolsDir "ffmpeg")
    Remove-Item $zip
}

$sf2 = Join-Path $ToolsDir "GeneralUser-GS.sf2"
if (-not (Test-Path $sf2)) {
    Write-Host "Downloading the GeneralUser GS instruments (about 30 MB)..."
    Invoke-WebRequest -UseBasicParsing -OutFile $sf2 `
        "https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/main/GeneralUser-GS.sf2"
}

if (-not (Get-ChildItem -Recurse $ToolsDir -Filter fluidsynth.exe -ErrorAction SilentlyContinue)) {
    Write-Host "Downloading FluidSynth..."
    $release = Get-Release "FluidSynth/fluidsynth"
    # prefer the cpp11 build: it reads DLS files (e.g. Windows' gm.dls) natively
    $asset = @($release.assets | Where-Object { $_.name -like "*win10-x64-cpp11*.zip" }) +
             @($release.assets | Where-Object { $_.name -like "*win10-x64*.zip" }) | Select-Object -First 1
    if (-not $asset) { throw "couldn't find a Windows x64 FluidSynth build in $($release.tag_name)" }
    $zip = Join-Path $ToolsDir $asset.name
    Invoke-WebRequest -UseBasicParsing -OutFile $zip $asset.browser_download_url
    Expand-Archive -Force $zip (Join-Path $ToolsDir "fluidsynth")
    Remove-Item $zip
}

$ff = Get-Command ffmpeg -ErrorAction SilentlyContinue
$ffPath = if ($ff) { $ff.Source } else { (Get-ChildItem -Recurse $ToolsDir -Filter ffmpeg.exe | Select-Object -First 1).FullName }
$fs = Get-ChildItem -Recurse $ToolsDir -Filter fluidsynth.exe | Select-Object -First 1
Write-Host "ffmpeg:     $ffPath"
Write-Host "FluidSynth: $($fs.FullName)"
Write-Host "SoundFont:  $sf2"
