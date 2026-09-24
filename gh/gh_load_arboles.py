# -*- coding: utf-8 -*-
"""
gh_load_arboles.py — GHPython (Rhino 8 / Python 3, ScriptEditor)
TFM UTCI Lavapies — carga de arbolado_lavapies_mesh.json

ENTRADAS DEL COMPONENTE : 2 solamente
    path  (List, str)  ruta hacia arbolado_lavapies_mesh.json
    eap   (Item)       Earth Anchor Point : texto Heron, punto lon/lat o punto UTM

SALIDAS : mesh (List) · clase (List) · keys (Tree) · values (Tree) · info (str)

ESTRUCTURA — estrictamente la de gh_load_edificios.py y gh_load_viario.py,
que pasan por Elefront. NO CAMBIARLA.
    mesh    lista plana de 7 836 mallas, orden copa, tronco, copa, tronco...
    clase   lista plana de 7 836 textos, 'copa' o 'tronco', MISMO orden
    keys    arbol {0}, {1}, ... una rama por malla
    values  idem

COLOREAR POR PARTE — conectar directamente 'clase' :
    clase -> Member Index (Set = Merge('copa','tronco')) -> Index
          -> List Item sobre Merge(color_copa, color_tronco) -> Object Colour
No hay que anadir ningun Graft ni Flatten : los caminos salen ya alineados.

VIA LIGERA — si los atributos no necesitan bakearse en el .3dm,
no conectar keys/values a Elefront : Layer + Object Colour bastan, y
la definicion resulta mucho mas rapida. Los atributos siguen en el CSV.

COLOREAR POR PARTE — conectar directamente 'clase' :
    clase -> Member Index (Set = Merge('copa','tronco')) -> Index
          -> List Item sobre Merge(color_copa, color_tronco) -> Object Colour
Ya no hacen falta Create Set ni List Item sobre las claves : 5 componentes menos.

AGRUPAR_POR_ARBOL = True da en su lugar un arbol {i} de 2 elementos por arbol
(copa en indice 0) y keys/values en {i;j}. Util para razonar por sujeto, pero
los caminos ya no coinciden : NO alimentar Elefront con ello, empareja
topologias incompatibles y la definicion se bloquea.

El fichero contiene 2 objetos por arbol : la copa y el tronco.
  copa   -> normales de VERTICE : superficie curva, render suave
  tronco -> normales de CARA    : prisma de 6 caras, aristas netas
Es el unico componente donde coexisten los dos modos, de ahi el tratamiento por
'clase' en vez de un ajuste global.

Diametro de copa : medido sobre el CHM (MDS 2023 [MAD-03] − MDT [MAD-10]),
enmascarado por las huellas edificadas, segmentado por linea divisoria de aguas
iniciada en la posicion de los arboles. Los arboles no segmentables retoman
D = R_forma x h_copa, con R calibrado sobre el barrio.
Metodo : DOCS/METODOLOGIA_copa_arboles_CHM.md § 3.6
Inventario : [SOURCE: MAD-05] · cotas de base : [SOURCE: MAD-10]

API Rhino : Mesh.Vertices.Add / Faces.AddFace / Normals.ComputeNormals /
Normals.Clear / FaceNormals.ComputeFaceNormals / Compact [SOURCE: GH-01]
"""

# ============================ AJUSTES =======================================
ACTIVO = True     # False : no carga nada, la geometria bakeada sigue en su sitio.
CLASES = ('copa', 'tronco')   # ('copa',) solo para alimentar Ladybug :
                              # los troncos casi no proyectan ninguna sombra
                              # y pesan 23 508 caras sobre 140 532.
AGRUPAR_POR_ARBOL = False     # False (defecto) : un objeto por rama -> Elefront.
                              # True : una rama por arbol, copa luego tronco,
                              # keys/values en {i;j}. Incompatible con Elefront.
Z_REF  = 0.0      # cota a restar de Z. 0 = altitud absoluta conservada.

# Orden dentro de una rama. Sirve tambien de clave de orden : la copa primero.
ORDEN_PARTES = ('copa', 'tronco')
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
    'id',
    'clase',
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


mesh = []            # lista plana, como edificios y viario
clase = []           # lista plana alineada con mesh, 'copa' o 'tronco'
keys = DataTree[object]()
values = DataTree[object]()
_bruto = []          # [(id_arbol, clase, malla, attr)] antes del agrupamiento
n_desc = n_filtrado = 0

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
            aviso('sin EAP : geometria dejada en UTM absoluto.')

    objetos = datos.get('objetos', [])
    linea('%s : %d objetos | %s arboles | copa=%s'
          % (os.path.basename(str(ruta)), len(objetos),
             meta.get('n_arboles'), meta.get('metodo_copa')))
    if meta.get('fuente_mds'):
        linea('   fuente del CHM : %s' % meta['fuente_mds'])

    for o in objetos:
        cl_obj = o.get('clase') or '?'      # variable local : NO llamarla
        if cl_obj not in CLASES:            # 'clase', que es una salida
            n_filtrado += 1; continue

        m = rg.Mesh(); va = m.Vertices
        for v in o['v']:
            va.Add(float(v[0]) - ox, float(v[1]) - oy, float(v[2]) - oz)
        fa = m.Faces
        for f in o['f']:
            if len(f) == 3:   fa.AddFace(f[0], f[1], f[2])
            elif len(f) == 4: fa.AddFace(f[0], f[1], f[2], f[3])

        # copa : elipsoide, cono o columna -> superficie curva, normales de
        # vertice, si no la copa aparece como un poliedro tosco.
        # tronco : prisma de 6 caras -> normales de cara, aristas netas.
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
        # id_arbol une la copa y el tronco de un mismo sujeto. Repliegue sobre
        # el id textual 'ARB_00042_copa' si falta el atributo.
        ida = attr.get('id_arbol')
        if ida is None:
            m_id = re.search(r'ARB_(\d+)', str(o.get('id') or ''))
            ida = int(m_id.group(1)) if m_id else len(_bruto)
        _bruto.append((int(ida), cl_obj, m, attr))

# ------------------------------------------------ agrupamiento por arbol
def orden(t):
    """Clave de orden : por id de arbol, luego copa antes que tronco."""
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
            if CLAVES and k not in CLAVES:
                continue
            keys.Add(str(k), hoja)
            values.Add('' if attr[k] is None else str(attr[k]), hoja)
        j += 1
        clase.append(cl)
        _todas.append(m); _clases.append(cl)
        _metodos.append(str(attr.get('metodo_copa') or '?'))
    mesh = arbol_mesh
    n_arboles = rama_i + 1
else:
    # Lista plana + un juego de atributos por rama : estructura identica a
    # la de los edificios y del viario, que bakean sin problema.
    for i, (ida, cl, m, attr) in enumerate(_bruto):
        rama = GH_Path(i)
        for k in sorted(attr.keys()):
            if CLAVES and k not in CLAVES:
                continue
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
