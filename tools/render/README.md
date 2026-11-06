# 3dmm-render: turn .3mm movies into video (2D or 3D)

`3dmm-render.exe` plays a 3D Movie Maker movie with the real 3DMM engine,
headlessly and faster than real time, and writes every frame plus the
soundtrack to a folder. `render-folder.ps1` runs it over a whole folder
of movies and encodes finished MP4s.

With `-Stereo`, each frame is rendered twice from two slightly separated
cameras. Actors are re-rendered for real; the pre-rendered sets are
reprojected using their depth maps. The result is side-by-side 3D,
red/cyan anaglyph, or plain 2D.

## Quick start

1. Download the `3dmm-render` artifact from the latest successful build
   on the Actions tab and unzip it. It includes the renderer, the 3DMM
   content and these scripts.
2. Install ffmpeg: `winget install Gyan.FFmpeg`
3. Fetch the music tools (FluidSynth and a General MIDI SoundFont):
   `powershell -ExecutionPolicy Bypass -File get-tools.ps1`
4. Convert a folder:

   ```powershell
   powershell -ExecutionPolicy Bypass -File render-folder.ps1 `
       -InputDir D:\3mm-archive -OutputDir D:\3mm-videos -Stereo
   ```

Outputs mirror the input folders: `Movie.sbs.mp4`, `Movie.anaglyph.mp4`
and `Movie.2d.mp4` (just `.2d.mp4` without `-Stereo`). `report.csv` lists
every movie with its status. Movies that need content you don't have, such
as the Nickelodeon pack, are marked `missing-content` and the needed packs
are named. Re-running the script skips anything already up to date.

## Useful options

| Option | Default | What it does |
|---|---|---|
| `-Stereo` | off | render 3D |
| `-Depth` | 2.5 | how far behind the screen the scene can go (% of width) |
| `-Formats` | all | any of `sbs`, `anaglyph`, `2d` |
| `-Scale` | 2 | nearest-neighbor upscale (2 gives 1088×612 per eye) |
| `-ClickPause` | 3 | seconds to hold "wait for a click" pauses |
| `-Root` | auto | folder containing `3D Movie Maker` (to use another install's content) |
| `-KeepFrames` | off | keep the raw frames and logs |
| `-Force` | off | redo movies that are already up to date |

## Running the renderer directly

```
3dmm-render <movie.3mm> <outdir> [--root <dir>] [--stereo] [--depth <pct>]
            [--pop <pct>] [--click-pause <sec>] [--max-frames <n>] [--debug]
```

The output folder contains:

- `frames\*.bmp`: every distinct frame
- `timeline.ffconcat`: exact frame timings
- `sounds\` and `audio.ffscript`: the extracted sounds and an ffmpeg mix script
- `events.txt`: transitions, pauses, sounds and stereo choices
- `render.log`: diagnostics

`encode-movie.ps1 -RenderDir <outdir> -OutBase <name>` turns that folder
into MP4s.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | ok |
| 1 | usage |
| 2 | init failed |
| 3 | couldn't load the movie |
| 4 | missing content |
| 5 | render failed |
| 6 | the movie never finished playing |

## How it stays faithful

- **Timing.** The engine's own playback code runs unchanged against a
  frozen application clock that the renderer advances in 5 ms steps.
  Frame timing, scrolling text, timed pauses and wait-for-sound pauses
  behave as they do in 3DMM, and the output is identical every run.
- **Sound.** Sound devices play nothing. They record what the engine
  played, when, how loud and for how long. Stopping, queueing, looping
  and the end-of-movie fade are all included in the mix.
- **Transitions.** Fades and dissolves are synthesized with the same
  pixel-dissolve approach 3DMM uses, over the same four seconds.
- **Music.** MIDI is rendered with FluidSynth, so it will sound different
  from the Windows 95 wavetable synth you remember.
