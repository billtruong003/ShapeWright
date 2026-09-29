"""Indexed triangle mesh: the kernel's only geometry type.

Every shape, operation and part produces a :class:`Mesh`. Vertices are shared
between faces (indexed) so topology checks are meaningful; per-corner data
(normals, UVs) is derived later in the surface stage and never stored here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Mesh:
    V: np.ndarray  # (n, 3) float64
    F: np.ndarray  # (m, 3) int64

    def __post_init__(self):
        self.V = np.asarray(self.V, dtype=np.float64).reshape(-1, 3)
        self.F = np.asarray(self.F, dtype=np.int64).reshape(-1, 3)

    def copy(self) -> "Mesh":
        return Mesh(self.V.copy(), self.F.copy())

    @property
    def n_tris(self) -> int:
        return len(self.F)

    def bounds(self) -> np.ndarray:
        if len(self.V) == 0:
            return np.zeros((2, 3))
        return np.stack([self.V.min(0), self.V.max(0)])

    def center(self) -> np.ndarray:
        b = self.bounds()
        return (b[0] + b[1]) / 2

    def size(self) -> np.ndarray:
        b = self.bounds()
        return b[1] - b[0]

    def triangles(self) -> np.ndarray:
        return self.V[self.F]

    def face_normals(self) -> tuple[np.ndarray, np.ndarray]:
        """Unit normals and areas per face (degenerate faces get a zero normal)."""
        t = self.triangles()
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        length = np.linalg.norm(n, axis=1)
        safe = np.where(length > 0, length, 1.0)
        return n / safe[:, None], length / 2

    def volume(self) -> float:
        t = self.triangles()
        return float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0)

    def area(self) -> float:
        return float(self.face_normals()[1].sum())

    def translated(self, d) -> "Mesh":
        return Mesh(self.V + np.asarray(d, dtype=np.float64), self.F.copy())

    def transformed(self, M: np.ndarray) -> "Mesh":
        V = self.V @ M[:3, :3].T + M[:3, 3]
        F = self.F.copy()
        if np.linalg.det(M[:3, :3]) < 0:
            F = F[:, ::-1].copy()
        return Mesh(V, F)

    def recentered(self) -> "Mesh":
        return self.translated(-self.center())

    def merged(self, decimals: int = 7) -> "Mesh":
        """Weld coincident vertices and drop faces that collapse."""
        if len(self.V) == 0:
            return self.copy()
        key = np.round(self.V, decimals)
        uniq, inverse = np.unique(key, axis=0, return_inverse=True)
        inverse = inverse.reshape(-1)
        # keep the first original position of each welded group (exact values)
        first = np.full(len(uniq), -1, dtype=np.int64)
        order = np.arange(len(self.V))[::-1]
        first[inverse[order]] = order
        V = self.V[first]
        F = inverse[self.F]
        keep = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
        return Mesh(V, F[keep]).compacted()

    def compacted(self) -> "Mesh":
        used = np.unique(self.F.reshape(-1))
        remap = np.full(len(self.V), -1, dtype=np.int64)
        remap[used] = np.arange(len(used))
        return Mesh(self.V[used], remap[self.F])

    def oriented_outward(self) -> "Mesh":
        """Flip all faces if the closed surface encloses negative volume."""
        if self.volume() < 0:
            return Mesh(self.V.copy(), self.F[:, ::-1].copy())
        return self.copy()

    def to_trimesh(self):
        import trimesh

        return trimesh.Trimesh(self.V, self.F, process=False)


def concat(meshes: list[Mesh]) -> Mesh:
    if not meshes:
        return Mesh(np.zeros((0, 3)), np.zeros((0, 3)))
    Vs, Fs, offset = [], [], 0
    for m in meshes:
        Vs.append(m.V)
        Fs.append(m.F + offset)
        offset += len(m.V)
    return Mesh(np.concatenate(Vs), np.concatenate(Fs))


def rotation_matrix(deg_xyz) -> np.ndarray:
    """4x4 rotation from XYZ Euler angles in degrees, applied X then Y then Z."""
    rx, ry, rz = np.radians(np.asarray(deg_xyz, dtype=np.float64))
    cx, sx, cy, sy, cz, sz = np.cos(rx), np.sin(rx), np.cos(ry), np.sin(ry), np.cos(rz), np.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    M = np.eye(4)
    M[:3, :3] = Rz @ Ry @ Rx
    return M


def translation_matrix(d) -> np.ndarray:
    M = np.eye(4)
    M[:3, 3] = d
    return M


def scale_matrix(s) -> np.ndarray:
    M = np.eye(4)
    M[:3, :3] = np.diag(np.broadcast_to(np.asarray(s, dtype=np.float64), (3,)))
    return M


def to_manifold(mesh: Mesh):
    import manifold3d as mf

    m = mf.Manifold(mf.Mesh(vert_properties=mesh.V.astype(np.float32), tri_verts=mesh.F.astype(np.uint32)))
    if m.status() != mf.Error.NoError:
        raise ValueError(f"mesh is not a closed manifold ({m.status().name}); booleans need closed shapes")
    return m


def from_manifold(m) -> Mesh:
    out = m.to_mesh()
    return Mesh(np.asarray(out.vert_properties[:, :3], dtype=np.float64), np.asarray(out.tri_verts, dtype=np.int64))


def geometry_hash(mesh: Mesh, decimals: int = 5) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update(np.round(mesh.V, decimals).astype(np.float64).tobytes())
    h.update(mesh.F.astype(np.int64).tobytes())
    return h.hexdigest()[:16]
