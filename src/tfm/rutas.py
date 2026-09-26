# -*- coding: utf-8 -*-
"""
rutas.py — árbol de directorios único del proyecto, construido a partir del
nombre de la zona.

Ninguna ruta se escribe a mano en otro punto de la cadena. Un solo sitio que
cambiar si el árbol del Drive se mueve.

RAÍZ :
  Colab  -> /content/drive/MyDrive/TFM_UTCI_Lavapies_2026
  Windows-> G:\\Mi unidad\\TFM_UTCI_Lavapies_2026
  o variable de entorno TFM_RAIZ (pruebas locales).
"""

import os
import json

NOMBRE_PROYECTO = 'TFM_UTCI_Lavapies_2026'

CANDIDATAS = [
    '/content/drive/MyDrive/' + NOMBRE_PROYECTO,
    'G:/Mi unidad/' + NOMBRE_PROYECTO,
    os.path.expanduser('~/Google Drive/Mi unidad/' + NOMBRE_PROYECTO),
]


def raiz():
    """Raíz del proyecto en el Drive."""
    r = os.environ.get('TFM_RAIZ')
    if r:
        return r.rstrip('/\\')
    for c in CANDIDATAS:
        if os.path.isdir(c):
            return c
    raise RuntimeError(
        'No se encuentra la raíz del proyecto. Monta el Drive '
        '(drive.mount) o define TFM_RAIZ. Probadas: %s' % CANDIDATAS)


class Rutas(object):
    """Todas las rutas de una zona. Crea las carpetas que falten."""

    def __init__(self, zona, crear=True):
        self.zona = zona
        self.raiz = raiz()
        self.modelo = self.raiz + '/04_VISUALIZACION/Modelo_3D'
        self.fuentes = self.modelo + '/Data_Contexto/FUENTES'
        self.maqueta = self.modelo + '/Data_Contexto/MAQUETA/' + zona
        self.docs = self.modelo + '/DOCS'
        self.informes = self.docs + '/INFORMES'
        self.gh_scripts = self.modelo + '/Python/GH_Scripts'
        self.datos = self.raiz + '/01_DATOS'
        self.ladybug = self.datos + '/LADYBUG_SIM/' + zona
        self.codigo = self.raiz + '/02_CODIGO'
        if crear:
            for d in (self.fuentes, self.maqueta, self.informes,
                      self.gh_scripts, self.ladybug, self.codigo):
                os.makedirs(d, exist_ok=True)

    # --- ficheros de la maqueta --------------------------------------------
    def m(self, nombre):
        """Fichero de la maqueta : m('suelo_%s_mesh.json')."""
        return self.maqueta + '/' + (nombre % self.zona if '%s' in nombre else nombre)

    @property
    def mdt(self):
        return self.m('topo_%s_mdt.tif')

    @property
    def mdt_limpio(self):
        return self.m('mdt_limpio_%s.tif')

    @property
    def huellas(self):
        return self.m('edificios_%s_huellas.geojson')

    @property
    def viario_gj(self):
        return self.m('viario_%s.geojson')

    @property
    def suelo(self):
        return self.m('suelo_%s_mesh.json')

    @property
    def lod1(self):
        return self.m('edificios_%s_lod1_mesh.json')

    @property
    def superstruct(self):
        return self.m('edificios_%s_superstruct_mesh.json')

    @property
    def arbolado(self):
        return self.m('arbolado_%s_mesh.json')

    @property
    def manifiesto(self):
        return self.m('manifest_%s.json')

    def informe(self, nombre):
        """Todos los informes van a DOCS/INFORMES."""
        return self.informes + '/' + (nombre % self.zona if '%s' in nombre else nombre)

    def run_ladybug(self, version):
        d = self.ladybug + '/' + version
        os.makedirs(d, exist_ok=True)
        return d


def _ficha_ml(cfg, config_dir):
    """Ficha de zona exportada por el cuaderno ML (config/zonas/ml/<fichero>), o None."""
    nombre = cfg.get('zona_ml')
    if not nombre:
        return None
    ruta = os.path.join(config_dir, 'ml', nombre)
    if not os.path.exists(ruta):
        raise RuntimeError('zona_ml = %s, pero no existe %s' % (nombre, ruta))
    with open(ruta, 'r', encoding='utf-8') as fh:
        ficha = json.load(fh)
    if ficha.get('crs', cfg.get('crs')) != cfg.get('crs', 'EPSG:25830'):
        raise RuntimeError('CRS de la ficha ML (%s) distinto del de la zona (%s)'
                           % (ficha.get('crs'), cfg.get('crs')))
    return ficha


def _derivar_geometria(cfg, config_dir):
    """Completa bbox, origen_local y eap. Prioridad, de mayor a menor:

      1. valor explícito en el json de la zona (Lavapiés conserva los suyos
         mientras el run v5 sea la referencia, ESTADO §6, 24/09);
      2. ficha ML (`zona_ml`): bbox = `dsm_extension`, la extensión EXACTA de
         los rásters de SOLWEIG. No es centro ± radio: el ráster se amplió
         101 m por lado (1 402 m de lado frente a 1 200 m);
      3. centro {lat, lon} ± radio_m, si no hay ficha.
    EAP = centro ML (lat, lon); origen_local = su proyección en el CRS de la zona.
    """
    faltan = [k for k in ('bbox', 'origen_local', 'eap') if k not in cfg]
    if not faltan:
        return cfg
    ficha = _ficha_ml(cfg, config_dir)
    centro = cfg.get('centro') or (ficha or {}).get('centro')
    if not centro:
        raise RuntimeError(
            'Zona %s: faltan %s y no hay centro {lat, lon} ni ficha ML para '
            'derivarlos.' % (cfg.get('zona'), ', '.join(faltan)))
    from pyproj import Transformer   # ya usado en pasos/arbolado.py
    lon, lat = float(centro['lon']), float(centro['lat'])
    tr = Transformer.from_crs('EPSG:4326', cfg.get('crs', 'EPSG:25830'),
                              always_xy=True)
    x, y = tr.transform(lon, lat)
    if 'bbox' not in cfg:
        if ficha and ficha.get('dsm_extension'):
            cfg['bbox'] = [float(v) for v in ficha['dsm_extension']]
            cfg['bbox_origen'] = 'ficha ML: dsm_extension'
        elif cfg.get('radio_m') is not None:
            r = float(cfg['radio_m'])
            cfg['bbox'] = [round(x - r, 2), round(y - r, 2),
                           round(x + r, 2), round(y + r, 2)]
            cfg['bbox_origen'] = 'centro ± radio_m'
        else:
            raise RuntimeError('Zona %s: sin bbox, sin dsm_extension y sin radio_m.'
                               % cfg.get('zona'))
    cfg.setdefault('origen_local', [round(x, 2), round(y, 2)])
    cfg.setdefault('eap', {'lon': lon, 'lat': lat})
    cfg['geometria_derivada'] = faltan   # trazabilidad: qué se ha calculado
    return cfg


def cargar_zona(zona, config_dir=None):
    """Lee config/zonas/<zona>.json (del repositorio), devuelve (config, Rutas).

    bbox, origen_local y eap pueden omitirse: se derivan en _derivar_geometria
    (ficha ML `zona_ml` o centro + radio_m).
    """
    if config_dir is None:
        config_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), 'config', 'zonas')
    ruta = os.path.join(config_dir, zona + '.json')
    if not os.path.exists(ruta):
        raise RuntimeError('No existe %s. Copia lavapies.json y edítalo.' % ruta)
    with open(ruta, 'r', encoding='utf-8') as fh:
        cfg = json.load(fh)
    cfg = _derivar_geometria(cfg, config_dir)
    cfg['bbox_contexto'] = [
        cfg['bbox'][0] - cfg['buffer_m'], cfg['bbox'][1] - cfg['buffer_m'],
        cfg['bbox'][2] + cfg['buffer_m'], cfg['bbox'][3] + cfg['buffer_m']]
    return cfg, Rutas(cfg['zona'])
