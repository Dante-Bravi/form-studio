"""Build a portable Windows ZIP from a verified Python runtime and dependencies."""
import argparse
import hashlib
from importlib.metadata import distributions
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ['FormStudio.exe', 'FORM.ico', 'desktop_server.py', 'live_camera.py', 'model_assets.py',
         'session_ui.py', 'exercise_pdf.py', 'train_form.py', 'form_models.joblib', 'movement_model.joblib',
         'pose_landmarker_lite.task', 'README.md', 'THIRD_PARTY.md', 'DEPENDENCIES.txt']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dependencies', type=Path, default=ROOT / '.training-deps')
    parser.add_argument('--reuse-runtime', action='store_true')
    args = parser.parse_args()
    deps = args.dependencies.resolve()
    runtime = Path(sys.base_prefix).resolve()
    stage = ROOT / 'dist/FormStudio'
    if stage.exists() and not args.reuse_runtime:
        raise SystemExit('dist/FormStudio already exists. Move it aside before rebuilding.')
    stage.mkdir(parents=True, exist_ok=True)
    inventory = sorted(f"{d.metadata['Name']}=={d.version}" for d in distributions(path=[str(deps)]))
    (ROOT / 'DEPENDENCIES.txt').write_text('Python ' + sys.version.split()[0] + '\n' + '\n'.join(inventory) + '\n')
    for name in FILES:
        if name == 'movement_model.joblib' and not (ROOT / name).exists():
            with (stage / name).open('wb') as output:
                for part in sorted((ROOT / 'models').glob('movement_model.part*')):
                    with part.open('rb') as source:
                        shutil.copyfileobj(source, output)
        else:
            shutil.copy2(ROOT / name, stage / name)
    shutil.copytree(ROOT / 'desktop', stage / 'desktop', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('main.cjs', '__pycache__', '*.log'))
    shutil.copytree(ROOT / 'assets', stage / 'assets', dirs_exist_ok=True)
    target = stage / 'runtime'
    target.mkdir(exist_ok=True)
    for file in ([] if args.reuse_runtime else runtime.iterdir()):
        if file.is_file() and (file.suffix in ('.exe', '.dll', '.txt') or file.name.startswith('LICENSE')):
            shutil.copy2(file, target / file.name)
    for name in (() if args.reuse_runtime else ('DLLs', 'Lib', 'tcl')):
        shutil.copytree(runtime / name, target / name,
            ignore=shutil.ignore_patterns('site-packages', '__pycache__', '*.pyc'))
    if not args.reuse_runtime:
        shutil.copytree(deps, target / 'Lib/site-packages',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'mpl-cache'))
    print('Portable runtime copied. Verifying isolated imports and models...', flush=True)
    import os
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    env['PYTHONNOUSERSITE'] = '1'
    env['MPLCONFIGDIR'] = str(ROOT / 'dist/verification-cache')
    subprocess.run([str(target / 'python.exe'), '-I', '-c',
        "import sys;sys.path.insert(0, '.');import runpy;sys.argv=['desktop_server.py','--check'];runpy.run_path('desktop_server.py',run_name='__main__')"],
        cwd=stage, env=env, check=True)
    manifest = {}
    for name in FILES:
        manifest[name] = hashlib.sha256((stage / name).read_bytes()).hexdigest()
    (stage / 'SHA256SUMS.json').write_text(json.dumps(manifest, indent=2))
    archive = ROOT / 'dist/FormStudio-Windows-x64.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for file in sorted(stage.rglob('*')):
            if file.is_file() and '__pycache__' not in file.parts:
                output.write(file, file.relative_to(stage.parent))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n')
    print(f'Built {archive.name} ({archive.stat().st_size / 1024**2:.1f} MB)', flush=True)


if __name__ == '__main__':
    main()
