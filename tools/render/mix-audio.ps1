# Builds the soundtrack for one 3dmm-render output folder from
# audio-cues.tsv (written by the renderer) into audio-stereo.wav and
# audio-51.wav, and returns a list of log lines describing what it did.
#
# -AudioLevel auto (default):
#   * speech and sound effects keep the balance they were authored with
#     (both were WAVs through the same sound card)
#   * each music track is measured on its own and set -MusicUnder LU below
#     the dialogue (or a little under the effects if there's no dialogue)
#   * music ducks -Duck dB while anyone is speaking
#   * the whole mix is normalized to -TargetLufs with peaks held under -1 dB
# -AudioLevel original: the raw mix, as the engine played it.
#
# 5.1 routing: speech -> center; effects + music -> front L/R; music at
# -6 dB -> surrounds; low end of effects + music -> LFE.
# Works in Windows PowerShell 5.1 and PowerShell 7.
param(
    [Parameter(Mandatory)] [string]$RenderDir,
    [ValidateSet("auto", "original")] [string]$AudioLevel = "auto",
    [double]$MusicUnder = 8,
    [double]$Duck = 6,
    [double]$TargetLufs = -16
)
$ErrorActionPreference = "Stop"
[Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::InvariantCulture
$inv = [Globalization.CultureInfo]::InvariantCulture
function F([double]$x, [int]$d = 3) { $x.ToString("F$d", $inv) }

$log = New-Object System.Collections.Generic.List[string]
function Note([string]$s) { $log.Add($s) | Out-Null }

# ffmpeg writes its reports to stderr; capture without tripping
# ErrorActionPreference=Stop in Windows PowerShell 5.1
function Invoke-Ffmpeg([string[]]$FfArgs) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & ffmpeg -hide_banner -nostats @FfArgs 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $old
    }
    return [pscustomobject]@{ Code = $code; Text = ($out -join "`n") }
}

# run a filtergraph script; ffmpeg 7 uses -/filter_complex, older -filter_complex_script
function Invoke-Graph([string]$Script, [string[]]$Outputs) {
    $r = Invoke-Ffmpeg (@("-y", "-/filter_complex", $Script) + $Outputs)
    if ($r.Code -ne 0) { $r = Invoke-Ffmpeg (@("-y", "-filter_complex_script", $Script) + $Outputs) }
    if ($r.Code -ne 0) { throw "ffmpeg failed on $Script`n$($r.Text)" }
}

# integrated loudness (LUFS) and true peak (dBTP); $null loudness = silent
function Measure-Loudness([string]$File) {
    $r = Invoke-Ffmpeg @("-i", $File, "-af", "ebur128=peak=true", "-f", "null", "-")
    $i = [regex]::Matches($r.Text, "I:\s+(-?[\d\.]+|-inf) LUFS") | Select-Object -Last 1
    $p = [regex]::Matches($r.Text, "Peak:\s+(-?[\d\.]+|-inf) dBFS") | Select-Object -Last 1
    $lufs = $null
    if ($i -and $i.Groups[1].Value -ne "-inf") {
        $v = [double]::Parse($i.Groups[1].Value, $inv)
        if ($v -gt -69) { $lufs = $v }
    }
    $peak = $null
    if ($p -and $p.Groups[1].Value -ne "-inf") { $peak = [double]::Parse($p.Groups[1].Value, $inv) }
    return [pscustomobject]@{ Lufs = $lufs; Peak = $peak }
}

Push-Location $RenderDir
try {
    if (-not (Test-Path audio-cues.tsv)) { throw "no audio-cues.tsv (render with a newer 3dmm-render)" }
    $duration = [double]::Parse(((Get-Content audio-cues.tsv -TotalCount 1) -split "`t")[1], $inv)
    $cues = @(Get-Content audio-cues.tsv | Select-Object -Skip 1 | ConvertFrom-Csv -Delimiter "`t")
    foreach ($c in $cues) {
        foreach ($k in "start", "duration", "offset", "volume", "length") { $c.$k = [double]::Parse($c.$k, $inv) }
        $c.loops = [int]$c.loops
        $c | Add-Member -NotePropertyName gain -NotePropertyValue 1.0
    }
    $speech = @($cues | Where-Object { $_.category -eq "speech" })
    $sfx = @($cues | Where-Object { $_.category -eq "sfx" })
    $music = @($cues | Where-Object { $_.category -eq "music" })
    Note ("audio: {0} speech, {1} effect and {2} music cues; mode {3}" -f $speech.Count, $sfx.Count, $music.Count, $AudioLevel)

    $base = "anullsrc=r=44100:cl=stereo,atrim=duration=$(F $duration),aformat=sample_fmts=fltp"
    function Write-Stem([object[]]$StemCues, [string]$Name) {
        $lines = New-Object System.Collections.Generic.List[string]
        if ($StemCues.Count -eq 0) {
            $lines.Add("${base}[aout]")
        } else {
            $lines.Add("${base}[base];")
            $n = 0
            foreach ($c in $StemCues) {
                $vol = $c.volume * $c.gain
                $line = ("amovie='{0}':loop={1},atrim=start={2}:duration={3},asetpts=PTS-STARTPTS," +
                    "aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={4}," +
                    "adelay=delays={5}:all=1[a{6}];") -f $c.file, $c.loops, (F $c.offset), (F $c.duration),
                    (F $vol 5), [long][Math]::Round($c.start * 1000), $n
                $lines.Add($line)
                $n++
            }
            $ins = "[base]" + ((0..($n - 1) | ForEach-Object { "[a$_]" }) -join "")
            $lines.Add("${ins}amix=inputs=$($n + 1):normalize=0:duration=first[aout]")
        }
        Set-Content -Path "stem-$Name.ffscript" -Value $lines -Encoding ASCII
        Invoke-Graph "stem-$Name.ffscript" @("-map", "[aout]", "-c:a", "pcm_f32le", "stem-$Name.wav")
    }

    Write-Stem $speech "speech"
    Write-Stem $sfx "sfx"
    $lSpeech = (Measure-Loudness "stem-speech.wav").Lufs
    $lSfx = (Measure-Loudness "stem-sfx.wav").Lufs
    Note ("dialogue: {0}" -f $(if ($null -ne $lSpeech) { "$(F $lSpeech 1) LUFS" } else { "none" }))
    Note ("effects:  {0}" -f $(if ($null -ne $lSfx) { "$(F $lSfx 1) LUFS" } else { "none" }))

    # --- music: level each track on its own ---------------------------------
    if ($AudioLevel -eq "auto" -and $music.Count -gt 0) {
        if ($null -ne $lSpeech) { $target = $lSpeech - $MusicUnder; $why = "$(F $MusicUnder 1) LU under dialogue" }
        elseif ($null -ne $lSfx) { $target = $lSfx - 4; $why = "4 LU under effects (no dialogue)" }
        else { $target = $TargetLufs; $why = "no dialogue or effects" }
        Note ("music target: {0} LUFS ({1})" -f (F $target 1), $why)
        foreach ($file in ($music | Select-Object -ExpandProperty file -Unique)) {
            $m = Measure-Loudness $file
            if ($null -eq $m.Lufs) { Note "  $file : silent"; continue }
            $gainDb = [Math]::Max(-30.0, [Math]::Min(20.0, $target - $m.Lufs))
            foreach ($c in ($music | Where-Object { $_.file -eq $file })) { $c.gain = [Math]::Pow(10, $gainDb / 20) }
            Note ("  {0} : measured {1} LUFS, applied {2} dB" -f $file, (F $m.Lufs 1), (F $gainDb 1))
        }
    }
    Write-Stem $music "music"

    # --- ducking: music dips while anyone speaks ----------------------------
    $duckExpr = $null
    if ($AudioLevel -eq "auto" -and $Duck -gt 0 -and $speech.Count -gt 0 -and $music.Count -gt 0) {
        $attack = 0.15; $release = 0.5
        $spans = @($speech | Sort-Object start | ForEach-Object { , @($_.start, ($_.start + $_.duration)) })
        $merged = New-Object System.Collections.Generic.List[object]
        foreach ($s in $spans) {
            if ($merged.Count -gt 0 -and $s[0] -le $merged[$merged.Count - 1][1] + $attack + $release) {
                $merged[$merged.Count - 1][1] = [Math]::Max($merged[$merged.Count - 1][1], $s[1])
            } else {
                $merged.Add(@($s[0], $s[1])) | Out-Null
            }
        }
        $terms = $merged | ForEach-Object {
            "clip((t-$(F ($_[0] - $attack)))/$(F $attack),0,1)*clip(($(F ($_[1] + $release))-t)/$(F $release),0,1)"
        }
        $duckExpr = "pow(10,-$(F $Duck 2)*min(1,$($terms -join '+'))/20)"
        Note ("ducking: music -{0} dB during {1} stretches of dialogue" -f (F $Duck 1), $merged.Count)
    }

    # --- master volume envelope (the engine's end-of-movie fade) -----------
    $masterExpr = $null
    if (Test-Path audio-master.tsv) {
        $ev = @(Import-Csv audio-master.tsv -Delimiter "`t")
        if ($ev.Count -gt 0) {
            $prev = "1.0"
            $sb = ""
            foreach ($e in $ev) { $sb += "if(lt(t,$($e.time)),$prev,"; $prev = $e.volume }
            $masterExpr = $sb + $prev + (")" * $ev.Count)
        }
    }

    function Write-Mix([double]$GainDb, [bool]$Limit, [bool]$Surround, [string]$Script) {
        $musicChain = "amovie='stem-music.wav'"
        if ($duckExpr) { $musicChain += ",volume='$duckExpr':eval=frame" }
        $tail = ",volume=$(F $GainDb 2)dB"
        if ($masterExpr) { $tail += ",volume='$masterExpr':eval=frame" }
        if ($Limit) { $tail += ",alimiter=limit=0.891:attack=5:release=50:level=disabled" }
        $lines = New-Object System.Collections.Generic.List[string]
        if ($Surround) {
            $lines.Add("amovie='stem-speech.wav',asplit=2[sp1][sp2];")
            $lines.Add("amovie='stem-sfx.wav',asplit=3[fx1][fx2][fx3];")
            $lines.Add("${musicChain},asplit=4[mu1][mu2][mu3][mu4];")
            $lines.Add("[sp1][fx1][mu1]amix=inputs=3:normalize=0:duration=first${tail}[st];")
            $lines.Add("[sp2]pan=mono|c0=0.5*c0+0.5*c1[c];")
            $lines.Add("[fx2][mu2]amix=inputs=2:normalize=0:duration=first[f];")
            $lines.Add("[mu3]volume=0.5[s];")
            $lines.Add("[fx3][mu4]amix=inputs=2:normalize=0:duration=first,pan=mono|c0=0.5*c0+0.5*c1,lowpass=f=80,volume=0.5[l];")
            $lines.Add("[f][c][l][s]join=inputs=4:channel_layout=5.1(side):map=0.0-FL|0.1-FR|1.0-FC|2.0-LFE|3.0-SL|3.1-SR${tail}[sur]")
        } else {
            $lines.Add("amovie='stem-speech.wav'[sp];")
            $lines.Add("amovie='stem-sfx.wav'[fx];")
            $lines.Add("${musicChain}[mu];")
            $lines.Add("[sp][fx][mu]amix=inputs=3:normalize=0:duration=first${tail}[st]")
        }
        Set-Content -Path $Script -Value $lines -Encoding ASCII
    }

    $gain = 0.0
    if ($AudioLevel -eq "auto") {
        Write-Mix 0 $false $false "mix-measure.ffscript"
        Invoke-Graph "mix-measure.ffscript" @("-map", "[st]", "-c:a", "pcm_f32le", "mix-measure.wav")
        $m = Measure-Loudness "mix-measure.wav"
        if ($null -ne $m.Lufs) { $gain = [Math]::Max(-30.0, [Math]::Min(30.0, $TargetLufs - $m.Lufs)) }
        Note ("mix: measured {0} LUFS, applied {1} dB toward {2} LUFS" -f $(if ($null -ne $m.Lufs) { F $m.Lufs 1 } else { "silent" }),
            (F $gain 1), (F $TargetLufs 1))
        Remove-Item mix-measure.wav
    }
    Write-Mix $gain ($AudioLevel -eq "auto") $true "mix.ffscript"
    Invoke-Graph "mix.ffscript" @("-map", "[st]", "-c:a", "pcm_s16le", "audio-stereo.wav",
        "-map", "[sur]", "-c:a", "pcm_s16le", "audio-51.wav")
    $final = Measure-Loudness "audio-stereo.wav"
    Note ("final stereo: {0} LUFS, true peak {1} dBTP" -f $(if ($null -ne $final.Lufs) { F $final.Lufs 1 } else { "silent" }),
        $(if ($null -ne $final.Peak) { F $final.Peak 1 } else { "-inf" }))
    Remove-Item stem-*.wav -ErrorAction SilentlyContinue
} finally {
    Pop-Location
}
$log
