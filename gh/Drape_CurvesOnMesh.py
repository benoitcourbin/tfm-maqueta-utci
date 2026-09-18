# -*- coding: utf-8 -*-
# Drape_CurvesOnMesh.py — GHPython (Rhino 8 ScriptEditor / Python 3)
# TFM UTCI Lavapies
#
# Recupere depuis Lavapies__07_09_v11_urba+ml.ghx le 10/09/2026, sans
# modification. Sauvegarde ici pour que le composant survive au fichier .gh.
#
# ENTREES  : curves (List access, Curve)  ·  mesh (Item access, Mesh — le terrain)
# SORTIES  : a (List, Curve)  ·  n_extrap (int)  ·  rapport (str)
#
# Se branche entre Import Vector (Heron) et gh_puntos_utci.py.
#
# Drape_CurvesOnMesh  —  Rhino 8 ScriptEditor / GHPython 3
# Remplace Project_CurvesToMesh. Garantit 1 courbe en sortie par courbe en entree.
#
# Inputs  : curves (list access), mesh (item access, le terrain)
# Outputs : a (courbes drapees), n_extrap (int), rapport (str)
#
# Methode : echantillonnage altimetrique sommet par sommet (ray-cast vertical).
#           Sommet hors emprise raster -> altitude du point de mesh le plus proche.
#           Aucune decoupe, aucune entite perdue.

import Rhino.Geometry as rg
from Rhino.Geometry.Intersect import Intersection

tol = ghdoc.ModelAbsoluteTolerance
bb = mesh.GetBoundingBox(True)
z_start = bb.Max.Z + 1000.0
down = rg.Vector3d(0, 0, -1)

def sommets(crv):
    """Sommets de la courbe. Polyligne -> exacts ; sinon -> echantillonnage."""
    ok, pl = crv.TryGetPolyline()
    if ok:
        return list(pl)
    n = max(2, int(crv.GetLength() / 1.0))          # 1 pt/m pour les arcs
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
    "DRAPAGE\n"
    "entree  {} courbes\n"
    "sortie  {} courbes\n"
    "sommets extrapoles  {}\n"
    "courbes concernees  {}\n{}"
).format(len(curves), len(a), n_extrap, len(courbes_touchees),
         courbes_touchees[:20])
