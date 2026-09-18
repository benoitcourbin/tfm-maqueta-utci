# -*- coding: utf-8 -*-
"""
capas_nb.py — exécute les sections du cuaderno `Maqueta_Lavapies_v1.ipynb`
depuis un script, une capa à la fois, avec la configuration de la zone.

POURQUOI PASSER PAR LE CUADERNO
Le code des cinq capas est vérifié et a produit la maquette actuelle. Le
réécrire en modules serait un second chantier, avec son lot de régressions.
On l'exécute donc tel quel, en remplaçant seulement sa cellule de configuration.
La migration capa par capa vers `pasos/<capa>.py` peut se faire ensuite, sans
casser la chaîne.

Chaque capa est exécutée dans le MEME espace de noms : la capa `viario` a besoin
du MDT écrit par `topo`, et `lod1` des emprises écrites par `edificios`.
"""

import os
import json

CELDA_CONFIG = 3          # [3] configuración global
CELDA_UTILES = 4          # [4] utilidades comunes
MARCA = "if '%s' in CAPAS:"


def _celdas(ruta_nb):
    with open(ruta_nb, 'r', encoding='utf-8') as fh:
        nb = json.load(fh)
    return [''.join(c['source']) for c in nb['cells'] if c['cell_type'] == 'code']


def preparar(ruta_nb, cfg, rutas):
    """Retourne l'espace de noms du cuaderno, configuré pour cette zone."""
    celdas = _celdas(ruta_nb)
    ns = {'__name__': '__main__'}
    exec(compile(celdas[CELDA_CONFIG], '<celda_3>', 'exec'), ns)
    # La configuration de la zone écrase celle du cuaderno.
    ns.update({
        'NOMBRE_ZONA': cfg['zona'],
        'BBOX': tuple(cfg['bbox']),
        'BUFFER_M': cfg['buffer_m'],
        'ORIGEN_LOCAL': tuple(cfg['origen_local']),
        'Z_MODE': cfg.get('z_mode', 'absolute'),
        'Z_LOCAL_REF': cfg.get('z_local_ref'),
        'TRANSLADAR_XY': cfg.get('trasladar_xy', False),
        'CRS': cfg.get('crs', 'EPSG:25830'),
        'DRIVE': rutas.modelo,
        'DIR_FUENTES': rutas.fuentes,
        'OUT_DIR': rutas.maqueta,
        'CAPAS': list(cfg.get('capas', [])),
        'DISTRITOS': list(cfg.get('distritos', [])),
        'COD_MUNICIPIO': cfg.get('cod_municipio', '28900'),
    })
    os.makedirs(rutas.maqueta, exist_ok=True)
    exec(compile(celdas[CELDA_UTILES], '<celda_4>', 'exec'), ns)
    ns['_celdas'] = celdas
    return ns


def ejecutar_capa(ns, capa):
    """Exécute toutes les cellules de la section `capa`.

    Les cellules d'une section commencent par `if '<capa>' in CAPAS:`. On force
    CAPAS à cette seule capa pour que les autres sections restent inertes.
    """
    ns['CAPAS'] = [capa]
    marca = MARCA % capa
    n = 0
    for i, src in enumerate(ns['_celdas']):
        if src.lstrip().startswith(marca):
            exec(compile(src, '<capa_%s_celda_%d>' % (capa, i), 'exec'), ns)
            n += 1
    if n == 0:
        raise RuntimeError('ninguna celda para la capa %s en el cuaderno' % capa)
    return n
