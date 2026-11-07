# Test movies

CI renders every `.3mm` in this folder on each push: quick previews, a
stereo check and an end-to-end batch run. With no movies here, those steps
are skipped and CI only builds and packages the renderer.

This repository and its `ci-results` branch are public, and CI publishes
frames and videos of whatever it renders. Only add movies whose authors are
happy for them to be published.

For full-length videos, list file names from this folder in
`ci-render-requests.txt`, one per line.
