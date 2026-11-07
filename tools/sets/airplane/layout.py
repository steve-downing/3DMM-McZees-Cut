"""Where the repeated props sit in the airplane cabin (measured; see seats.py).
Local prop frame: x across, y up, z forward; flip = turned 180 degrees about y."""
import numpy as np

XS = [-18.6, -10.2, 9.6, 18.2]
# rows A and B face the rear (+z); row C faces the front, its backs toward the rear wall
ROWS = [(-16.4, False), (-1.0, False), (26.56, True)]
INST = [(np.array([x, 0.0, z]), f) for z, f in ROWS for x in XS]
# the small seat at the end of the aisle: the same seat, scaled (see assemble)
SMALL = dict(t=[-0.6, 0.0, 26.56], flip=True)

def R(flip): return np.diag([-1.0, 1, -1]) if flip else np.eye(3)

TABLES = [(np.eye(3), np.array([-21.35, 0.0, 13.2])), (np.diag([-1.0, 1, 1]), np.array([21.1, 0.0, 13.1]))]
