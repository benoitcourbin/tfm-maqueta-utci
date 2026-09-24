# -*- coding: utf-8 -*-
"""
capas_nb.py — ejecuta las secciones del cuaderno `Maqueta_Lavapies_v1.ipynb`
desde un script, una capa cada vez, con la configuración de la zona.

POR QUÉ PASAR POR EL CUADERNO
El código de las cinco capas está verificado y ha producido la maqueta actual.
Reescribirlo en módulos sería una segunda obra, con su lote de regresiones.
Por eso se ejecuta tal cual, sustituyendo sólo su celda de configuración.
La migración capa a capa hacia `pasos/<capa>.py` puede hacerse después, sin
romper la cadena.

Cada capa se ejecuta en el MISMO espacio de nombres: la capa `viario` necesita
el MDT escrito por `topo`, y `lod1` las huellas escritas por `edificios`.
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


def _distritos(cfg):
    """Nombres de carpetas Multipatch: los del JSON, si no, los detectados."""
    if cfg.get('distritos'):
        return list(cfg['distritos'])
    return ['%s.%s_3D' % (c, n.upper().replace(' ', '_'))
            for c, n in (cfg.get('distritos_detectados') or [])]


def preparar(ruta_nb, cfg, rutas):
    """Devuelve el espacio de nombres del cuaderno, configurado para esta zona."""
    celdas = _celdas(ruta_nb)
    ns = {'__name__': '__main__'}
    exec(compile(celdas[CELDA_CONFIG], '<celda_3>', 'exec'), ns)
    # La configuración de la zona sobrescribe la del cuaderno.
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
        'DISTRITOS': _distritos(cfg),
        'COD_MUNICIPIO': cfg.get('cod_municipio', '28900'),
    })
    os.makedirs(rutas.maqueta, exist_ok=True)
    exec(compile(celdas[CELDA_UTILES], '<celda_4>', 'exec'), ns)
    ns['_celdas'] = celdas
    return ns


def ejecutar_capa(ns, capa):
    """Ejecuta todas las celdas de la sección `capa`.

    Las celdas de una sección empiezan por `if '<capa>' in CAPAS:`. Se fuerza
    CAPAS a esa única capa para que las demás secciones queden inertes.
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
