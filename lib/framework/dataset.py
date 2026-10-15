"""dataset.py — leitura padronizada dos casos (NPZ) gravados pelo pipeline."""
import json
from pathlib import Path

import numpy as np


def _s(z, k, default=""):
    return str(z[k]) if k in z.files else default


def ctx_from_npz(path):
    """Contexto de verificação (scope=case) reconstruído SÓ do disco."""
    with np.load(path, allow_pickle=False) as z:
        arrays = {k: np.asarray(z[k]) for k in z.files if np.asarray(z[k]).ndim >= 1 and z[k].dtype.kind in "biufc"}
        scalars = json.loads(_s(z, "scalars_json", "{}"))
        grid = {k: float(z[k]) for k in ("dx", "dy", "dz", "dV") if k in z.files}
        grid.update({k: int(z[k]) for k in ("z_struct_start", "z_struct_end") if k in z.files})
        meta = {"geometry": _s(z, "geometry"), "geometry_hash": _s(z, "geometry_hash"), "case_signature": _s(z, "case_signature"),
                "seed": None if int(z["seed"]) < 0 else int(z["seed"]), "frequency_thz": float(z["frequency_THz"])}
    return {"scope": "case", "arrays": arrays, "scalars": scalars, "grid": grid, "meta": meta, "path": str(path)}


class CaseData:
    def __init__(self, path):
        self.path = Path(path)
        c = ctx_from_npz(self.path)
        self.meta, self.scalars, self.grid = c["meta"], c["scalars"], c["grid"]
        self.geometry, self.seed, self.frequency_thz = self.meta["geometry"], self.meta["seed"], self.meta["frequency_thz"]

    @property
    def key(self):
        return self.path.stem

    @property
    def group(self):
        return self.geometry

    def array(self, name):
        with np.load(self.path, allow_pickle=False) as z:
            return np.asarray(z[name])


class Dataset:
    def __init__(self, cases):
        self.cases = sorted(cases, key=lambda c: (c.frequency_thz, c.geometry, -1 if c.seed is None else c.seed))

    @classmethod
    def from_dir(cls, cases_dir):
        return cls([CaseData(p) for p in sorted(Path(cases_dir).glob("*.npz"))])

    def select(self, geometry=None, seeds=None, frequency_thz=None):
        out = self.cases
        if geometry:
            out = [c for c in out if c.geometry == geometry]
        if seeds is not None:
            out = [c for c in out if c.seed in seeds]
        if frequency_thz is not None:
            out = [c for c in out if abs(c.frequency_thz - frequency_thz) < 1e-9]
        return Dataset(out)

    def frequencies(self):
        return sorted({c.frequency_thz for c in self.cases})

    def __len__(self):
        return len(self.cases)
