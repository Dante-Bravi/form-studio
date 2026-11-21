"""Load bundled weights or the smaller parts stored in the source repository."""
import io
from pathlib import Path
import joblib

ROOT = Path(__file__).resolve().parent


def movement_model():
    model = ROOT / 'movement_model.joblib'
    if model.exists():
        return joblib.load(model)
    parts = sorted((ROOT / 'models').glob('movement_model.part*'))
    if not parts:
        raise FileNotFoundError('Movement model is missing. Extract the entire release or clone all model parts.')
    return joblib.load(io.BytesIO(b''.join(part.read_bytes() for part in parts)))
