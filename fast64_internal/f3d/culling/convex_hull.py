"""Pylance is horrible at numpy typing and this file proves it, type: ignore my beloved"""

import numpy as np
from collections import deque
from typing import cast, NamedTuple
import heapq

from bpy.types import Mesh, Object
from mathutils import Matrix

from ...utility import PluginError


IntPoint = np.ndarray[np.int64, 3]  # type: ignore
FloatPoint = np.ndarray[np.float64, 3]  # type: ignore

IntPoints = np.ndarray[np.int64, (..., 3)]  # type: ignore
FloatPoints = np.ndarray[np.float64, (..., 3)]  # type: ignore


def point_to_f64(point: IntPoint):
    return cast(FloatPoint, point.astype(np.float64))


class FaceHull:
    def __init__(
        self,
        p1_idx: int,
        p2_idx: int,
        p3_idx: int,
        all_points: IntPoints,
    ):
        self.indices: list[int] = [p1_idx, p2_idx, p3_idx]
        # make these float64 for calculations
        p1, p2, p3 = (point_to_f64(all_points[vertex_idx]) for vertex_idx in (p1_idx, p2_idx, p3_idx))

        self.normal: FloatPoint = np.cross(p2 - p1, p3 - p1)  # type: ignore
        norm_len = float(np.linalg.norm(self.normal))

        if norm_len < TOLERANCE:  # degenerate
            self.normal = cast(FloatPoint, np.zeros(3, dtype=np.float64))
            self.d: float = 0.0
            self.is_valid: bool = False
        else:
            self.normal: FloatPoint = self.normal / norm_len  # type: ignore
            # plane equation
            self.d = -np.dot(self.normal, p1)
            self.is_valid = True

        self.outside_set: set[int] = set()  # indices of points outside this face
        self.centroid: FloatPoint = (p1 + p2 + p3) / 3.0  # type: ignore

    def dist(self, point: FloatPoint) -> float:
        return np.dot(self.normal, point) + self.d


def get_face_sort_key(f: FaceHull):
    return (f.centroid[0], f.centroid[1], f.centroid[2])


class OutsidePointsInfo(NamedTuple):
    points: FloatPoints
    dists: np.ndarray[np.float64, (...)]
    mask: np.ndarray[np.bool_, (...)]


class HullPlaneResult(NamedTuple):
    normals: FloatPoints
    ds: np.ndarray[np.float64, (...)]
    valid_plane_mask: np.ndarray[np.bool_, (...)]
    valid_normals: FloatPoints
    valid_ds: np.ndarray[np.float64, (...)]


TOLERANCE = 1e-8


class ConvexHull3D:
    """
    Computes an exact 3D convex hull in integer coordinates
    and a containment-guaranteed decimation algorithm.
    """

    def __init__(self, points: IntPoints):
        self.original_points = points

        if len(self.original_points) < 4:
            raise ValueError("Need at least 4 points for 3D convex hull")

        # final output vertices
        self.hull_points = cast(IntPoints, np.array([], dtype=np.int64).reshape(0, 3))

        # vertices for calculations
        self.calc_points = cast(FloatPoints, self.original_points.astype(np.float64))
        self.hull_calc_points = cast(FloatPoints, np.array([], dtype=np.float64).reshape(0, 3))

        # self.faces will store lists of indices into self.hull_points
        self.faces: list[list[int]] = []

        # cache for hull planes
        self._hull_normals: FloatPoints | None = None
        self._hull_ds: np.ndarray[np.float64] | None = None  # plane distances # type: ignore
        self._valid_plane_mask: np.ndarray[np.bool_] | None = None  # type: ignore
        self._valid_hull_normals: FloatPoints | None = None
        self._valid_hull_ds: np.ndarray[np.float64] | None = None  # type: ignore

    def _find_initial_simplex(self):
        """Find four points that form a 3D tetrahedron with real volume (not degenerate), otherwise error out."""
        # find extreme points along x-axis
        min_idx = int(np.argmin(self.calc_points[:, 0]))
        max_idx = int(np.argmax(self.calc_points[:, 0]))

        p1, p2 = self.calc_points[min_idx], self.calc_points[max_idx]

        # find point farthest point from the line p1 -> p2
        dists_line: FloatPoints = np.linalg.norm(np.cross(self.calc_points - p1, p2 - p1), axis=1)  # type: ignore
        third_idx = int(np.argmax(dists_line))

        p3 = self.calc_points[third_idx]

        # find point farthest from plane of first 3 points
        normal: FloatPoint = np.cross(p2 - p1, p3 - p1)  # type: ignore
        norm_len: float = np.linalg.norm(normal)  # type: ignore
        if norm_len < TOLERANCE:
            # the first 3 points are collinear, find a different third point
            sorted_indices = np.argsort(dists_line)
            for i in range(1, len(sorted_indices) + 1):
                third_idx_candidate = int(sorted_indices[-i])
                if third_idx_candidate not in (min_idx, max_idx):
                    third_idx = third_idx_candidate
                    p3 = self.calc_points[third_idx]
                    normal = np.cross(p2 - p1, p3 - p1)  # type: ignore
                    norm_len = np.linalg.norm(normal)  # type: ignore
                    if norm_len > TOLERANCE:
                        break
            else:
                raise RuntimeError("Could not find 3 non-collinear points.")

        normal: FloatPoint = normal / norm_len  # type: ignore
        dists_plane: FloatPoints = np.abs(np.dot(self.calc_points - p1, normal))  # type: ignore
        fourth_idx = int(np.argmax(dists_plane))

        if dists_plane[fourth_idx] < TOLERANCE:
            raise RuntimeError("Could not find 4 non-coplanar points. Points are coplanar.")

        return (min_idx, max_idx, third_idx, fourth_idx)

    def _get_initial_faces(self, simplex_indices: tuple[int, int, int, int]):
        centroid: FloatPoint = np.mean(self.calc_points[list(simplex_indices)], axis=0)  # type: ignore

        faces: set[FaceHull] = set()
        for idx0, idx1, idx2 in [(0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)]:
            face = FaceHull(simplex_indices[idx0], simplex_indices[idx1], simplex_indices[idx2], self.original_points)
            if face.dist(centroid) > TOLERANCE:  # face is pointing inward, flip it
                face = FaceHull(face.indices[0], face.indices[2], face.indices[1], self.original_points)
            faces.add(face)

        return faces

    def _initial_points(self, hull_vertex_indices: set[int], all_faces: set[FaceHull]):
        """Assign the points to the initial faces, putting points into the outside set of the face with the largest distance"""
        all_points_indices: set[int] = set(range(len(self.calc_points))) - hull_vertex_indices
        process_queue: deque[FaceHull] = deque()

        sorted_faces = sorted(list(all_faces), key=get_face_sort_key)

        for pt_idx in sorted(list(all_points_indices)):
            pt: FloatPoint = self.calc_points[pt_idx]
            best_face: FaceHull | None = None
            max_dist: float = TOLERANCE
            for face in sorted_faces:
                d = face.dist(pt)
                if d > max_dist:
                    max_dist = d
                    best_face = face

            if best_face:
                best_face.outside_set.add(pt_idx)

        for face in sorted_faces:
            if face.outside_set:
                process_queue.append(face)

        return process_queue

    def find_visible_faces(self, current_face: FaceHull, all_faces: set[FaceHull], furthest_point: FloatPoint):
        """
        Find all neighboring faces visible from a given point, the points outside them, and their horizon edges.

        Returns the visible faces, their outside points, and the edges
        shared between visible and hidden faces (the horizon) used to attach new faces.
        """

        class NeighboringResult(NamedTuple):
            visible_faces: set[FaceHull]
            horizon_edges: dict[tuple[int, int], int]
            points_to_reassign: set[int]

        result = NeighboringResult(set(), {}, set())
        visible_faces, horizon_edges, points_to_reassign = result

        neighbour_queue: deque[FaceHull] = deque([current_face])
        visited: set[FaceHull] = {current_face}

        sorted_faces = sorted(list(all_faces), key=get_face_sort_key)

        while neighbour_queue:
            face = neighbour_queue.popleft()
            if face.dist(furthest_point) <= TOLERANCE:
                continue  # face is not visible

            visible_faces.add(face)
            points_to_reassign.update(face.outside_set)

            for i in range(3):  # find neighbors
                v1, v2, v_other = face.indices[i], face.indices[(i + 1) % 3], face.indices[(i + 2) % 3]
                edge = tuple(sorted((v1, v2)))

                if edge in horizon_edges:  # edge is shared by two visible faces, remove from horizon
                    del horizon_edges[edge]  # type: ignore
                else:
                    horizon_edges[edge] = v_other  # type: ignore

                for other_face in sorted_faces:
                    if other_face in visited or other_face == face:
                        continue

                    if v1 in other_face.indices and v2 in other_face.indices:  # found a neighbor
                        neighbour_queue.append(other_face)
                        visited.add(other_face)
                        break

        return result

    def create_new_faces(
        self, furthest_pt_idx: int, horizon_edges: dict[tuple[int, int], int], points_to_reassign: set[int]
    ):
        new_faces: list[FaceHull] = []
        for edge, v_other in sorted(horizon_edges.items()):
            p1, p2 = edge

            # create new face (using int points)
            new_face = FaceHull(p1, p2, furthest_pt_idx, self.original_points)

            # orient it correctly
            # we use v_other (from the old visible face) as a reference point
            # the new face should point *away* from it
            if new_face.dist(self.calc_points[v_other]) > -TOLERANCE:
                # pointing towards v_other (inward) or co-planar, flip it
                new_face = FaceHull(p2, p1, furthest_pt_idx, self.original_points)

            if new_face.is_valid:
                new_faces.append(new_face)

        # re-assign points to new faces
        for pt_idx in points_to_reassign:
            pt = self.calc_points[pt_idx]
            best_face = None
            max_dist = TOLERANCE
            for face in new_faces:
                d = face.dist(pt)
                if d > max_dist:
                    max_dist = d
                    best_face = face
            if best_face:
                best_face.outside_set.add(pt_idx)

        return new_faces

    def compute_hull(self) -> bool:
        try:
            # this is just an initial state, it will never represent any real mesh by it self, it will wrap as much as it can
            # with 4 of the original points
            simplex_indices = self._find_initial_simplex()
        except Exception as exc:
            print("Failed to find initial simplex.")
            return False

        all_faces = self._get_initial_faces(simplex_indices)

        hull_vertex_indices = set(simplex_indices)
        process_queue = self._initial_points(hull_vertex_indices, all_faces)

        while process_queue:
            current_face = process_queue.popleft()

            if not current_face.outside_set or current_face not in all_faces:
                continue  # this face was already processed or removed

            # find furthest point
            furthest_pt_idx = -1
            max_dist = 0.0
            for pt_idx in current_face.outside_set:
                d = current_face.dist(self.calc_points[pt_idx])
                if d > max_dist:
                    max_dist = d
                    furthest_pt_idx = pt_idx

            if furthest_pt_idx == -1:
                continue  # no points outside this face

            hull_vertex_indices.add(furthest_pt_idx)
            furthest_point: FloatPoint = self.calc_points[furthest_pt_idx]

            visible_faces, horizon_edges, points_to_reassign = self.find_visible_faces(
                current_face, all_faces, furthest_point
            )
            if not visible_faces:  # point was inside (numerical error)
                continue
            all_faces -= visible_faces

            new_faces = self.create_new_faces(furthest_pt_idx, horizon_edges, points_to_reassign)
            all_faces.update(new_faces)

            # add new faces with points to the queue
            for face in new_faces:
                if face.outside_set:
                    process_queue.append(face)

        # finalize
        # convert hull vertex indices to final coordinate array
        # and re-map face indices to be local
        final_hull_indices_list: list[int] = sorted(list(hull_vertex_indices))
        self.hull_points = self.original_points[final_hull_indices_list]
        self.hull_calc_points = cast(FloatPoints, self.calc_points[final_hull_indices_list])

        # map from original_points index -> hull_points index
        vertex_map: dict[int, int] = {orig_idx: new_idx for new_idx, orig_idx in enumerate(final_hull_indices_list)}

        # convert FaceHull objects to simple index lists
        self.faces = []
        for face in all_faces:
            if not face.is_valid:
                continue
            remapped_face = [vertex_map[i] for i in face.indices]
            self.faces.append(remapped_face)
        # winding is fixed during creation, but we call this just in case
        self._fix_winding()
        return True

    def invalidate_hull_cache(self):
        self._hull_normals = None
        self._hull_ds = None
        self._valid_plane_mask = None
        self._valid_hull_normals = None
        self._valid_hull_ds = None

    def _orient_faces_list_outward(
        self,
        faces_list: list[list[int]],
        vertex_positions: FloatPoints,
        centroid: FloatPoint,
    ):
        """
        Ensures a list of faces is oriented to point away from a given centroid (in-place).
        Returns True if any faces were flipped
        """
        if not faces_list:
            return False

        face_indices_arr = np.array(faces_list, dtype=np.int64)
        if face_indices_arr.shape[0] == 0:
            return False
        face_verts = vertex_positions[face_indices_arr]

        v0s = face_verts[:, 0]
        v1s = face_verts[:, 1]
        v2s = face_verts[:, 2]

        normals = np.cross(v1s - v0s, v2s - v0s)  # type: ignore
        face_centers = (v0s + v1s + v2s) / 3.0  # type: ignore

        norms: np.ndarray[np.float64] = np.linalg.norm(normals, axis=1)  # type: ignore
        valid_mask = norms > TOLERANCE  # type: ignore

        dots = np.zeros(len(faces_list), dtype=np.float64)
        dots[valid_mask] = np.sum(normals[valid_mask] * (face_centers[valid_mask] - centroid), axis=1)

        faces_changed = False
        for i, face in enumerate(faces_list):
            if dots[i] < -TOLERANCE:  # inward, flip
                faces_list[i] = [face[0], face[2], face[1]]
                faces_changed = True

        return faces_changed

    def _fix_winding(self):
        """Ensure all faces have outward-pointing normals."""
        if not self.faces or len(self.hull_calc_points) == 0:
            return

        centroid: FloatPoint = np.mean(self.hull_calc_points, axis=0)  # type: ignore

        faces_changed = self._orient_faces_list_outward(self.faces, self.hull_calc_points, centroid)

        if faces_changed:
            self.invalidate_hull_cache()

    def get_hull_points(self) -> IntPoints:
        return np.unique(self.hull_points, axis=0)  # type: ignore

    def _compute_hull_planes(self) -> HullPlaneResult:
        """
        Vectorized computation of all hull face planes (normal and d).
        Results are cached in self._hull_normals and self._hull_ds.
        Only runs if not already cached.
        """

        if self._hull_normals is not None and self._hull_ds is not None and self._valid_plane_mask is not None:
            return HullPlaneResult(self._hull_normals, self._hull_ds, self._valid_plane_mask, self._valid_hull_normals, self._valid_hull_ds)  # type: ignore

        if not self.faces:
            self._hull_normals = np.array([], dtype=np.float64).reshape(0, 3)  # type: ignore
            self._hull_ds = np.array([], dtype=np.float64)  # type: ignore
            self._valid_plane_mask = np.array([], dtype=np.bool_)  # type: ignore
            self._valid_hull_normals = np.array([], dtype=np.float64).reshape(0, 3)  # type: ignore
            self._valid_hull_ds = np.array([], dtype=np.float64)  # type: ignore
            return self._compute_hull_planes()

        faces_arr = np.array(self.faces, dtype=np.int64)
        v0s: FloatPoints = self.hull_calc_points[faces_arr[:, 0]]  # type: ignore
        v1s: FloatPoints = self.hull_calc_points[faces_arr[:, 1]]  # type: ignore
        v2s: FloatPoints = self.hull_calc_points[faces_arr[:, 2]]  # type: ignore

        normals: FloatPoints = np.cross(v1s - v0s, v2s - v0s)  # type: ignore
        self._hull_normals = np.zeros_like(normals, dtype=np.float64)  # type: ignore

        # create a mask for valid (non-zero-area) faces
        norms: np.ndarray[np.float64] = np.linalg.norm(normals, axis=1)  # type: ignore
        self._valid_plane_mask = norms > TOLERANCE  # type: ignore
        valid_norms: np.ndarray[np.float64] = norms[self._valid_plane_mask]  # type: ignore

        # normalize all valid normals
        if valid_norms.shape[0] > 0:
            self._hull_normals[self._valid_plane_mask] = (  # type: ignore
                normals[self._valid_plane_mask] / valid_norms[:, np.newaxis]
            )

        # compute d for all planes (Ax + By + Cz + d = 0)
        # d = -np.dot(normal, v0)
        self._hull_ds = -np.sum(self._hull_normals * v0s, axis=1)  # type: ignore

        self._valid_hull_normals = self._hull_normals[self._valid_plane_mask]  # type: ignore
        self._valid_hull_ds = self._hull_ds[self._valid_plane_mask]  # type: ignore

        return self._compute_hull_planes()

    def all_points_inside(self, test_points: FloatPoints, error_allowance: float) -> bool:
        """
        Vectorized check if all test_points are inside the *current* hull
        """
        test_points_arr = np.asarray(test_points, dtype=np.float64)
        if test_points_arr.ndim == 1:
            test_points_arr = test_points_arr.reshape(1, -1)

        if not self.faces:
            return False  # no hull to be inside of

        hull_planes = self._compute_hull_planes()
        valid_normals, valid_ds = hull_planes.valid_normals, hull_planes.valid_ds

        if valid_normals.shape[0] == 0:
            return False  # no valid faces to be inside of

        dists: np.ndarray[np.float64] = np.dot(test_points_arr, valid_normals.T) + valid_ds  # type: ignore

        # all points must have dist <= tolerance for all valid planes
        return np.all(dists <= TOLERANCE + error_allowance)  # type: ignore

    ###### Decimation logic ######
    def _calculate_all_removal_errors(self, costs: np.ndarray[np.float64]):  # type: ignore
        for i in range(len(self.hull_calc_points)):
            costs[i] = self._calculate_removal_error(i)

    def _get_vertex_ring(self, vert_idx: int) -> tuple[list[int], list[int]]:
        """
        Finds all faces using vert_idx and returns the ordered
        ring of neighbor vertices that form the "hole" boundary.
        """
        affected_faces: dict[int, list[int]] = {}  # face_idx -> face
        edge_to_face_map: dict[tuple[int, int], int] = {}  # (v1, v2) -> face_idx

        for face_idx, face in enumerate(self.faces):
            if vert_idx not in face:
                continue
            affected_faces[face_idx] = face
            for i in range(3):
                v1 = face[i]
                v2 = face[(i + 1) % 3]
                if vert_idx not in (v1, v2):  # this is a boundary edge
                    edge_to_face_map[tuple(sorted((v1, v2)))] = face_idx  # type: ignore

        if len(edge_to_face_map) <= 0:  # isolated vertex
            return [], []

        # build an adjacency list for the ring vertices
        adj_list: dict[int, list[int]] = {}
        for v1, v2 in sorted(edge_to_face_map.keys()):
            adj_list.setdefault(v1, []).append(v2)
            adj_list.setdefault(v2, []).append(v1)

        # traverse the adjacency list to get the ordered ring
        ring: list[int] = []
        if len(adj_list) <= 0:
            return [], []
        start_node = sorted(list(adj_list.keys()))[0]
        current_node = start_node
        prev_node = -1

        for _ in range(len(adj_list)):
            ring.append(current_node)
            neighbors = adj_list[current_node]

            if len(neighbors) != 2:  # non-manifold
                return [], []

            next_node = neighbors[0] if neighbors[0] != prev_node else neighbors[1]

            prev_node = current_node
            current_node = next_node
            if current_node == start_node:
                break

        return ring, list(affected_faces.keys())

    def _triangulate_ring(self, ring: list[int]):
        """Simple fan triangulation of an ordered vertex ring."""
        if len(ring) < 3:
            return []

        v0 = ring[0]
        new_faces: list[list[int]] = []
        for i in range(1, len(ring) - 1):
            new_faces.append([v0, ring[i], ring[i + 1]])
        return new_faces

    def _calculate_removal_error(self, vert_idx: int):
        """
        Calculates the max geometric error of removing a vertex (or infinite for degenerates)
        Tries to remove the vertex and fill the gap by connecting its
        neighboring vertices into a triangle fan. The error is the largest
        distance between the vertex's old position and the new surface that
        would replace it.
        """
        v0_pos: FloatPoint = self.hull_calc_points[vert_idx]
        neighbor_ring: list[int]
        neighbor_ring, _ = self._get_vertex_ring(vert_idx)

        if len(neighbor_ring) < 3:
            return np.inf  # cannot be removed

        new_faces = self._triangulate_ring(neighbor_ring)
        if not new_faces:
            return np.inf

        geometric_error = 0.0
        for face in new_faces:
            p1, p2, p3 = (
                self.hull_calc_points[face[0]],
                self.hull_calc_points[face[1]],
                self.hull_calc_points[face[2]],
            )

            normal: FloatPoint = np.cross(p2 - p1, p3 - p1)  # type: ignore
            norm_len: float = np.linalg.norm(normal)  # type: ignore
            if norm_len < TOLERANCE:
                continue  # degenerate new face
            normal: FloatPoint = normal / norm_len  # type: ignore
            dist: float = np.abs(np.dot(v0_pos - p1, normal))  # type: ignore
            geometric_error = max(geometric_error, dist)

        return geometric_error

    def _get_points_outside(self, test_points: FloatPoints):
        """
        Finds all points outside the current hull and returns them,
        along with the plane normals and distances.
        """

        if test_points.shape[0] == 0 or not self.faces:
            return OutsidePointsInfo(np.array([], dtype=np.float64).reshape(0, 3), np.array([], dtype=np.float64), np.array([], dtype=np.bool_))  # type: ignore

        hull_planes = self._compute_hull_planes()
        valid_normals, valid_ds = hull_planes.valid_normals, hull_planes.valid_ds

        if valid_normals.shape[0] == 0:
            # all points are "outside" if there's no hull
            all_dists = np.full((test_points.shape[0], 1), np.inf)  # type: ignore
            all_mask = np.ones(test_points.shape[0], dtype=np.bool_)  # type: ignore
            return OutsidePointsInfo(test_points, all_dists, all_mask)  # type: ignore

        dists: np.ndarray[np.float64] = np.dot(test_points, valid_normals.T) + valid_ds  # type: ignore
        max_dists: np.ndarray[np.float64] = np.max(dists, axis=1)  # type: ignore
        outside_mask: np.ndarray[np.bool_] = max_dists > TOLERANCE  # type: ignore

        return OutsidePointsInfo(test_points[outside_mask], dists[outside_mask], outside_mask)  # type: ignore

    def _get_removal_triangulation(self, current_vert_idx: int) -> tuple[list[int], list[int], list[list[int]]]:
        """
        Gets the vertex ring, affected faces, and new triangulation for a vertex removal.
        Returns empty lists if removal is not possible.
        """
        neighbor_ring, affected_face_indices = self._get_vertex_ring(current_vert_idx)
        if not neighbor_ring:
            return [], [], []

        new_faces = self._triangulate_ring(neighbor_ring)
        if not new_faces:
            return [], [], []

        current_centroid: FloatPoint = np.mean(self.hull_calc_points, axis=0)  # type: ignore
        self._orient_faces_list_outward(new_faces, self.hull_calc_points, current_centroid)

        return neighbor_ring, affected_face_indices, new_faces

    def _patch_mesh_after_removal(
        self,
        current_vert_idx: int,
        orig_vert_idx: int,
        neighbor_ring: list[int],
        affected_face_indices: list[int],
        new_faces: list[list[int]],
        orig_to_current_idx_map: dict[int, int],
        current_to_orig_idx_map: list[int],
    ):
        """
        Performs the mesh surgery: removes old faces, adds new ones,
        deletes the vertex, and updates all vertex indices.
        Returns the set of *new* indices for the neighbor ring.
        """
        # remove old faces
        affected_face_indices_set = set(affected_face_indices)
        self.faces = [f for i, f in enumerate(self.faces) if i not in affected_face_indices_set]

        # add new faces
        self.faces.extend(new_faces)

        # update vertices and their indices to remove old vertex
        self.hull_points = np.delete(self.hull_points, current_vert_idx, axis=0)
        self.hull_calc_points = cast(FloatPoints, np.delete(self.hull_calc_points, current_vert_idx, axis=0))

        for face in self.faces:
            for i, vertex_idx in enumerate(face):
                if vertex_idx > current_vert_idx:
                    face[i] -= 1

        self.invalidate_hull_cache()

        # update the maps
        del orig_to_current_idx_map[orig_vert_idx]
        del current_to_orig_idx_map[current_vert_idx]
        for i, orig_idx_affected in enumerate(current_to_orig_idx_map):
            orig_to_current_idx_map[orig_idx_affected] = i

        # Find the new indices of the neighbor ring vertices
        neighbor_ring_new_indices: set[int] = set()
        for vertex_idx in neighbor_ring:
            if vertex_idx > current_vert_idx:
                neighbor_ring_new_indices.add(vertex_idx - 1)
            elif vertex_idx < current_vert_idx:
                neighbor_ring_new_indices.add(vertex_idx)
        return neighbor_ring_new_indices

    def _fix_hull_containment(self, original_points_f64: FloatPoints) -> set[int]:
        """
        Checks if any original points are outside the new hull.
        If so, moves faces outward to re-contain them.
        Returns the set of all vertices whose costs must be recalculated.
        """
        outside_info = self._get_points_outside(original_points_f64)
        if outside_info.points.shape[0] == 0:
            return set()

        hull_planes = self._compute_hull_planes()
        hull_normals, valid_plane_mask = hull_planes.normals, hull_planes.valid_plane_mask
        valid_plane_indices = np.where(valid_plane_mask)[0]
        assert valid_plane_indices.shape[0] > 0, "Should have at least one valid plane"

        vertices_to_adjust: set[int] = set()
        max_dists_per_point: np.ndarray[np.float64] = outside_info.dists.max(axis=1)  # type: ignore
        max_plane_idx_per_point: np.ndarray[np.int64] = outside_info.dists.argmax(axis=1)  # type: ignore

        for i in range(outside_info.points.shape[0]):
            dist = max_dists_per_point[i]
            valid_plane_idx = max_plane_idx_per_point[i]
            assert valid_plane_idx < len(
                valid_plane_indices
            ), f"{valid_plane_idx} (valid_plane_idx) >= {len(valid_plane_indices)} (valid_plane_indices.shape[0])"

            face_idx = valid_plane_indices[valid_plane_idx]
            assert face_idx < len(self.faces), f"{face_idx} (face_idx) >= {len(self.faces)} (len(self.faces))"
            assert face_idx < len(hull_normals), f"{face_idx} (face_idx) >= {len(hull_normals)} (len(hull_normals))"

            # move vertices of this face outward
            face = self.faces[face_idx]
            normal = hull_normals[face_idx]
            move_vector = normal * (dist + TOLERANCE)
            for vertex_idx in face:
                if vertex_idx not in vertices_to_adjust:
                    self.hull_calc_points[vertex_idx] += move_vector
                    self.hull_points[vertex_idx] = np.round(self.hull_calc_points[vertex_idx]).astype(np.int64)
                    vertices_to_adjust.add(vertex_idx)

        if vertices_to_adjust:
            self.invalidate_hull_cache()
            # need to recalculate costs for adjusted vertices AND their neighbors
            all_adjusted_neighbors = set()
            for vertex_idx in vertices_to_adjust:
                all_adjusted_neighbors.add(vertex_idx)
                ring, _ = self._get_vertex_ring(vertex_idx)
                all_adjusted_neighbors.update(ring)
            return all_adjusted_neighbors

        return set()

    def _recalculate_costs_and_update_queue(
        self,
        pq: list[tuple[float, int]],
        vertices_to_recalc: set[int],
        current_to_orig_idx_map: list[int],
    ):
        """Recalculates removal costs and pushes updates to the priority queue."""
        for current_idx in sorted(list(vertices_to_recalc)):
            if current_idx >= len(current_to_orig_idx_map):
                continue  # Vertex index is out of bounds (e.g., already removed)

            orig_idx = current_to_orig_idx_map[current_idx]
            new_cost = self._calculate_removal_error(current_idx)
            heapq.heappush(pq, (new_cost, orig_idx))

    def decimate_hull(self, buffer_size: int, max_geometric_error: float) -> IntPoints:
        """
        This decimation strategy prioritizes removing vertices with low
        geometric error. If a removal breaks the containment, it attempts to fix the containment
        by adjusting neighbor vertices outwards.
        """
        max_geometric_error = max(0.0, max_geometric_error)
        if max_geometric_error <= 0.0 or len(self.hull_calc_points) <= 8:
            return self.get_hull_points()

        costs: np.ndarray[np.float64] = np.full(len(self.hull_points), np.inf)  # type: ignore
        self._calculate_all_removal_errors(costs)

        orig_to_current_idx_map: dict[int, int] = {i: i for i in range(len(self.hull_points))}
        current_to_orig_idx_map: list[int] = list(range(len(self.hull_points)))

        pq: list[tuple[float, int]] = [(costs[i], i) for i in range(len(costs))]

        # i've never tried to use heapify. didn't even know it was a thing and I assume others don't either
        # the smallest element is always at the top, so we don´t need to manually sort
        heapq.heapify(pq)

        original_points_f64 = self.original_points.astype(np.float64)

        while pq:
            cost, orig_vert_idx = heapq.heappop(pq)

            if (cost > max_geometric_error or len(self.hull_calc_points) <= 8) and not len(
                self.hull_calc_points
            ) > buffer_size:
                break
            elif orig_vert_idx not in orig_to_current_idx_map:  # vertex was already removed
                continue

            current_vert_idx = orig_to_current_idx_map[orig_vert_idx]

            neighbor_ring, affected_face_indices, new_faces = self._get_removal_triangulation(current_vert_idx)
            if not new_faces:
                continue  # cannot remove this vertex

            neighbor_ring_new_indices = self._patch_mesh_after_removal(
                current_vert_idx,
                orig_vert_idx,
                neighbor_ring,
                affected_face_indices,
                new_faces,
                orig_to_current_idx_map,
                current_to_orig_idx_map,
            )

            adjusted_and_neighbor_vertices = self._fix_hull_containment(original_points_f64)

            # combine vertices from the removed ring and any adjusted vertices
            vertices_to_recalc_set = neighbor_ring_new_indices.union(adjusted_and_neighbor_vertices)
            self._recalculate_costs_and_update_queue(pq, vertices_to_recalc_set, current_to_orig_idx_map)

        return self.get_hull_points()


def create_convex_hull(mesh_points_int: IntPoints, buffer_size: int, max_geometric_error: float) -> IntPoints:
    """
    Creates a (optionally) decimated convex hull
    """

    try:
        hull = ConvexHull3D(mesh_points_int)
        result = hull.compute_hull()
        if result is False:  # if an expected error occurs, fallback on a simple set of points
            return mesh_points_int
        hull.decimate_hull(buffer_size, max_geometric_error)

        final_hull_points = hull.get_hull_points()

    except Exception as e:
        raise PluginError(f"Error during hull computation for {mesh.name}: {e}")

    return final_hull_points
