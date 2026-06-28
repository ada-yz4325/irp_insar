"""
Shared helper for reading ISCE2 binary image products via their .xml
metadata sidecar (width/length/band-count/interleave-scheme/dtype),
instead of assuming single-band float32 like ad-hoc readers tend to.

ISCE2's topsStack .unw products are 2-band BIL (amplitude, phase) and
.conncomp products are single-band byte -- guessing the layout (as the
original plot_isce2_products.py did) silently misreads multi-band files.
"""

import sys

import isce  # noqa: F401 -- required for isceobj's plugin registration
import isceobj
import numpy as np

_DTYPE_MAP = {
    "FLOAT": np.float32,
    "CFLOAT": np.complex64,
    "DOUBLE": np.float64,
    "BYTE": np.uint8,
    "SHORT": np.int16,
    "INT": np.int32,
}


def read_isce_image(path: str):
    """
    Read an ISCE2 image product given its data file path (no .xml suffix).

    Returns a single 2D array if the image has one band, otherwise a list
    of 2D arrays (one per band, in band order).
    """
    img = isceobj.createImage()
    img.load(path + ".xml")
    width = img.getWidth()
    length = img.getLength()
    bands = img.bands
    scheme = img.scheme.upper()
    dtype = _DTYPE_MAP.get(img.dataType.upper(), np.float32)

    raw = np.fromfile(path, dtype=dtype)
    expected = length * width * bands
    if raw.size != expected:
        sys.exit(
            f"{path}: read {raw.size} samples, expected {expected} "
            f"(length={length}, width={width}, bands={bands})"
        )

    if bands == 1:
        return raw.reshape(length, width)
    if scheme == "BIL":
        arr = raw.reshape(length, bands, width)
        return [arr[:, b, :] for b in range(bands)]
    if scheme == "BSQ":
        arr = raw.reshape(bands, length, width)
        return [arr[b] for b in range(bands)]
    if scheme == "BIP":
        arr = raw.reshape(length, width, bands)
        return [arr[:, :, b] for b in range(bands)]
    sys.exit(f"{path}: unsupported interleave scheme {scheme!r}")
