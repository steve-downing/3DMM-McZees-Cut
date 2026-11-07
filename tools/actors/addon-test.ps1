# CI check for add-on actors: 3DMM loads an exported actor and plays it the
# same as the original.
#
# -AddonDir holds add-on actors (.3cn + .3th) and movies:
#   <movie>-addon.3mm  a sample movie retargeted at an exported copy of its own
#                      actor; rendered next to <movie>.3mm, every frame compared
#   <name>-show.3mm    a movie starring a new actor; rendered (smooth) into a
#                      contact sheet, sample frames and a preview video
#
# -PackageDir is a packaged McZee's Cut (3dmm-render.exe, Microsoft Kids\...).
param(
    [Parameter(Mandatory)] [string]$PackageDir,
    [Parameter(Mandatory)] [string]$AddonDir,
    [string]$OutDir = "ci-out/addon"
)
$ErrorActionPreference = "Stop"
$pkg = Resolve-Path $PackageDir
New-Item -ItemType Directory -Force $OutDir | Out-Null
$OutDir = Resolve-Path $OutDir

$tmp = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
$stage = Join-Path $tmp "stage-addon"
$product = Join-Path $stage "3D Movie Maker"
New-Item -ItemType Directory -Force $product | Out-Null
Copy-Item (Join-Path $pkg "Microsoft Kids/3D Movie Maker/*") $product
Copy-Item "$AddonDir/*.3cn", "$AddonDir/*.3th" $product
$exe = Join-Path $pkg "3dmm-render.exe"
"content folder:" | Write-Host; Get-ChildItem $product | Format-Table Name, Length | Out-String | Write-Host

$work = Join-Path $tmp "addon-work"
$results = @()
foreach ($addon in Get-ChildItem $AddonDir -Filter "*-addon.3mm") {
    $orig = Join-Path $AddonDir ($addon.Name -replace '-addon\.3mm$', '.3mm')
    $dirs = @{}
    foreach ($m in @($orig, $addon.FullName)) {
        $d = Join-Path $work ([IO.Path]::GetFileNameWithoutExtension($m))
        New-Item -ItemType Directory -Force $d | Out-Null
        $p = Start-Process -FilePath $exe -PassThru -NoNewWindow `
            -ArgumentList @("`"$m`"", "`"$d`"", "--root", "`"$stage`"", "--max-frames", "400") `
            -RedirectStandardOutput "$d.out.txt" -RedirectStandardError "$d.err.txt"
        $null = $p.Handle
        if (-not $p.WaitForExit(600000)) { $p.Kill(); throw "$m timed out" }
        Copy-Item "$d.out.txt", "$d.err.txt" $OutDir
        if ($p.ExitCode -ne 0) { Get-Content "$d.err.txt" | Write-Host; throw "$m exit $($p.ExitCode)" }
        $dirs[$m] = $d
    }
    $a = Get-ChildItem "$($dirs[$orig])/frames" -Filter *.bmp | Sort-Object Name
    $b = Get-ChildItem "$($dirs[$addon.FullName])/frames" -Filter *.bmp | Sort-Object Name
    $same = 0; $worst = [double]::PositiveInfinity; $worstFrame = ""
    foreach ($i in 0..([Math]::Min($a.Count, $b.Count) - 1)) {
        if ((Get-FileHash $a[$i].FullName).Hash -eq (Get-FileHash $b[$i].FullName).Hash) { $same++; continue }
        $log = & ffmpeg -hide_banner -i $a[$i].FullName -i $b[$i].FullName -lavfi psnr -f null - 2>&1 | Out-String
        $psnr = if ($log -match 'average:(inf|[\d\.]+)') { if ($matches[1] -eq 'inf') { 99 } else { [double]$matches[1] } } else { 0 }
        if ($psnr -lt $worst) { $worst = $psnr; $worstFrame = $a[$i].Name }
    }
    $r = [pscustomobject]@{ movie = $orig | Split-Path -Leaf; frames = $a.Count; addonFrames = $b.Count; identical = $same
                            worstPsnr = if ($worstFrame) { [Math]::Round($worst, 1) } else { 'all identical' }; worstFrame = $worstFrame }
    $results += $r
    # side by side of the worst (or middle) frame for a look
    $show = if ($worstFrame) { $worstFrame } else { $a[[int]($a.Count / 2)].Name }
    & ffmpeg -hide_banner -loglevel error -y -i (Join-Path "$($dirs[$orig])/frames" $show) -i (Join-Path "$($dirs[$addon.FullName])/frames" $show) `
        -filter_complex hstack (Join-Path $OutDir "$($addon.BaseName)-compare.png")
}
# movies starring new actors: just show them
$tools = Join-Path $pkg "tools"
$soundFont = Join-Path $tools "GeneralUser-GS.sf2"
$fluid = Get-ChildItem -Recurse $tools -Filter fluidsynth.exe -ErrorAction SilentlyContinue | Select-Object -First 1
foreach ($show in Get-ChildItem $AddonDir -Filter "*-show.3mm") {
    $d = Join-Path $work $show.BaseName
    $keep = Join-Path $OutDir $show.BaseName
    New-Item -ItemType Directory -Force $d, $keep | Out-Null
    $p = Start-Process -FilePath $exe -PassThru -NoNewWindow `
        -ArgumentList @("`"$($show.FullName)`"", "`"$d`"", "--root", "`"$stage`"", "--smooth") `
        -RedirectStandardOutput "$keep/stdout.txt" -RedirectStandardError "$keep/stderr.txt"
    $null = $p.Handle
    if (-not $p.WaitForExit(900000)) { $p.Kill(); throw "$($show.Name) timed out" }
    if ($p.ExitCode -ne 0) { Get-Content "$keep/stderr.txt" | Write-Host; throw "$($show.Name) exit $($p.ExitCode)" }
    Copy-Item "$d/render.log" $keep -ErrorAction SilentlyContinue
    $frames = @(Get-ChildItem "$d/frames" -Filter *.bmp | Sort-Object Name)
    if (-not $frames) { throw "$($show.Name): no frames" }
    $step = [int][Math]::Max(1, [Math]::Floor($frames.Count / 16))
    $pick = for ($i = 0; $i -lt 16 -and $i * $step -lt $frames.Count; $i++) { $frames[$i * $step] }
    $list = Join-Path $d "contact.txt"
    ($pick | ForEach-Object { "file '$($_.FullName -replace '\\','/')'" }) | Set-Content $list
    & ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i $list -vf "scale=320:240,tile=4x4" -frames:v 1 (Join-Path $keep "contact.png")
    foreach ($k in 1..4) {
        $f = $frames[[int][Math]::Floor($frames.Count * $k / 5)]
        & ffmpeg -hide_banner -loglevel error -y -i $f.FullName (Join-Path $keep ("frame-{0}.png" -f $k))
    }
    $enc = @{ RenderDir = $d; OutBase = (Join-Path $keep "preview"); Formats = "2d"; Crf = 26 }
    if ($fluid -and (Test-Path $soundFont)) { $enc.SoundFont = $soundFont; $enc.FluidSynth = $fluid.FullName }
    & (Join-Path $pkg "encode-movie.ps1") @enc *>&1 | Out-File (Join-Path $keep "encode.txt")
    $results += [pscustomobject]@{ movie = $show.Name; frames = $frames.Count; addonFrames = '-'; identical = '-'; worstPsnr = 'shown'; worstFrame = '' }
}

$results | Format-Table | Out-String | Tee-Object -FilePath (Join-Path $OutDir "summary.txt") | Write-Host
foreach ($r in $results | Where-Object { $_.worstPsnr -ne 'shown' }) {
    if ($r.frames -eq 0 -or $r.frames -ne $r.addonFrames) { throw "$($r.movie): $($r.frames) frames vs $($r.addonFrames) with the add-on" }
    if ($r.worstFrame -and $r.worstPsnr -lt 40) { throw "$($r.movie): frame $($r.worstFrame) differs (PSNR $($r.worstPsnr) dB)" }
}
