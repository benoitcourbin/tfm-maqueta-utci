# -*- coding: utf-8 -*-
"""
maqueta_suelo_lavapies.py — Colab (ou Python 3 local)
TFM UTCI Lavapies — sol unifié : viario + relleno + bordillos, sur MDT nettoyé.

Remplace topo_lavapies_mesh.json ET viario_lavapies_mesh.json pour la simulation.

POURQUOI
  - La topo (grille 10 m) et le viario (MDT 1 m au pixel) ne suivent pas le même
    terrain : 39 % des sommets du viario passent SOUS la topo, jusqu'à 3,6 m
    (mesure du 17/09) -> "ergots".
  - Topo et viario se superposent (doublon de surfaces).
  - Voirie et trottoirs sont des nappes indépendantes, décalées en Z dans GH.

METHODE
  1. MDT nettoyé : |z - médiane 21 m| > 5 m -> médiane (31 px dans la zone).
  2. Partition plane exclusive par priorité :
       huella > adoquinado > acera > isleta > vado > calzada ; relleno = reste.
  3. Noeuds communs : toutes les frontières + une grille de 50 m sont unies
     (noding), polygonisées, puis simplifiées en couverture -> deux faces
     voisines partagent EXACTEMENT leurs sommets.
  4. Triangulation contrainte (lib `triangle`, option Y : aucun point ajouté sur
     les frontières) + points intérieurs sur grille pour suivre le relief.
  5. Z = interpolation bilinéaire du MDT nettoyé, une seule fonction pour tous.
  6. Niveaux : chaussée 0, trottoir/isleta/relleno +H_BORD ; bordillos verticaux
     sur chaque arête entre deux niveaux différents.

Dépendances : numpy, scipy, rasterio, shapely>=2.0, triangle
    !pip install -q triangle
"""

# ====================== REGLAGES (via variables d'environnement) ============
# Le pas est piloté par run_maqueta.py, qui exporte TFM_SUELO_* avant d'appeler
# ce fichier. Les valeurs ci-dessous sont les repliegues : lancé seul, le script
# reproduit le run du 17/09 sur Lavapiés.
import os, ast

def _cfg(clave, defecto):
    v = os.environ.get('TFM_SUELO_' + clave)
    return ast.literal_eval(v) if v is not None else defecto

BASE = os.environ.get(
    'MAQUETA_DIR',
    '/content/drive/MyDrive/TFM_UTCI_Lavapies_2026/04_VISUALIZACION/'
    'Modelo_3D/Data_Contexto/MAQUETA/lavapies')
ZONA = os.environ.get('TFM_ZONA', 'lavapies')

MDT_TIF      = BASE + '/topo_%s_mdt.tif' % ZONA
VIARIO_GJ    = BASE + '/viario_%s.geojson' % ZONA
HUELLAS_GJ   = BASE + '/edificios_%s_huellas.geojson' % ZONA
OUT_DIR      = os.environ.get('MAQUETA_OUT', BASE)

BBOX_CONTEXTO = tuple(_cfg('BBOX_CONTEXTO', (439274.77, 4472345.06, 441079.55, 4474148.43)))
BBOX_ANALISIS = tuple(_cfg('BBOX_ANALISIS', (439574.77, 4472645.06, 440779.55, 4473848.43)))

UMBRAL_MDT  = _cfg('UMBRAL_MDT', 5.0)    # m : écart à la médiane -> pixel corrigé
VENTANA_MDT = _cfg('VENTANA_MDT', 21)    # px (1 m) : fenêtre de la médiane
SIMPLIFICAR = _cfg('SIMPLIFICAR', 0.25)  # m : simplification de couverture
PASO_INT    = _cfg('PASO_INT', 10.0)     # m : grille de points intérieurs
MARGEN_INT  = 1.0    # m : distance mini des points intérieurs à la frontière
H_BORD      = _cfg('H_BORD', 0.15)       # m : hauteur de bordillo
PRECISION   = 0.01   # m : grille d'accrochage des coordonnées
CELDA       = _cfg('CELDA', 50.0)        # m : découpe des faces avant triangulation
GRUPO       = 100.0  # m : regroupement des faces en objets (limite le nb d'objets Rhino)
AREA_MIN    = 0.5    # m2 : fragments plus petits -> fusionnés dans relleno
# Emprises : mêmes règles que le LOD1 (metadata_edificios_lod1)
TOL_HUELLA  = 0.10
AREA_MIN_HUELLA = 3.0

PRIORIDAD = ['adoquinado', 'acera', 'isleta', 'vado', 'calzada']
NIVEL = {'calzada': 0.0, 'adoquinado': 0.0, 'vado': 0.0,
         'acera': H_BORD, 'isleta': H_BORD, 'relleno': H_BORD}
# relleno / bordillo : valeurs provisoires (topo : 0,20 / 0,92 ; bordillo = hormigón)
MATERIAL_EXTRA = {'relleno':  {'material': 'suelo', 'albedo': 0.20, 'emisividad': 0.92},
                  'bordillo': {'material': 'hormigon', 'albedo': 0.30, 'emisividad': 0.92}}
# ============================================================================

import json, time, math
from collections import defaultdict, Counter
import numpy as np
import rasterio
from scipy import ndimage
import shapely
import shapely.prepared
from shapely.geometry import shape, box, Polygon, MultiPolygon, Point
from shapely.ops import unary_union, polygonize
from shapely.strtree import STRtree
import triangle as tr

T0 = time.time()
LOG = []
def log(t=''):
    print(t); LOG.append(str(t))

def partes(g):
    """Explose une géométrie en liste de Polygon valides."""
    if g is None or g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    if hasattr(g, 'geoms'):
        out = []
        for x in g.geoms:
            out += partes(x)
        return out
    return []

# ------------------------------------------------------------ 1. MDT nettoyé
with rasterio.open(MDT_TIF) as src:
    Z = src.read(1).astype('float64')
    perfil = src.profile.copy()
    TR = src.transform
    nod = src.nodata
malo = ~np.isfinite(Z) | ((Z < 300) | (Z > 1200))
if nod is not None:
    malo |= (Z == nod)
if malo.any():
    Z[malo] = np.nanmedian(Z[~malo])
med = ndimage.median_filter(Z, size=VENTANA_MDT)
fuera = np.abs(Z - med) > UMBRAL_MDT
Zl = np.where(fuera, med, Z)
log('MDT : %d x %d px | corregidos %d px (|dz| > %.1f m, ventana %d m) | sin dato %d'
    % (Z.shape[1], Z.shape[0], int(fuera.sum()), UMBRAL_MDT, VENTANA_MDT, int(malo.sum())))
perfil.update(dtype='float32', nodata=None)
MDT_OUT = OUT_DIR + '/mdt_limpio_%s.tif' % ZONA
with rasterio.open(MDT_OUT, 'w', **perfil) as dst:
    dst.write(Zl.astype('float32'), 1)

inv = ~TR
def cota(x, y):
    """Bilinéaire sur le MDT nettoyé (centres de pixel)."""
    c, r = inv * (x, y)
    c -= 0.5; r -= 0.5
    c0 = int(math.floor(c)); r0 = int(math.floor(r))
    c0 = min(max(c0, 0), Zl.shape[1] - 2); r0 = min(max(r0, 0), Zl.shape[0] - 2)
    fc = min(max(c - c0, 0.0), 1.0); fr = min(max(r - r0, 0.0), 1.0)
    z00, z01 = Zl[r0, c0], Zl[r0, c0 + 1]
    z10, z11 = Zl[r0 + 1, c0], Zl[r0 + 1, c0 + 1]
    return float((z00 * (1 - fc) + z01 * fc) * (1 - fr) + (z10 * (1 - fc) + z11 * fc) * fr)

# ------------------------------------------------ 2. partition exclusive
MARCO = box(*BBOX_CONTEXTO)
ANALISIS = box(*BBOX_ANALISIS)

hu = json.load(open(HUELLAS_GJ, encoding='utf-8'))
huellas = []
for f in hu['features']:
    if not f.get('geometry'):
        continue
    g = shapely.make_valid(shapely.force_2d(shape(f['geometry']))).simplify(TOL_HUELLA)
    for p in partes(g):
        if p.area >= AREA_MIN_HUELLA and p.intersects(MARCO):
            huellas.append(p)
EDIF = shapely.set_precision(unary_union(huellas), PRECISION).intersection(MARCO)
log('Huellas : %d polígonos -> %.0f m2' % (len(huellas), EDIF.area))

vi = json.load(open(VIARIO_GJ, encoding='utf-8'))
por_clase = defaultdict(list)
props_clase = {}
for f in vi['features']:
    pr = f['properties']; cl = pr['clase']
    # le GeoJSON viario porte des Z : on travaille strictement en 2D
    por_clase[cl].append(shapely.make_valid(shapely.force_2d(shape(f['geometry']))))
    props_clase.setdefault(cl, {k: pr.get(k) for k in ('capa', 'material', 'albedo', 'emisividad')})

GEOM = {}                 # clase -> géométrie exclusive
ocupado = EDIF
for cl in PRIORIDAD:
    g = shapely.set_precision(unary_union(por_clase.get(cl, [])), PRECISION)
    g = g.intersection(MARCO).difference(ocupado)
    GEOM[cl] = g
    ocupado = ocupado.union(g)
GEOM['relleno'] = MARCO.difference(ocupado)
for cl in PRIORIDAD + ['relleno']:
    log('  %-11s %9.0f m2' % (cl, GEOM[cl].area))

# ------------------------------------------------ 3. noeuds communs
lineas = [MARCO.exterior] + [EDIF.boundary]
# Grille de découpe : chaque face <= CELDA x CELDA m. Les lignes de grille sont
# nodées avec le reste, donc les points de coupe sont partagés entre voisins.
# Evite les faces géantes (calzada de 56 ha) sur lesquelles `triangle` échoue.
x0, y0, x1, y1 = BBOX_CONTEXTO
for gx in np.arange(math.ceil(x0 / CELDA) * CELDA, x1, CELDA):
    lineas.append(shapely.LineString([(gx, y0), (gx, y1)]))
for gy in np.arange(math.ceil(y0 / CELDA) * CELDA, y1, CELDA):
    lineas.append(shapely.LineString([(x0, gy), (x1, gy)]))
for cl in PRIORIDAD + ['relleno']:
    if not GEOM[cl].is_empty:
        lineas.append(GEOM[cl].boundary)
red = unary_union(lineas)                       # noding : coupe à chaque croisement
caras = [p for p in polygonize(red) if p.area > 1e-4]
log('Caras polygonizadas : %d' % len(caras))
# Simplification de COUVERTURE : les arêtes communes sont simplifiées une seule
# fois, les noeuds (jonctions, croisements de grille) sont conservés.
# Le Catastro/T03 porte un sommet tous les 2 à 4 m : c'est lui qui gonfle le
# nombre de faces, pas le relief.
if SIMPLIFICAR:
    n0 = sum(len(p.exterior.coords) + sum(len(r.coords) for r in p.interiors) for p in caras)
    caras = list(shapely.coverage_simplify(np.array(caras, dtype=object), SIMPLIFICAR,
                                           simplify_boundary=False))
    caras = [p for p in caras if p is not None and not p.is_empty and p.area > 1e-4]
    n1 = sum(len(p.exterior.coords) + sum(len(r.coords) for r in p.interiors) for p in caras)
    log('Simplificación de cobertura %.2f : %d -> %d vértices de borde' % (SIMPLIFICAR, n0, n1))

# classe de chaque face par point représentatif
arbol_cl = []
for cl in ['edif'] + PRIORIDAD:
    g = EDIF if cl == 'edif' else GEOM[cl]
    for p in partes(g):
        arbol_cl.append((p, cl))
tree = STRtree([p for p, _ in arbol_cl])
def clase_de(face):
    pt = face.representative_point()
    idx = tree.query(pt, predicate='within')
    cls = [arbol_cl[i][1] for i in idx]
    for cl in ['edif'] + PRIORIDAD:     # priorité en cas de contact
        if cl in cls:
            return cl
    return 'relleno'

CARAS = []
for p in caras:
    cl = clase_de(p)
    if cl == 'edif':
        continue
    if p.area < AREA_MIN and cl != 'relleno':
        cl = 'relleno'
    CARAS.append((shapely.geometry.polygon.orient(p, 1.0), cl))
log('Caras de suelo : %d | %s' % (len(CARAS), dict(Counter(c for _, c in CARAS))))

# ------------------------------------------------ 4. triangulation
def clave(x, y):
    return (float(x), float(y))   # coordonnées exactes du réseau nodé

def puntos_interiores(face):
    if face.area < 4 * PASO_INT * PASO_INT:
        return []
    nucleo = face.buffer(-MARGEN_INT)
    if nucleo.is_empty:
        return []
    x0, y0, x1, y1 = nucleo.bounds
    xs = np.arange(math.ceil(x0 / PASO_INT) * PASO_INT, x1, PASO_INT)
    ys = np.arange(math.ceil(y0 / PASO_INT) * PASO_INT, y1, PASO_INT)
    if not len(xs) or not len(ys):
        return []
    gx, gy = np.meshgrid(xs, ys)
    pts = shapely.points(gx.ravel(), gy.ravel())
    dentro = shapely.contains(nucleo, pts)
    return list(zip(gx.ravel()[dentro], gy.ravel()[dentro]))

def triangular(face):
    """Retourne (liste xy, liste triangles). Aucun point ajouté sur les bords."""
    idx = {}; V = []; S = []
    def add(x, y):
        k = clave(x, y)
        if k not in idx:
            idx[k] = len(V); V.append(k)
        return idx[k]
    anillos = [face.exterior] + list(face.interiors)
    for an in anillos:
        cs = list(an.coords)[:-1]
        ids = [add(x, y) for x, y in cs]
        for a, b in zip(ids, ids[1:] + ids[:1]):
            if a != b:
                S.append((a, b))
    for x, y in puntos_interiores(face):
        add(x, y)
    datos = {'vertices': np.array(V), 'segments': np.array(S)}
    agujeros = []
    for an in face.interiors:
        h = Polygon(an)
        if h.area > 1e-6:
            agujeros.append(h.representative_point().coords[0])
    if agujeros:
        datos['holes'] = np.array(agujeros)
    try:
        t = tr.triangulate(datos, 'pYQ')
        if len(t['vertices']) == len(V) and 'triangles' in t:
            return V, t['triangles'].tolist()
    except Exception:
        pass
    # repli : Delaunay contrainte de shapely, sans point intérieur ni point ajouté
    ESTAD['repli'] += 1
    tris = shapely.constrained_delaunay_triangles(face)
    out = []
    for g in partes(tris):
        c = list(g.exterior.coords)[:-1]
        k3 = [clave(x, y) for x, y in c]
        if len(set(k3)) == 3 and all(k in idx for k in k3):
            out.append([idx[k] for k in k3])
        else:
            ESTAD['tri_perdido'] += 1
    return V, out

ESTAD = Counter()

def area2(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

cache_z = {}
def z_de(xy):
    k = clave(*xy)
    if k not in cache_z:
        cache_z[k] = cota(k[0], k[1])
    return cache_z[k]

OBJ = []
grupos = defaultdict(lambda: {'v': [], 'f': [], 'area': 0.0})
aristas = defaultdict(list)     # arête non orientée -> [(nivel, sens a->b, id_obj)]
n_err = 0
for i, (face, cl) in enumerate(CARAS):
    try:
        V, T = triangular(face)
    except Exception as ex:
        n_err += 1
        log('  ⚠️ cara %d (%s, %.1f m2) no triangulada : %s' % (i, cl, face.area, ex))
        continue
    niv = NIVEL[cl]
    v3 = [[x, y, round(z_de((x, y)) + niv, 3)] for x, y in V]
    f3 = []
    for a, b, c in T:
        s = area2(V[a], V[b], V[c])
        if abs(s) < 1e-8:
            continue
        f3.append([a, b, c] if s > 0 else [a, c, b])     # normale vers +Z
    # arêtes de frontière, dans le sens de l'anneau orienté (intérieur à gauche)
    for an in [face.exterior] + list(face.interiors):
        cs = [clave(x, y) for x, y in list(an.coords)]
        for p, q in zip(cs[:-1], cs[1:]):
            if p != q:
                aristas[frozenset((p, q))].append((niv, (p, q), i))
    c = face.representative_point()
    gk = (cl, int(c.x // GRUPO), int(c.y // GRUPO))
    g = grupos[gk]
    base = len(g['v'])
    g['v'] += v3
    g['f'] += [[a + base, b + base, d + base] for a, b, d in f3]
    g['area'] += face.area

for (cl, gx, gy), g in sorted(grupos.items()):
    pr = dict(props_clase.get(cl) or {})
    pr.update(MATERIAL_EXTRA.get(cl, {}))
    x0, y0 = gx * GRUPO, gy * GRUPO
    attr = {'clase': cl, 'capa': pr.get('capa') or ('SUELO_' + cl.upper()),
            'material': pr.get('material'), 'albedo': pr.get('albedo'),
            'emisividad': pr.get('emisividad'), 'nivel_m': NIVEL[cl],
            'area_m2': round(g['area'], 2), 'celda': '%d_%d' % (gx, gy),
            'en_analisis': bool(box(x0, y0, x0 + GRUPO, y0 + GRUPO).intersects(ANALISIS))}
    OBJ.append({'id': 'SUE_%05d' % len(OBJ), 'capa': attr['capa'], 'clase': cl,
                'v': g['v'], 'f': g['f'], 'attr': attr})

# ------------------------------------------------ 5. bordillos
def celda(p):
    return (int(p[0] // GRUPO), int(p[1] // GRUPO))

PARES = Counter()
muros = defaultdict(lambda: {'v': [], 'f': [], 'long': 0.0})
n_desnudas = n_limite = 0
LIMITE = shapely.prepared.prep(unary_union([MARCO.exterior, EDIF.boundary]).buffer(0.05))
for k, lst in aristas.items():
    if len(lst) == 1:
        p, q = lst[0][1]
        mid = Point((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        if LIMITE.contains(mid):
            n_limite += 1
        else:
            n_desnudas += 1
        continue
    if len(lst) != 2:
        n_desnudas += 1
        continue
    (n1, s1, i1), (n2, s2, i2) = lst
    _par = tuple(sorted((CARAS[i1][1], CARAS[i2][1])))
    if abs(n1 - n2) >= 1e-6:
        PARES[_par] += math.dist(s1[0], s1[1])
    if abs(n1 - n2) < 1e-6:
        continue
    alto, sentido = (n1, s1) if n1 > n2 else (n2, s2)
    bajo = min(n1, n2)
    p, q = sentido                      # intérieur de la face haute à gauche
    P, Q = p, q
    zp, zq = z_de(P), z_de(Q)
    m = muros[celda(p)]
    b = len(m['v'])
    m['v'] += [[P[0], P[1], round(zp + bajo, 3)], [Q[0], Q[1], round(zq + bajo, 3)],
               [Q[0], Q[1], round(zq + alto, 3)], [P[0], P[1], round(zp + alto, 3)]]
    # normale vers la droite = vers la face basse
    m['f'] += [[b, b + 1, b + 2], [b, b + 2, b + 3]]
    m['long'] += math.hypot(Q[0] - P[0], Q[1] - P[1])

pr = MATERIAL_EXTRA['bordillo']
lon_tot = 0.0
for (cx, cy), m in sorted(muros.items()):
    lon_tot += m['long']
    x0, y0 = cx * GRUPO, cy * GRUPO
    en = box(x0, y0, x0 + GRUPO, y0 + GRUPO).intersects(ANALISIS)
    OBJ.append({'id': 'SUE_%05d' % len(OBJ), 'capa': 'SUELO_BORDILLO', 'clase': 'bordillo',
                'v': m['v'], 'f': m['f'],
                'attr': {'clase': 'bordillo', 'capa': 'SUELO_BORDILLO',
                         'material': pr['material'], 'albedo': pr['albedo'],
                         'emisividad': pr['emisividad'], 'altura_m': H_BORD,
                         'longitud_m': round(m['long'], 1), 'en_analisis': bool(en)}})

# ------------------------------------------------ 6. contrôle + export
log('')
log('=== CONTROL DE CALIDAD ===')
log('Caras no trianguladas : %d | repli Delaunay shapely : %d | triángulos perdidos : %d'
    % (n_err, ESTAD['repli'], ESTAD['tri_perdido']))
log('Aristas de borde : %d en límite (marco / fachada) | %d desnudas' % (n_limite, n_desnudas))
log('  (desnudas debe ser 0 : superficie continua entre clases)')
log('Bordillos por par de clases (m) : %s' % {k: round(v) for k, v in PARES.most_common()})
log('Bordillos : %.0f m lineales en %d objetos' % (lon_tot, len(muros)))
area_suelo = sum(f.area for f, _ in CARAS)
log('Suelo : %.0f m2 | edificado %.0f m2 | suma %.2f %% del marco'
    % (area_suelo, EDIF.area, 100 * (area_suelo + EDIF.area) / MARCO.area))
cc = Counter(); nf = Counter()
for o in OBJ:
    cc[o['clase']] += 1; nf[o['clase']] += len(o['f'])
log('Objetos por clase : %s' % dict(cc))
log('Caras por clase   : %s' % dict(nf))
log('Caras totales : %d (todas triangulares)' % sum(nf.values()))
zs = [v[2] for o in OBJ for v in o['v']]
log('Z : %.2f – %.2f m' % (min(zs), max(zs)))
# écart au MDT brut aux sommets du sol (hors niveaux)
dz = []
for k, z in cache_z.items():
    c, r = inv * (k[0], k[1])
    r = min(max(int(r), 0), Z.shape[0] - 1); c = min(max(int(c), 0), Z.shape[1] - 1)
    dz.append(z - Z[r, c])
dz = np.array(dz)
log('Suelo − MDT bruto (píxel) : p1 %.2f | mediana %.2f | p99 %.2f | |dz|>1 m : %d / %d'
    % (np.percentile(dz, 1), np.median(dz), np.percentile(dz, 99),
       int((np.abs(dz) > 1).sum()), len(dz)))

meta = {'tipo': 'suelo', 'zona': ZONA, 'crs': 'EPSG:25830', 'unidades': 'm',
        'z_mode': 'absolute', 'dx': 0.0, 'dy': 0.0, 'dz': 0.0,
        'cotas': 'mdt_limpio (bilineal)', 'umbral_mdt_m': UMBRAL_MDT,
        'ventana_mdt_m': VENTANA_MDT, 'simplificar_m': SIMPLIFICAR, 'celda_m': CELDA,
        'paso_interior_m': PASO_INT, 'h_bordillo_m': H_BORD, 'nivel': NIVEL,
        'prioridad': ['edificio'] + PRIORIDAD + ['relleno'],
        'fuentes': {'viario': os.path.basename(VIARIO_GJ),
                    'huellas': os.path.basename(HUELLAS_GJ),
                    'mdt': os.path.basename(MDT_TIF)},
        'n_objetos': len(OBJ), 'n_caras': int(sum(nf.values())),
        'generado': time.strftime('%Y-%m-%dT%H:%M:%S')}
salida = OUT_DIR + '/suelo_%s_mesh.json' % ZONA
with open(salida, 'w', encoding='utf-8') as fh:
    json.dump({'meta': meta, 'objetos': OBJ}, fh, ensure_ascii=False, separators=(',', ':'))
with open(OUT_DIR + '/metadata_suelo_%s.json' % ZONA, 'w', encoding='utf-8') as fh:
    json.dump(meta, fh, ensure_ascii=False, indent=2)
log('✔ %s  %.2f MB' % (os.path.basename(salida), os.path.getsize(salida) / 1e6))
log('✔ %s' % os.path.basename(MDT_OUT))
log('Duración : %.1f s' % (time.time() - T0))
with open(os.environ.get('TFM_INFORME_SUELO', OUT_DIR + '/informe_suelo_%s.md' % ZONA), 'w', encoding='utf-8') as fh:
    fh.write('# Informe — maqueta SUELO %s\n\nGenerado el %s\n\n```\n%s\n```\n'
             % (ZONA, meta['generado'], '\n'.join(LOG)))
