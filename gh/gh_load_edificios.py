# -*- coding: utf-8 -*-
"""
gh_load_edificios.py — GHPython (Rhino 8 / Python 3, ScriptEditor)
TFM UTCI Lavapies — carga de edificios_lavapies_lod1_mesh.json
                    y de edificios_lavapies_superstruct_mesh.json

UN SOLO COMPONENTE PARA LOS DOS FICHEROS (fusion del 18/09)
    Antes, dos componentes : Edificios_py (LOD1) y Superest_py (superestructuras).
    El script ya acepta una lista de rutas : se conectan las dos a la misma
    entrada `path` y todo sale en un unico juego mesh / keys / values.
    4 660 + 4 636 objetos, 266 536 caras, todas triangulares.
    La salida `edificios` de gh_cache.py da estas dos rutas en el orden correcto.

ENTRADAS DEL COMPONENTE : 2 solamente
    path  (List, str)  ruta(s) hacia el/los *_mesh.json
    eap   (Item)       Earth Anchor Point : texto Heron, punto lon/lat o punto UTM

SALIDAS : mesh (List) · keys (Tree) · values (Tree) · info (str)

Todo lo demas se ajusta con las 3 constantes de abajo, en el codigo.

Los solidos ya estan cerrados y son 2-manifold en la generacion (build_lod1.py) :
sin Weld angular, sin FillHoles. Normales de CARA, nunca de vertice —
es el suavizado de las normales de vertice lo que daba el aspecto "organico".

API Rhino : Mesh.Vertices.Add / Faces.AddFace / Normals.Clear /
FaceNormals.ComputeFaceNormals / Compact [SOURCE: GH-01]
Geometria : [SOURCE: MAD-01] · atributos : [SOURCE: CAT-01] [SOURCE: CAT-03]
"""

# ============================ AJUSTES =======================================
ACTIVO    = True    # False : no carga nada, la geometria bakeada en las
                    # capas Rhino sigue en su sitio. Poner a False tras el
                    # bake para que el .gh se abra rapido.
RADIO_MAX = 1200.0  # m alrededor del EAP. Descarta los 10 objetos 01_MARQUESINA_P
                    # situados a 8,5-11,9 km que extendian la bbox a 12,8 km.
                    # 0 = sin filtro.
Z_REF     = 0.0     # cota a restar de Z. 0 = altitud absoluta conservada.
ALT_MAX_MARQUESINA = 20.0   # m. Una marquesina mas alta es un artefacto de extrusion
                            # del SHP, no una construccion : 4 casos en Lavapies, de 64
                            # a 88 m (ids 150180-150183), para 15 a 130 m2 de huella
                            # y 16 caras. Proyectan sombras inexistentes.
                            # 0 = sin filtro. Verificado con la mediana del barrio :
                            # 27,1 m, y ningun EDIFICIO_P resulta afectado.
# ============================================================================

# --------------------------- CLAVES RETENIDAS -------------------------------
# Lista blanca de atributos escritos en el .3dm. [] = todas.
# Lo que no esta aqui sigue en el CSV de la capa, unible por el id.
# Se conservan las claves que PILOTAN algo en Grasshopper: v5 lee las capas
# con Reference by Layer, que devuelve geometria Y atributos. Sin ellas no
# se puede agrupar por epoca (albedo de fachada) ni por pavimento.
# Motivo: cada clave x objeto es una escritura de user text; 9 296 objetos x
# 23 claves tumbaban Rhino (trampa §7.10).
CLAVES = [
    'id_3d',
    'anio_construccion',
]
# ----------------------------------------------------------------------------


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
    """Transverse Mercator zona 30N, GRS80 (EPSG:25830)."""
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
    """Texto Heron, Point3d lon/lat o Point3d UTM -> (E, N) en EPSG:25830."""
    if obj is None:
        return None
    if isinstance(obj, str):
        lon = re.search(r'Long\w*\s*[:=]\s*(-?\d+\.?\d*)', obj, re.I)
        lat = re.search(r'Lat\w*\s*[:=]\s*(-?\d+\.?\d*)', obj, re.I)
        if lon and lat:
            e, n = latlon_a_utm30(float(lat.group(1)), float(lon.group(1)))
            linea('EAP (texto Heron) -> UTM %.2f %.2f' % (e, n)); return e, n
        aviso('EAP en texto no interpretable : %s' % obj); return None
    try:
        x, y = float(obj.X), float(obj.Y)
    except Exception:
        aviso('tipo de EAP no admitido : %s' % type(obj)); return None
    if abs(x) <= 180.0 and abs(y) <= 90.0:
        e, n = latlon_a_utm30(y, x)
        linea('EAP (punto lon/lat) -> UTM %.2f %.2f' % (e, n)); return e, n
    linea('EAP (punto UTM) %.2f %.2f' % (x, y)); return x, y


def construir_malla(obj, ox, oy, oz):
    """Malla desde {'v':[[x,y,z]...],'f':[[i,j,k]...]}. Indices ya compartidos :
    la topologia es correcta en el origen, no hace falta ninguna soldadura."""
    m = rg.Mesh(); va = m.Vertices
    for v in obj['v']:
        va.Add(float(v[0]) - ox, float(v[1]) - oy, float(v[2]) - oz)
    fa = m.Faces
    for f in obj['f']:
        if len(f) == 3:   fa.AddFace(f[0], f[1], f[2])
        elif len(f) == 4: fa.AddFace(f[0], f[1], f[2], f[3])
    # Normales de CARA. Un vertice de arista pertenece a tres caras
    # perpendiculares : unas normales de vertice harian su media y
    # Rhino interpolaria -> degradado continuo en las aristas, aspecto organico.
    m.Normals.Clear()
    m.FaceNormals.ComputeFaceNormals()
    m.Compact()
    return m


mesh = []
keys = DataTree[object]()
values = DataTree[object]()
n_obj = n_desc = n_lejos = n_marq = 0

if not ACTIVO:
    linea('ACTIVO = False : nada cargado. La geometria bakeada sigue en las capas.')
    _paths = []
elif not _paths:
    aviso('el puerto path esta vacio : nada que cargar. '
          'Conectar la salida correspondiente de gh_cache.py '
          '(y comprobar su salida info).')


_eap_utm = resolver_eap(_eap) if ACTIVO else None

for ruta in _paths:
    if not ruta or not os.path.exists(str(ruta)):
        aviso('ruta inexistente : %s' % ruta); continue
    with open(str(ruta), 'r', encoding='utf-8') as fh:
        datos = json.load(fh)
    if 'objetos' not in datos:
        aviso('%s : falta la clave "objetos"' % os.path.basename(str(ruta))); continue

    meta = datos.get('meta', {})
    dx = float(meta.get('dx', 0.0) or 0.0)
    dy = float(meta.get('dy', 0.0) or 0.0)
    dz = float(meta.get('dz', 0.0) or 0.0)
    if _eap_utm is not None:
        ox, oy, oz = _eap_utm[0] - dx, _eap_utm[1] - dy, Z_REF - dz
    else:
        ox = oy = oz = 0.0
        if ACTIVO:
            aviso('sin EAP : geometria dejada en UTM absoluto (~440 000 / 4 473 000).')

    objetos = datos.get('objetos', [])
    linea('%s : %d objetos | tipo=%s' % (os.path.basename(str(ruta)),
                                        len(objetos), meta.get('tipo')))

    for o in objetos:
        if RADIO_MAX > 0.0:
            vs = o['v']
            cx = sum(p[0] for p in vs) / len(vs) - ox
            cy = sum(p[1] for p in vs) / len(vs) - oy
            if (cx*cx + cy*cy) ** 0.5 > RADIO_MAX:
                n_lejos += 1; continue

        # Artefactos de extrusion : marquesinas inverosimilmente altas.
        if ALT_MAX_MARQUESINA > 0.0:
            _capa = str((o.get('attr') or {}).get('nombre_capa') or '')
            if 'MARQUESINA' in _capa.upper():
                try:
                    _h = float((o.get('attr') or {}).get('altura_m') or 0.0)
                except Exception:
                    _h = 0.0
                if _h > ALT_MAX_MARQUESINA:
                    n_marq += 1
                    continue

        m = construir_malla(o, ox, oy, oz)
        if not m.IsValid or m.Faces.Count == 0:
            n_desc += 1; continue

        rama = GH_Path(n_obj)
        attr = dict(o.get('attr') or {})
        attr.setdefault('id', o.get('id'))
        attr.setdefault('clase', o.get('clase'))
        attr.setdefault('capa', o.get('capa'))
        for k in sorted(attr.keys()):
            if CLAVES and k not in CLAVES:
                continue
            keys.Add(str(k), rama)
            values.Add('' if attr[k] is None else str(attr[k]), rama)
        mesh.append(m); n_obj += 1

linea('')
linea('Solidos : %d   (invalidos: %d | fuera de radio %.0f m: %d)'
      % (len(mesh), n_desc, RADIO_MAX, n_lejos))
if mesh:
    cerradas = sum(1 for m in mesh if m.IsClosed)
    if n_marq:
        linea('Marquesinas descartadas (> %.0f m) : %d' % (ALT_MAX_MARQUESINA, n_marq))
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
