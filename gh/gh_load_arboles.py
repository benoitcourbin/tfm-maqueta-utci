# -*- coding: utf-8 -*-
"""
gh_load_arboles.py — GHPython (Rhino 8 / Python 3, ScriptEditor)
TFM UTCI Lavapies — chargement de arbolado_lavapies_mesh.json

ENTREES DU COMPOSANT : 2 seulement
    path  (List, str)  chemin vers arbolado_lavapies_mesh.json
    eap   (Item)       Earth Anchor Point : texte Heron, point lon/lat ou point UTM

SORTIES : mesh (List) · clase (List) · keys (Tree) · values (Tree) · info (str)

STRUCTURE — strictement celle de gh_load_edificios.py et gh_load_viario.py,
qui passent dans Elefront. NE PAS EN CHANGER.
    mesh    liste plate de 7 836 mailles, ordre copa, tronco, copa, tronco...
    clase   liste plate de 7 836 textes, 'copa' ou 'tronco', MEME ordre
    keys    arbre {0}, {1}, ... une branche par maille
    values  idem

COLORER PAR PARTIE — brancher directement 'clase' :
    clase -> Member Index (Set = Merge('copa','tronco')) -> Index
          -> List Item sur Merge(couleur_copa, couleur_tronco) -> Object Colour
Aucun Graft ni Flatten a ajouter : les chemins sortent deja alignes.

VOIE LEGERE — si les attributs n'ont pas besoin d'etre bakes dans le .3dm,
ne pas brancher keys/values sur Elefront : Layer + Object Colour suffisent, et
la definition devient beaucoup plus rapide. Les attributs restent dans le CSV.

COLORER PAR PARTIE — brancher directement 'clase' :
    clase -> Member Index (Set = Merge('copa','tronco')) -> Index
          -> List Item sur Merge(couleur_copa, couleur_tronco) -> Object Colour
Plus besoin de Create Set ni de List Item sur les cles : 5 composants en moins.

AGRUPAR_POR_ARBOL = True donne a la place un arbre {i} de 2 elements par arbre
(copa en indice 0) et keys/values en {i;j}. Utile pour raisonner par sujet, mais
les chemins ne coincident plus : NE PAS alimenter Elefront avec, il apparie des
topologies incompatibles et la definition se bloque.

Le fichier contient 2 objets par arbre : la copa et le tronco.
  copa   -> normales de SOMMET : surface courbe, rendu lisse
  tronco -> normales de FACE   : prisme a 6 pans, aretes nettes
C'est le seul composant ou les deux modes coexistent, d'ou le traitement par
'clase' plutot qu'un reglage global.

Diametre de houppier : mesure sur le CHM (MDS 2023 [MAD-03] − MDT [MAD-10]),
masque par les emprises baties, segmente par ligne de partage des eaux amorcee
sur la position des arbres. Les arbres non segmentables reprennent
D = R_forme x h_copa, avec R calibre sur le quartier.
Methode : DOCS/METODOLOGIA_copa_arboles_CHM.md § 3.6
Inventaire : [SOURCE: MAD-05] · cotes de base : [SOURCE: MAD-10]

API Rhino : Mesh.Vertices.Add / Faces.AddFace / Normals.ComputeNormals /
Normals.Clear / FaceNormals.ComputeFaceNormals / Compact [SOURCE: GH-01]
"""

# ============================ REGLAGES ======================================
ACTIVO = True     # False : ne charge rien, la geometrie bakee reste en place.
CLASES = ('copa', 'tronco')   # ('copa',) seul pour alimenter Ladybug :
                              # les troncs ne portent quasiment aucune ombre
                              # et pesent 23 508 faces sur 140 532.
AGRUPAR_POR_ARBOL = False     # False (defaut) : un objet par branche -> Elefront.
                              # True : une branche par arbre, copa puis tronco,
                              # keys/values en {i;j}. Incompatible avec Elefront.
Z_REF  = 0.0      # cote a retrancher a Z. 0 = altitude absolue conservee.

# Ordre a l'interieur d'une branche. Sert aussi de cle de tri : la copa d'abord.
ORDEN_PARTES = ('copa', 'tronco')
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


mesh = []            # liste plate, comme edificios et viario
clase = []           # liste plate alignee sur mesh, 'copa' ou 'tronco'
keys = DataTree[object]()
values = DataTree[object]()
_bruto = []          # [(id_arbol, clase, malla, attr)] avant regroupement
n_desc = n_filtrado = 0

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
    linea('%s : %d objets | %s arboles | copa=%s'
          % (os.path.basename(str(ruta)), len(objetos),
             meta.get('n_arboles'), meta.get('metodo_copa')))
    if meta.get('fuente_mds'):
        linea('   fuente del CHM : %s' % meta['fuente_mds'])

    for o in objetos:
        cl_obj = o.get('clase') or '?'      # variable locale : NE PAS nommer
        if cl_obj not in CLASES:            # 'clase', qui est une sortie
            n_filtrado += 1; continue

        m = rg.Mesh(); va = m.Vertices
        for v in o['v']:
            va.Add(float(v[0]) - ox, float(v[1]) - oy, float(v[2]) - oz)
        fa = m.Faces
        for f in o['f']:
            if len(f) == 3:   fa.AddFace(f[0], f[1], f[2])
            elif len(f) == 4: fa.AddFace(f[0], f[1], f[2], f[3])

        # copa : ellipsoide, cone ou colonne -> surface courbe, normales de
        # sommet, sinon le houppier apparait comme un polyedre grossier.
        # tronco : prisme a 6 pans -> normales de face, aretes nettes.
        if cl_obj == 'copa':
            m.Normals.ComputeNormals()
        else:
            m.Normals.Clear()
            m.FaceNormals.ComputeFaceNormals()
        m.Compact()

        if not m.IsValid or m.Faces.Count == 0:
            n_desc += 1; continue

        attr = dict(o.get('attr') or {})
        attr.setdefault('id', o.get('id'))
        attr.setdefault('clase', cl_obj)
        # id_arbol relie la copa et le tronco d'un meme sujet. Repli sur l'id
        # textuel 'ARB_00042_copa' si l'attribut manque.
        ida = attr.get('id_arbol')
        if ida is None:
            m_id = re.search(r'ARB_(\d+)', str(o.get('id') or ''))
            ida = int(m_id.group(1)) if m_id else len(_bruto)
        _bruto.append((int(ida), cl_obj, m, attr))

# ------------------------------------------------ regroupement par arbre
def orden(t):
    """Cle de tri : par id d'arbre, puis copa avant tronco."""
    try:
        j = ORDEN_PARTES.index(t[1])
    except ValueError:
        j = len(ORDEN_PARTES)
    return (t[0], j)

_bruto.sort(key=orden)

_todas, _clases, _metodos = [], [], []
n_arboles = len(set(t[0] for t in _bruto))

if AGRUPAR_POR_ARBOL:
    arbol_mesh = DataTree[object]()
    rama_i, ida_prev, j = -1, None, 0
    for ida, cl, m, attr in _bruto:
        if ida != ida_prev:
            rama_i += 1; ida_prev = ida; j = 0
        arbol_mesh.Add(m, GH_Path(rama_i))
        hoja = GH_Path(rama_i, j)
        for k in sorted(attr.keys()):
            keys.Add(str(k), hoja)
            values.Add('' if attr[k] is None else str(attr[k]), hoja)
        j += 1
        clase.append(cl)
        _todas.append(m); _clases.append(cl)
        _metodos.append(str(attr.get('metodo_copa') or '?'))
    mesh = arbol_mesh
    n_arboles = rama_i + 1
else:
    # Liste plate + un jeu d'attributs par branche : structure identique a
    # celle des edificios et du viario, qui bakent sans probleme.
    for i, (ida, cl, m, attr) in enumerate(_bruto):
        rama = GH_Path(i)
        for k in sorted(attr.keys()):
            keys.Add(str(k), rama)
            values.Add('' if attr[k] is None else str(attr[k]), rama)
        mesh.append(m)
        clase.append(cl)
        _todas.append(m); _clases.append(cl)
        _metodos.append(str(attr.get('metodo_copa') or '?'))

linea('')
linea('Objetos cargados : %d   (invalidos: %d | filtrados por clase: %d)'
      % (len(_todas), n_desc, n_filtrado))
if _todas:
    if AGRUPAR_POR_ARBOL:
        tam = {}
        for i in range(mesh.BranchCount):
            c = mesh.Branch(i).Count
            tam[c] = tam.get(c, 0) + 1
        linea('Agrupacion : %d ramas, una por arbol, orden %s'
              % (n_arboles, ' > '.join(ORDEN_PARTES)))
        linea('Objetos por rama : ' + ' | '.join('%d obj -> %d ramas' % kv
                                                 for kv in sorted(tam.items())))
        aviso('AGRUPAR_POR_ARBOL = True : mesh en {i}, keys/values en {i;j}. '
              'Los caminos no coinciden : no alimentar Elefront con esta salida.')
    else:
        linea('Agrupacion : lista plana | %d arboles' % n_arboles)
        linea('Alineacion : mesh %d | clase %d | keys %d ramas | values %d ramas'
              % (len(mesh), len(clase), keys.BranchCount, values.BranchCount))
        if not (len(mesh) == len(clase) == keys.BranchCount == values.BranchCount):
            aviso('Las salidas NO estan alineadas.')
    linea('Clases cargadas : ' + ', '.join(CLASES))
    cc = {}
    for i, m in enumerate(_todas):
        cc[_clases[i]] = cc.get(_clases[i], 0) + m.Faces.Count
    linea('Caras por clase : ' + ' | '.join('%s %d' % kv for kv in sorted(cc.items())))
    linea('Caras totales : %d' % sum(m.Faces.Count for m in _todas))
    cm = {}
    for i, m in enumerate(_todas):
        if _clases[i] == 'copa':
            cm[_metodos[i]] = cm.get(_metodos[i], 0) + 1
    if cm:
        linea('Diametro de copa : ' + ' | '.join('%s %d' % kv for kv in sorted(cm.items()))
              + '   (chm = medido | alometria = D = R x h_copa, R calibrado)')
    bb = rg.BoundingBox.Empty
    for m in _todas:
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
