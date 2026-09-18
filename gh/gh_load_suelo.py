# -*- coding: utf-8 -*-
"""
gh_load_suelo.py — GHPython (Rhino 8 / Python 3, ScriptEditor)
TFM UTCI Lavapies — chargement de suelo_lavapies_mesh.json
(viario + relleno + bordillos, généré par maqueta_suelo_lavapies.py)

Remplace, pour la simulation, les composants Topo_py ET Calles_py.

ENTREES DU COMPOSANT : 2 seulement
    path  (Item, str)  chemin vers suelo_lavapies_mesh.json (COPIE LOCALE, pas G:\)
    eap   (Item)       Earth Anchor Point : texte Heron, point lon/lat ou point UTM

SORTIES : mesh (List) · keys (Tree) · values (Tree) · albedo (List)
          suelo (Item) · info (str)
    mesh / keys / values : un objet par branche -> EleFront (meme structure
                           que edificios et viario).
    albedo : aligne sur mesh -> contexte Ladybug.
    suelo  : UNE malla jointe des surfaces horizontales (sans bordillos),
             a brancher sur l'entree `mesh` de Drape_CurvesOnMesh.

Le fichier est deja propre : triangles uniquement, sommets partages entre
classes, niveaux (chaussee 0 / trottoir +0,15 m) integres a la generation.
Donc : pas de reduction, pas de decalage par classe.

API Rhino : Mesh.Vertices.Add / Faces.AddFace / Vertices.CombineIdentical /
Faces.CullDegenerateFaces / Mesh.Append / Normals.Clear /
FaceNormals.ComputeFaceNormals / Compact [SOURCE: GH-01]
Geometrie : [SOURCE: MAD-07] T03_VIARIO · cotes : [SOURCE: MAD-10] MDT nettoye
"""

# ============================ REGLAGES ======================================
ACTIVO      = True   # False : ne charge rien, la geometrie bakee reste en place.
LIMPIAR     = True   # soudure des sommets identiques + faces degenerees.
SOLO_AMBITO = False  # True : ne garde que attr['en_analisis'] = True (Ladybug).
BORDILLOS   = True   # False : ignore les objets 'bordillo'.
Z_REF       = 0.0    # cote a retrancher a Z. 0 = altitude absolue conservee.
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


mesh, albedo, _clases = [], [], []
keys = DataTree[object]()
values = DataTree[object]()
n_obj = n_desc = n_fuera = n_degen = n_dupli = n_bord = 0
suelo = None          # malla unica de las superficies horizontales
caras_ini = caras_fin = 0

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
            aviso('sans EAP : geometrie laissee en UTM absolu.')

    objetos = datos.get('objetos', [])
    linea('%s : %d objets | tipo=%s | cotas=%s | bordillo=%s m'
          % (os.path.basename(str(ruta)), len(objetos), meta.get('tipo'),
             meta.get('cotas'), meta.get('h_bordillo_m')))
    if meta.get('tipo') != 'suelo':
        aviso('%s n\'est pas un fichier suelo (tipo=%s)' % (os.path.basename(str(ruta)), meta.get('tipo')))

    for o in objetos:
        attr = dict(o.get('attr') or {})
        if SOLO_AMBITO and not attr.get('en_analisis'):
            n_fuera += 1; continue
        if not BORDILLOS and (o.get('clase') == 'bordillo'):
            n_bord += 1; continue

        # construction
        m = rg.Mesh(); va = m.Vertices
        for v in o['v']:
            va.Add(float(v[0]) - ox, float(v[1]) - oy, float(v[2]) - oz)
        fa = m.Faces
        for f in o['f']:
            if len(f) == 3:   fa.AddFace(f[0], f[1], f[2])
            elif len(f) == 4: fa.AddFace(f[0], f[1], f[2], f[3])
        caras_ini += m.Faces.Count

        # cause A : nettoyage topologique, sans effet sur la geometrie visible
        if LIMPIAR:
            try: m.Vertices.CombineIdentical(True, True)
            except Exception: pass
            try: n_degen += m.Faces.CullDegenerateFaces()
            except Exception: pass
            try:
                dup = m.Faces.ExtractDuplicateFaces()
                if dup: n_dupli += dup.Faces.Count
            except Exception: pass

        clase = o.get('clase') or attr.get('clase') or '?'

        # surfaces facettees, pas de surfaces courbes : normales de face
        m.Normals.Clear()
        m.FaceNormals.ComputeFaceNormals()
        m.Compact()

        if not m.IsValid or m.Faces.Count == 0:
            n_desc += 1; continue

        caras_fin += m.Faces.Count
        rama = GH_Path(n_obj)
        attr.setdefault('id', o.get('id'))
        attr.setdefault('clase', clase)
        attr.setdefault('capa', o.get('capa'))
        for k in sorted(attr.keys()):
            keys.Add(str(k), rama)
            values.Add('' if attr[k] is None else str(attr[k]), rama)
        mesh.append(m)
        if clase != 'bordillo':
            if suelo is None:
                suelo = rg.Mesh()
            suelo.Append(m)
        albedo.append(float(attr.get('albedo') or 0.0))
        _clases.append(clase)
        n_obj += 1

if suelo is not None:
    if LIMPIAR:
        try: suelo.Vertices.CombineIdentical(True, True)
        except Exception: pass
    suelo.Normals.Clear()
    suelo.FaceNormals.ComputeFaceNormals()
    suelo.Compact()

linea('')
linea('Objetos : %d   (invalidos: %d | fuera del ambito: %d | bordillos ignorados: %d)'
      % (len(mesh), n_desc, n_fuera, n_bord))
if mesh:
    linea('Caras : %d -> %d  (%.1f %%)'
          % (caras_ini, caras_fin, 100.0*caras_fin/caras_ini if caras_ini else 0))
    linea('  A limpieza  : %s (%d degeneradas, %d duplicadas)'
          % ('ON' if LIMPIAR else 'OFF', n_degen, n_dupli))
    linea('Suelo unido (drapeado) : %d caras' % (suelo.Faces.Count if suelo else 0))
    cc = {}
    for i, m in enumerate(mesh):
        cc[_clases[i]] = cc.get(_clases[i], 0) + m.Faces.Count
    linea('Caras por clase : ' + ' | '.join('%s %d' % kv for kv in sorted(cc.items())))
    linea('Albedos : ' + ', '.join('%.2f' % a for a in sorted(set(albedo)))
          + '   (provisionales, sin fuente documentada)')
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
