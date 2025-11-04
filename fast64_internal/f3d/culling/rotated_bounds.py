import numpy as np

from mathutils import Matrix
from bpy.types import Mesh


def get_rotated_bounding_box(mesh_points_int: np.ndarray[np.int64, (..., 3)]) -> np.ndarray[np.int64, (8, 3)]:
    mins = mesh_points_int.min(axis=0)
    maxs = mesh_points_int.max(axis=0)

    return np.array(
        [
            [mins[0], mins[1], mins[2]],
            [maxs[0], mins[1], mins[2]],
            [maxs[0], maxs[1], mins[2]],
            [mins[0], maxs[1], mins[2]],
            [mins[0], mins[1], maxs[2]],
            [maxs[0], mins[1], maxs[2]],
            [maxs[0], maxs[1], maxs[2]],
            [mins[0], maxs[1], maxs[2]],
        ],
        dtype=np.int64,
    )
