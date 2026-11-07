# McZee's Cut

_Your 3D Movie Maker movies, exported to video and remastered: smooth motion, real stereo 3D, CRT looks and 5.1 sound._

![Gustave's karate kick: 3D Movie Maker's 6 frames a second on the left, smoothed to 24 on the right](img/smooth-compare.gif)

<sub>Gustave, one of 3DMM's own actors, in the rebuilt airplane cabin from the [set explorer](#try-the-3d-set-explorer). Every fourth frame on the right is exactly 3DMM's. The renderer's `-Smooth` uses the same blending.</sub>

McZee's Cut turns `.3mm` movies into MP4s you can watch anywhere, using
3D Movie Maker's real engine. It plays each movie headlessly and faster than
real time, so the timing, transitions, text and sound come out the way 3DMM
played them. Then it goes further than 3DMM could:

- **Smooth motion.** 3DMM animates at 6 frames a second. `-Smooth` blends
  every actor's motion between those frames and exports at 24.
- **Stereo 3D.** Side-by-side 3D for VR headsets and 3D TVs, red/cyan
  anaglyph, or plain 2D. Actors are rendered twice for real. The
  pre-rendered sets are reprojected from their depth maps.
- **CRT looks.** A 4K version that looks like a mid-90s monitor, a
  Trinitron or a TV, with an HDR option.
- **Sound.** 5.1 Dolby Digital with dialogue in the center, plus stereo.
  Loudness is leveled so every movie plays at a similar volume.
- **Period-correct AVI.** A small Cinepak `.avi` that plays on Windows 95
  and 98 with nothing extra installed.
- **Whole archives at once.** Point it at a folder of movies and it
  converts everything, writes a report, and picks up where it left off if
  interrupted.

Everything that changes the movie (smooth motion, ducking) is opt-in. Left
alone, you get the movie as 3DMM played it, leveled to a normal volume.

## Try the 3D set explorer

Ahead of a VR player, 3DMM's sets are being rebuilt as real 3D models. The
first one, the airplane cabin, is in a test explorer in your browser:
**[open the explorer](https://claude.ai/artifact/VJHCRE9hk4drqAkeEcy79R)**.

- Fly around the cabin, or jump to any of the 9 original 3DMM camera angles.
- Fade between the rebuilt set and the original 1995 picture to compare
  them.
- Drop in any of 3DMM's 45 actors. Choose an action and a costume, scrub
  through the frames, and play it at 3DMM's 6 fps or smoothed to 24 fps.

It works with a mouse and keyboard (WASD to move, drag to look) or on a
phone. How the sets are rebuilt is in
[`tools/sets/README.md`](tools/sets/README.md).

## Export your movies

These steps are for Windows 10 or 11.

1. Download the `3dmm-render` package from the latest successful build on
   the [Actions tab](../../actions) and unzip it. (GitHub asks you to sign
   in to download build files.) The package includes the renderer, 3D Movie
   Maker's content, the app and the scripts.
2. Double-click **McZee's Cut.exe**. Windows may say it doesn't recognize
   the app: choose **More info**, then **Run anyway**.
3. Add your movies, pick a style, tick what you want, and press
   **Make videos**. The first time, it downloads ffmpeg and the music
   instruments, about 200 MB.

The app has two styles. **Improved**, the default, smooths the motion and
dips the music while characters talk. **Faithful** is exactly what 3D Movie
Maker played. Hover over any choice to see what it makes.

### From the command line

The app runs `render-folder.ps1`, which has every option (see
[What it can do](#what-it-can-do)). In the unzipped folder:

```powershell
powershell -ExecutionPolicy Bypass -File get-tools.ps1     # once: ffmpeg and the music tools
powershell -ExecutionPolicy Bypass -File render-folder.ps1 `
    -InputDir D:\3mm-archive -OutputDir D:\3mm-videos -Smooth -Duck
```

`get-tools.ps1` skips ffmpeg if it's already installed. The output folder
mirrors the input folder. `My Movie.3mm` becomes `My Movie.mp4`, plus any
other formats you asked for, and `report.csv` lists every movie and how it
went. Run the script again and it skips anything already up to date.

### Recipes

| You want | Add |
|---|---|
| The app's Improved style | `-Smooth -Duck` |
| The best-looking 2D video, music untouched | `-Smooth` |
| 3D for a VR headset or 3D TV | `-Smooth -Formats sbs` |
| 3D, red/cyan, and 2D, all at once | `-Smooth -Formats sbs,anaglyph,2d` |
| The 90s monitor look, in 4K | `-Smooth -Formats crt` |
| A 4K HDR CRT for an OLED | `-Smooth -Formats crt -CrtPreset hdr` |
| A file for a real Windows 98 PC | `-Formats avi` |
| Music that dips when characters talk | `-Duck` |
| The movie's own voice clips and music, as files | `-ExtractSounds` |
| The movie exactly as 3DMM played it, including its raw sound mix | `-AudioLevel original` |

## What it can do

This section explains each feature. The [option reference](#option-reference)
below lists every option with its values and default.

### Formats

`-Formats` picks which files each movie gets. List as many as you like,
separated by commas.

| Format | File | What it is |
|---|---|---|
| `2d` (the default) | `Movie.mp4` | The movie as 3DMM showed it |
| `sbs` | `Movie.sbs.mp4` | Side-by-side 3D, left eye then right, for VR headsets, 3D TVs and players in SBS mode |
| `anaglyph` | `Movie.anaglyph.mp4` | Red/cyan 3D, for paper glasses |
| `crt` | `Movie.crt.mp4` | 4K, looking like a 90s CRT |
| `avi` | `Movie.avi` | Cinepak for Windows 95 and 98 |
| `none` | | No video, for when you only want `-ExtractSounds` |

Asking for `sbs` or `anaglyph` renders the movie from two cameras. Every
other format comes from the plain 2D picture, even when it's rendered
alongside 3D.

### Smooth motion

3D Movie Maker moves everything at 6 frames a second. `-Smooth` draws three
in-between frames for every step, and the video plays at 24 fps.

- Every actor part's position, rotation and scale is blended. So is the
  stretch in squash-and-stretch poses. Every fourth frame is still exactly
  3DMM's own frame.
- When a part changes model, such as a new hand shape or mouth, the change
  happens halfway between frames.
- A part that turns more than about 115° in one step snaps instead of
  spinning through the turn.
- Steps where anything besides actor poses changes are left exactly as they
  were. That includes a camera cut, a text box, a costume change and an
  actor entering. So are poses the movie holds for longer than one step.
- Sound timing doesn't change. The movie's log counts the steps it blended
  and the steps it left alone.

Smooth motion applies to every format, AVI included.

### 3D

Each frame is rendered from two slightly separated cameras. Actors are
re-rendered for real. The sets are pre-rendered pictures, so they're
reprojected using their depth maps. `-Depth` sets how far behind the screen
the scene can go.

### CRT looks

The `crt` format draws the movie the way it looked on a CRT: scanlines that
widen with brightness, a phosphor mask, a little glow, scaled to 4K.
`-CrtPreset` picks the screen: a mid-90s PC monitor (the default), a
Trinitron, a TV, or the PC monitor in 10-bit HDR for an OLED. The other
`-Crt` options adjust one part of the preset. CRT effects are 2D only.

### AVI for Windows 95 and 98

The `avi` format writes Cinepak video at 3DMM's original 544×306, with
22 kHz stereo sound. That's what Windows 95 and 98 play with nothing extra
installed. Only frames that change are stored, so files are small.

An AVI is always the plain 2D picture at the original size, so `-Scale`,
`-Depth`, `-Channels` and the `-Crt` options don't apply to it. Everything
else does. With `-Smooth` it plays at 24 fps, and its sound gets the same
leveling and ducking as the MP4s. Leave out `-Smooth` for the 6 fps original.

### Sound

3DMM tags every sound as speech, a sound effect or music, and McZee's Cut
uses those tags.

- **Leveling** (`-AudioLevel auto`, the default). Speech and effects keep
  the balance they were made with. Each music track is measured and set a
  little under the dialogue, since MIDI loudness depended on whoever's PC
  it was. The whole movie is then brought to a standard loudness, so
  movies play at similar volumes. `-AudioLevel original` skips all of this
  and keeps the raw mix.
- **Ducking** (`-Duck`, off by default). Music dips while anyone is
  talking. It's often easier to follow, but 3DMM never did it.
- **Channels** (`-Channels`). By default each video gets two soundtracks:
  5.1 Dolby Digital, with dialogue in the center, and stereo.
- **Music instruments** (`-SoundFont`, `-MidiGain`). MIDI music is played
  with FluidSynth and a General MIDI SoundFont. Any SoundFont works, and
  `windows` uses the instruments of Windows' own GS Wavetable Synth.
- **Extracting sounds** (`-ExtractSounds`). Also writes `Movie.sounds.zip`,
  with every sound imported or recorded into the movie, in the order
  they're first played, plus a list of when each one plays.
  `-IncludeLibrarySounds` adds the 3DMM sounds the movie uses.

### Playback

- **Pauses.** A "wait for mouse click" pause is held for `-ClickPause`
  seconds, and the last frame is held for `-EndHold` seconds.
- **Fonts.** Text boxes ask for fonts by name. A font that isn't installed
  falls back to the Windows system font, as it did in the 90s, and the
  report lists it. `-Fonts` takes a folder of font files to use for
  rendering, without installing them.

### Batches

`report.csv` gets a row per movie: whether it worked, how long it took,
and what it wrote. Movies that need content you don't have, such as the
Nickelodeon pack, are marked `missing-content`, along with the packs they
need. A run that's stopped picks up where it left off, because movies whose
files are newer than the `.3mm` are skipped. `-Force` redoes them anyway.

## Option reference

All options belong to `render-folder.ps1`. Only `-InputDir` and
`-OutputDir` are required. [What it can do](#what-it-can-do) covers the
bigger features in more depth.

| Option | What it does | Values | Default | Applies to |
|---|---|---|---|---|
| `-InputDir` | The folder of `.3mm` movies to convert, including its subfolders | folder | required | |
| `-OutputDir` | Where the videos go, in the same subfolders | folder | required | |
| `-Formats` | Which files to make for each movie ([formats](#formats)) | `2d`, `sbs`, `anaglyph`, `crt`, `avi`, `none` | `2d` | |
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

## Running the renderer directly

`render-folder.ps1` is the easy way. For your own pipeline, `3dmm-render`
writes a movie's frames, exact timings and sounds to a folder, and
`encode-movie.ps1 -RenderDir <dir> -OutBase <name>` turns that folder into
videos, taking the same format and sound options.

```
3dmm-render <movie.3mm> <outdir> [options]
```

| Flag | What it does | Values | Default |
|---|---|---|---|
| `--smooth` | Adds three in-between frames to each of 3DMM's 6 frames a second | | off |
| `--stereo` | Renders each frame for the left eye, the right eye and the plain 2D view | | off |
| `--depth` | How far behind the screen a 3D scene can go | % of picture width | 2.5 |
| `--pop` | How far in front of the screen things can come in 3D | % of picture width | 1.5 |
| `--root` | Where 3D Movie Maker's content is | folder containing `3D Movie Maker` | the renderer's own folder |
| `--fonts` | Extra fonts for text boxes, used without installing them | folder | none |
| `--click-pause` | How long to wait at a "click to continue" pause | seconds | 3 |
| `--end-hold` | How long the last frame stays up | seconds | 3 |
| `--max-frames` | Stops after this many frames, for quick tests | number | no limit |
| `--debug` | Also writes depth maps and depth statistics | | off |

[`tools/render/README.md`](tools/render/README.md) has the rest: the
output folder, exit codes, the CRT presets in detail, and how the renderer
stays faithful to 3DMM.

### Rendering in GitHub Actions

Every push builds and packages the renderer, then renders quick previews
of the movies in `test-movies/`: six of the sample movies from the 3DMM
CD. To get full-length videos of particular movies, list them in
`ci-render-requests.txt`, one file name per line. Lines starting with `-`
are options for all of them, such as `-Smooth` or `-Formats 2d,avi`. The
results are pushed to the `ci-results` branch. On a public fork, that
branch is public too, so only add movies whose authors are happy for them
to be published.

## Building

You need CMake 3.23 and Visual Studio 2022. Only 32-bit x86 builds work for
now.

```console
$ cmake --preset x86:msvc:relwithdebinfo
$ cmake --build build
```

This builds `3dmovie.exe` (3D Movie Maker itself) and `3dmm-render.exe`.
[VCVars](https://github.com/bruxisma/VCVars) for PowerShell is a quick way
to set up the x86 compiler environment:
`pushvc (invoke-vcvars -TargetArch x86 -HostArch AMD64)`.

`SITOBREN.EXE` doesn't build, because it needs the SoftImage SDK, which
isn't included.

## Where this came from

McZee's Cut is a fork of [3DMMForever](https://github.com/foone/3DMMForever),
the community effort to keep 3D Movie Maker building and running on modern
systems. 3DMMForever exists because Microsoft
[released 3DMM's source code](https://github.com/microsoft/Microsoft-3D-Movie-Maker)
under the [MIT license](LICENSE) in May 2022.

Released in 1995, 3D Movie Maker let kids make animated movies from its 3D
sets, actors, sounds and music. It was hosted by McZee, who would surely
approve of this cut.

**McZee's Cut is not affiliated with or endorsed by Microsoft.** 3D Movie
Maker, McZee and the program's content belong to Microsoft.

## Legal stuff

The following sections have been carried over from the original 3D Movie Maker [GitHub repository](https://github.com/microsoft/Microsoft-3D-Movie-Maker) released by Microsoft in May 2022.

### Code cleanup

This code was restored from the Microsoft corporate archives and cleared for release.

- Developer names and aliases were removed, with the exception of current employees who worked on the
  original release who consented to keeping their names in place
- The archive consisted of several CDs, some of which were for alternate builds or products, and
  have been excluded
- The code does not build with today's engineering tools, and is released as-is.

### Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.

This repo includes a build from 1995 of BRender from Argonaut software. Approval to open source BRender as MIT was given in an email from Jez San, former CEO of Argonaut. Other versions of BRender exist at https://github.com/foone/BRender-v1.3.2 and https://github.com/foone/BRender-1997 Thanks to Jez and the whole BRender team for their hard work on this amazing engine. A full historical list of BRender contributors is available at https://github.com/foone/BRender-v1.3.2/blob/main/README.md

This repo does NOT include the SoftImage SDK "./DKIT" from 1992.

Jez also offered this interesting BRender anecdote in an email:

```
When Sam Littlewood designed BRender, he didn’t write the code. And then document it.
The way most things were built at the time.
First, he wrote the manual.  The full documentation
That served as the spec.  Then the coding started.
```
