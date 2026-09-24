# -*- coding: utf-8 -*-
# Drape_CurvesOnMesh.py — GHPython (Rhino 8 ScriptEditor / Python 3)
# TFM UTCI Lavapies
#
# Recuperado de Lavapies__07_09_v11_urba+ml.ghx el 10/09/2026, sin
# modificacion. Guardado aqui para que el componente sobreviva al fichero .gh.
#
# ENTRADAS : curves (List access, Curve)  ·  mesh (Item access, Mesh — el terreno)
# SALIDAS  : a (List, Curve)  ·  n_extrap (int)  ·  rapport (str)
#
# Se conecta entre Import Vector (Heron) y gh_puntos_utci.py.
#
# Drape_CurvesOnMesh  —  Rhino 8 ScriptEditor / GHPython 3
# Sustituye a Project_CurvesToMesh. Garantiza 1 curva de salida por curva de entrada.
#
# Inputs  : curves (list access), mesh (item access, el terreno)
# Outputs : a (curvas drapeadas), n_extrap (int), rapport (str)
#
# Metodo : muestreo altimetrico vertice a vertice (ray-cast vertical).
#          Vertice fuera de la huella raster -> altura del punto de malla mas cercano.
#          Ningun recorte, ninguna entidad perdida.

import Rhino.Geometry as rg
from Rhino.Geometry.Intersect import Intersection

tol = ghdoc.ModelAbsoluteTolerance
bb = mesh.GetBoundingBox(True)
z_start = bb.Max.Z + 1000.0
down = rg.Vector3d(0, 0, -1)

def sommets(crv):
    """Vertices de la curva. Polilinea -> exactos ; si no -> muestreo."""
    ok, pl = crv.TryGetPolyline()
    if ok:
        return list(pl)
    n = max(2, int(crv.GetLength() / 1.0))          # 1 pt/m para los arcos
    return [crv.PointAt(t) for t in crv.DivideByCount(n, True)]

a = []
n_extrap = 0
courbes_touchees = []

for i, crv in enumerate(curves):
    pts_out = []
    extrap_ici = 0
    for p in sommets(crv):
        ray = rg.Ray3d(rg.Point3d(p.X, p.Y, z_start), down)
        t = Intersection.MeshRay(mesh, ray)
        if t >= 0.0:
            pts_out.append(ray.PointAt(t))
        else:
            mp = mesh.ClosestMeshPoint(rg.Point3d(p.X, p.Y, bb.Center.Z), 0.0)
            z = mesh.PointAt(mp).Z if mp else bb.Center.Z
            pts_out.append(rg.Point3d(p.X, p.Y, z))
            extrap_ici += 1
    if extrap_ici:
        n_extrap += extrap_ici
        courbes_touchees.append(i)
    a.append(rg.PolylineCurve(rg.Polyline(pts_out)))

rapport = (
    "DRAPEADO\n"
    "entrada  {} curvas\n"
    "salida   {} curvas\n"
    "vertices extrapolados  {}\n"
    "curvas afectadas  {}\n{}"
).format(len(curves), len(a), n_extrap, len(courbes_touchees),
         courbes_touchees[:20])
