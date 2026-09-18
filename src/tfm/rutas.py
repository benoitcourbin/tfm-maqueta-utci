# -*- coding: utf-8 -*-
"""
rutas.py — arborescence unique du projet, construite à partir du nom de zone.

Aucun chemin n'est écrit en dur ailleurs dans la chaîne. Un seul endroit à
changer si l'arborescence du Drive bouge.

RACINE :
  Colab  -> /content/drive/MyDrive/TFM_UTCI_Lavapies_2026
  Windows-> G:\\Mi unidad\\TFM_UTCI_Lavapies_2026
  ou variable d'environnement TFM_RAIZ (tests locaux).
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
    """Racine du projet sur le Drive."""
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
    """Tous les chemins d'une zone. Crée les dossiers manquants."""

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

    # --- fichiers de la maquette -------------------------------------------
    def m(self, nombre):
        """Fichier de la maquette : m('suelo_%s_mesh.json')."""
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
        """Tous les rapports vont dans DOCS/INFORMES."""
        return self.informes + '/' + (nombre % self.zona if '%s' in nombre else nombre)

    def run_ladybug(self, version):
        d = self.ladybug + '/' + version
        os.makedirs(d, exist_ok=True)
        return d


def cargar_zona(zona, config_dir=None):
    """Lit config/zonas/<zona>.json (du dépôt), retourne (config, Rutas)."""
    if config_dir is None:
        config_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), 'config', 'zonas')
    ruta = os.path.join(config_dir, zona + '.json')
    if not os.path.exists(ruta):
        raise RuntimeError('No existe %s. Copia lavapies.json y edítalo.' % ruta)
    with open(ruta, 'r', encoding='utf-8') as fh:
        cfg = json.load(fh)
    cfg['bbox_contexto'] = [
        cfg['bbox'][0] - cfg['buffer_m'], cfg['bbox'][1] - cfg['buffer_m'],
        cfg['bbox'][2] + cfg['buffer_m'], cfg['bbox'][3] + cfg['buffer_m']]
    return cfg, Rutas(cfg['zona'])
