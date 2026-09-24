# -*- coding: utf-8 -*-
"""
gh_cache.py — GHPython (Rhino 8 / Python 3, ScriptEditor)
TFM UTCI — punto de entrada unico de la definicion Grasshopper.

Lee `manifest_<zona>.json` (escrito por run_maqueta.py) y saca TODO lo que la
definicion necesita : las rutas de cada capa, el anclaje (EAP) y la huella
(bbox). Una sola entrada : el nombre de la zona. Cambiar de barrio =
cambiar una palabra.

ENTRADAS
    zona      (Item, str)   ej. 'lavapies'. Texto simple, sin acentos (las
                            mayusculas se normalizan a minusculas) :
                            es la clave de config/zonas/<zona>.json y el nombre
                            del manifiesto. Ninguna concatenacion manual.
    raiz      (Item, str)   raiz del Drive. Vacio -> 'G:\\Mi unidad\\TFM_UTCI_Lavapies_2026'
    modo      (Item, str)   'cache' (defecto) | 'directo'
    refrescar (Item, bool)  True : recopia aunque la huella no haya cambiado

SALIDAS — rutas
    suelo       (Item, str)   suelo_<zona>_mesh.json          -> gh_load_suelo.path
    edificios   (List, str)   LOD1 luego superestructuras     -> gh_load_edificios.path
    arbolado    (Item, str)   arbolado_<zona>_mesh.json       -> gh_load_arboles.path
    mdt         (Item, str)   mdt_limpio_<zona>.tif
    epw         (Item, str)   EPW de la zona                  -> Panel EPW_Path (v5 LB)
    manifiesto  (Item, str)   ruta del manifiesto leido

SALIDAS — anclaje y huella
    lon, lat, alt (Item, float)   -> Heron `Set EarthAnchorPoint`
    eap           (Item, Point3d) punto lon/lat -> puerto `eap` de los tres cargadores
    eap_txt       (Item, str)     mismo anclaje en formato texto Heron. Usarlo
                                  cuando el puerto `eap` del cargador es de tipo str :
                                  `resolver_eap` lee este formato directamente.
    eap_utm       (Item, Point3d) control : X/Y en EPSG:25830
    bbox          (Item, Rectangle3d) huella de analisis, COORDENADAS MODELO (UTM - EAP)
    bbox_ctx      (Item, Rectangle3d) idem + buffer de contexto
    crs           (Item, str)     ej. 'EPSG:25830'
    info          (Item, str)     informe de control

Los cargadores aceptan un punto lon/lat, un punto UTM o el texto Heron
(`resolver_eap`), asi que `eap` se conecta tal cual y el componente EAP_Editor
desaparece de la definicion.

MODO 'cache' — recomendado
    Los ficheros se copian en %LOCALAPPDATA%\\TFM_UTCI\\<zona>\\ y solo salen las
    rutas locales. La copia solo se rehace si la huella del manifiesto ha
    cambiado. Motivo : en Drive for desktop en streaming, « files are primarily
    stored in the cloud, but will be made available offline when accessed » y
    « some applications use a combination of APIs that make files difficult to
    stream » [Google Drive Help, "Stream and mirror files with Drive for desktop"].
    Un .json de 10 MB leido desde G:\\ pasa entonces por una descarga bajo
    demanda, dentro de la llamada bloqueante de Grasshopper.

MODO 'directo'
    Saca las rutas del Drive tal cual. Usarlo solo si la carpeta de la zona
    esta marcada « Disponible sin conexion » en Drive for desktop.

API : shutil.copy2 / os.path [Python 3 stdlib] · Rhino.Geometry [SOURCE: GH-01]
Proyeccion : Transversa de Mercator WGS84 -> UTM 30N, misma implementacion que
gh_load_suelo.py (sin dependencia externa).
"""

import os
import json
import math
import shutil

import Rhino.Geometry as rg

G = globals()
_zona_in = (G.get('zona') or 'lavapies').strip()
_zona = _zona_in.lower()
_raiz = (G.get('raiz') or '').strip() or 'G:\\Mi unidad\\TFM_UTCI_Lavapies_2026'
_modo = (G.get('modo') or 'cache').strip().lower()
_refrescar = bool(G.get('refrescar'))

_lineas = []
def linea(t): _lineas.append(str(t))
def aviso(t): _lineas.append('AVISO: ' + str(t))


def latlon_a_utm30(lat, lon):
    """WGS84 -> EPSG:25830. Identico a gh_load_suelo.py, sin dependencia."""
    a, f = 6378137.0, 1 / 298.257223563
    e2 = 2 * f - f * f
    ep2 = e2 / (1 - e2)
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


def rect_modelo(caja, ox, oy):
    """[minx, miny, maxx, maxy] en UTM -> Rectangle3d en coordenadas modelo."""
    if not caja or len(caja) < 4:
        return None
    x0, y0, x1, y1 = [float(v) for v in caja[:4]]
    return rg.Rectangle3d(rg.Plane.WorldXY,
                          rg.Interval(x0 - ox, x1 - ox),
                          rg.Interval(y0 - oy, y1 - oy))


def rebasar(ruta):
    """Ruta del manifiesto -> ruta utilizable en ESTA maquina.

    El manifiesto puede haber sido escrito desde Colab : sus rutas empiezan
    entonces por \\content\\drive\\MyDrive\\... y no existen en Windows.
    Se corta tras el nombre de la carpeta raiz del Drive y se pega sobre `raiz`.
    """
    if not ruta:
        return None
    r = str(ruta).replace('/', os.sep).replace('\\', os.sep)
    # 1. ruta relativa a la raiz : el manifiesto portable (desde el 18/09)
    cand = os.path.join(_raiz, r.lstrip(os.sep))
    if os.path.exists(cand):
        return cand
    # 2. ruta absoluta valida en esta maquina
    if os.path.exists(r):
        return r
    # 3. manifiesto antiguo, escrito desde Colab : cortar tras el nombre del proyecto
    tag = os.path.basename(_raiz.rstrip('/\\'))         # TFM_UTCI_Lavapies_2026
    i = r.lower().find(tag.lower())
    if i >= 0:
        cand = os.path.join(_raiz, r[i + len(tag):].lstrip(os.sep))
        if os.path.exists(cand):
            return cand
    return None


_base_maqueta = os.path.join(_raiz, '04_VISUALIZACION', 'Modelo_3D',
                             'Data_Contexto', 'MAQUETA')
manifiesto = os.path.join(_base_maqueta, _zona, 'manifest_%s.json' % _zona)

suelo = arbolado = mdt = epw = None
edificios = []
lon = lat = alt = None
eap = eap_utm = bbox = bbox_ctx = crs = None
eap_txt = None

if not os.path.exists(manifiesto):
    aviso('no existe %s' % manifiesto)
    try:
        zonas = sorted(d for d in os.listdir(_base_maqueta)
                       if os.path.isdir(os.path.join(_base_maqueta, d)))
        linea('Zonas disponibles : %s' % (', '.join(zonas) if zonas else '(ninguna)'))
    except Exception:
        linea('No se puede listar %s' % _base_maqueta)
    linea('Lanzar antes :  python run_maqueta.py --zona %s' % _zona)
else:
    with open(manifiesto, 'r', encoding='utf-8') as fh:
        M = json.load(fh)
    if _zona_in != _zona:
        linea('zona "%s" -> "%s" (clave en minusculas)' % (_zona_in, _zona))
    linea('Manifiesto %s | generado %s | completo=%s'
          % (_zona, M.get('generado'), M.get('completo')))

    destino_base = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
                                'TFM_UTCI', _zona)

    def resolver(clave):
        """Ruta utilizable para esta clave del manifiesto, segun el modo."""
        ent = (M.get('ficheros') or {}).get(clave)
        if not ent:
            linea('  %-12s AUSENTE en el manifiesto' % clave)
            return None
        origen = rebasar(ent['ruta'])
        if origen is None:
            aviso('%-12s el manifiesto lo declara pero no está en el disco : %s'
                  % (clave, ent['ruta']))
            return None
        if origen != str(ent['ruta']).replace('/', os.sep).replace('\\', os.sep):
            linea('  %-12s ruta rebasada sobre raiz (manifiesto escrito en Colab)'
                  % clave)
        if _modo == 'directo':
            linea('  %-12s directo (%.1f MB)' % (clave, ent['bytes'] / 1e6))
            return origen
        os.makedirs(destino_base, exist_ok=True)
        local = os.path.join(destino_base, os.path.basename(origen))
        sello = local + '.huella'
        actual = None
        if os.path.exists(sello):
            with open(sello, 'r', encoding='utf-8') as fh:
                actual = fh.read().strip()
        if _refrescar or actual != ent['huella'] or not os.path.exists(local):
            shutil.copy2(origen, local)
            with open(sello, 'w', encoding='utf-8') as fh:
                fh.write(ent['huella'])
            linea('  %-12s copiado (%.1f MB)' % (clave, ent['bytes'] / 1e6))
        else:
            linea('  %-12s en caché, sin cambios' % clave)
        return local

    # ---- rutas ------------------------------------------------------------
    suelo = resolver('suelo')
    for k in ('lod1', 'superstruct'):
        r = resolver(k)
        if r:
            edificios.append(r)
    arbolado = resolver('arbolado')
    mdt = resolver('mdt_limpio') or resolver('mdt')
    epw = resolver('epw')

    # ---- anclaje ----------------------------------------------------------
    crs = M.get('crs') or 'EPSG:25830'
    _eap = M.get('eap') or {}
    if 'lon' in _eap and 'lat' in _eap:
        lon = float(_eap['lon'])
        lat = float(_eap['lat'])
        alt = float(_eap.get('alt', 0.0))
        ex, ey = latlon_a_utm30(lat, lon)
        eap = rg.Point3d(lon, lat, alt)       # lon/lat : los cargadores lo detectan
        # Formato texto Heron : leido por resolver_eap (regex Long.../Lat...).
        eap_txt = ('EarthAnchorPoint\n  Longitude: %.8f\n  Latitude: %.8f\n'
                   '  Elevation: %.2f' % (lon, lat, alt))
        eap_utm = rg.Point3d(ex, ey, 0.0)
        linea('EAP  lon %.8f  lat %.8f  ->  X %.2f  Y %.2f  (%s)'
              % (lon, lat, ex, ey, crs))
    else:
        ex = ey = 0.0
        aviso('el manifiesto no trae eap {lon, lat} : sin ancrage, bbox en UTM absoluto')

    # ---- huella -----------------------------------------------------------
    bbox = rect_modelo(M.get('bbox'), ex, ey)
    bbox_ctx = rect_modelo(M.get('bbox_contexto') or M.get('bbox'), ex, ey)
    if bbox is not None:
        _c = M['bbox']
        linea('bbox analisis  %.0f x %.0f m  (UTM %.2f %.2f -> %.2f %.2f)'
              % (_c[2] - _c[0], _c[3] - _c[1], _c[0], _c[1], _c[2], _c[3]))
    else:
        aviso('el manifiesto no trae bbox')
    if bbox_ctx is not None and M.get('bbox_contexto'):
        _k = M['bbox_contexto']
        linea('bbox contexto  %.0f x %.0f m' % (_k[2] - _k[0], _k[3] - _k[1]))

    linea('Modo : %s%s' % (_modo, '' if _modo == 'directo' else ' -> ' + destino_base))
    if not M.get('completo'):
        aviso('el run no terminó completo. Ver DOCS/INFORMES/'
              'informe_ejecucion_%s.md' % _zona)

info = '\n'.join(_lineas)
try:
    import Grasshopper
    if any(l.startswith('AVISO') for l in _lineas):
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning,
            'Ver la salida info')
except Exception:
    pass
