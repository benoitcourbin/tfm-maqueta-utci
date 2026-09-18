# -*- coding: utf-8 -*-
"""
exportar_resultados.py — Ladybug -> Drive, format original + CSV.

    python exportar_resultados.py --zona lavapies --sim "C:/Users/benoi/Documents/M10_TFM_Local/simulation_v5" --version v5

Copie dans `01_DATOS/LADYBUG_SIM/<zona>/<version>/` uniquement ce dont la
comparaison avec SOLWEIG a besoin :

  ORIGINAL   grids_info.json · __inputs__.json · results/temperature/*.npy (MRT)
             et results/condition_intensity/ si présent
  CSV        LB_MRT.csv · LB_UTCI.csv · LB_orden_grids.csv · LB_metadata.json

PIEGES REPRIS DE §7 DE L'ESTADO
  §7.4  MRT et UTCI ne sont pas écrits dans le même ordre de capteurs.
        L'ordre vient de `grids_info.json`, jamais d'une concaténation naïve.
  §7.5  Les fichiers de `initial_results/conditions/` ont une extension .csv
        mais sont des binaires NumPy : toujours essayer np.load() d'abord.
  §7.7  `carpeta_sim` pointe sur `…/simulation_vN/utci_comfort_map`.
"""

import os
import sys
import json
import time
import shutil
import argparse

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))
from tfm.rutas import cargar_zona                     # noqa: E402

SUB = ('results/temperature', 'results/condition_intensity')


def leer_npy(ruta):
    """Les .csv de Ladybug sont parfois des binaires NumPy (§7.5)."""
    try:
        return np.load(ruta)
    except Exception:
        return np.loadtxt(ruta, delimiter=',')


def exportar(sim, destino, zona):
    base = sim if sim.rstrip('/\\').endswith('utci_comfort_map') \
        else os.path.join(sim, 'utci_comfort_map')
    if not os.path.isdir(base):
        raise RuntimeError('no existe %s (§7.7 : la carpeta es .../utci_comfort_map)' % base)

    gi = os.path.join(base, 'grids_info.json')
    if not os.path.exists(gi):
        gi = os.path.join(base, 'results', 'temperature', 'grids_info.json')
    with open(gi, 'r', encoding='utf-8') as fh:
        grids = json.load(fh)
    orden = [g.get('full_id') or g.get('identifier') or g.get('name') for g in grids]

    # --- original ---------------------------------------------------------
    copiados = []
    for rel in ('__inputs__.json',):
        o = os.path.join(base, rel)
        if os.path.exists(o):
            shutil.copy2(o, os.path.join(destino, 'parametros_run___inputs__.json'))
            copiados.append(rel)
    shutil.copy2(gi, os.path.join(destino, 'grids_info.json'))
    copiados.append('grids_info.json')

    series = {}
    for sub in SUB:
        d = os.path.join(base, sub)
        if not os.path.isdir(d):
            continue
        dd = os.path.join(destino, 'original', os.path.basename(sub))
        os.makedirs(dd, exist_ok=True)
        filas, ids = [], []
        for gid in orden:
            for ext in ('.npy', '.csv'):
                f = os.path.join(d, gid + ext)
                if os.path.exists(f):
                    shutil.copy2(f, os.path.join(dd, os.path.basename(f)))
                    a = np.atleast_2d(leer_npy(f))
                    filas.append(a)
                    ids += ['%s_%d' % (gid, i) for i in range(a.shape[0])]
                    copiados.append(os.path.join(sub, gid + ext))
                    break
        if filas:
            series[os.path.basename(sub)] = (np.vstack(filas), ids)

    # --- CSV --------------------------------------------------------------
    nombres = {'temperature': 'LB_MRT.csv', 'condition_intensity': 'LB_UTCI.csv'}
    meta = {'zona': zona, 'exportado': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'origen': base, 'n_grids': len(orden), 'series': {}}
    for clave, (arr, ids) in series.items():
        np.savetxt(os.path.join(destino, nombres.get(clave, clave + '.csv')),
                   arr, delimiter=',', fmt='%.4f')
        meta['series'][clave] = {'filas': int(arr.shape[0]),
                                 'columnas': int(arr.shape[1]),
                                 'min': float(np.nanmin(arr)),
                                 'mediana': float(np.nanmedian(arr)),
                                 'max': float(np.nanmax(arr))}
        with open(os.path.join(destino, 'LB_orden_grids.csv'), 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(ids) + '\n')
    with open(os.path.join(destino, 'LB_metadata.json'), 'w', encoding='utf-8') as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    return meta, copiados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--zona', required=True)
    ap.add_argument('--sim', required=True, help='carpeta simulation_vN (o .../utci_comfort_map)')
    ap.add_argument('--version', required=True, help='v5, v6…')
    args = ap.parse_args()

    cfg, rutas = cargar_zona(args.zona)
    destino = rutas.run_ladybug(args.version)
    meta, copiados = exportar(args.sim, destino, args.zona)

    L = ['# Informe de exportación Ladybug — %s %s' % (args.zona, args.version), '',
         'Generado el %s' % meta['exportado'], '',
         'Origen : `%s`' % meta['origen'], '',
         'Destino : `%s`' % destino.replace('/', '\\'), '',
         '| Serie | Filas | Columnas | Mín | Mediana | Máx |', '|---|---|---|---|---|---|']
    for k, v in meta['series'].items():
        L.append('| %s | %d | %d | %.2f | %.2f | %.2f |'
                 % (k, v['filas'], v['columnas'], v['min'], v['mediana'], v['max']))
    L += ['', 'Ficheros originales copiados : %d' % len(copiados), '',
          'El orden de sensores sale de `grids_info.json` (§7.4), no de la '
          'concatenación de los ficheros.']
    ruta = rutas.informe('informe_ladybug_%s_' + args.version + '.md')
    with open(ruta, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(L) + '\n')
    print('Exportado a %s' % destino)
    print('Informe : %s' % ruta)


if __name__ == '__main__':
    main()
