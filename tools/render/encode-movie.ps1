# Turns one 3dmm-render output folder into finished video files.
#
#   encode-movie.ps1 -RenderDir out\MyMovie -OutBase videos\MyMovie [-Formats 2d,sbs,anaglyph]
#
# Builds the soundtrack first (MIDI rendered with FluidSynth if it and a
# SoundFont are available; otherwise music is left silent and a warning
# printed), then encodes each requested format from timeline.ffconcat:
#
# -AudioLevel auto (default) levels each music track against the dialogue,
# ducks music under speech and normalizes loudness; "original" keeps the
# raw mix. -Channels both (default) writes a 5.1 Dolby Digital track
# (dialogue in the center) plus a stereo AAC track. Levels go in render.log,
# which is copied next to the videos as <name>.log.
#
# -SoundFont takes a .sf2/.sf3 SoundFont or a .dls file (e.g. an SC-55
# SoundFont), or the word "windows" for the Microsoft GS Wavetable Synth's
# own instruments (%WINDIR%\System32\drivers\gm.dls). DLS needs a FluidSynth
# build with native DLS support (the "cpp11" Windows builds have it).
#
#   2d        mono render as-is, or the left eye of a stereo render
#   sbs       full side-by-side (left | right), for 3D TVs / players in SBS mode
#   anaglyph  red/cyan
#   crt       2d with CRT effects, 4K (see -CrtPreset; needs 3dmm-crt.exe)
# Returns non-zero if any encode failed.
param(
    [Parameter(Mandatory)] [string]$RenderDir,
    [Parameter(Mandatory)] [string]$OutBase,
    [string[]]$Formats,
    [string]$SoundFont = $env:SOUNDFONT,
    [string]$FluidSynth = "fluidsynth",
    [double]$MidiGain = 0.6,
    [ValidateSet("auto", "original")] [string]$AudioLevel = "auto",
    [ValidateSet("both", "stereo", "5.1")] [string]$Channels = "both",
    [int]$Scale = 2,
    [int]$Crf = 18,
    # CRT effects (the "crt" format): see 3dmm-crt.exe
    [ValidateSet("pc", "trinitron", "tv", "hdr")] [string]$CrtPreset = "pc",
    [ValidateSet("", "shadow", "grille", "slot", "none")] [string]$CrtMask = "",
    [double]$CrtScanlines = -1,
    [double]$CrtGlow = -1,
    [double]$CrtCurvature = -1,
    [ValidateSet("420", "444")] [string]$CrtChroma = "420",
    [int]$CrtMaxFrames = 0,
    [string]$CrtTool
)
$ErrorActionPreference = "Stop"
# "-Formats a,b" arrives as one string when run with powershell -File
if ($Formats) { $Formats = @($Formats | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }
$RenderDir = (Resolve-Path $RenderDir).Path
if ($SoundFont -eq "windows") { $SoundFont = Join-Path $env:WINDIR "System32\drivers\gm.dls" }
if ($SoundFont -and -not (Test-Path $SoundFont)) { Write-Warning "SoundFont not found: $SoundFont" }
if ($SoundFont) { $SoundFont = (Resolve-Path $SoundFont -ErrorAction SilentlyContinue).Path }
$stereo = (Select-String -Path (Join-Path $RenderDir "render.log") -Pattern "^stereo:" -Quiet)
if (-not $Formats) { $Formats = if ($stereo) { @("sbs", "anaglyph", "2d") } else { @("2d") } }
$outDir = Split-Path -Parent $OutBase
if ($outDir) { New-Item -ItemType Directory -Force $outDir | Out-Null }
if (-not $outDir) { $outDir = "." }
$OutBase = Join-Path (Resolve-Path $outDir).Path (Split-Path -Leaf $OutBase)

# The "crt" format: 3dmm-crt.exe draws each frame as a 4K CRT image and
# streams raw video to ffmpeg. Runs through a .cmd file so the binary pipe
# works the same in Windows PowerShell 5.1 and PowerShell 7.
function Invoke-CrtEncode([string]$Out) {
    $tool = $CrtTool
    if (-not $tool) {
        $tool = @((Join-Path $PSScriptRoot "3dmm-crt.exe"), (Join-Path $PSScriptRoot "..\..\build\3dmm-crt.exe")) |
            Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if (-not $tool) { Write-Warning "can't find 3dmm-crt.exe (pass -CrtTool)"; return $false }
    $crtArgs = @("--preset", $CrtPreset)
    if ($CrtMask) { $crtArgs += @("--mask", $CrtMask) }
    if ($CrtScanlines -ge 0) { $crtArgs += @("--scanlines", "$CrtScanlines") }
    if ($CrtGlow -ge 0) { $crtArgs += @("--glow", "$CrtGlow") }
    if ($CrtCurvature -ge 0) { $crtArgs += @("--curvature", "$CrtCurvature") }
    if ($CrtMaxFrames -gt 0) { $crtArgs += @("--max-frames", "$CrtMaxFrames") }
    $info = (& $tool $RenderDir --info @crtArgs) -split " "
    $q = { param($a) if ($a -match '[\s&|<>^]') { '"' + $a + '"' } else { $a } }
    $video = if ($CrtPreset -eq "hdr") {
        # 10-bit HDR10: BT.2020 primaries, PQ transfer
        @("-vf", "scale=out_color_matrix=bt2020nc:out_range=tv,format=yuv420p10le", "-c:v", "libx265", "-crf", "$Crf",
            "-preset", "medium", "-tag:v", "hvc1", "-color_primaries", "bt2020", "-color_trc", "smpte2084",
            "-colorspace", "bt2020nc", "-x265-params",
            "hdr10=1:repeat-headers=1:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:max-cll=1000,400:master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1)")
    } else {
        # 4:2:0 plays everywhere but softens the phosphor colors; 4:4:4 keeps them
        $pf = if ($CrtChroma -eq "444") { "yuv444p" } else { "yuv420p" }
        @("-vf", "format=$pf", "-c:v", "libx264", "-crf", "$Crf", "-preset", "medium")
    }
    $ff = @("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", $info[2],
        "-s", "$($info[0])x$($info[1])", "-r", $info[3], "-i", "-") + $audioInputs + @("-map", "0:v") + $audioMaps +
        $video + @("-movflags", "+faststart", "-shortest", $Out)
    $line = ((@($tool, $RenderDir) + $crtArgs | ForEach-Object { & $q $_ }) -join " ") + " | " +
        (($ff | ForEach-Object { & $q $_ }) -join " ")
    $cmdFile = Join-Path $RenderDir "crt-encode.cmd"
    Set-Content -Path $cmdFile -Value "@echo off`r`n$line`r`nexit /b %ERRORLEVEL%" -Encoding ASCII
    & cmd /c $cmdFile
    return ($LASTEXITCODE -eq 0 -and (Test-Path $Out))
}

Push-Location $RenderDir
try {
    # --- soundtrack -------------------------------------------------------
    $haveSynth = $SoundFont -and (Test-Path $SoundFont) -and (Get-Command $FluidSynth -ErrorAction SilentlyContinue)
    foreach ($mid in Get-ChildItem sounds -Filter *.mid -ErrorAction SilentlyContinue) {
        $wav = "$($mid.FullName).wav"
        if (Test-Path $wav) { Remove-Item $wav }   # always re-render: the SoundFont may have changed
        if ($haveSynth) {
            & $FluidSynth -ni -q -g $MidiGain -r 44100 -F $wav $SoundFont $mid.FullName | Out-Null
            if (-not (Test-Path $wav)) {
                $hint = if ($SoundFont -like "*.dls") { " (DLS needs a FluidSynth build with DLS support, e.g. the cpp11 one)" } else { "" }
                Write-Warning "FluidSynth couldn't render $($mid.Name) with $SoundFont$hint"
            }
        }
        if (-not (Test-Path $wav)) {
            if (-not $haveSynth) { Write-Warning "no FluidSynth/SoundFont: $($mid.Name) will be silent" }
            ffmpeg -hide_banner -loglevel error -y -f lavfi -i "anullsrc=r=44100:cl=stereo" -t 1 $wav
        }
    }
    $audio51 = $null
    $audioStereo = $null
    if (Test-Path audio-cues.tsv) {
        # leveled stems -> stereo + 5.1 (see mix-audio.ps1)
        try {
            $levels = & "$PSScriptRoot/mix-audio.ps1" -RenderDir $RenderDir -AudioLevel $AudioLevel
            $levels | ForEach-Object { Write-Host $_ }
            Add-Content -Path render.log -Value $levels
            $audioStereo = "audio-stereo.wav"
            $audio51 = "audio-51.wav"
        } catch {
            Write-Warning "soundtrack mix failed; encoding silent: $_"
            Add-Content -Path render.log -Value "audio: mix failed: $_"
        }
    } elseif (Test-Path audio.ffscript) {
        # renders from before audio-cues.tsv existed: the raw stereo mix
        ffmpeg -hide_banner -loglevel error -y -/filter_complex audio.ffscript -map "[aout]" -c:a pcm_s16le audio-stereo.wav 2>$null
        if ($LASTEXITCODE -ne 0) {
            ffmpeg -hide_banner -loglevel error -y -filter_complex_script audio.ffscript -map "[aout]" -c:a pcm_s16le audio-stereo.wav
        }
        if ($LASTEXITCODE -eq 0) { $audioStereo = "audio-stereo.wav" } else { Write-Warning "soundtrack mix failed; encoding silent" }
    }
    if ($Channels -eq "stereo") { $audio51 = $null }
    if ($Channels -eq "5.1" -and $audio51) { $audioStereo = $null }

    # --- video ------------------------------------------------------------
    # audio inputs/maps shared by every format: 5.1 (Dolby Digital,
    # dialogue in the center) first and default, then stereo AAC
    $audioInputs = @()
    $audioMaps = @()
    $ia = 0
    if ($audio51) {
        $audioInputs += @("-i", $audio51)
        $audioMaps += @("-map", "$($ia + 1):a", "-c:a:$ia", "ac3", "-b:a:$ia", "448k",
            "-metadata:s:a:$ia", "title=5.1 (dialogue in center)", "-disposition:a:$ia", "default")
        $ia++
    }
    if ($audioStereo) {
        $audioInputs += @("-i", $audioStereo)
        $audioMaps += @("-map", "$($ia + 1):a", "-c:a:$ia", "aac", "-b:a:$ia", "192k", "-metadata:s:a:$ia", "title=Stereo")
        if ($ia -gt 0) { $audioMaps += @("-disposition:a:$ia", "0") }
        $ia++
    }

    $failed = 0
    foreach ($fmt in $Formats) {
        $out = "$OutBase.$fmt.mp4"
        if ($fmt -eq "crt") {
            if (-not (Invoke-CrtEncode $out)) { Write-Warning "encode failed: $out"; $failed++ }
            continue
        }
        $vf = switch ($fmt) {
            "2d"       { if ($stereo) { "crop=iw/2:ih:0:0" } else { "null" } }
            "sbs"      { if ($stereo) { "null" } else { $null } }
            "anaglyph" { if ($stereo) { "stereo3d=sbsl:arcd" } else { $null } }
            default    { throw "unknown format $fmt" }
        }
        if (-not $vf) { Write-Warning "$fmt needs a --stereo render; skipped"; continue }
        $vf = "$vf,scale=iw*${Scale}:ih*${Scale}:flags=neighbor,fps=30,format=yuv420p"
        $inputs = @("-f", "concat", "-safe", "0", "-i", "timeline.ffconcat") + $audioInputs
        ffmpeg -hide_banner -loglevel error -y @inputs -vf $vf -map 0:v @audioMaps -c:v libx264 -crf $Crf -preset medium `
            -movflags +faststart -shortest $out
        if ($LASTEXITCODE -ne 0) { Write-Warning "encode failed: $out"; $failed++ }
    }
    if (Test-Path render.log) { Copy-Item render.log "$OutBase.log" }
} finally {
    Pop-Location
}
exit $failed
