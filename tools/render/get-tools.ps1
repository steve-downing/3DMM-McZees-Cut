# Downloads what render-folder.ps1 needs for music into .\tools next to
# this script: FluidSynth (MIDI synthesizer) and the GeneralUser GS
# General MIDI SoundFont. ffmpeg you install yourself, e.g.:
#     winget install Gyan.FFmpeg
# Works in Windows PowerShell 5.1 and PowerShell 7.
param(
    [string]$ToolsDir = (Join-Path $PSScriptRoot "tools")
)
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
New-Item -ItemType Directory -Force $ToolsDir | Out-Null

$sf2 = Join-Path $ToolsDir "GeneralUser-GS.sf2"
if (-not (Test-Path $sf2)) {
    Write-Host "Downloading GeneralUser GS SoundFont..."
    Invoke-WebRequest -UseBasicParsing -OutFile $sf2 `
        "https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/main/GeneralUser-GS.sf2"
}

if (-not (Get-ChildItem -Recurse $ToolsDir -Filter fluidsynth.exe -ErrorAction SilentlyContinue)) {
    Write-Host "Downloading FluidSynth..."
    $release = Invoke-RestMethod -UseBasicParsing "https://api.github.com/repos/FluidSynth/fluidsynth/releases/latest"
    $asset = $release.assets | Where-Object { $_.name -like "*win10-x64*.zip" } | Select-Object -First 1
    if (-not $asset) { throw "couldn't find a Windows x64 FluidSynth build in $($release.tag_name)" }
    $zip = Join-Path $ToolsDir $asset.name
    Invoke-WebRequest -UseBasicParsing -OutFile $zip $asset.browser_download_url
    Expand-Archive -Force $zip (Join-Path $ToolsDir "fluidsynth")
    Remove-Item $zip
}

$fs = Get-ChildItem -Recurse $ToolsDir -Filter fluidsynth.exe | Select-Object -First 1
Write-Host "FluidSynth: $($fs.FullName)"
Write-Host "SoundFont:  $sf2"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Warning "ffmpeg isn't on PATH yet (try: winget install Gyan.FFmpeg)"
}
