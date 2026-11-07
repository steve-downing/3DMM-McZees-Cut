# McZee's Cut: ideas and loose ends

Things we want to do, roughly in the order we'd get to them. Add freely.

## Attach actors to actors and props

Let one actor ride another: on someone's shoulders, on a crawling Bongo's
back, in the car, in the balloon's basket.

**Model.** An attachment is a span on the rider: attached at frame X,
detached at frame Y (or never), to one of the mount's body parts, at an
offset captured when attaching. Mounts can be actors or props, and riders
can have riders (no cycles).

**Position and rotation are the truth.** The rider's movement while
attached is saved as ordinary move and rotate events, the same as if it
had been animated by hand, so the movie plays correctly anywhere,
including original 3DMM. Attached-ness is editing metadata: it tells the
studio to keep regenerating those events from the mount while you edit
the mount. If the two ever disagree, the saved motion wins.

**Editing.** Any move, rotate or other change made to the rider directly
detaches it at that frame.

**File format.** Store the attachment spans in a new child chunk of the
rider's ACTR (e.g. `ATCH`: frame range, the mount's actor id, body part
index, offset matrix). Original 3DMM only reads the children it knows
(PATH, GGAE), so it ignores the chunk; the movie version stays 2, so it
still opens. Don't add a new actor event type for this: original 3DMM
stops on events it doesn't know (`Bug("Unimplemented actor event")`).

**In original 3DMM:** the movie opens and plays (the baked motion), and
the attachments are dropped from any scene the user edits and saves there.
Check that untouched scenes keep their extra chunks.

**Open questions**
- UI: pick the rider, choose Attach, click a body part on the mount (the
  costume tool already picks body parts)? A key held while dragging one
  actor onto another?
- How often to bake: every frame of the span, or only where the mount's
  part moves?
- Path recording and undo assume every actor owns its own position; see
  how they cope with a rider whose events are generated.

## McZee

- Refine the blockout (addons/mczee): proportions, head shape, fewer
  triangles (about 2,700 now; Gustave is about 1,000).
- More outfits as costumes: studio (cap and jacket), ticket booth (vest and
  bow tie), inspiration (jacket and olive pants), snack bar chef.
- His own actions: a talk with mouth shapes, a wave, the unicycle.
- Publish the add-on as its own download (McZee.zip), not in the core
  package.

## Actors

- A Blender add-on (a panel with Import and Export buttons) on top of
  tools/actors.
- Skinned meshes: split a weighted mesh into rigid parts by bone, so
  people can start from a normal rigged character.
- Movies that carry their own custom actors, the way 3D text is saved
  inside the movie (`ksidUseCrf`), so a friend without the add-on can
  still open the movie.
- A list of add-on chunk number blocks so add-ons from different people
  never collide.
- Costume browser thumbnails for add-on actors.

## New content from other games

Converters run on the user's own copies of the games; none of their assets
go in this repo or its downloads.

- **Background writer.** The piece everything below needs: write BKGD
  chunks (a picture and a depth map per camera, camera, lights, palette)
  into an add-on .3cn/.3th, from a 3D scene rendered in Blender.
- **Minecraft (Java Edition) characters.** Skins and mobs are already rigid
  boxes, which is exactly how 3DMM actors work. Build the box models from
  Minecraft's model dimensions and the player's own skin PNG, with a
  procedural action set (walk, run, jump, sit, wave, talk...). Mob
  textures come from the user's Minecraft install.
- **Minecraft worlds as sets.** Read a region of a world save (Anvil
  .mca files, e.g. from our own server), build it in Blender and render
  it as a 3DMM background from several camera angles. The real 3D stays
  available for VR.
- **Cartooners and Cartooners in Space.** Figure out their file formats,
  then turn sprites into "paper cutout" actors (flat cards that swap
  pictures per cel, the way 3DMM swaps models) and backgrounds into sets.
  Also: original characters and sets in a Cartooners style.

## Export

- The Save As and Export dialogs: the old portfolio skin and the newer
  Windows common dialog don't fit together well. Give them some love.
- Cancel an export from 3DMM's progress panel.
- Movie Exporter's main window: a real percentage per movie, from the
  same progress reports.

## Later

- A VR player: the cartoon cabin and actors, with dialogue placed where the
  characters are (WebXR).
- Low-poly VRML export of sets and actors.
