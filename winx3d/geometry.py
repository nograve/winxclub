"""Procedural mesh construction.

The whole game is modelled from code, so there are no binary art assets to
ship.  Everything funnels through :class:`MeshBuilder`, which accumulates
triangles with per-vertex colours and bakes them into a single ``Geom``.  One
geom per visual object keeps the draw-call count low, which matters a great
deal on the fixed-function hardware this game targets.
"""
from __future__ import annotations

import math

from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexData,
                          GeomVertexFormat, GeomVertexWriter, NodePath, Vec3,
                          Vec4)

TAU = math.pi * 2.0


def _as_vec3(p) -> Vec3:
    return p if isinstance(p, Vec3) else Vec3(p[0], p[1], p[2])


def _as_vec4(c) -> Vec4:
    if isinstance(c, Vec4):
        return c
    if len(c) == 3:
        return Vec4(c[0], c[1], c[2], 1.0)
    return Vec4(c[0], c[1], c[2], c[3])


def shade(color, factor: float, alpha: float | None = None) -> Vec4:
    """Multiply a colour's RGB by ``factor``, clamped, keeping or overriding alpha."""
    c = _as_vec4(color)
    a = c[3] if alpha is None else alpha
    return Vec4(min(1.0, c[0] * factor), min(1.0, c[1] * factor),
                min(1.0, c[2] * factor), a)


def mix(a, b, t: float) -> Vec4:
    ca, cb = _as_vec4(a), _as_vec4(b)
    return Vec4(*(ca[i] + (cb[i] - ca[i]) * t for i in range(4)))


class MeshBuilder:
    """Accumulates triangles, then bakes them into a single Geom."""

    def __init__(self) -> None:
        self._verts: list[tuple[Vec3, Vec3, Vec4]] = []
        self._tris: list[tuple[int, int, int]] = []

    # -- low level ----------------------------------------------------------
    def add_vertex(self, pos, normal, color) -> int:
        self._verts.append((_as_vec3(pos), _as_vec3(normal), _as_vec4(color)))
        return len(self._verts) - 1

    def add_tri(self, p0, p1, p2, color, normal=None) -> None:
        p0, p1, p2 = _as_vec3(p0), _as_vec3(p1), _as_vec3(p2)
        if normal is None:
            n = (p1 - p0).cross(p2 - p0)
            if n.lengthSquared() < 1e-12:
                return
            n.normalize()
        else:
            n = _as_vec3(normal)
        i = self.add_vertex(p0, n, color)
        j = self.add_vertex(p1, n, color)
        k = self.add_vertex(p2, n, color)
        self._tris.append((i, j, k))

    def add_quad(self, p0, p1, p2, p3, color, normal=None) -> None:
        self.add_tri(p0, p1, p2, color, normal)
        self.add_tri(p0, p2, p3, color, normal)

    # -- primitives ---------------------------------------------------------
    def box(self, center, size, color, top_color=None) -> None:
        """Axis-aligned box; ``size`` is the full extent on each axis."""
        c = _as_vec3(center)
        hx, hy, hz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5
        x0, x1 = c.x - hx, c.x + hx
        y0, y1 = c.y - hy, c.y + hy
        z0, z1 = c.z - hz, c.z + hz
        side = _as_vec4(color)
        top = side if top_color is None else _as_vec4(top_color)
        # top / bottom
        self.add_quad((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), top)
        self.add_quad((x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0),
                      shade(side, 0.55))
        # sides, subtly shaded so edges read without a texture
        self.add_quad((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1),
                      shade(side, 0.92))
        self.add_quad((x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1),
                      shade(side, 0.78))
        self.add_quad((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1),
                      shade(side, 0.86))
        self.add_quad((x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1),
                      shade(side, 0.70))

    def cylinder(self, base, radius_bottom, radius_top, height, color,
                 segments=12, cap_top=True, cap_bottom=True,
                 top_color=None) -> None:
        """Cylinder/cone/frustum standing on +Z from ``base``."""
        b = _as_vec3(base)
        top_c = _as_vec4(color if top_color is None else top_color)
        ring_b, ring_t = [], []
        for i in range(segments):
            a = TAU * i / segments
            ca, sa = math.cos(a), math.sin(a)
            ring_b.append(Vec3(b.x + ca * radius_bottom, b.y + sa * radius_bottom, b.z))
            ring_t.append(Vec3(b.x + ca * radius_top, b.y + sa * radius_top, b.z + height))
        for i in range(segments):
            j = (i + 1) % segments
            a = TAU * (i + 0.5) / segments
            # cheap side shading: faces pointing away from the key light darken
            lit = 0.72 + 0.28 * max(0.0, math.cos(a - 0.9))
            col = shade(mix(color, top_c, 0.5), lit)
            if radius_bottom <= 1e-6:
                self.add_tri(b, ring_t[i], ring_t[j], col)
            elif radius_top <= 1e-6:
                apex = Vec3(b.x, b.y, b.z + height)
                self.add_tri(ring_b[i], ring_b[j], apex, col)
            else:
                self.add_quad(ring_b[i], ring_b[j], ring_t[j], ring_t[i], col)
        if cap_top and radius_top > 1e-6:
            centre = Vec3(b.x, b.y, b.z + height)
            for i in range(segments):
                j = (i + 1) % segments
                self.add_tri(centre, ring_t[i], ring_t[j], top_c, Vec3(0, 0, 1))
        if cap_bottom and radius_bottom > 1e-6:
            dark = shade(color, 0.5)
            for i in range(segments):
                j = (i + 1) % segments
                self.add_tri(b, ring_b[j], ring_b[i], dark, Vec3(0, 0, -1))

    def sphere(self, center, radius, color, segments=12, rings=8,
               squash=1.0) -> None:
        """UV sphere; ``squash`` scales Z (1.0 = round, <1 = flattened)."""
        c = _as_vec3(center)

        def point(ri, si):
            phi = math.pi * ri / rings
            theta = TAU * si / segments
            return Vec3(c.x + radius * math.sin(phi) * math.cos(theta),
                        c.y + radius * math.sin(phi) * math.sin(theta),
                        c.z + radius * math.cos(phi) * squash)

        for ri in range(rings):
            # vertical gradient gives the sphere form without any lighting
            t0 = 1.05 - 0.35 * (ri / max(1, rings - 1))
            col = shade(color, t0)
            for si in range(segments):
                sj = (si + 1) % segments
                p00, p01 = point(ri, si), point(ri, sj)
                p10, p11 = point(ri + 1, si), point(ri + 1, sj)
                if ri == 0:
                    self.add_tri(p00, p11, p10, col)
                elif ri == rings - 1:
                    self.add_tri(p00, p01, p10, col)
                else:
                    self.add_quad(p00, p01, p11, p10, col)

    def prism(self, center, size, color) -> None:
        """Triangular prism (a roof) with its ridge along the Y axis."""
        c = _as_vec3(center)
        hx, hy, hz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5
        a0 = Vec3(c.x - hx, c.y - hy, c.z - hz)
        a1 = Vec3(c.x + hx, c.y - hy, c.z - hz)
        b0 = Vec3(c.x - hx, c.y + hy, c.z - hz)
        b1 = Vec3(c.x + hx, c.y + hy, c.z - hz)
        r0 = Vec3(c.x, c.y - hy, c.z + hz)
        r1 = Vec3(c.x, c.y + hy, c.z + hz)
        self.add_quad(a0, b0, r1, r0, shade(color, 1.0))
        self.add_quad(b1, a1, r0, r1, shade(color, 0.82))
        self.add_tri(a0, r0, a1, shade(color, 0.9))
        self.add_tri(b1, r1, b0, shade(color, 0.9))
        self.add_quad(a0, a1, b1, b0, shade(color, 0.5))

    def grid_ground(self, width, depth, color_a, color_b, step=8.0,
                    center=(0, 0, 0)) -> None:
        """Checkerboard ground plane — reads as terrain with zero textures."""
        c = _as_vec3(center)
        nx = max(1, int(width / step))
        ny = max(1, int(depth / step))
        x0, y0 = c.x - width * 0.5, c.y - depth * 0.5
        for ix in range(nx):
            for iy in range(ny):
                col = color_a if (ix + iy) % 2 == 0 else color_b
                ax, ay = x0 + ix * step, y0 + iy * step
                bx, by = ax + step, ay + step
                self.add_quad((ax, ay, c.z), (bx, ay, c.z), (bx, by, c.z),
                              (ax, by, c.z), col, Vec3(0, 0, 1))

    def transform(self, mat) -> None:
        """Apply a matrix to everything accumulated so far."""
        out = []
        for pos, nrm, col in self._verts:
            p = mat.xformPoint(pos)
            n = mat.xformVec(nrm)
            if n.lengthSquared() > 1e-12:
                n.normalize()
            out.append((p, n, col))
        self._verts = out

    # -- baking -------------------------------------------------------------
    def is_empty(self) -> bool:
        return not self._tris

    def build_node(self, name: str = "mesh") -> GeomNode:
        vdata = GeomVertexData(name, GeomVertexFormat.getV3n3c4(),
                               Geom.UHStatic)
        vdata.setNumRows(max(1, len(self._verts)))
        vw = GeomVertexWriter(vdata, "vertex")
        nw = GeomVertexWriter(vdata, "normal")
        cw = GeomVertexWriter(vdata, "color")
        for pos, nrm, col in self._verts:
            vw.addData3(pos)
            nw.addData3(nrm)
            cw.addData4(col)
        prim = GeomTriangles(Geom.UHStatic)
        for i, j, k in self._tris:
            prim.addVertices(i, j, k)
        prim.closePrimitive()
        geom = Geom(vdata)
        geom.addPrimitive(prim)
        node = GeomNode(name)
        node.addGeom(geom)
        return node

    def build(self, name: str = "mesh") -> NodePath:
        return NodePath(self.build_node(name))


def single(name: str, fn, *args, **kwargs) -> NodePath:
    """Convenience: build a one-primitive NodePath, e.g. ``single('a','sphere',…)``."""
    mb = MeshBuilder()
    getattr(mb, fn)(*args, **kwargs)
    return mb.build(name)
