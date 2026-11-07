# Actors: Blender ⇄ 3D Movie Maker

Make new 3DMM actors in Blender, or open the 66 that came with 3DMM to learn
from or remix. An actor goes back into 3DMM as an **add-on**: two files you
drop into 3DMM's content folder, after which it shows up in the actor browser
like any other.

| Script | What it does |
| --- | --- |
| `import_actor.py <actor> <out.blend>` | Opens a stock actor in Blender: body parts, every action, every costume |
| `export_actor.py <in.blend> <folder>` | Writes an add-on (`<name>.3cn` + `<name>.3th`) from a .blend |
| `check_actor.py <actor> <in.blend> --all` | Checks an imported actor against 3DMM's own posing math |
| `roundtrip.py <actor> <folder>` | Imports, exports and compares with the original, cel by cel |
| `retarget_movie.py <in.3mm> <out.3mm> --from A --to B` | Recasts a movie: everyone played by actor A is played by B |

They need Python 3.13 with Blender's Python module:

    pip install bpy==5.2.3 numpy pillow
    python tools/actors/import_actor.py Gustave gustave.blend --preview gustave.png

## Installing an add-on

Copy the `.3cn` and `.3th` into 3DMM's content folder (in McZee's Cut,
`Microsoft Kids\3D Movie Maker`, next to `tmpls.3cn`) and start 3DMM. The
actor is in the actor browser.

Movies remember actors by number, so a movie with an add-on actor in it needs
that add-on to open. Share the add-on along with the movie.

## How an actor is built

3DMM actors are puppets made of rigid pieces: each body part is one model
that moves as a whole (it can also scale, for squash and stretch). Nothing
bends or deforms. Actions are flip-books at 6 frames a second. Each frame
(a "cel") says where every body part is and which model it shows. A walk
cycle also says how far forward the actor moves per cel when it follows a
path you drew.

In Blender that's an armature with meshes parented to its bones:

**Units and axes.** One Blender meter is 10 3DMM units; Z is up. Stock people
are about 1.8 m tall (18 units), feet at Z = 0. Like 3DMM's own models,
actors are modeled facing **−X** in Blender: the template's rest rotation
(below) turns them to face the camera.

**Bones are body parts.** One bone per part, parented the way the parts hang
together. The bone's rest position is where the part sits; its head is the
part's pivot. Imported actors name bones after their costume group and part
number (`Head.03`); any names work. Order matters only to keep movies working
(a body part's place in the list is its number), so imported actors carry a
`part` property; new ones are numbered parents first. Stock people have 23 to
27 parts.

**Meshes are models.** Parent each mesh to its bone (Parent → Bone). Rigid
only: no armature modifier, no weights. A part can have several meshes
(an open and a closed hand, mouth shapes) as long as only one shows at a
time. Imported actors switch them with a `model` property on the bone,
keyed per frame with constant interpolation, and drivers that hide the
others; you can do the same, or keyframe the meshes' visibility yourself.
The exporter looks at what's visible in each frame.

- Each mesh becomes a BRender model: triangles, one UV per vertex (seams are
  split for you), at most 32,767 vertices. Stock people are about 1,000
  triangles in total.
- Shading: smooth faces are smoothed, flat faces are flat, and sharp edges
  stay sharp. Imported meshes carry 3DMM's own smoothing groups as a
  `smoothing_group` face attribute, which wins when present.

**Body part sets and costumes.** Parts are grouped into sets (head, top,
bottom, feet...) that change costume together, set by the `set` property on
each bone (default 0). Each set has one or more costume options; an option
gives each part in the set a material and, optionally, an accessory mesh
(Gustave's glasses) that shows whenever the part's `model` is −1.

The armature's `costumes` property (JSON) lists them:

```json
[{"set": 0, "parts": ["Head.00", "Head.01"],
  "options": [{"name": "", "materials": ["Skin", "Hat"], "accessories": ["", "Glasses"]}]}]
```

`""` is nothing, and `"-"` is an empty accessory (it takes one off). Without
the property, every set gets one costume: what its parts wear now.
Imported actors have a `costume_N` property per set to try the options on.

**Materials** become 8-bit 3DMM materials:

- A material with an image texture (the first Image Texture node) becomes a
  texture, matched to 3DMM's 256-color palette with no dithering. Stock
  textures are mostly 100 to 250 pixels across and never over 452; images
  over 512 are scaled down. Imported
  materials keep 3DMM's texture transform in `uv_transform`.
- Anything else is a solid color: the closest of the 17 color ramps 3DMM
  shades with (`palette_base` and `palette_range` override the choice).

Lighting in 3DMM comes from the scene, so materials carry color only.

**Actions.** Each Blender action with a `3dmm` property (imported ones have
it) becomes an action, named after the Blender action, in the order of its
`anid` property (then by name). Keyframes are at 6 fps, one cel per frame,
across the action's frame range. Hold poses with constant interpolation, or
let Blender's curves give you in-betweens: the exporter samples each frame.

| Action property | What it does | Default |
| --- | --- | --- |
| `steps` | Distance moved along the path at each cel, in meters | 0 |
| `flags` | 1, 2, 4: turn about X, Y, Z to follow the path; 8: stays put | 2 if it moves, else 10 |

Stock walks end their names with ` *`, and nearly all people share the same
33 actions in the same order (At Rest, Crawl *, Run *, ... Yell). New actors
can have any set; 3DMM starts a new actor on the first one.

**Template properties** on the armature:

| Property | What it does | Default |
| --- | --- | --- |
| `3dmm_actor` | Name in 3DMM | the armature's name |
| `rest_rotation` | Degrees about X, Y, Z that face the actor to the camera | 0, 90, 0 |
| `template_flags` | 1: only its own costumes; 4: a prop | 1 |
| `thumbnail` | Picture for the actor browser | `//thumbnail.png`, else a rendered close-up |

## Chunk numbers

3DMM loads every content file in its folder into one pool, so an add-on's
pieces need numbers nobody else uses. The exporter gives each actor a block of
4,096 picked from its name (`--cno` picks one yourself). Keep it the same
between versions of an actor, because saved movies point at it.

## How we know it works

`roundtrip.py` runs in CI on a handful of stock actors: it imports each one,
checks every cel of every action against 3DMM's math, exports it, and
compares the result with the original. Then the Windows build renders a CD
sample movie twice, once with Bongo and once with the exported copy of Bongo
as an add-on, and checks that the frames match.
