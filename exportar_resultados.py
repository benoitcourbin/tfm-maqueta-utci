# -*- coding: utf-8 -*-
"""
exportar_resultados.py — archiva un run de Ladybug en el Drive del equipo.

DONDE SE EJECUTA
    En Windows, fuera de Rhino (PowerShell o VSCode). Tambien en Colab, donde
    la raiz del Drive se resuelve sola. Necesita numpy y nada mas.

QUE HACE
    Toma la carpeta de una simulacion terminada (`simulation_vN`) y copia al
    Drive UNICAMENTE lo que la comparacion con SOLWEIG necesita, en dos
    formatos que se complementan :

      ORIGINAL   grids_info.json · __inputs__.json
                 results/temperature/*.npy            (UTCI por sensor)
                 results/condition_intensity/*.npy    (categoria de estres)
                 -> se guardan tal cual, para poder rehacer el calculo.

      CSV        LB_MRT.csv · LB_UTCI.csv             copiados tal cual de
                 LB_orden_grids.csv                   RESULT_REUNIDOS_CSV, que
                 LB_metadata.json                     produce el componente de
                                                      Grasshopper. FUENTE
                                                      CANONICA de la comparacion.

                 LB_UTCI_recipe.csv                   reconstruidos aqui a partir
                 LB_condicion_categoria.csv           de results/. Control cruzado.
                 LB_metadata_exportacion.json

    ⚠ En el recipe UTCI Comfort Map, `results/temperature` es el **UTCI**, no
      la MRT (lo declara results_info.json), y `condition_intensity` son
      categorias enteras de estres. La MRT real sale de longwave_mrt +
      shortwave_mrt y solo la tiene RESULT_REUNIDOS_CSV. Ver trampa §7.26.

    Destino : 01_DATOS/LADYBUG_SIM/<zona>/<version>/
    Ademas escribe un informe en DOCS/INFORMES/informe_ladybug_<zona>_<version>.md

DOS MANERAS DE LLAMARLO
    1. Interactiva — sin argumentos. El script pregunta zona, carpeta y
       version, proponiendo un valor por defecto entre corchetes. Enter acepta
       el valor propuesto.

           python exportar_resultados.py

    2. Automatica — con argumentos. No pregunta nada. Es la forma que usan
       run_maqueta.py y el cuaderno de Colab.

           python exportar_resultados.py --zona lavapies ^
               --sim "C:/Users/benoi/Documents/M10_TFM_Local/simulation_v5" ^
               --version v5

    --si  salta la confirmacion final (util en un script encadenado).

TRAMPAS DEL §7 DEL ESTADO QUE ESTE SCRIPT EVITA
    §7.4  MRT y UTCI NO se escriben en el mismo orden de sensores. El orden
          correcto es el de `grids_info.json`; concatenar los ficheros por
          orden alfabetico mezcla los tramos sin que salte ningun error.
    §7.5  Los ficheros de `initial_results/conditions/` llevan extension .csv
          pero son binarios NumPy. Por eso `leer_npy` intenta np.load antes
          que np.loadtxt.
    §7.7  Los resultados NO estan en `simulation_vN` sino en
          `simulation_vN/utci_comfort_map`. El script acepta las dos rutas y
          anade el subdirectorio si hace falta.
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

# Las dos series que se exportan, en el orden en que aparecen en el informe.
SUB = ('results/temperature', 'results/condition_intensity')

# Carpeta de trabajo local donde viven las simulaciones, para proponer un
# valor por defecto. Si no existe, no se propone nada : no es un error.
SIM_LOCAL = os.path.expanduser('~/Documents/M10_TFM_Local')

ANCHO = 74


# ============================================================================
#  1. ENCUADRE : lo que se muestra y se pregunta antes de tocar nada
# ============================================================================

def marco(titulo, lineas):
    """Dibuja un recuadro de texto. Solo presentacion, no calcula nada."""
    print('')
    print('+' + '-' * (ANCHO - 2) + '+')
    print('| ' + titulo.ljust(ANCHO - 4) + ' |')
    print('+' + '-' * (ANCHO - 2) + '+')
    for l in lineas:
        for trozo in (l[i:i + ANCHO - 4] for i in range(0, max(len(l), 1), ANCHO - 4)):
            print('| ' + trozo.ljust(ANCHO - 4) + ' |')
    print('+' + '-' * (ANCHO - 2) + '+')


def ultima_simulacion():
    """Carpeta simulation_vN mas reciente en la carpeta de trabajo local.

    Devuelve (ruta, version) o (None, None). Se usa solo para proponer un
    valor por defecto : el usuario siempre puede escribir otro.
    """
    if not os.path.isdir(SIM_LOCAL):
        return None, None
    cand = []
    for n in os.listdir(SIM_LOCAL):
        if n.startswith('simulation_v') and os.path.isdir(os.path.join(SIM_LOCAL, n)):
            resto = n[len('simulation_v'):]
            if resto.isdigit():
                cand.append((int(resto), n))
    if not cand:
        return None, None
    num, nombre = max(cand)
    return os.path.join(SIM_LOCAL, nombre), 'v%d' % num


def preguntar(etiqueta, defecto=None):
    """Pide un valor por teclado. Enter acepta el valor propuesto."""
    aviso = '  %s' % etiqueta
    if defecto:
        aviso += ' [%s]' % defecto
    aviso += ' : '
    while True:
        try:
            r = input(aviso).strip().strip('"').strip("'")
        except (EOFError, KeyboardInterrupt):
            print('\nCancelado.')
            sys.exit(1)
        if r:
            return r
        if defecto:
            return defecto
        print('  -> hace falta un valor.')


def pedir_parametros():
    """Encuadre interactivo. Devuelve (zona, sim, version)."""
    sim_def, ver_def = ultima_simulacion()
    marco('EXPORTAR UN RUN DE LADYBUG AL DRIVE', [
        '',
        'Tres datos hacen falta :',
        '',
        '  zona      nombre del barrio, tal como se llama su fichero de',
        '            configuracion en config/zonas/ (ej. lavapies)',
        '',
        '  sim       carpeta de la simulacion terminada. Vale tanto',
        '            ...\\simulation_v5 como ...\\simulation_v5\\utci_comfort_map',
        '',
        '  version   etiqueta de archivo (v5, v6...). Da nombre a la carpeta',
        '            de destino en el Drive y al informe.',
        '',
        'Enter acepta el valor propuesto entre corchetes.',
        '',
    ])
    zona = preguntar('zona   ', 'lavapies')
    sim = preguntar('sim    ', sim_def)
    version = preguntar('version', ver_def)
    return zona, sim, version


def carpeta_base(sim):
    """Resuelve la carpeta que contiene de verdad los resultados (§7.7)."""
    s = sim.rstrip('/\\')
    return s if s.endswith('utci_comfort_map') else os.path.join(s, 'utci_comfort_map')


def ruta_grids_info(base):
    """grids_info.json esta en la raiz del run o dentro de results/temperature."""
    gi = os.path.join(base, 'grids_info.json')
    if os.path.exists(gi):
        return gi
    return os.path.join(base, 'results', 'temperature', 'grids_info.json')


def comprobar(zona, sim, version, forzar):
    """Verifica que todo esta en su sitio ANTES de escribir nada.

    Devuelve (base, destino). Sale del programa si algo falta o si el usuario
    no confirma el aplastamiento de una exportacion anterior.
    """
    problemas, notas = [], []

    base = carpeta_base(sim)
    if not os.path.isdir(base):
        problemas.append('No existe la carpeta de resultados :')
        problemas.append('  %s' % base)
        problemas.append('Recuerda (§7.7) que los resultados estan dentro de')
        problemas.append('utci_comfort_map, no en la raiz de simulation_vN.')
    else:
        notas.append('Origen   : %s' % base)

    n_grids = n_sensores = 0
    if not problemas:
        gi = ruta_grids_info(base)
        if not os.path.exists(gi):
            problemas.append('Falta grids_info.json : el run no llego a terminar.')
        else:
            with open(gi, 'r', encoding='utf-8') as fh:
                grids = json.load(fh)
            n_grids = len(grids)
            n_sensores = sum(int(g.get('count', 0)) for g in grids)
            notas.append('Rejillas : %d   Sensores : %d' % (n_grids, n_sensores))

    if not problemas:
        for sub in SUB:
            d = os.path.join(base, sub)
            n = len([f for f in os.listdir(d) if f.endswith('.npy')]) \
                if os.path.isdir(d) else 0
            estado = '%d ficheros' % n if n else 'AUSENTE'
            notas.append('  %-28s %s' % (sub, estado))
            if sub == 'results/temperature' and n == 0:
                problemas.append('Sin ficheros de MRT : no hay nada que exportar.')

    # La raiz del Drive se resuelve aqui : si el Drive no esta montado, mejor
    # saberlo antes de haber leido 2 500 ficheros.
    destino = None
    try:
        _cfg, rutas = cargar_zona(zona)
        destino = rutas.ladybug + '/' + version
        notas.append('Destino  : %s' % destino.replace('/', '\\'))
    except Exception as e:
        problemas.append('No se puede resolver el destino : %s' % e)

    pisa = destino is not None and os.path.isdir(destino) and os.listdir(destino)
    if pisa:
        notas.append('')
        notas.append('ATENCION : el destino ya contiene una exportacion.')
        notas.append('Los ficheros con el mismo nombre se sobrescriben.')

    marco('COMPROBACION PREVIA — %s %s' % (zona, version),
          notas + ([''] + ['ERROR : ' + p for p in problemas] if problemas else []))

    if problemas:
        sys.exit(1)
    if pisa and not forzar:
        r = input('  Sobrescribir esa exportacion ? [s/N] : ').strip().lower()
        if r not in ('s', 'si', 'sí', 'y', 'yes'):
            print('  Cancelado. Usa otra --version para no pisar nada.')
            sys.exit(1)
    return base, destino


# ============================================================================
#  2. LECTURA Y COPIA
# ============================================================================

def leer_npy(ruta):
    """Lee un resultado de Ladybug.

    Los ficheros de `initial_results/conditions/` llevan extension .csv pero
    son binarios NumPy (§7.5) : se prueba np.load antes que np.loadtxt.
    """
    try:
        return np.load(ruta)
    except Exception:
        return np.loadtxt(ruta, delimiter=',')


def copiar_reunidos(base, destino):
    """Copia RESULT_REUNIDOS_CSV, producido por el componente de Grasshopper.

    Esos cuatro ficheros son la fuente CANONICA de la comparacion : la MRT
    real (mediana 62,1 °C a las 13 h en v5) sale de ahi, no de `results/`.
    El recipe guarda en `results/temperature` el UTCI, no la MRT (§7.26).
    """
    d = os.path.join(base, 'RESULT_REUNIDOS_CSV')
    if not os.path.isdir(d):
        return []
    hechos = []
    for n in ('LB_MRT.csv', 'LB_UTCI.csv', 'LB_orden_grids.csv',
              'LB_metadata.json'):
        o = os.path.join(d, n)
        if os.path.exists(o):
            shutil.copy2(o, os.path.join(destino, n))
            hechos.append(n)
    return hechos


def exportar(sim, destino, zona):
    """Copia el run y construye los CSV. El orden de sensores manda (§7.4)."""
    base = carpeta_base(sim)
    if not os.path.isdir(base):
        raise RuntimeError('no existe %s (§7.7 : la carpeta es .../utci_comfort_map)' % base)

    # --- 1/4 : el orden de los sensores -----------------------------------
    # Este orden es la unica referencia valida. MRT y UTCI se escriben en
    # ficheros distintos y no comparten orden : alinearlos por nombre de
    # fichero, o por orden alfabetico, mezcla los tramos en silencio (§7.4).
    gi = ruta_grids_info(base)
    with open(gi, 'r', encoding='utf-8') as fh:
        grids = json.load(fh)
    orden = [g.get('full_id') or g.get('identifier') or g.get('name') for g in grids]
    print('  1/4  Orden de sensores leido : %d rejillas.' % len(orden))

    # --- 2/4 : copia de los ficheros originales ---------------------------
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
            print('  2/4  %s ausente : se omite.' % sub)
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
                    # Un sensor por fila : el sufijo _i distingue los sensores
                    # de una misma rejilla (los tramos largos tienen varios).
                    ids += ['%s_%d' % (gid, i) for i in range(a.shape[0])]
                    copiados.append(os.path.join(sub, gid + ext))
                    break
        if filas:
            series[os.path.basename(sub)] = (np.vstack(filas), ids)
            print('  2/4  %-28s %d ficheros copiados.'
                  % (os.path.basename(sub), len(filas)))

    # --- 3/4 : construccion de los CSV ------------------------------------
    # Nombres honestos. OJO (trampa §7.26) : en el recipe UTCI Comfort Map,
    # `results/temperature` NO es la MRT sino el propio UTCI — lo declara
    # `initial_results/conditions/results_info.json` :
    # "data_type": "UniversalThermalClimateIndex", "unit": "C".
    # Y `condition_intensity` son categorias enteras de estres, no grados.
    # La MRT no esta en results/ : sale de longwave_mrt + shortwave_mrt, y la
    # calcula el componente gh_utci_lavapies.py (ver copiar_reunidos).
    nombres = {'temperature': 'LB_UTCI_recipe.csv',
               'condition_intensity': 'LB_condicion_categoria.csv'}
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
        # El orden se reescribe con cada serie : las dos comparten el mismo,
        # precisamente porque las dos se han recorrido siguiendo `orden`.
        with open(os.path.join(destino, 'LB_orden_grids.csv'), 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(ids) + '\n')
        print('  3/4  %-14s %d filas x %d columnas  (med %.2f)'
              % (nombres.get(clave, clave), arr.shape[0], arr.shape[1],
                 meta['series'][clave]['mediana']))

    # --- 4/4 : CSV reunidos por Grasshopper + metadatos --------------------
    reunidos = copiar_reunidos(base, destino)
    if reunidos:
        print('  4/4  RESULT_REUNIDOS_CSV copiado : %s' % ', '.join(reunidos))
        copiados += ['RESULT_REUNIDOS_CSV/' + n for n in reunidos]
        meta['reunidos_gh'] = reunidos
    else:
        print('  4/4  AVISO : falta RESULT_REUNIDOS_CSV en el run.')
        print('       Sin el, la MRT NO se exporta : `results/temperature`')
        print('       del recipe es el UTCI, no la MRT (trampa §7.26).')
        meta['reunidos_gh'] = []
    with open(os.path.join(destino, 'LB_metadata_exportacion.json'), 'w',
              encoding='utf-8') as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    print('  4/4  LB_metadata_exportacion.json escrito.')
    return meta, copiados


# ============================================================================
#  3. INFORME Y PUNTO DE ENTRADA
# ============================================================================

def escribir_informe(rutas, zona, version, destino, meta, copiados):
    """Escribe el informe en DOCS/INFORMES y devuelve su ruta."""
    L = ['# Informe de exportación Ladybug — %s %s' % (zona, version), '',
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
    ruta = rutas.informe('informe_ladybug_%s_' + version + '.md')
    with open(ruta, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(L) + '\n')
    return ruta


def main():
    ap = argparse.ArgumentParser(
        description='Archiva un run de Ladybug en el Drive. Sin argumentos, '
                    'pregunta los tres datos que hacen falta.')
    ap.add_argument('--zona', help='nombre del barrio (config/zonas/<zona>.json)')
    ap.add_argument('--sim', help='carpeta simulation_vN (o .../utci_comfort_map)')
    ap.add_argument('--version', help='etiqueta de archivo : v5, v6…')
    ap.add_argument('--si', action='store_true',
                    help='no pide confirmacion si el destino ya existe')
    args = ap.parse_args()

    # Interactivo solo si falta algo : un run automatizado no se bloquea nunca.
    if args.zona and args.sim and args.version:
        zona, sim, version = args.zona, args.sim, args.version
    else:
        zona, sim, version = pedir_parametros()

    base, _ = comprobar(zona, sim, version, args.si)

    _cfg, rutas = cargar_zona(zona)
    destino = rutas.run_ladybug(version)          # aqui si se crea la carpeta

    print('')
    print('  Exportando...')
    meta, copiados = exportar(base, destino, zona)
    ruta = escribir_informe(rutas, zona, version, destino, meta, copiados)

    marco('EXPORTACION TERMINADA', [
        'Destino  : %s' % destino.replace('/', '\\'),
        'Informe  : %s' % ruta.replace('/', '\\'),
        'Ficheros : %d originales + 4 CSV/JSON' % len(copiados),
        '',
        'Siguiente paso : abrir el cuaderno de comparacion y apuntarlo a',
        'esta carpeta para cruzar el run con los resultados de SOLWEIG.',
    ])


if __name__ == '__main__':
    main()
