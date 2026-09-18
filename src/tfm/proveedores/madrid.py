# -*- coding: utf-8 -*-
"""
madrid.py — catalogue des sources pour Madrid.

Une ville = un module de ce dossier. Pour ajouter Barcelone, il faudra écrire
`barcelona.py` avec le même contrat : FUENTES + verificar() + descargar().
Les URLs proviennent du cuaderno Maqueta_Lavapies_v1.ipynb, vérifiées le 08/09/2026.

Codes de source du TFM : [MAD-01] Multipatch · [MAD-03] MDS 2023 ·
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


def fuentes(cfg, rutas):
    """Liste des fichiers d'entrée attendus, avec leur remède en cas d'absence."""
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
        {'clave': 'arbolado',
         'ruta': rutas.fuentes + '/Arbolado/arboles_%s_clean.csv' % cfg['zona'],
         'url': None, 'auto': False,
         'remedio': ('Inventario de arbolado preparado a mano. Dejar el CSV limpio '
                     'en `%s/Arbolado/arboles_%s_clean.csv` con columnas de '
                     'coordenadas y altura. Sin él, la capa arbolado se omite.'
                     % (rutas.fuentes, cfg['zona']))},
        {'clave': 'epw', 'ruta': rutas.fuentes + '/EPW/' + cfg['epw'],
         'url': None, 'auto': False,
         'remedio': ('Generar el EPW con `generar_epw_2023.py` (ERA5) y dejarlo en '
                     '`%s/EPW/`. Hace falta sólo para la simulación Ladybug, no '
                     'para la maqueta.' % rutas.fuentes)},
    ]
    for d in cfg.get('distritos', []):
        F.append({'clave': 'multipatch_' + d,
                  'ruta': rutas.modelo + '/' + d, 'carpeta': True,
                  'url': URL_MULTIPATCH % d, 'auto': True,
                  'remedio': ('Descargar %s y descomprimir en `%s`. Comprobar el '
                              'nombre exacto del distrito en el Geoportal. [MAD-01]'
                              % (URL_MULTIPATCH % d, rutas.modelo + '/' + d))})
    return F


def existe(f):
    """Un dossier compte comme présent s'il contient au moins un fichier."""
    if f.get('carpeta'):
        return os.path.isdir(f['ruta']) and bool(os.listdir(f['ruta']))
    return os.path.exists(f['ruta'])


def descargar(url, destino, timeout=1800):
    """Téléchargement en flux vers un .part, renommé à la fin.

    Une coupure laisse le .part : la fois suivante recommence au lieu de
    travailler sur un fichier tronqué.
    """
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    tmp = destino + '.part'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, 'wb') as fh:
        while True:
            trozo = r.read(1024 * 1024)
            if not trozo:
                break
            fh.write(trozo)
    os.replace(tmp, destino)
    return destino
