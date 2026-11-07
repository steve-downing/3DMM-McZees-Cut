# 3dmm-render: turn .3mm movies into video (2D or 3D)

`3dmm-render.exe` plays a 3D Movie Maker movie with the real 3DMM engine,
headlessly and faster than real time, and writes every frame plus the
soundtrack to a folder. `render-folder.ps1` runs it over a whole folder
of movies and encodes finished MP4s.

For 3D, each frame is rendered twice from two slightly separated
cameras. Actors are re-rendered for real; the pre-rendered sets are
reprojected using their depth maps. The result is side-by-side 3D,
red/cyan anaglyph, or plain 2D.

## Quick start

The easy way is the app: double-click **McZee's Cut.exe**, add movies,
press **Make videos**. The first time, it downloads ffmpeg and the music
tools. Windows may say it doesn't recognize the app: choose **More info**,
then **Run anyway**.

From the command line:

1. Fetch ffmpeg and the music tools (FluidSynth and a General MIDI
   SoundFont) into `tools\`. ffmpeg is skipped if it's already installed:
   `powershell -ExecutionPolicy Bypass -File get-tools.ps1`
2. Convert a folder:

   ```powershell
   powershell -ExecutionPolicy Bypass -File render-folder.ps1 `
       -InputDir D:\3mm-archive -OutputDir D:\3mm-videos -Smooth
   ```

Outputs mirror the input folders: `Movie.3mm` becomes `Movie.mp4`, plus
any other formats you ask for (below). `report.csv` lists every movie with
its status. Movies that need content you don't have, such
as the Nickelodeon pack, are marked `missing-content` and the needed packs
are named. Re-running the script skips anything already up to date.

Text boxes store their fonts by name. If a font isn't installed (or in
the `-Fonts` folder), 3DMM falls back to the Windows system font, as it
did in the 90s. The renderer reports every such font in `events.txt`,
in the report's `missingFonts` column, and in a summary at the end. 3-D
text uses 3DMM's own fonts and is never affected.

## Formats

`-Formats` picks which files each movie gets, as a comma-separated list.

| Format | File | What it is |
|---|---|---|
| `2d` (the default) | `Movie.mp4` | The movie as 3DMM showed it |
| `sbs` | `Movie.sbs.mp4` | Side-by-side 3D (left eye, right eye) for VR headsets, 3D TVs and players in SBS mode |
| `anaglyph` | `Movie.anaglyph.mp4` | Red/cyan 3D |
| `crt` | `Movie.crt.mp4` | 4K with CRT effects (below) |
| `avi` | `Movie.avi` | Cinepak for Windows 95/98 (below) |
| `none` | | No video, e.g. for just `-ExtractSounds` |

Asking for `sbs` or `anaglyph` renders the movie in 3D. Every other format
is made from the plain 2-D view, even in a 3D render.

## Option reference

The sections after the table cover the bigger features in more depth.

| Option | What it does | Values | Default | Applies to |
|---|---|---|---|---|
| `-InputDir` | The folder of `.3mm` movies to convert, including its subfolders | folder | required | |
| `-OutputDir` | Where the videos go, in the same subfolders | folder | required | |
| `-Formats` | Which files to make for each movie (see [Formats](#formats)) | `2d`, `sbs`, `anaglyph`, `crt`, `avi`, `none` | `2d` | |
| `-Smooth` | Makes motion smooth: adds three in-between frames to each of 3DMM's 6 frames a second, for 24 | switch | off | all formats |
| `-Scale` | Makes the picture bigger without blurring it, by repeating pixels. 2 doubles 544×306 to 1088×612 | whole number | 2 | `2d`, `sbs`, `anaglyph` |
| `-Depth` | How deep the 3D looks: how far behind the screen the scene can go, as a percentage of the picture's width | number | 2.5 | `sbs`, `anaglyph` |
| `-CrtPreset` | Which old screen to imitate: a 90s PC monitor, a Trinitron, a TV, or the PC monitor in HDR | `pc`, `trinitron`, `tv`, `hdr` | `pc` | `crt` |
| `-CrtMask` | The pattern of colored dots or stripes on the glass | `shadow`, `grille`, `slot`, `none` | per preset | `crt` |
| `-CrtScanlines` | How visible the dark gaps between the lines are | number | per preset | `crt` |
| `-CrtGlow` | How much bright areas glow | number | per preset | `crt` |
| `-CrtCurvature` | How curved the glass is | number | per preset | `crt` |
| `-CrtChroma` | `444` keeps the tiny colored dots sharp, but some players can't play it | `420`, `444` | `420` | `crt` |
| `-AudioLevel` | `auto` evens out the volume: every movie plays about as loud as the next, and MIDI music sits under the dialogue. `original` keeps the sound exactly as 3DMM mixed it | `auto`, `original` | `auto` | all formats |
| `-Duck` | Turns the music down while someone is talking, so you can hear them, then back up. Audio editors call this "ducking". 3DMM never did it | switch | off | all formats |
| `-Channels` | Which soundtracks to include: surround sound (5.1, with voices in the center speaker), stereo, or both | `both`, `stereo`, `5.1` | `both` | MP4s (an AVI is always stereo) |
| `-SoundFont` | The instrument sounds used to play MIDI music. `windows` uses the ones built into Windows | `.sf2`, `.sf3` or `.dls` file, or `windows` | GeneralUser GS | all formats |
| `-MidiGain` | How loud MIDI music is played, before any leveling | number | 0.6 | all formats |
| `-ExtractSounds` | Also saves the voices, sound effects and music added to the movie, as a ZIP of audio files | switch | off | |
| `-IncludeLibrarySounds` | Adds 3DMM's own sounds that the movie uses to that ZIP | switch | off | with `-ExtractSounds` |
| `-ClickPause` | How many seconds to wait at a "click to continue" pause | seconds | 3 | all formats |
| `-EndHold` | How many seconds the last frame stays on screen | seconds | 3 | all formats |
| `-Fonts` | A folder of fonts for text boxes whose font isn't installed. They're used for rendering, not installed | folder | none | all formats |
| `-Root` | Use 3D Movie Maker content from somewhere else, like another install | folder containing `3D Movie Maker` | the package folder | |
| `-Renderer` | Where `3dmm-render.exe` is | file | found automatically | |
| `-FluidSynth` | Where FluidSynth, the MIDI player, is | file | found automatically | |
| `-TimeoutMinutes` | Gives up on a movie that takes longer than this | minutes | 30 | |
| `-KeepFrames` | Keeps the raw frames and logs, for troubleshooting | switch | off | |
| `-Force` | Redoes movies even if their videos are already up to date | switch | off | |

## Sound

3DMM tags every sound as speech, sound effect or music, and the renderer
keeps those tags. With `-AudioLevel auto` (the default):

- **Speech and effects** keep the balance they were made with. Both were
  WAVs through the same sound card.
- **Each music track** is measured on its own and set 8 LU below the
  dialogue. MIDI loudness used to depend on whoever's PC it was.
- **The whole mix** is normalized to -16 LUFS with peaks under -1 dB, so
  movies play at similar volumes.

`-AudioLevel original` keeps the raw mix, as the engine played it.

`-Duck` dips the music 6 dB whenever someone is talking, with either
setting. It's off by default because 3DMM never did it.

`-SoundFont` picks the MIDI instruments: any `.sf2`, `.sf3` or `.dls`, or
`windows` for the Windows GS Wavetable Synth's `gm.dls`. `-MidiGain` is the
synth's gain before leveling. `-Channels` picks the soundtracks: both (the
default), or just `stereo` or `5.1`.

Every measurement and adjustment is written to the movie's `.log`, next
to the videos.

The 5.1 track puts dialogue in the center channel, effects and music in
front, music at -6 dB in the surrounds, and the low end of effects and
music in the LFE. It's Dolby Digital, so receivers and TVs decode it
natively. A stereo AAC track is included for everything else.

## CRT effects

The `crt` format writes `Movie.crt.mp4`: the movie as it looked on a CRT,
at 4K. The picture is scaled 6× (544×306 becomes 3264×1836) and centered.

- **Scanlines:** each line is drawn as an electron beam whose width grows
  with brightness. Bright lines fill in; dark lines leave gaps.
- **Phosphor mask:** applied after the beam, in screen pixels.
- **Glow:** a little light around bright areas.
- **Brightness:** boosted to make up for what the mask and gaps take away.

| Preset | Look |
|---|---|
| `pc` (default) | mid-90s PC monitor (where most 3DMM movies were watched): fine shadow mask, light scanlines, mild glow, flat |
| `trinitron` | aperture grille, stronger scanlines, slight curvature |
| `tv` | consumer TV: slot mask, heavy scanlines, softer focus, curvature with rounded corners |
| `hdr` | `pc` written as 10-bit HDR10. The OLED's headroom makes up the mask's lost light, so the mask can be stronger. |

`-CrtMask`, `-CrtScanlines`, `-CrtGlow` and `-CrtCurvature` override one
part of the preset. `-CrtChroma 444` keeps the phosphor colors crisp, but
fewer players handle it.

CRT effects are 2-D only. In a 3D render, `.crt.mp4` is made from the
movie's ordinary 2-D view, and the log says so. Side-by-side and anaglyph
output don't get CRT effects.

## AVI for Windows 95/98

The `avi` format writes `Movie.avi` at the original 544×306: Cinepak
video and 22 kHz 16-bit stereo sound, which Windows 95 and 98 play with
nothing extra installed. Only frames that change are stored, so files are
small (roughly 10 MB a minute). Cinepak needs a height divisible by 4, so
the picture has a black line above and below. Cinepak is slow to encode:
allow a few minutes per movie.

An AVI is always the plain 2-D picture at the original size: `-Scale`,
`-Depth`, `-Channels` and the CRT options don't apply. Everything else
does. With `-Smooth` it plays at 24 fps (otherwise 15, which covers 3DMM's
6 fps steps and its transitions), and its sound gets the same leveling and
ducking as the MP4s.

## Extracting sounds

`-ExtractSounds` writes `Movie.sounds.zip` with every sound that was
imported or recorded into the movie, in the order they're first played:

```
S01F001-music-Theme.mid
S03F014-speech-What-a-beautiful-day.wav
S03F022-sfx-Boing.wav
unused-speech-Take-2.wav
sounds.csv
```

`S03F014` is scene 3, frame 14 (counting from the scene's first frame).
Sounds that are stored in the movie but never played come last, as
`unused-`. WAVs are exactly as stored in the movie. MIDI is rebuilt from
3DMM's internal format as a standard `.mid`. `sounds.csv` lists each
file's time in the movie, scene, frame, kind and original name.
`-IncludeLibrarySounds` adds the 3DMM sounds the movie uses as well.

## Running the renderer directly

```
3dmm-render <movie.3mm> <outdir> [--root <dir>] [--stereo] [--depth <pct>]
            [--pop <pct>] [--smooth] [--fonts <dir>] [--click-pause <sec>] [--end-hold <sec>]
            [--max-frames <n>] [--debug]
```

The output folder contains:

- `frames\*.bmp`: every distinct frame (stereo: left eye, right eye and
  the 2-D view, side by side)
- `timeline.ffconcat`: exact frame timings
- `sounds\`, `audio-cues.tsv` and `audio.ffscript`: the extracted sounds, a cue sheet (category, timing, volume) and the raw mix
- `sounds\index.tsv`: each sound's name, kind, source (movie or 3DMM) and where it's first played
- `events.txt`: transitions, pauses, sounds and stereo choices
- `render.log`: diagnostics

`encode-movie.ps1 -RenderDir <outdir> -OutBase <name>` turns that folder
into videos. It takes the same `-Formats` and sound options as
`render-folder.ps1`.

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
  pixel-dissolve approach 3DMM uses, over the same four seconds. As in
  3DMM, the transition plays as soon as the scene changes, and the new
  scene's first sounds start after it.
- **Screen updates.** 3DMM draws a frame as soon as the movie advances
  to it, and starts that frame's sounds with the next frame command, about
  1/6 second later. Scrolling credits move one pixel every 1/12 second
  while the movie waits for them. The renderer runs the same update loop,
  so all of this matches.
- **Music.** MIDI is rendered with FluidSynth, so it will sound different
  from the Windows 95 wavetable synth you remember.

## Smooth motion (`-Smooth`)

3D Movie Maker moves everything at 6 frames a second. With `-Smooth`, the
renderer draws three in-between frames for every 6 fps step, and the videos
play at 24 fps.

- **What gets blended.** Every actor part's position, rotation and scale is
  blended between the two frames. So is any shear in squash-and-stretch
  cels, so each blended run still lands exactly on 3DMM's own frames.
- **Model swaps.** When a part changes to a different model, such as a new
  hand shape or mouth, the swap happens halfway between the two frames.
- **Flips.** A part that turns more than about 115° in one step snaps
  rather than spinning through the turn.
- **Steps left alone.** Steps where anything besides actor poses changes are
  left as they were, with no in-betweens. That includes a camera cut, a
  text box, a costume change or an actor entering. Steps longer than one
  frame are also left alone, so held poses stay held.
- **The log.** `render.log` ends with a count of the steps that were
  blended and the steps that were held.

Sound timing is unchanged. Transitions stay at 15 fps. Every format,
`.avi` included, gets the in-betweens.

