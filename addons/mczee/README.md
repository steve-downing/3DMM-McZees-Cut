# McZee

McZee, 3D Movie Maker's host, as an actor you can put in your own movies:
an add-on for McZee's Cut. He's a fan-made 3D take on the character from
3DMM's own 2D animations, which Microsoft released with 3DMM's source under
the MIT license. Not made or endorsed by Microsoft.

He wears his bellhop outfit, fez and all (or just his tuft of hair: pick
"Hat" in the costume browser), and does everything the stock actors do.

## Installing

Copy `mczee.3cn` and `mczee.3th` into `Microsoft Kids\3D Movie Maker` in your
McZee's Cut folder and start 3D Movie Maker. He's in the actor browser.
Movies with McZee in them need the add-on to open.

## Building him

    pip install bpy==5.2.3 numpy pillow
    python addons/mczee/build_mczee.py out --export --preview

`build_mczee.py` makes `mczee.blend` and the add-on. He's built from simple
shapes on Gustave's skeleton, so he gets all 33 of Gustave's actions; the
shapes, colors and outfits are at the top of the script. `preview.py` draws a
turnaround sheet. See [tools/actors](../../tools/actors/README.md) for how
actors work and how to make your own.
