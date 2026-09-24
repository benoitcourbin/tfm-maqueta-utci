# -*- coding: utf-8 -*-
"""
madrid.py — catálogo de las fuentes para Madrid.

Una ciudad = un módulo de esta carpeta. Para añadir Barcelona, habrá que
escribir `barcelona.py` con el mismo contrato : FUENTES + verificar() +
descargar().
Las URL proceden del cuaderno Maqueta_Lavapies_v1.ipynb, verificadas el 08/09/2026.

Códigos de fuente del TFM : [MAD-01] Multipatch · [MAD-03] MDS 2023 ·
[MAD-07] T03 Viario · [MAD-10] MDT · [CAT-03] Catastro INSPIRE ATOM.
"""

import os
import urllib.request

GEOPORTAL = 'https://geoportal.madrid.es/fsdescargas/IDEAM_WBGEOPORTAL/'
CARTO = GEOPORTAL + 'CARTOGRAFIA/CARTOGRAFIA_ACTUALIZADA/'

URL_MULTIPATCH = CARTO + '3D_EDIFICACIONES_CONSTRUCCIONES/MULTIPATCH/%s.zip'
URL_T03 = CARTO + 'CM1000_SHAPE_TEMAS/T03_VIARIO.zip'
URL_MDS = GEOPORTAL + 'ELEVACIONES/2023/MDS/MOSAICO/MDS2023_1m.zip'
URL_MDT_MOSAICO = GEOPORTAL + 'ELEVACIONES/2019/MDT/MOSAICO/MDT2019_COG.zip'
WCS_MDT = ['https://servpub.madrid.es/georaster/ELEVACIONES/MDT2023_COG/ows',
           'https://servpub.madrid.es/georaster/ELEVACIONES/MDT2019_COG/ows']
URL_CATASTRO = ('https://www.catastro.hacienda.gob.es/INSPIRE/buildings/%s/'
                '%s-MADRID/A.ES.SDGC.BU.%s.zip')
# Limites administrativos : sirven para deducir los distritos a partir de la
# bbox, de modo que configurar una zona se reduzca a EAP + bbox. EPSG:25830.
URL_DISTRITOS = GEOPORTAL + 'LIMITES_ADMINISTRATIVOS/Distritos/Distritos.zip'
# Ficha del conjunto de datos, para el remedio si falla la descarga :
# https://geoportal.madrid.es/IDEAM_WBGEOPORTAL/dataset.iam?id=541f4ef6-762b-11e9-861d-ecb1d753f6e8


def fuentes(cfg, rutas):
    """Lista de los ficheros de entrada esperados, con su remedio si faltan."""
    cod = cfg.get('cod_municipio', '28900')
    F = [
        {'clave': 'mdt', 'ruta': rutas.fuentes + '/MDT/mdt_%s.tif' % cfg['zona'],
         'url': URL_MDT_MOSAICO, 'auto': True,
         'remedio': ('El WCS de Madrid falla a menudo (404). Descargar el mosaico '
                     '%s, descomprimirlo y dejar el .tif en `%s/MDT/`. '
                     'El recorte por bbox lo hace la cadena. [MAD-10]'
                     % (URL_MDT_MOSAICO, rutas.fuentes))},
        {'clave': 'mds', 'ruta': rutas.fuentes + '/MDS', 'carpeta': True,
         'url': URL_MDS, 'auto': True,
         'remedio': ('Mosaico de 1,53 GB. Descargar %s, descomprimir y dejar el '
                     'COG (.tif) en `%s/MDS/`. Sólo hace falta para el CHM del '
                     'arbolado (METODO_COPA = "chm"); con "alometria" se puede '
                     'seguir sin él. [MAD-03]' % (URL_MDS, rutas.fuentes))},
        {'clave': 'viario_t03',
         'ruta': rutas.fuentes + '/Madrid_Viario/Viario_T03', 'carpeta': True,
         'url': URL_T03, 'auto': True,
         'remedio': ('Descargar %s y descomprimir en `%s/Madrid_Viario/Viario_T03/`. '
                     'Deben aparecer 03_ACERA_P.shp, 03_VADO_P.shp, 03_ISLETA_P.shp '
                     'y 03_ADOQUINADO_L.shp. [MAD-07]' % (URL_T03, rutas.fuentes))},
        {'clave': 'catastro',
         'ruta': rutas.fuentes + '/Catastro/Catastro_INSPIRE', 'carpeta': True,
         'url': URL_CATASTRO % (cod[:2], cod, cod), 'auto': True,
         'remedio': ('Descargar %s y descomprimir en `%s/Catastro/Catastro_INSPIRE/`. '
                     'Aporta año de construcción y uso; sin él la maqueta se genera '
                     'igual, con esos atributos vacíos. [CAT-03]'
                     % (URL_CATASTRO % (cod[:2], cod, cod), rutas.fuentes))},
        {'clave': 'distritos', 'ruta': rutas.fuentes + '/Limites/Distritos',
         'carpeta': True, 'url': URL_DISTRITOS, 'auto': True,
         'remedio': ('Descargar %s y descomprimir en `%s/Limites/Distritos/`. '
                     'Sirve para deducir de la bbox qué distritos hay que bajar; '
                     'sin él hay que escribir "distritos" a mano en el JSON de la '
                     'zona. Ficha: geoportal.madrid.es, «Distritos municipales de '
                     'Madrid». [MAD-11]' % (URL_DISTRITOS, rutas.fuentes))},
        {'clave': 'arbolado', 'ruta': rutas.fuentes + '/Arbolado',
         'carpeta': True, 'url': None, 'auto': False,
         'remedio': ('Inventario municipal de arbolado, DE TODA LA CIUDAD, en '
                     '`%s/Arbolado/` (CSV o GeoJSON). La cadena lo recorta a la '
                     'bbox de cada zona: se descarga una sola vez. Origen: portal '
                     'de datos abiertos del Ayuntamiento (datos.madrid.es), '
                     'conjunto de arbolado. Columnas necesarias: coordenadas '
                     '(X/Y en EPSG:25830 o longitud/latitud), altura_total_m, '
                     'h_inicio_follaje_m, forma_copa. Sin él, la capa arbolado '
                     'se omite.' % rutas.fuentes)},
        # Un EPW sirve para toda la ciudad : basta con que haya UNO en la carpeta.
        # `cfg['epw']` es sólo una preferencia, no una obligación.
        # Se busca en todo FUENTES : el ERA5 del TFM está en la raíz, los TMYx
        # en EPW/. Da igual dónde esté, mientras haya uno.
        {'clave': 'epw', 'ruta': rutas.fuentes, 'carpeta': True,
         'patron': '*.epw', 'url': None, 'auto': False,
         'remedio': ('Dejar un fichero .epw en `%s/EPW/` (subcarpetas incluidas). '
                     'Dos vías: (a) TMYx de la estación más cercana, descargable '
                     'sin cuenta desde climate.onebuilding.org [LB-04] — año tipo, '
                     'no un año concreto; (b) ERA5 del año estudiado con '
                     '`generar_epw_2023.py`, que necesita una clave gratuita del '
                     'Copernicus CDS. Para comparar con SOLWEIG hace falta la vía '
                     '(b): SOLWEIG corre sobre ERA5. Sólo afecta a la simulación, '
                     'no a la maqueta.' % rutas.fuentes)},
    ]
    for d in cfg.get('distritos') or []:
        F.append({'clave': 'multipatch_' + d,
                  'ruta': rutas.modelo + '/' + d, 'carpeta': True,
                  'url': URL_MULTIPATCH % d, 'auto': True,
                  'remedio': ('Descargar %s y descomprimir en `%s`. Comprobar el '
                              'nombre exacto del distrito en el Geoportal. [MAD-01]'
                              % (URL_MULTIPATCH % d, rutas.modelo + '/' + d))})
    return F


def existe(f):
    """Presencia de una fuente.

    `patron` : basta con que exista un fichero correspondiente en cualquier
    punto de la carpeta — un EPW vale para toda la ciudad, sea cual sea su nombre.
    """
    if f.get('patron'):
        import glob
        return bool(glob.glob(f['ruta'] + '/**/' + f['patron'], recursive=True))
    if f.get('carpeta'):
        return os.path.isdir(f['ruta']) and bool(os.listdir(f['ruta']))
    return os.path.exists(f['ruta'])


def epw_de(cfg, rutas):
    """Ruta del EPW a usar : el del JSON si está, si no el primero."""
    import glob
    encontrados = sorted(glob.glob(rutas.fuentes + '/**/*.epw', recursive=True))
    if not encontrados:
        return None
    pref = cfg.get('epw')
    for e in encontrados:
        if pref and os.path.basename(e) == pref:
            return e
    return encontrados[0]


def descargar(url, destino, timeout=1800, esperado=None):
    """Descarga en flujo hacia un .part, renombrado al final.

    Un corte deja el .part : la vez siguiente se vuelve a empezar en lugar de
    trabajar sobre un fichero truncado.

    `esperado` : 'zip' verifica la firma del fichero. Sin ese control, una
    página de error HTML devuelta con un 200 se guarda como si fuera el
    archivo pedido (constatado el 18/09 con los Multipatch).
    """
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    tmp = destino + '.part'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, 'wb') as fh:
        tipo = (r.headers.get('Content-Type') or '').lower()
        while True:
            trozo = r.read(1024 * 1024)
            if not trozo:
                break
            fh.write(trozo)
    if esperado == 'zip':
        with open(tmp, 'rb') as fh:
            firma = fh.read(4)
        tam = os.path.getsize(tmp)
        if firma[:2] != b'PK' or tam < 10000:
            os.remove(tmp)
            raise RuntimeError('la respuesta no es un ZIP (%d bytes, %s)'
                               % (tam, tipo or 'sin content-type'))
    os.replace(tmp, destino)
    return destino


# --------------------------------------------------------------- distritos
def _sin_acentos(t):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', t)
                   if unicodedata.category(c) != 'Mn')


def candidatos_multipatch(codigo, nombre):
    """Grafías posibles del nombre de fichero Multipatch de un distrito.

    Observado en el Drive : `01.CENTRO_3D`, `02.ARGANZUELA_3D`. El Geoportal
    no expone ninguna regla : se prueba, y lo que falla va al informe.
    """
    n = _sin_acentos(nombre).strip().replace(' ', '_')
    salida = []
    for forma in (n.upper(), n.title(), n):
        for patron in ('%s.%s_3D', '%s.%s'):
            v = patron % (codigo, forma)
            if v not in salida:
                salida.append(v)
    return salida


def distritos_en_bbox(bbox, rutas):
    """Distritos cuya geometría toca la bbox (EPSG:25830).

    Devuelve [(codigo, nombre)]. Exige la capa Distritos ya descargada.
    """
    import glob
    import geopandas as gpd
    from shapely.geometry import box as _box

    carpeta = rutas.fuentes + '/Limites/Distritos'
    shps = glob.glob(carpeta + '/**/*.shp', recursive=True)
    if not shps:
        raise RuntimeError('falta la capa de distritos en %s' % carpeta)
    gdf = gpd.read_file(shps[0])
    if gdf.crs is not None and gdf.crs.to_epsg() != 25830:
        gdf = gdf.to_crs(epsg=25830)
    marco = _box(*bbox)
    sel = gdf[gdf.intersects(marco)]
    # Los nombres de columna varían según la edición de la capa.
    col_cod = next((c for c in gdf.columns
                    if c.upper() in ('CODDISTRIT', 'COD_DIS', 'CODIGO', 'NUMERO',
                                     'COD_DISTRI', 'DISTRITO')), None)
    col_nom = next((c for c in gdf.columns
                    if c.upper() in ('NOMBRE', 'NOMDIS', 'NOMBRE_DIS', 'DESBDT',
                                     'NOMDISTRIT')), None)
    if col_nom is None:
        raise RuntimeError('no encuentro la columna de nombre en %s : %s'
                           % (os.path.basename(shps[0]), list(gdf.columns)))
    salida = []
    for _, fila in sel.iterrows():
        nombre = str(fila[col_nom])
        cod = str(fila[col_cod]).strip() if col_cod else ''
        cod = ('%02d' % int(float(cod))) if cod.replace('.', '').isdigit() else cod
        salida.append((cod, nombre))
    return sorted(salida)


def descargar_multipatch(codigo, nombre, destino):
    """Prueba las grafías hasta que una responda CON un ZIP de verdad.

    Control de salida : tiene que haber un .shp tras la extracción. Si no, se
    limpia y se lanza el error, en vez de dejar creer que el distrito está.
    """
    import glob
    import zipfile
    intentos = []
    for cand in candidatos_multipatch(codigo, nombre):
        zip_tmp = destino + '/_%s.zip' % cand
        try:
            os.makedirs(destino, exist_ok=True)
            descargar(URL_MULTIPATCH % cand, zip_tmp, esperado='zip')
            with zipfile.ZipFile(zip_tmp) as z:
                z.extractall(destino)
            os.remove(zip_tmp)
            if not glob.glob(destino + '/**/*.shp', recursive=True):
                intentos.append('%s : ZIP sin .shp' % cand)
                continue
            return cand
        except Exception as ex:
            intentos.append('%s : %s' % (cand, ex))
            if os.path.exists(zip_tmp):
                os.remove(zip_tmp)
    raise RuntimeError('ninguna grafia responde con un Multipatch valido | '
                       + ' | '.join(intentos))
