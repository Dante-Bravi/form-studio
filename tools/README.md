# Release build

Run `Build-Launcher.ps1`, then run `tools/build_release.py` with the verified Python 3.12 runtime and `--dependencies` pointing to its installed packages. The builder includes a portable interpreter, packages with their notices, frontend, and model weights, checks isolated loading, and creates `dist/FormStudio-Windows-x64.zip` plus its SHA-256 checksum.

Raw videos, feature caches, experiments, old models, logs, and local environments are excluded from Git and the release ZIP. `DEPENDENCIES.txt` records the exact installed versions included in a build.
