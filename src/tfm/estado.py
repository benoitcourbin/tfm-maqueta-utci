# -*- coding: utf-8 -*-
"""
estado.py — suivi d'exécution, manifeste et rapport d'incidents.

Principe : la chaîne ne s'arrête jamais. Chaque étape est enveloppée, son échec
est enregistré avec sa cause et la marche à suivre manuelle, et l'exécution
continue. À la fin, deux fichiers :

  DOCS/INFORMES/informe_ejecucion_<zona>.md   lisible : quoi faire à la main
  MAQUETA/<zona>/manifest_<zona>.json         machine : ce que Grasshopper lit
"""

import os
import json
import time
import hashlib
import traceback

OK, FALLO, OMITIDO = 'ok', 'fallo', 'omitido'


def huella(ruta, bloque=1024 * 1024):
    """SHA1 du premier Mo + taille : suffit pour détecter un fichier changé."""
    h = hashlib.sha1()
    with open(ruta, 'rb') as fh:
        h.update(fh.read(bloque))
    return '%s-%d' % (h.hexdigest()[:16], os.path.getsize(ruta))


class Ejecucion(object):
    def __init__(self, zona, rutas):
        self.zona = zona
        self.rutas = rutas
        self.pasos = []
        self.t0 = time.time()

    # ------------------------------------------------------------------ pasos
    def paso(self, nombre, funcion, remedio='', salidas=None, omitir=False):
        """Exécute `funcion()`. Ne relance jamais l'exception.

        remedio : texte affiché dans le rapport si l'étape échoue.
        salidas : fichiers attendus ; leur absence vaut échec.
        """
        if omitir:
            self.pasos.append({'paso': nombre, 'estado': OMITIDO, 'seg': 0,
                               'salidas': salidas or [], 'remedio': remedio})
            print('— %s : omitido' % nombre)
            return None
        t = time.time()
        reg = {'paso': nombre, 'estado': OK, 'seg': 0, 'detalle': '',
               'salidas': [], 'remedio': remedio}
        try:
            res = funcion()
        except Exception as ex:
            reg['estado'] = FALLO
            reg['detalle'] = '%s: %s' % (type(ex).__name__, ex)
            # Une absence de fichier n'a pas besoin de sa trace : le remède suffit.
            if 'no se descarga' not in str(ex):
                reg['traza'] = traceback.format_exc(limit=3)
            res = None
        for s in (salidas or []):
            if os.path.exists(s):
                reg['salidas'].append({'ruta': s, 'bytes': os.path.getsize(s),
                                       'huella': huella(s)})
            else:
                reg['estado'] = FALLO
                reg['detalle'] = (reg['detalle'] + ' | ' if reg['detalle'] else '') \
                    + 'falta la salida %s' % os.path.basename(s)
        reg['seg'] = round(time.time() - t, 1)
        self.pasos.append(reg)
        print('%s %s (%.1f s)%s'
              % ('✔' if reg['estado'] == OK else '✗', nombre, reg['seg'],
                 '' if reg['estado'] == OK else ' — ' + reg['detalle']))
        return res

    @property
    def fallos(self):
        return [p for p in self.pasos if p['estado'] == FALLO]

    # -------------------------------------------------------------- salidas
    def manifiesto(self, cfg):
        datos = {'zona': self.zona, 'generado': time.strftime('%Y-%m-%dT%H:%M:%S'),
                 'crs': cfg.get('crs'), 'bbox': cfg.get('bbox'),
                 'bbox_contexto': cfg.get('bbox_contexto'), 'eap': cfg.get('eap'),
                 'completo': not self.fallos, 'ficheros': {}}
        claves = {'suelo': self.rutas.suelo, 'lod1': self.rutas.lod1,
                  'superstruct': self.rutas.superstruct,
                  'arbolado': self.rutas.arbolado, 'mdt': self.rutas.mdt,
                  'mdt_limpio': self.rutas.mdt_limpio,
                  'huellas': self.rutas.huellas, 'viario': self.rutas.viario_gj}
        for k, r in claves.items():
            if os.path.exists(r):
                datos['ficheros'][k] = {'ruta': r.replace('/', '\\'),
                                        'bytes': os.path.getsize(r),
                                        'huella': huella(r)}
            else:
                datos['ficheros'][k] = None
        with open(self.rutas.manifiesto, 'w', encoding='utf-8') as fh:
            json.dump(datos, fh, ensure_ascii=False, indent=2)
        return datos

    def informe(self, cfg):
        L = []
        a = L.append
        a('# Informe de ejecución — %s' % self.zona)
        a('')
        a('Generado el %s · duración total %.1f min'
          % (time.strftime('%Y-%m-%dT%H:%M:%S'), (time.time() - self.t0) / 60))
        a('')
        a('| Paso | Estado | s | Salidas |')
        a('|---|---|---|---|')
        for p in self.pasos:
            a('| %s | %s | %.0f | %d |'
              % (p['paso'],
                 {'ok': '✅', 'fallo': '❌', 'omitido': '⏭️'}[p['estado']],
                 p['seg'], len(p['salidas'])))
        a('')
        if not self.fallos:
            a('## Sin incidencias')
            a('')
            a('Todas las salidas existen. El manifiesto está listo para Grasshopper:')
            a('`%s`' % self.rutas.manifiesto.replace('/', '\\'))
        else:
            a('## Tareas manuales pendientes')
            a('')
            for p in self.fallos:
                a('### %s' % p['paso'])
                a('')
                a('**Qué ha pasado:** %s' % (p.get('detalle') or 'sin detalle'))
                a('')
                if p.get('remedio'):
                    a('**Cómo resolverlo:**')
                    a('')
                    a(p['remedio'])
                    a('')
                if p.get('traza'):
                    a('```')
                    a(p['traza'].strip())
                    a('```')
                a('')
            a('Tras resolverlo, volver a lanzar sólo los pasos que fallaron:')
            a('')
            a('```bash')
            a('python run_maqueta.py --zona %s --pasos %s'
              % (self.zona, ','.join(p['paso'] for p in self.fallos)))
            a('```')
        a('')
        a('## Ficheros del manifiesto')
        a('')
        a('| Clave | Fichero | MB |')
        a('|---|---|---|')
        m = json.load(open(self.rutas.manifiesto, encoding='utf-8')) \
            if os.path.exists(self.rutas.manifiesto) else {'ficheros': {}}
        for k, v in sorted(m.get('ficheros', {}).items()):
            a('| %s | %s | %s |' % (k,
                                    os.path.basename(v['ruta']) if v else '—',
                                    '%.1f' % (v['bytes'] / 1e6) if v else '—'))
        ruta = self.rutas.informe('informe_ejecucion_%s.md')
        with open(ruta, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(L) + '\n')
        return ruta
