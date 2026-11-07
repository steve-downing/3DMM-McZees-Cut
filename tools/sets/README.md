# Rebuilt 3DMM sets, in 3D

3D Movie Maker's sets ("backgrounds") are not 3D models. Each one ships as a
handful of pre-rendered 1995 pictures, one per camera angle, and each picture
comes with a depth buffer and the camera's position. These tools turn that
into real 3D sets you can walk around in: first to measure the set from the
pictures, then to rebuild it as a clean, low-poly "cartoon" model for VR.

Done so far: the airplane cabin (`AD-Airplane Background`, background 10).

- `STYLE.md` covers how the rebuilt sets should look, plus the review
  checklist to run before showing a new version. Read it before starting
  a set.
- `lib/` holds the parts every set uses:
  - reading the game files
  - point clouds from the depth buffers
  - fusing many views into one mesh
  - baking the original pictures onto a mesh
  - the cartoon toolkit
- `airplane/` holds the cabin's own measurements and build scripts.
- `viewer/` has three parts:
  - the 3D explorer page
  - a headless render harness
  - the side-by-side camera compare

## Setup

```sh
pip install numpy scipy pillow trimesh mapbox_earcut shapely scikit-image xatlas
cd viewer && npm install          # three.js (and Playwright, if you don't have it)
npx playwright install chromium   # only if Playwright has no browser yet
```

Also needed:

- a C compiler, for `lib/kcd.c`, the Kauai chunk decompressor; it's built
  automatically on first use
- `gltfpack`, only for the photo model (`npm i -g gltfpack`, or it's run
  through `npx`)

The game data is read from `content-files/bkgds.3cn` in this repo. Set
`TDMM_BKGDS` to read another copy.

## Build the cartoon cabin

```sh
python airplane/toon.py            # -> airplane/out/toon.glb  (a few seconds)
```

This uses the measurements already committed in `airplane/data/`.

`toon.py` is where all of the cabin's shapes, colors and placements live. For
a change of look, edit it and rebuild.

## Actors

`lib/actor.py` reads 3DMM's actor templates from `content-files/tmpls.3cn`. It
gives you the body-part tree, every action's cels, and the default costume,
which is either palette colors or 8-bit textures. It can pose any actor in
any cel, and `to_meshes` turns the result into textured glTF pieces with
BRender's smoothing groups. To list an actor's parts and materials:

```sh
python lib/actor.py Gustave
```

The explorer's actor picker uses `viewer/export_actors.py <dir>`. For each of
the 45 actors in the game's actor browser, it exports two files:

- a `.glb` holding every model that actor's actions use, in the model's own
  space, wearing the default costume
- a `.json` with the body-part tree and every action's cels: which model
  each part shows, and its transform relative to its parent part (float16)

`rig()` in `lib/actor.py` documents the format. Pass that folder as the fourth
argument to `build_site.py`. The page loads one actor at a time on demand, and
poses each frame by swapping models and setting part matrices, as 3DMM does.

`python airplane/actors.py` writes a static pose of two actors standing in the
aisle (`out/actors.glb`). `viewer/shoot.js` accepts it as an optional fourth
argument, for test renders.

Actors are measured in the same world units as the sets: Gustave is about
18 units tall, and a cabin seat back is about 12.6.

## Look at it

```sh
python viewer/export_views.py 10 views        # the 9 original pictures + cams.json
python viewer/compare.py airplane/out/toon.glb views compare.png
python viewer/export_actors.py build              # all 45 actors -> build/actors (~42 MB)
python viewer/build_site.py airplane views site build
```

- `compare.py` renders every original camera angle, putting ours on the left
  and the 1995 picture on the right. Use it all the time.
- `build_site.py` gathers the explorer page into `site/`. Serve that folder
  over http, for example with `python -m http.server -d site`, because
  `file://` won't load the page's modules.
- `viewer/shoot.js` renders any view headlessly:

  ```sh
  node viewer/shoot.js airplane/out/toon.glb views/cams.json \
      '[{"js":"setView(4)","out":"cam5.png"},{"js":"setFree(-14,10,12, -14,8.5,-1, 45)","out":"seat.png"}]'
  ```

  `setView(k)` is original camera k, counting from 0. `setFree` takes an
  eye position, a target and a vertical field of view, all in world units.

The explorer page, `viewer/index.html`, has the airplane's camera list and
title written into it. For another set, paste that set's `cams.json` into
`CAMS` and change the title.

### Units and axes

These are BRender world units, the same as the game.

- y is up, and the floor is y = 0.
- In the cabin, z runs from the door end (z = -17) to the rear wall
  (z = 27.25).
- The aisle is at x ≈ -0.5.
- Each repeated prop has a local frame: x across, y up, z forward. "Flip"
  means turned 180° about y. Placements are in `airplane/layout.py`.

## Measuring a set from scratch

This is the route the cabin took. Every step reads and writes one working
folder, here `airplane/build/`, which isn't committed.

1. **Point cloud.** `python lib/cloud.py airplane/build/cloud.npz 10`

   This puts every pixel of every camera's picture into world space, with
   its color and normal.

   It's the main measuring tool. Load it in a few lines of numpy and ask for
   heights, widths, colors and counts of whatever you're rebuilding,
   instead of eyeballing them.

2. **Cross-section** (sets that are a swept shape, like the cabin).
   `python airplane/xsection.py airplane/build`

   This produces `profile.json` and a debug picture, `xsec.png`.

3. **Shell textures.** `python airplane/shell.py airplane/build`

   This produces:

   - `shell.json`: the full profile loop, the end-wall extents and the door
     arch
   - `shell.jpg`: the walls unrolled along the profile
   - `shell_win.png`: a mask of where the windows are
   - `front.jpg` and `rear.jpg`

   Copy these into `airplane/data/`.

4. **Repeated props.** `python airplane/seats.py airplane/build`

   This finds each seat by aligning a reference seat to the point cloud,
   with ICP. The resulting positions were rounded by hand into
   `airplane/layout.py`.

5. **Photo version.** This step is optional. It's the original pictures
   baked onto the rebuilt shape.

   ```sh
   python airplane/seatfuse.py airplane/build/seat          # every view of every seat, fused (TSDF)
   python airplane/seatfuse.py airplane/build/table table
   ```

   Then come some hand steps:

   - Keep the biggest piece of `seat.raw.ply`, then simplify it with
     `gltfpack -si` to about 8k triangles.
   - Do the same for the table top.
   - Pick the table's leg and bracket colors and its top height, and record
     them in `data/photo/table_parts.json`.

   Then bake textures from all instances × all views:

   ```sh
   python airplane/seatbake.py <seat.glb> airplane/data/photo/seat_tex
   python airplane/seatbake.py <table.glb> airplane/data/photo/table_tex
   python airplane/assemble.py     # -> airplane/out/cabin.glb
   ```

6. **Cartoon version.** `python airplane/toon.py`, then review with
   `compare.py`, following `STYLE.md`.

`lib/fuse.py` and `lib/texture.py` are the first approach. They fuse a whole
background into one mesh and texture it from whichever camera saw each face
best:

```sh
python lib/fuse.py <background number> out/name
python lib/texture.py <background number> out/name.mesh.npz out/name.glb out/name.json
```

This gives a quick look at any set, but expect floating triangles and smeared
textures. That's why the cabin was rebuilt from measured parts.

## Notes

- **Window openings.** The cartoon cabin's windows are real holes. The sky
  is a sphere far outside the plane (`makeSky` in `viewer/surface.js`), so
  anything placed outside shows through the windows.
- **Surface texture.** Each face carries its texture kind in the alpha
  channel of its vertex color. The kinds are: plain, fabric, carpet, wood,
  metal and hammered metal. `viewer/surface.js` adds a matching procedural
  texture in the shader, so the model itself stays flat-colored and small.
- **Camera 7.** Camera 7 sits just outside the cabin's simplified
  overhead-bin corner. The explorer pushes its near clipping plane out at
  that camera (the `NEAR` table in `index.html`).
