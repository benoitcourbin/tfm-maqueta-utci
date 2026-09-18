# -*- coding: utf-8 -*-
"""
gh_load_edificios.py — GHPython (Rhino 8 / Python 3, ScriptEditor)
TFM UTCI Lavapies — chargement de edificios_lavapies_lod1_mesh.json
                    et de edificios_lavapies_superstruct_mesh.json

UN SEUL COMPOSANT POUR LES DEUX FICHIERS (fusion du 18/09)
    Avant, deux composants : Edificios_py (LOD1) et Superest_py (superstructures).
    Le script accepte deja une liste de chemins : on branche les deux sur la meme
    entree `path` et tout sort dans un seul jeu mesh / keys / values.
    4 660 + 4 636 objets, 266 536 faces, toutes triangulaires.
    La sortie `edificios` de gh_cache.py donne ces deux chemins dans le bon ordre.

ENTREES DU COMPOSANT : 2 seulement
    path  (List, str)  chemin(s) vers le(s) *_mesh.json
    eap   (Item)       Earth Anchor Point : texte Heron, point lon/lat ou point UTM

SORTIES : mesh (List) · keys (Tree) · values (Tree) · info (str)

Tout le reste se regle sur les 3 constantes ci-dessous, dans le code.

Les solides sont deja fermes et 2-manifold a la generation (build_lod1.py) :
pas de Weld angulaire, pas de FillHoles. Normales de FACE, jamais de sommet —
c'est le lissage des normales de sommet qui donnait l'aspect "organique".

API Rhino : Mesh.Vertices.Add / Faces.AddFace / Normals.Clear /
FaceNormals.ComputeFaceNormals / Compact [SOURCE: GH-01]
Geometrie : [SOURCE: MAD-01] · attributs : [SOURCE: CAT-01] [SOURCE: CAT-03]
"""

# ============================ REGLAGES ======================================
ACTIVO    = True    # False : ne charge rien, la geometrie bakee dans les
                    # calques Rhino reste en place. A passer a False apres le
                    # bake pour que le .gh s'ouvre vite.
RADIO_MAX = 1200.0  # m autour de l'EAP. Ecarte les 10 objets 01_MARQUESINA_P
                    # situes a 8,5-11,9 km qui etendaient la bbox a 12,8 km.
                    # 0 = pas de filtre.
Z_REF     = 0.0     # cote a retrancher a Z. 0 = altitude absolue conservee.
# ============================================================================

import json, os, re, math
import Rhino.Geometry as rg
import Grasshopper
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

G = globals()
_paths = G.get('path')
_paths = _paths if isinstance(_paths, list) else ([_paths] if _paths else [])
_eap = G.get('eap')

_lineas, _avisos = [], []
def linea(t): _lineas.append(str(t))
def aviso(t):
    _avisos.append(str(t)); _lineas.append('AVISO: ' + str(t))


def latlon_a_utm30(lat, lon):
    """Transverse Mercator zone 30N, GRS80 (EPSG:25830)."""
    a, f = 6378137.0, 1.0 / 298.257222101
    e2 = f * (2 - f); ep2 = e2 / (1 - e2)
    k0, lon0, FE = 0.9996, math.radians(-3.0), 500000.0
    p, l = math.radians(lat), math.radians(lon)
    sp, cp, tp = math.sin(p), math.cos(p), math.tan(p)
    N = a / math.sqrt(1 - e2 * sp * sp); T = tp * tp
    C = ep2 * cp * cp; A = (l - lon0) * cp
    M = a * ((1 - e2/4 - 3*e2**2/64 - 5*e2**3/256) * p
             - (3*e2/8 + 3*e2**2/32 + 45*e2**3/1024) * math.sin(2*p)
             + (15*e2**2/256 + 45*e2**3/1024) * math.sin(4*p)
             - (35*e2**3/3072) * math.sin(6*p))
    x = FE + k0 * N * (A + (1-T+C)*A**3/6 + (5-18*T+T*T+72*C-58*ep2)*A**5/120)
    y = k0 * (M + N*tp*(A*A/2 + (5-T+9*C+4*C*C)*A**4/24
                        + (61-58*T+T*T+600*C-330*ep2)*A**6/720))
    return x, y


def resolver_eap(obj):
    """Texte Heron, Point3d lon/lat ou Point3d UTM -> (E, N) en EPSG:25830."""
    if obj is None:
        return None
    if isinstance(obj, str):
        lon = re.search(r'Long\w*\s*[:=]\s*(-?\d+\.?\d*)', obj, re.I)
        lat = re.search(r'Lat\w*\s*[:=]\s*(-?\d+\.?\d*)', obj, re.I)
        if lon and lat:
            e, n = latlon_a_utm30(float(lat.group(1)), float(lon.group(1)))
            linea('EAP (texte Heron) -> UTM %.2f %.2f' % (e, n)); return e, n
        aviso('EAP texte non interpretable : %s' % obj); return None
    try:
        x, y = float(obj.X), float(obj.Y)
    except Exception:
        aviso('type EAP non supporte : %s' % type(obj)); return None
    if abs(x) <= 180.0 and abs(y) <= 90.0:
        e, n = latlon_a_utm30(y, x)
        linea('EAP (point lon/lat) -> UTM %.2f %.2f' % (e, n)); return e, n
    linea('EAP (point UTM) %.2f %.2f' % (x, y)); return x, y


def construir_malla(obj, ox, oy, oz):
    """Malla depuis {'v':[[x,y,z]...],'f':[[i,j,k]...]}. Indices deja partages :
    la topologie est correcte a la source, aucune soudure necessaire."""
    m = rg.Mesh(); va = m.Vertices
    for v in obj['v']:
        va.Add(float(v[0]) - ox, float(v[1]) - oy, float(v[2]) - oz)
    fa = m.Faces
    for f in obj['f']:
        if len(f) == 3:   fa.AddFace(f[0], f[1], f[2])
        elif len(f) == 4: fa.AddFace(f[0], f[1], f[2], f[3])
    # Normales de FACE. Un sommet d'arete appartient a trois faces
    # perpendiculaires : des normales de sommet en feraient la moyenne et
    # Rhino interpolerait -> degrade continu sur les aretes, aspect organique.
    m.Normals.Clear()
    m.FaceNormals.ComputeFaceNormals()
    m.Compact()
    return m


mesh = []
keys = DataTree[object]()
values = DataTree[object]()
n_obj = n_desc = n_lejos = 0

if not ACTIVO:
    linea('ACTIVO = False : nada cargado. La geometria bakeada sigue en las capas.')
    _paths = []

_eap_utm = resolver_eap(_eap) if ACTIVO else None

for ruta in _paths:
    if not ruta or not os.path.exists(str(ruta)):
        aviso('chemin inexistant : %s' % ruta); continue
    with open(str(ruta), 'r', encoding='utf-8') as fh:
        datos = json.load(fh)
    if 'objetos' not in datos:
        aviso('%s : cle "objetos" absente' % os.path.basename(str(ruta))); continue

    meta = datos.get('meta', {})
    dx = float(meta.get('dx', 0.0) or 0.0)
    dy = float(meta.get('dy', 0.0) or 0.0)
    dz = float(meta.get('dz', 0.0) or 0.0)
    if _eap_utm is not None:
        ox, oy, oz = _eap_utm[0] - dx, _eap_utm[1] - dy, Z_REF - dz
    else:
        ox = oy = oz = 0.0
        if ACTIVO:
            aviso('sans EAP : geometrie laissee en UTM absolu (~440 000 / 4 473 000).')

    objetos = datos.get('objetos', [])
    linea('%s : %d objets | tipo=%s' % (os.path.basename(str(ruta)),
                                        len(objetos), meta.get('tipo')))

    for o in objetos:
        if RADIO_MAX > 0.0:
            vs = o['v']
            cx = sum(p[0] for p in vs) / len(vs) - ox
            cy = sum(p[1] for p in vs) / len(vs) - oy
            if (cx*cx + cy*cy) ** 0.5 > RADIO_MAX:
                n_lejos += 1; continue

        m = construir_malla(o, ox, oy, oz)
        if not m.IsValid or m.Faces.Count == 0:
            n_desc += 1; continue

        rama = GH_Path(n_obj)
        attr = dict(o.get('attr') or {})
        attr.setdefault('id', o.get('id'))
        attr.setdefault('clase', o.get('clase'))
        attr.setdefault('capa', o.get('capa'))
        for k in sorted(attr.keys()):
            keys.Add(str(k), rama)
            values.Add('' if attr[k] is None else str(attr[k]), rama)
        mesh.append(m); n_obj += 1

linea('')
linea('Solidos : %d   (invalidos: %d | fuera de radio %.0f m: %d)'
      % (len(mesh), n_desc, RADIO_MAX, n_lejos))
if mesh:
    cerradas = sum(1 for m in mesh if m.IsClosed)
    linea('Cerrados : %d / %d  (%.1f %%)'
          % (cerradas, len(mesh), 100.0*cerradas/len(mesh)))
    linea('Caras : %d' % sum(m.Faces.Count for m in mesh))
    if cerradas < len(mesh):
        aviso('%d solidos abiertos : revisar build_lod1.py' % (len(mesh)-cerradas))
    bb = rg.BoundingBox.Empty
    for m in mesh:
        bb.Union(m.GetBoundingBox(True))
    linea('BBox : X %.1f-%.1f | Y %.1f-%.1f | Z %.1f-%.1f'
          % (bb.Min.X, bb.Max.X, bb.Min.Y, bb.Max.Y, bb.Min.Z, bb.Max.Z))

info = '\n'.join(_lineas)
try:
    for a in _avisos:
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, a)
except Exception:
    pass
