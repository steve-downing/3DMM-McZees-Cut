"""Where things live: the repo root, the shipped 3DMM content, and the build cache."""
import os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
BKGDS = os.environ.get('TDMM_BKGDS', os.path.join(ROOT, 'content-files', 'bkgds.3cn'))
BASEPAL = os.path.join(ROOT, 'src', 'render', 'basepal.h')
