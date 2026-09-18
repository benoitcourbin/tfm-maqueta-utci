# -*- coding: utf-8 -*-
"""
arbolado.py — découpe l'inventaire municipal d'arbolado à la bbox de la zone.

L'inventaire se télécharge UNE FOIS pour toute la ville, dans
`FUENTES/Arbolado/`. Cette étape en extrait les arbres de la zone et écrit
`FUENTES/Arbolado/arboles_<zona>_clean.csv`, qui est ce que la capa `arbolado`
du cuaderno attend. Plus de fichier préparé à la main par quartier.

Formats acceptés : CSV (séparateur , ou ;) et GeoJSON.
Coordonnées : colonnes X/Y en EPSG:25830, ou longitud/latitud en degrés, ou la
géométrie du GeoJSON.
"""

import os
import glob

COLS_X = ('x', 'coord_x', 'utm_x', 'este', 'x_utm', 'coordenada_x')
COLS_Y = ('y', 'coord_y', 'utm_y', 'norte', 'y_utm', 'coordenada_y')
COLS_LON = ('longitud', 'lon', 'lng', 'long', 'longitude')
COLS_LAT = ('latitud', 'lat', 'latitude')
# Ce que la capa `arbolado` du cuaderno lit ensuite.
COLS_MINIMAS = ('altura_total_m', 'h_inicio_follaje_m', 'forma_copa')


def _columna(df, candidatas):
    baja = {c.lower(): c for c in df.columns}
    for c in candidatas:
        if c in baja:
            return baja[c]
    return None


def _cargar(ruta):
    import pandas as pd
    if ruta.lower().endswith(('.geojson', '.json')):
        import geopandas as gpd
        g = gpd.read_file(ruta)
        if g.crs is not None and g.crs.to_epsg() != 25830:
            g = g.to_crs(epsg=25830)
        df = pd.DataFrame(g.drop(columns='geometry'))
        df['X'] = g.geometry.x.values
        df['Y'] = g.geometry.y.values
        return df
    for sep in (',', ';'):
        try:
            df = pd.read_csv(ruta, sep=sep, low_memory=False)
            if df.shape[1] > 1:
                return df
        except Exception:
            continue
    raise RuntimeError('no se puede leer %s' % os.path.basename(ruta))


def _xy(df):
    """Retourne (serie_x, serie_y) en EPSG:25830, ou lève."""
    cx, cy = _columna(df, COLS_X), _columna(df, COLS_Y)
    if cx and cy:
        import pandas as pd
        x = pd.to_numeric(df[cx], errors='coerce')
        y = pd.to_numeric(df[cy], errors='coerce')
        # Des degrés dans une colonne nommée X : on ne se fie pas au nom.
        if x.abs().max() <= 180 and y.abs().max() <= 90:
            cx = cy = None
        else:
            return x, y
    clon, clat = _columna(df, COLS_LON), _columna(df, COLS_LAT)
    if clon and clat:
        import pandas as pd
        from pyproj import Transformer
        tr = Transformer.from_crs('EPSG:4326', 'EPSG:25830', always_xy=True)
        lon = pd.to_numeric(df[clon], errors='coerce')
        lat = pd.to_numeric(df[clat], errors='coerce')
        x, y = tr.transform(lon.values, lat.values)
        return pd.Series(x, index=df.index), pd.Series(y, index=df.index)
    raise RuntimeError('sin columnas de coordenadas reconocibles : %s'
                       % list(df.columns)[:15])


def recortar(cfg, rutas, log=print):
    """Écrit arboles_<zona>_clean.csv à partir de l'inventaire de la ville."""
    zona = cfg['zona']
    carpeta = rutas.fuentes + '/Arbolado'
    destino = carpeta + '/arboles_%s_clean.csv' % zona

    candidatos = [f for f in glob.glob(carpeta + '/*')
                  if f.lower().endswith(('.csv', '.geojson', '.json'))
                  and os.path.basename(f) != os.path.basename(destino)]
    if not candidatos:
        raise RuntimeError('no hay ningún inventario en %s' % carpeta)
    # Le plus gros fichier est celui de la ville ; les découpes sont plus petites.
    candidatos.sort(key=os.path.getsize, reverse=True)

    x0, y0, x1, y1 = cfg['bbox_contexto']
    ultimo = None
    for ruta in candidatos:
        try:
            df = _cargar(ruta)
            x, y = _xy(df)
        except Exception as ex:
            ultimo = '%s : %s' % (os.path.basename(ruta), ex)
            continue
        dentro = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
        n = int(dentro.sum())
        log('   %-40s %7d registros | %5d en la bbox'
            % (os.path.basename(ruta), len(df), n))
        if n == 0:
            ultimo = '%s : ningún árbol en la bbox' % os.path.basename(ruta)
            continue
        fuera = [c for c in COLS_MINIMAS if _columna(df, (c,)) is None]
        if fuera:
            log('   ⚠️ faltan columnas %s : la capa arbolado usará sus valores '
                'por defecto' % ', '.join(fuera))
        sal = df[dentro.values].copy()
        sal['X'] = x[dentro.values].values
        sal['Y'] = y[dentro.values].values
        sal.to_csv(destino, index=False)
        log('   -> %s (%d árboles, origen %s)'
            % (os.path.basename(destino), n, os.path.basename(ruta)))
        return destino
    raise RuntimeError('ningún inventario utilizable (%s)' % ultimo)
