# -*- coding: utf-8 -*-
"""
arbolado.py — inventario municipal de arbolado → FUENTES/Arbolado/arboles_<zona>_clean.csv

Origen [MAD-12]: datos.madrid.es, conjunto 300761-0 «Arbolado en parques y zonas
verdes de Madrid (detalle)». `proveedores/madrid.py` lo descarga UNA VEZ, para toda
la ciudad, en `FUENTES/Arbolado/raw/`.

Pasos (los del cuaderno «Arbolado Lavapiés — Parser BBox + Exportación GeoJSON»,
02/06/2026, pasados a módulo):
  1. leer el bruto (CSV , ; o tabulador · decimal con coma);
  2. recortar a bbox_contexto con X/Y en EPSG:25830;
  3. conservar solo las columnas necesarias y calcular:
       diametro_tronco_cm = PERIMETRO / π
       altura_total_m     = ALTURA_TOTAL
       forma_copa, h_inicio_follaje_m = altura × ratio   ← tabla por especie
       longitud, latitud  (pyproj)
  4. escribir el CSV que lee la capa `arbolado` del cuaderno de la maqueta.

La tabla por especie (`config/especies_arbolado.json`) es una HIPÓTESIS de
modelización: forma de copa y ratio de inicio de follaje no vienen del inventario.

Reglas:
  - Solo lee `raw/`: nunca vuelve a leer sus propias salidas.
  - No reescribe un `_clean.csv` válido salvo `forzar=True`.
  - Si falta una columna del bruto, se detiene con la lista de columnas leídas.
"""

import os
import glob
import json
import math

# Columnas del bruto, verificadas en 300761-0-arbolado-especies (2025).
# Se buscan sin distinguir mayúsculas.
BRUTO = {'x': 'X', 'y': 'Y', 'altura': 'ALTURA_TOTAL', 'perimetro': 'PERIMETRO',
         'especie': 'CODIGO_ESPECIE', 'barrio': 'NBRE_BARRIO'}
OPCIONALES = ('barrio',)

# Lo que escribe este paso, en este orden (cabecera del inventario del 18/09).
COLS_SALIDA = ['CODIGO_ESPECIE', 'nombre_especie', 'forma_copa', 'diametro_tronco_cm',
               'altura_total_m', 'h_inicio_follaje_m', 'X', 'Y', 'longitud', 'latitud',
               'NBRE_BARRIO']
# Lo que la capa `arbolado` del cuaderno exige.
COLS_MINIMAS = ('altura_total_m', 'h_inicio_follaje_m', 'forma_copa')


def _tabla_especies():
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))), 'config', 'especies_arbolado.json')
    with open(ruta, encoding='utf-8') as f:
        return json.load(f)


def _separador(ruta, codif):
    with open(ruta, encoding=codif, errors='strict') as f:
        cab = f.readline()
    return max((';', ',', '\t'), key=cab.count)


def _leer_bruto(ruta):
    """Lee solo las columnas necesarias del inventario de la ciudad."""
    import pandas as pd
    ultimo = None
    for codif in ('utf-8-sig', 'latin-1'):
        try:
            sep = _separador(ruta, codif)
            cab = pd.read_csv(ruta, sep=sep, nrows=0, encoding=codif).columns
        except (UnicodeDecodeError, pd.errors.ParserError) as e:
            ultimo = e
            continue
        mapa = {c.strip().lower(): c for c in cab}
        cols, faltan = {}, []
        for clave, nombre in BRUTO.items():
            real = mapa.get(nombre.lower())
            if real is None and clave not in OPCIONALES:
                faltan.append(nombre)
            elif real is not None:
                cols[clave] = real
        if faltan:
            raise RuntimeError(
                '%s: faltan las columnas %s. Columnas leídas: %s'
                % (os.path.basename(ruta), faltan, list(cab)[:25]))
        df = pd.read_csv(ruta, sep=sep, encoding=codif, dtype=str,
                         usecols=list(cols.values()), low_memory=False)
        return df.rename(columns={v: k for k, v in cols.items()})
    raise RuntimeError('no se puede leer %s (%s)' % (os.path.basename(ruta), ultimo))


def _num(serie):
    """Texto con decimal español (coma) → float; lo ilegible queda en NaN."""
    import pandas as pd
    return pd.to_numeric(serie.str.strip().str.replace(',', '.', regex=False),
                         errors='coerce')


def _valido(ruta):
    """¿El _clean.csv existente tiene lo que la capa exige?"""
    import pandas as pd
    try:
        cols = pd.read_csv(ruta, nrows=0).columns
    except Exception:
        return False
    return all(c in cols for c in COLS_MINIMAS)


def elegir_bruto(cfg, rutas):
    """Fichero bruto a usar: el de cfg['arbolado_bruto'] si está, si no el más reciente."""
    carpeta = rutas.fuentes + '/Arbolado/raw'
    brutos = [f for f in glob.glob(carpeta + '/*.csv') if not f.endswith('.part')]
    if not brutos:
        raise RuntimeError('no hay inventario en %s' % carpeta)
    pref = cfg.get('arbolado_bruto')
    for f in brutos:
        if pref and os.path.basename(f) == pref:
            return f
    return max(brutos, key=os.path.getmtime)


def recortar(cfg, rutas, forzar=False, log=print):
    """Escribe arboles_<zona>_clean.csv desde el inventario bruto de la ciudad."""
    import numpy as np
    from pyproj import Transformer

    destino = rutas.fuentes + '/Arbolado/arboles_%s_clean.csv' % cfg['zona']
    if os.path.isfile(destino) and _valido(destino) and not forzar:
        log('   %s ya existe y es válido: no se reescribe (forzar=True para '
            'regenerarlo)' % os.path.basename(destino))
        return destino

    bruto = elegir_bruto(cfg, rutas)
    df = _leer_bruto(bruto)
    x, y = _num(df['x']), _num(df['y'])
    x0, y0, x1, y1 = cfg['bbox_contexto']
    dentro = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
    n = int(dentro.sum())
    log('   %s: %d árboles en la ciudad | %d en la bbox de contexto'
        % (os.path.basename(bruto), len(df), n))
    if n == 0:
        raise RuntimeError('ningún árbol de %s en la bbox de %s'
                           % (os.path.basename(bruto), cfg['zona']))

    d = df[dentro].copy()
    d['X'], d['Y'] = x[dentro].values, y[dentro].values
    tabla = _tabla_especies()
    esp, defecto = tabla['especies'], tabla['_por_defecto']
    cod = d['especie'].fillna('').str.strip()
    fila = [esp.get(c, defecto) for c in cod]
    sin_tabla = int(sum(1 for c in cod if c not in esp))

    altura = _num(d['altura'])
    ratio = np.array([f['ratio_follaje'] for f in fila], dtype=float)
    sal = {
        'CODIGO_ESPECIE': cod.values,
        'nombre_especie': [f['nombre'] for f in fila],
        'forma_copa': [f['forma_copa'] for f in fila],
        'diametro_tronco_cm': (_num(d['perimetro']) / math.pi).round(1).values,
        'altura_total_m': altura.round(1).values,
        'h_inicio_follaje_m': (altura.round(1) * ratio).round(1).values,
        'X': d['X'].values,
        'Y': d['Y'].values,
    }
    tr = Transformer.from_crs(cfg.get('crs', 'EPSG:25830'), 'EPSG:4326', always_xy=True)
    lon, lat = tr.transform(d['X'].values, d['Y'].values)
    sal['longitud'], sal['latitud'] = np.round(lon, 7), np.round(lat, 7)
    sal['NBRE_BARRIO'] = d['barrio'].values if 'barrio' in d else None

    import pandas as pd
    out = pd.DataFrame(sal)[COLS_SALIDA]
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    out.to_csv(destino, index=False, encoding='utf-8')
    log('   -> %s (%d árboles; %d con especie fuera de la tabla → «%s» por defecto)'
        % (os.path.basename(destino), len(out), sin_tabla, defecto['forma_copa']))
    return destino
