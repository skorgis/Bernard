"""The image type shared by every pipeline stage."""

import numpy as np
import numpy.typing as npt

type Image = npt.NDArray[np.uint8]
"""An 8-bit image as OpenCV uses it: `(h, w)` grayscale or `(h, w, 3)` BGR."""
