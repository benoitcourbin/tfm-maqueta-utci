# -*- coding: utf-8 -*-
"""
gh_cache.py — GHPython (Rhino 8 / Python 3, ScriptEditor)
TFM UTCI — point d'entrée unique des chemins dans Grasshopper.

Lit `manifest_<zona>.json` (écrit par run_maqueta.py) et sort les chemins de
chaque couche, prêts à brancher sur les cargadores. Fini les Panels recopiés
à la main : une seule entrée, le nom de la zone.

ENTREES
    zona      (Item, str)   ex. 'lavapies'
    raiz      (Item, str)   racine du Drive. Vide -> 'G:\\Mi unidad\\TFM_UTCI_Lavapies_2026'
    modo      (Item, str)   'cache' (defaut) | 'directo'
    refrescar (Item, bool)  True : recopie meme si l'empreinte n'a pas change

SORTIES
    suelo · edificios (List de 2) · arbolado · mdt · manifiesto · info

MODE 'cache' — recommande
    Les fichiers sont copies dans %LOCALAPPDATA%\\TFM_UTCI\\<zona>\\ et seuls les
    chemins locaux sortent. La copie ne se refait que si l'empreinte du manifeste
    a change. Motif : sur Drive for desktop en streaming, « files are primarily
    stored in the cloud, but will be made available offline when accessed » et
    « some applications use a combination of APIs that make files difficult to
    stream » [Google Drive Help, "Stream and mirror files with Drive for desktop"].
    Un .json de 10 Mo lu depuis G:\\ passe donc par un telechargement a la demande,
    a l'interieur de l'appel bloquant de Grasshopper.

MODE 'directo'
    Sort les chemins du Drive tels quels. A n'utiliser que si le dossier de la
    zone est marque « Disponible sin conexion » dans Drive for desktop : les
    fichiers sont alors deja sur le disque.

API : shutil.copy2 / os.path [Python 3 stdlib]
"""

import os
import json
import shutil

G = globals()
_zona = (G.get('zona') or 'lavapies').strip()
_raiz = (G.get('raiz') or '').strip() or 'G:\\Mi unidad\\TFM_UTCI_Lavapies_2026'
_modo = (G.get('modo') or 'cache').strip().lower()
_refrescar = bool(G.get('refrescar'))

_lineas = []
def linea(t): _lineas.append(str(t))

manifiesto = os.path.join(_raiz, '04_VISUALIZACION', 'Modelo_3D', 'Data_Contexto',
                          'MAQUETA', _zona, 'manifest_%s.json' % _zona)

suelo = arbolado = mdt = None
edificios = []

if not os.path.exists(manifiesto):
    linea('AVISO: no existe %s' % manifiesto)
    linea('Lanzar antes :  python run_maqueta.py --zona %s' % _zona)
else:
    with open(manifiesto, 'r', encoding='utf-8') as fh:
        M = json.load(fh)
    linea('Manifiesto %s | generado %s | completo=%s'
          % (_zona, M.get('generado'), M.get('completo')))

    destino_base = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
                                'TFM_UTCI', _zona)

    def resolver(clave):
        """Chemin utilisable pour cette clé du manifeste, selon le mode."""
        ent = (M.get('ficheros') or {}).get(clave)
        if not ent:
            linea('  %-12s AUSENTE en el manifiesto' % clave)
            return None
        origen = ent['ruta']
        if not os.path.exists(origen):
            linea('  %-12s el manifiesto lo declara pero no está en el disco : %s'
                  % (clave, origen))
            return None
        if _modo == 'directo':
            linea('  %-12s directo (%.1f MB)' % (clave, ent['bytes'] / 1e6))
            return origen
        os.makedirs(destino_base, exist_ok=True)
        local = os.path.join(destino_base, os.path.basename(origen))
        sello = local + '.huella'
        actual = None
        if os.path.exists(sello):
            with open(sello, 'r', encoding='utf-8') as fh:
                actual = fh.read().strip()
        if _refrescar or actual != ent['huella'] or not os.path.exists(local):
            shutil.copy2(origen, local)
            with open(sello, 'w', encoding='utf-8') as fh:
                fh.write(ent['huella'])
            linea('  %-12s copiado (%.1f MB)' % (clave, ent['bytes'] / 1e6))
        else:
            linea('  %-12s en caché, sin cambios' % clave)
        return local

    suelo = resolver('suelo')
    for k in ('lod1', 'superstruct'):
        r = resolver(k)
        if r:
            edificios.append(r)
    arbolado = resolver('arbolado')
    mdt = resolver('mdt_limpio') or resolver('mdt')
    linea('Modo : %s%s' % (_modo, '' if _modo == 'directo' else ' -> ' + destino_base))
    if not M.get('completo'):
        linea('AVISO: el run no terminó completo. Ver DOCS/INFORMES/'
              'informe_ejecucion_%s.md' % _zona)

info = '\n'.join(_lineas)
try:
    import Grasshopper
    if any(l.startswith('AVISO') for l in _lineas):
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning,
            'Ver la salida info')
except Exception:
    pass
