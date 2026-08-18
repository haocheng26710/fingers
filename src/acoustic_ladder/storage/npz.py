"""Canonical timestamp-free NumPy archive encoding shared by synthetic artifacts."""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Mapping

import numpy as np
from numpy.typing import NDArray

_ARRAY_NAME = re.compile(r"^[A-Za-z0-9_]+$")


def deterministic_npz_bytes(arrays: Mapping[str, NDArray[np.generic]]) -> bytes:
    """Encode sorted C-contiguous non-object arrays with fixed ZIP metadata."""

    if not arrays:
        raise ValueError("deterministic NPZ requires at least one array")
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(arrays):
            array = arrays[name]
            if _ARRAY_NAME.fullmatch(name) is None:
                raise ValueError(f"unsafe NPZ array name: {name!r}")
            if array.dtype.hasobject:
                raise ValueError(f"object arrays are forbidden: {name}")
            if not array.flags.c_contiguous:
                raise ValueError(f"NPZ array must be C-contiguous: {name}")
            if array.dtype.kind in "fc" and not bool(np.isfinite(array).all()):
                raise ValueError(f"NPZ array contains non-finite values: {name}")
            npy = io.BytesIO()
            np.save(npy, array, allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o600 << 16
            archive.writestr(info, npy.getvalue())
    return output.getvalue()


def load_deterministic_npz(payload: bytes) -> dict[str, NDArray[np.generic]]:
    """Decode an NPZ and prove it is byte-canonical and pickle-free."""

    try:
        with np.load(io.BytesIO(payload), allow_pickle=False) as archive:
            arrays = {name: np.ascontiguousarray(archive[name]) for name in sorted(archive.files)}
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise ValueError(f"invalid deterministic NPZ: {exc}") from exc
    if deterministic_npz_bytes(arrays) != payload:
        raise ValueError("NPZ bytes are not canonical")
    return arrays
