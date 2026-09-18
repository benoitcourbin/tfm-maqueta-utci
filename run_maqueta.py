# -*- coding: utf-8 -*-
"""
run_maqueta.py — point d'entrée unique de la chaîne.

    python run_maqueta.py --zona lavapies
    python run_maqueta.py --zona lavapies --pasos suelo
    python run_maqueta.py --zona lavapies --sin-descargas

La chaîne NE S'ARRETE PAS sur une erreur : chaque étape est enregistrée et le
rapport final dit ce qu'il reste à faire à la main, avec l'URL et le dossier
de destination. Les rapports vont tous dans `DOCS/INFORMES/`.
"""

import os
import sys
import argparse
import importlib
import runpy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from tfm.rutas import cargar_zona                     # noqa: E402
from tfm.estado import Ejecucion                      # noqa: E402
from tfm.pasos import capas_nb                        # noqa: E402

PASOS_CAPAS = ['topo', 'edificios', 'viario', 'arbolado', 'lod1']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--zona', required=True)
    ap.add_argument('--pasos', default='', help='lista separada por comas; vacío = todos')
    ap.add_argument('--sin-descargas', action='store_true',
                    help='no descarga nada, sólo comprueba lo que hay')
    ap.add_argument('--cuaderno', default=None,
                    help='ruta del .ipynb de las capas (por defecto, el del Drive)')
    args = ap.parse_args()

    cfg, rutas = cargar_zona(args.zona)
    prov = importlib.import_module('tfm.proveedores.' + cfg.get('proveedor', 'madrid'))
    ej = Ejecucion(cfg['zona'], rutas)
    solo = [p.strip() for p in args.pasos.split(',') if p.strip()]

    def activo(nombre):
        return (not solo) or (nombre in solo)

    print('Zona %s · raíz %s' % (cfg['zona'], rutas.raiz))

    # ------------------------------------------------------------ 1. fuentes
    for f in prov.fuentes(cfg, rutas):
        nombre = 'fuente:' + f['clave']

        def obtener(f=f):
            if prov.existe(f):
                return 'ya presente'
            if args.sin_descargas or not f.get('auto') or not f.get('url'):
                raise RuntimeError('falta y no se descarga automáticamente')
            destino = f['ruta'] if not f.get('carpeta') \
                else f['ruta'] + '/' + os.path.basename(f['url'])
            prov.descargar(f['url'], destino)
            if destino.endswith('.zip'):
                import zipfile
                with zipfile.ZipFile(destino) as z:
                    z.extractall(os.path.dirname(destino))
                os.remove(destino)
            return 'descargado'

        ej.paso(nombre, obtener, remedio=f['remedio'],
                omitir=not activo(nombre) and not activo('fuentes'))

    # -------------------------------------------------------------- 2. capas
    cuaderno = args.cuaderno or (rutas.modelo +
                                 '/Python/Notebooks/Maqueta_Lavapies_v1.ipynb')
    ns = {}
    capas_pedidas = [c for c in PASOS_CAPAS if c in cfg.get('capas', [])]
    if any(activo('capa:' + c) or activo('capas') for c in capas_pedidas):
        def preparar():
            ns.update(capas_nb.preparar(cuaderno, cfg, rutas))
            return True
        ej.paso('capas:preparar', preparar, remedio=(
            'No se ha podido cargar `%s`. Comprobar que el cuaderno está en el '
            'Drive y que su celda [3] sigue siendo la configuración global.'
            % cuaderno))

    for capa in capas_pedidas:
        nombre = 'capa:' + capa
        if not ns:
            break

        def correr(capa=capa):
            return capas_nb.ejecutar_capa(ns, capa)

        ej.paso(nombre, correr, omitir=not (activo(nombre) or activo('capas')),
                remedio=('Abrir `%s` en Colab, poner `CAPAS = [\'%s\']` en la celda '
                         '[3] y ejecutar sólo esa sección. El log de la celda dice '
                         'qué fuente falta.' % (cuaderno, capa)))

    # -------------------------------------------------------------- 3. suelo
    def correr_suelo():
        s = cfg.get('suelo', {})
        os.environ.update({
            'MAQUETA_DIR': rutas.maqueta, 'MAQUETA_OUT': rutas.maqueta,
            'TFM_ZONA': cfg['zona'],
            'TFM_INFORME_SUELO': rutas.informe('informe_suelo_%s.md'),
            'TFM_SUELO_BBOX_CONTEXTO': repr(tuple(cfg['bbox_contexto'])),
            'TFM_SUELO_BBOX_ANALISIS': repr(tuple(cfg['bbox'])),
            'TFM_SUELO_UMBRAL_MDT': repr(s.get('umbral_mdt_m', 5.0)),
            'TFM_SUELO_VENTANA_MDT': repr(s.get('ventana_mdt_m', 21)),
            'TFM_SUELO_SIMPLIFICAR': repr(s.get('simplificar_m', 0.25)),
            'TFM_SUELO_PASO_INT': repr(s.get('paso_interior_m', 10.0)),
            'TFM_SUELO_H_BORD': repr(s.get('h_bordillo_m', 0.15)),
            'TFM_SUELO_CELDA': repr(s.get('celda_m', 50.0)),
        })
        runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    'src', 'tfm', 'pasos', 'suelo.py'),
                       run_name='__main__')
        return True

    ej.paso('suelo', correr_suelo, salidas=[rutas.suelo, rutas.mdt_limpio],
            omitir=not activo('suelo'), remedio=(
        'El suelo necesita tres ficheros de la etapa anterior: `%s`, `%s` y `%s`. '
        'Si falta `triangle`, instalarlo (`pip install triangle`). '
        'Se puede lanzar suelto: `python src/tfm/pasos/suelo.py` con MAQUETA_DIR '
        'apuntando a la carpeta de la zona.'
        % (os.path.basename(rutas.mdt), os.path.basename(rutas.viario_gj),
           os.path.basename(rutas.huellas))))

    # ------------------------------------------------- 4. manifiesto + informe
    ej.paso('manifiesto', lambda: ej.manifiesto(cfg), salidas=[rutas.manifiesto],
            remedio='Sin manifiesto, Grasshopper no encuentra los ficheros.')
    ruta_inf = ej.informe(cfg)
    print('\nInforme : %s' % ruta_inf)
    print('Pasos con fallo : %d' % len(ej.fallos))
    return 0 if not ej.fallos else 1


if __name__ == '__main__':
    sys.exit(main())
