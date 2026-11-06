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
#   2d        the movie as 3DMM showed it (from a stereo render too)
#   sbs       full side-by-side (left | right), for 3D TVs / players in SBS mode
#   anaglyph  red/cyan
#   crt       2d with CRT effects, 4K (see -CrtPreset; needs 3dmm-crt.exe)
#   win98     <name>.win98.avi: Cinepak video at the original 544x306 and
#             22 kHz PCM sound, which Windows 95/98 play out of the box
#
# -ExtractSounds also writes <name>.sounds.zip: the sounds that were added
# to the movie itself (imported or recorded, plus any that are never
# played), named in the order the movie first plays them, e.g.
# S03F014-speech-What-a-beautiful-day.wav. -IncludeLibrarySounds adds the
# 3DMM sounds the movie uses too.
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
    [string]$CrtTool,
    [switch]$ExtractSounds,
    [switch]$IncludeLibrarySounds
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

# Stereo frames are left | right | the plain 2-D view. Renders from older
# builds are just left | right; their "2d" is the left eye.
$layout = "mono"
if ($stereo) {
    $layout = "pair"
    $first = Select-String -Path (Join-Path $RenderDir "timeline.ffconcat") -Pattern "^file '(.*)'" | Select-Object -First 1
    if ($first) {
        $bmp = [IO.File]::ReadAllBytes((Join-Path $RenderDir $first.Matches[0].Groups[1].Value))
        if ([BitConverter]::ToInt32($bmp, 18) -ge 4 * [Math]::Abs([BitConverter]::ToInt32($bmp, 22))) { $layout = "triple" }
    }
}
$cropEyes = if ($layout -eq "triple") { "crop=iw*2/3:ih:0:0," } else { "" }
$crop2d = switch ($layout) { "triple" { "crop=iw/3:ih:iw*2/3:0," } "pair" { "crop=iw/2:ih:0:0," } default { "" } }

# File-name-safe version of a sound's name
function Get-SafeName([string]$Name) {
    $t = ($Name -replace "[^A-Za-z0-9]+", "-").Trim("-")
    if ($t.Length -gt 60) { $t = $t.Substring(0, 60).TrimEnd("-") }
    if (-not $t) { $t = "sound" }
    return $t
}

# <name>.sounds.zip from sounds\index.tsv (written by 3dmm-render)
function Export-Sounds([string]$Zip) {
    $index = Join-Path $RenderDir "sounds\index.tsv"
    if (-not (Test-Path $index)) { Write-Warning "no sounds\index.tsv (render with a newer 3dmm-render); no sounds extracted"; return $false }
    $rows = @(Get-Content $index | Where-Object { $_ -and -not $_.StartsWith("#") } | ForEach-Object {
            $c = $_ -split "`t"
            [pscustomobject]@{ file = $c[0]; first = $c[1]; scene = $c[2]; frame = $c[3]; category = $c[4]; source = $c[5]; name = $c[6] }
        })
    if (-not $IncludeLibrarySounds) { $rows = @($rows | Where-Object { $_.source -eq "movie" }) }
    $stage = Join-Path $RenderDir "sounds-export"
    if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
    New-Item -ItemType Directory -Force $stage | Out-Null
    $used = @($rows | Where-Object { $_.first -ne "" } | Sort-Object { [double]$_.first })
    $unused = @($rows | Where-Object { $_.first -eq "" })
    $sw = [Math]::Max(2, ("" + (@($used | ForEach-Object { [int]$_.scene }) + 0 | Measure-Object -Maximum).Maximum).Length)
    $fw = [Math]::Max(3, ("" + (@($used | ForEach-Object { [int]$_.frame }) + 0 | Measure-Object -Maximum).Maximum).Length)
    $taken = @{}
    $list = @()
    foreach ($r in $used + $unused) {
        $ext = [IO.Path]::GetExtension($r.file)
        $stem = if ($r.first -ne "") {
            "S{0}F{1}-{2}-{3}" -f $r.scene.PadLeft($sw, "0"), $r.frame.PadLeft($fw, "0"), $r.category, (Get-SafeName $r.name)
        } else {
            "unused-{0}-{1}" -f $r.category, (Get-SafeName $r.name)
        }
        $name = "$stem$ext"
        for ($k = 2; $taken.ContainsKey($name.ToLower()); $k++) { $name = "$stem-$k$ext" }
        $taken[$name.ToLower()] = $true
        Copy-Item (Join-Path $RenderDir "sounds\$($r.file)") (Join-Path $stage $name)
        $list += [pscustomobject]@{ file = $name; time = $r.first; scene = $r.scene; frame = $r.frame
            category = $r.category; source = $r.source; name = $r.name }
    }
    if ($list.Count -eq 0) {
        # still write a zip, so batch runs see this movie as done
        $msg = if ($IncludeLibrarySounds) { "This movie plays no sounds." } else {
            "No sounds were added to this movie (it only uses 3D Movie Maker's own). -IncludeLibrarySounds extracts those." }
        Write-Host $msg
        Set-Content -Path (Join-Path $stage "no-sounds.txt") -Value $msg -Encoding ASCII
    } else {
        $list | Export-Csv -NoTypeInformation (Join-Path $stage "sounds.csv")
    }
    if (Test-Path $Zip) { Remove-Item $Zip }
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $Zip
    Remove-Item -Recurse -Force $stage
    Write-Host "$($list.Count) sounds -> $Zip"
    return (Test-Path $Zip)
}

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
        if ($fmt -eq "none") { continue }   # e.g. just -ExtractSounds
        $out = "$OutBase.$fmt.mp4"
        if ($fmt -eq "crt") {
            # CRT effects are 2-D only; a stereo render keeps the 2-D view for this
            $note = switch ($layout) {
                "triple" { "crt: CRT effects are 2-D only; made from the 2-D view of this stereo render" }
                "pair"   { "crt: CRT effects are 2-D only; this stereo render has no 2-D view, so the left eye was used" }
                default  { $null }
            }
            if ($note) { Write-Host $note; Add-Content -Path render.log -Value $note }
            if (-not (Invoke-CrtEncode $out)) { Write-Warning "encode failed: $out"; $failed++ }
            continue
        }
        if ($fmt -eq "win98") {
            # Cinepak + 22 kHz PCM in an AVI: plays with what Windows 95/98
            # shipped. Only frames that change are encoded; the rest are
            # AVI null frames ("show the last one again"). 306 isn't a
            # multiple of 4, which Cinepak needs, so a black line is added
            # above and below.
            $out = "$OutBase.win98.avi"
            $w98In = @()
            $w98Map = @()
            if ($audioStereo) {
                $w98In = @("-i", $audioStereo)
                $w98Map = @("-map", "1:a", "-c:a", "pcm_s16le", "-ar", "22050", "-ac", "2")
            }
            ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i timeline.ffconcat @w98In -map 0:v @w98Map `
                -vf "${crop2d}fps=15,format=yuv444p,mpdecimate=hi=1:lo=1:frac=0:max=15,pad=544:308:0:1,format=rgb24" -fps_mode vfr `
                -c:v cinepak -max_extra_cb_iterations 0 -min_strips 3 -max_strips 3 $out
            if ($LASTEXITCODE -ne 0) { Write-Warning "encode failed: $out"; $failed++ }
            continue
        }
        $vf = switch ($fmt) {
            "2d"       { "${crop2d}null" }
            "sbs"      { if ($stereo) { "${cropEyes}null" } else { $null } }
            "anaglyph" { if ($stereo) { "${cropEyes}stereo3d=sbsl:arcd" } else { $null } }
            default    { throw "unknown format $fmt" }
        }
        if (-not $vf) { Write-Warning "$fmt needs a --stereo render; skipped"; continue }
        $vf = "$vf,scale=iw*${Scale}:ih*${Scale}:flags=neighbor,fps=30,format=yuv420p"
        $inputs = @("-f", "concat", "-safe", "0", "-i", "timeline.ffconcat") + $audioInputs
        ffmpeg -hide_banner -loglevel error -y @inputs -vf $vf -map 0:v @audioMaps -c:v libx264 -crf $Crf -preset medium `
            -movflags +faststart -shortest $out
        if ($LASTEXITCODE -ne 0) { Write-Warning "encode failed: $out"; $failed++ }
    }
    if ($ExtractSounds -and -not (Export-Sounds "$OutBase.sounds.zip")) { Write-Warning "sound extraction failed"; $failed++ }
    if (Test-Path render.log) { Copy-Item render.log "$OutBase.log" }
} finally {
    Pop-Location
}
exit $failed
