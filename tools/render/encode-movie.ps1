# Turns one 3dmm-render output folder into finished video files.
#
#   encode-movie.ps1 -RenderDir out\MyMovie -OutBase videos\MyMovie [-Formats 2d,sbs,anaglyph]
#
# Builds the soundtrack first (MIDI rendered with FluidSynth if it and a
# SoundFont are available; otherwise music is left silent and a warning
# printed), then encodes each requested format from timeline.ffconcat:
#   2d        mono render as-is, or the left eye of a stereo render
#   sbs       full side-by-side (left | right), for 3D TVs / players in SBS mode
#   anaglyph  red/cyan
# Returns non-zero if any encode failed.
param(
    [Parameter(Mandatory)] [string]$RenderDir,
    [Parameter(Mandatory)] [string]$OutBase,
    [string[]]$Formats,
    [string]$SoundFont = $env:SOUNDFONT,
    [string]$FluidSynth = "fluidsynth",
    [int]$Scale = 2,
    [int]$Crf = 18
)
$ErrorActionPreference = "Stop"
$RenderDir = (Resolve-Path $RenderDir).Path
$stereo = (Select-String -Path (Join-Path $RenderDir "render.log") -Pattern "^stereo:" -Quiet)
if (-not $Formats) { $Formats = if ($stereo) { @("sbs", "anaglyph", "2d") } else { @("2d") } }
$outDir = Split-Path -Parent $OutBase
if ($outDir) { New-Item -ItemType Directory -Force $outDir | Out-Null }
if (-not $outDir) { $outDir = "." }
$OutBase = Join-Path (Resolve-Path $outDir).Path (Split-Path -Leaf $OutBase)

Push-Location $RenderDir
try {
    # --- soundtrack -------------------------------------------------------
    $haveSynth = $SoundFont -and (Test-Path $SoundFont) -and (Get-Command $FluidSynth -ErrorAction SilentlyContinue)
    foreach ($mid in Get-ChildItem sounds -Filter *.mid -ErrorAction SilentlyContinue) {
        $wav = "$($mid.FullName).wav"
        if (Test-Path $wav) { continue }
        if ($haveSynth) {
            & $FluidSynth -ni -q -g 0.6 -r 44100 -F $wav $SoundFont $mid.FullName | Out-Null
        }
        if (-not (Test-Path $wav)) {
            if (-not $haveSynth) { Write-Warning "no FluidSynth/SoundFont: $($mid.Name) will be silent" }
            ffmpeg -hide_banner -loglevel error -y -f lavfi -i "anullsrc=r=44100:cl=stereo" -t 1 $wav
        }
    }
    $audio = $null
    if (Test-Path audio.ffscript) {
        ffmpeg -hide_banner -loglevel error -y -filter_complex_script audio.ffscript -map "[aout]" -c:a pcm_s16le audio.wav
        if ($LASTEXITCODE -eq 0) { $audio = "audio.wav" } else { Write-Warning "soundtrack mix failed; encoding silent" }
    }

    # --- video ------------------------------------------------------------
    $failed = 0
    foreach ($fmt in $Formats) {
        $vf = switch ($fmt) {
            "2d"       { if ($stereo) { "crop=iw/2:ih:0:0" } else { "null" } }
            "sbs"      { if ($stereo) { "null" } else { $null } }
            "anaglyph" { if ($stereo) { "stereo3d=sbsl:arcd" } else { $null } }
            default    { throw "unknown format $fmt" }
        }
        if (-not $vf) { Write-Warning "$fmt needs a --stereo render; skipped"; continue }
        $vf = "$vf,scale=iw*${Scale}:ih*${Scale}:flags=neighbor,fps=30,format=yuv420p"
        $out = "$OutBase.$fmt.mp4"
        $inputs = @("-f", "concat", "-safe", "0", "-i", "timeline.ffconcat")
        $maps = @("-map", "0:v")
        if ($audio) { $inputs += @("-i", $audio); $maps += @("-map", "1:a", "-c:a", "aac", "-b:a", "192k") }
        ffmpeg -hide_banner -loglevel error -y @inputs -vf $vf @maps -c:v libx264 -crf $Crf -preset medium `
            -movflags +faststart -shortest $out
        if ($LASTEXITCODE -ne 0) { Write-Warning "encode failed: $out"; $failed++ }
    }
} finally {
    Pop-Location
}
exit $failed
