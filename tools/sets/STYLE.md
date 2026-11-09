# How the rebuilt sets should look

These rules came out of rebuilding the airplane cabin over many rounds of
notes from Steve. They're here so the next set starts where the cabin ended
up, not where it began.

The goal is to stand inside a 3DMM movie in a VR headset (SteamVR, through a
browser). Internal coherence matters more than fidelity to the old models.
Everything should look like it belongs to one world, with nothing floating
or smeared. The world should still read as the original set.

## Shape

- **Low-poly but not crude.** Build from simple solids: chamfered boxes,
  hulls, extruded outlines and swept profiles. Round the corners people
  notice, like headrests, shoulders, window corners and arches, with real
  radii, and keep the rest boxy. The airplane cabin, with 13 seats, came to
  about 37k triangles, which is fine for VR.
- **Copy counts and placements from the original exactly.** Number of
  stripes, handles, legs, compartments and windows; where a door handle
  sits; how far each window shade is pulled. Measure them, don't
  estimate. Every one of these was a note on the cabin.
- **Proportions can be tuned to read better, but features aren't invented
  or dropped.** The seats got narrower so neighbors stand apart, the
  armrests flatter, and the headrest wider. Nothing was added that the
  original doesn't have, and nothing it has was left out. If it's hard to
  tell what something in the original is (a reflection? a panel?), look at
  every camera angle that sees it before deciding.
- **Build a repeated prop once and place copies.** The seats, the tables
  and the bin handles are each one model placed many times. A prop that
  differs from its siblings, like the jump seat, gets its own model rather
  than a scaled copy.
- **Real openings.** Windows are holes in the wall, not pictures on it, so
  things outside the set, like props flying past, can be seen. A window
  into another room, like the porthole in the door, is dark glass instead.
- **Things touch what they stand on.** Legs reach the floor, dark bands at
  the base of walls meet the floor, and nothing floats.

## Color

- **Stay close to the original colors.** Every color is about 90% the
  original color measured from the 1995 pictures and 10% a brighter cartoon
  color (`half(cartoon, original)`, `CARTOON = 0.10` in `lib/toonkit.py`).
  Brighter palettes were tried and rejected.
- **Measure colors from well-lit areas of the pictures**, not shadows.
  Use the median over the area.
- **Matching materials match exactly.** Where the original uses the same
  material in two places, use one color for both: green walls are the
  floor's carpet, and the jump seat's stripes are the other seats' stripes.
- **Exposure is 1.4**, with ACES tone mapping in the viewer. Pick colors
  under that setting, not raw.

## Surfaces

- **Flat colors, with a procedural texture strong enough to see.** Fabric,
  carpet, wood, metal and hammered metal patterns come from the shader
  (`viewer/surface.js`). Each face carries its kind in its vertex color.
  - The cabin needed the texture turned up three times.
  - The door then needed it toned back down.
  - The carpet wanted a coarse, blotchy pattern.
  - The mansion added flagstones (staggered slabs, each its own shade)
    and damask wallpaper (a flame motif on a half-drop repeat).
- **Smooth shading across gentle bends, crisp at real edges.** Normals are
  averaged across bends under 40°, in `smooth_normals`. Without this,
  curved parts like headrests look rough.
- **Stripes and panels are painted on, not stuck on.** Split the mesh along
  the stripe's edges and color the faces, projected straight through the
  object, so a stripe wraps around edges onto side faces. Raised strips
  looked janky where they met a bend.
- **A stripe keeps its color all the way along.** Going up a seat back, the
  same x position stays the same color from bottom to top. The colors don't
  change partway.

## Things beyond the set

- **The sky** is mostly white, softly mottled lavender cloud, at an
  effectively infinite distance (a sphere, looked up by view direction), so
  it sits right in a headset. The mansion's is a moonlit night.
- **Pictures stay pictures.** A painting on a wall keeps the original's
  image as a texture (brightened, since the player lights it again).
- **Windows look out on something.** Ground, a horizon and whatever the
  original shows through the glass (the dining room: dead trees), not just
  sky.

## Notes from the dining room

- **Wood grain follows the piece.** The shader runs grain along the mesh's
  own z, so build long pieces (a table) with their length along z and
  place them turned; don't leave the grain running across.
- **Ornate where the original is busy.** A rug or a frame that's a blur
  of pattern in 1995 gets real ornament: the rug is a drawn texture
  (`dining/rug.py`), the frame a stepped, beaded molding with corner
  rosettes. Keep it in the room's palette and no brighter than its
  surroundings.
- **Molding has weight.** Cornices and dado rails are stepped profiles,
  not single bands.
- **Check shapes against the clearest camera.** The table's legs, the
  webs' extent and the stripes' direction were all clear in one view and
  wrong when guessed.
- **Lighting is computed once.** Shadows are rendered a single time and
  frames are only drawn when something changes. Earlier versions made a
  MacBook run hot.

## VRML and retro machines (later)

For the low-poly VRML export to period PCs, jank is welcome. Drop the
painted-stripe splits and the bevels, and keep the silhouettes. Everything
above is for the VR version.

## Process for a new set

1. **Gather the pictures and measurements.** Export the original views
   (`viewer/export_views.py`) and build the point cloud (`lib/cloud.py`).
   Look at all of the camera angles before building anything.
2. **List what's in the set.**
   - The structure: walls, floor, ceiling, openings.
   - Each kind of prop, and how many of it there are.
   - Every small feature you can see: stripes, handles, panels, lights,
     shades, trim.
   - For each, which cameras see it best.
3. **Measure each item from the point cloud:** position, size, color and
   count. Write the numbers into the build script with a comment saying
   where they came from.
4. **Build the structure first, then the props, then the details.**
5. **Review before showing anyone.** Run `viewer/compare.py` and go through
   every camera angle, ours next to the original, with this checklist.
   Only then publish.

### Review checklist

For each camera angle, compare ours against the original:

- **Counts.** Stripes per wall section, handles, windows, legs, lights.
  Are the stripes evenly spaced?
- **Positions.** Handles, portholes and shades: are they at the same height
  and edge distance? Do bands on walls line up with the original's
  heights?
- **Openings.** Can you see through what should be see-through, like
  windows and cup holders, and not through what shouldn't be?
- **Contact.** Does everything reach the floor or wall it should? Is
  anything floating? Does anything poke through?
- **Color.** Is each material one color everywhere? Is anything brighter or
  more saturated than the original next to it?
- **Shape.** Silhouettes of the main props. Are curves round where the
  original is round? Do supports lean the right way?
- **Texture.** Can you see the texture on every surface? Is it the right
  kind for the material?
- **Extras.** Is there anything ours has that the original doesn't, like a
  bezel, a crossbar or an extra stripe? Those were common notes on the cabin.
- **Comfort.** Is the triangle count reasonable? Does the explorer stay
  responsive?

Then walk around in the explorer at seated and standing eye height, from
places the original cameras never went. That's where VR will take people.
