"""立体声宽度处理包。"""

from .stereo import (
    WidthError,
    bass_mono,
    correlation,
    from_mid_side,
    mid_side,
    phase_guard,
    validate,
    widen,
    width_batch,
)

__all__ = [
    "WidthError",
    "mid_side",
    "from_mid_side",
    "widen",
    "bass_mono",
    "phase_guard",
    "correlation",
    "validate",
    "width_batch",
]
