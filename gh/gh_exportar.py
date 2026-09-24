# -*- coding: utf-8 -*-
"""
gh_exportar.py — GHPython (Rhino 8 / Python 3, ScriptEditor)
TFM UTCI Lavapies — lanza la exportacion de un run al Drive SIN bloquear Rhino

POR QUE UN LANZADOR Y NO LA EXPORTACION DENTRO DE GRASSHOPPER
    exportar_resultados.py copia unos 2 850 ficheros .npy hacia G:\\, que es
    una unidad de Google Drive en modo streaming. Cada copia dispara una
    subida DENTRO de la llamada, y GHPython es sincrono : Rhino se queda
    congelado hasta que termina (trampa §7.9, aqui en escritura, que es peor
    que en lectura).
    Este componente no exporta nada : construye la linea de comando y lanza
    el script en un proceso aparte, con su propia consola. Grasshopper queda
    libre en el acto y la consola muestra el avance.

ENTRADAS DEL COMPONENTE : 5
    _zona      (Item, str)   nombre del barrio            ej. "lavapies"
    _sim       (Item, str)   carpeta simulation_vN        ej. "...\\simulation_v5"
    _version   (Item, str)   etiqueta de archivo          ej. "v5"
    _si        (Item, bool)  True = no pide confirmacion si el destino existe
    _lanzar    (Item, bool)  boton. False no hace nada.

    _zona, _sim y _version pueden venir de gh_cache.py y del Concatenate que
    ya construye carpeta_sim : asi el lanzador sigue la zona sin tocar nada.

SALIDAS : comando · info
    comando  la linea exacta, para pegarla en PowerShell si se prefiere
    info     estado, ruta del python usado y lo que hara el script

NOTAS
    - El componente NO espera al proceso : no hay communicate() ni wait().
      Si hiciera falta esperar, volveriamos a congelar Rhino.
    - Se usa un marcador en sc.sticky para no relanzar el mismo comando cada
      vez que Grasshopper recalcula. Poner _lanzar a False y a True otra vez
      fuerza un nuevo lanzamiento.
    - El python que se usa NO es el de Rhino : el script escribe en el Drive
      y no debe compartir proceso con Rhino. Ver PYTHONS mas abajo.
"""

import os
import sys
import subprocess

import scriptcontext as sc

# ============================== AJUSTES =====================================
# Interpretes probados por orden. El primero que exista en el disco se usa.
# Anadir aqui el python propio si se instala en otro sitio. Solo hace falta
# numpy : el script no usa nada mas fuera de la libreria estandar.
PYTHONS = [
    r'C:\Python314\python.exe',
    r'C:\Python312\python.exe',
    r'C:\Python311\python.exe',
]

# Carpeta del repositorio desplegado en el Drive. Es la copia de referencia
# de los .py desde el 20/09 (trampa §7.24) : lanzar otra copia arriesga
# ejecutar una version atrasada.
PIPELINE = r'G:\Mi unidad\TFM_UTCI_Lavapies_2026\02_CODIGO\pipeline'

# True abre una consola nueva y visible. False lanza en silencio, sin ventana,
# y entonces no se ve el avance : dejarlo en True.
CONSOLA = True

# True mantiene la ventana ABIERTA cuando el script termina (cmd /k).
# Imprescindible mientras se depura : si el script falla al arrancar, la
# consola se cierra en menos de un segundo y el error no se llega a leer.
# El destino vacio sin ningun mensaje viene siempre de ahi.
MANTENER_ABIERTA = True
# ============================================================================

CREATE_NEW_CONSOLE = 0x00000010     # flag de CreateProcess (solo Windows)

# Variables de entorno que Rhino define para SU propio interprete (py39-rh8).
# Un proceso hijo las hereda, y entonces C:\Python314 arranca con la libreria
# estandar de Rhino : "AssertionError: SRE module mismatch" al importar re.
# Se quitan del entorno del hijo, nunca del de Rhino.
ENTORNO_FUERA = ('PYTHONHOME', 'PYTHONPATH', 'PYTHONSTARTUP',
                 'PYTHONEXECUTABLE', 'PYTHONUSERBASE', 'PYTHONPLATLIBDIR')

# ----------------------- entradas tolerantes --------------------------------
# Si un puerto todavia no existe en el componente, Python lanzaria
# "name '_zona' is not defined" y no se veria nada en info. Se leen desde
# globals() para poder avisar en claro de cual falta.
_zona    = globals().get('_zona')
_sim     = globals().get('_sim')
_version = globals().get('_version')
_si      = globals().get('_si')
_lanzar  = globals().get('_lanzar')

_msg = []


def linea(t):
    _msg.append(str(t))


def aviso(t):
    _msg.append('/!\\ ' + str(t))


def buscar_python():
    """Primer interprete de PYTHONS que exista en el disco."""
    for p in PYTHONS:
        if os.path.exists(p):
            return p
    return None


def entorno_limpio():
    """Copia del entorno sin las variables Python que impone Rhino.

    Sin esto el interprete externo carga la libreria estandar de py39-rh8 y
    falla en el primer `import re` con "SRE module mismatch". No es un
    problema del guion : es el entorno heredado.
    """
    env = dict(os.environ)
    quitadas = []
    for v in ENTORNO_FUERA:
        if env.pop(v, None) is not None:
            quitadas.append(v)
    return env, quitadas


def normalizar_sim(s):
    """El script acepta las dos rutas; se manda la raiz simulation_vN."""
    s = str(s).strip().strip('"').rstrip('/\\')
    if s.lower().endswith('utci_comfort_map'):
        s = os.path.dirname(s)
    return s


comando = None

# --------------------------- comprobaciones ---------------------------------
guion = os.path.join(PIPELINE, 'exportar_resultados.py')
python = buscar_python()

falta = []
if not _zona:
    falta.append('_zona')
if not _sim:
    falta.append('_sim')
if not _version:
    falta.append('_version')

if falta:
    aviso('faltan entradas : %s' % ', '.join(falta))
elif python is None:
    aviso('ningun interprete encontrado. Probados :')
    for p in PYTHONS:
        aviso('    %s' % p)
    aviso('Anadir la ruta correcta en PYTHONS, arriba del componente.')
elif not os.path.exists(guion):
    aviso('no se encuentra el guion : %s' % guion)
    aviso('Comprobar que el Drive esta montado y que PIPELINE es correcto.')
else:
    sim = normalizar_sim(_sim)
    if not os.path.isdir(sim):
        aviso('la carpeta de simulacion no existe : %s' % sim)
        aviso('Se lanzara igualmente : el script lo comprobara y lo dira.')

    # La zona se normaliza en minusculas : el 19/09 'Lavapies' y 'lavapies'
    # crearon dos carpetas de destino distintas en el Drive.
    zona = str(_zona).strip().lower()
    if zona != str(_zona).strip():
        linea('Zona normalizada a minusculas : %s' % zona)

    partes = [python, guion,
              '--zona', zona,
              '--sim', sim,
              '--version', str(_version).strip()]
    if _si:
        partes.append('--si')

    # Linea legible, para pegar en PowerShell si se prefiere lanzarlo a mano.
    comando = ' '.join('"%s"' % p if ' ' in p else p for p in partes)

    linea('Python  : %s' % python)
    _hered = [v for v in ENTORNO_FUERA if v in os.environ]
    if _hered:
        linea('Aviso   : Rhino define %s ; se quitan en el hijo.'
              % ', '.join(_hered))
    linea('Guion   : %s' % guion)
    linea('Zona    : %s   Version : %s' % (_zona, _version))
    linea('Origen  : %s' % sim)
    linea('')

    clave = 'tfm_exportar_ultimo'

    if not _lanzar:
        # Al soltar el boton se borra el marcador : asi el siguiente True
        # vuelve a lanzar de verdad, aunque el comando sea el mismo.
        sc.sticky.pop(clave, None)
        linea('_lanzar = False. Nada lanzado.')
        linea('Poner _lanzar a True para abrir la consola de exportacion.')
    else:
        # Un mismo comando no se relanza en cada recalculo de Grasshopper
        # mientras el boton siga pulsado.
        if sc.sticky.get(clave) == comando:
            linea('Ya lanzado con este mismo comando : no se repite en cada')
            linea('recalculo. Poner _lanzar a False y luego a True otra vez.')
        else:
            try:
                banderas = CREATE_NEW_CONSOLE if CONSOLA else 0
                if CONSOLA and MANTENER_ABIERTA:
                    # cmd /s /k deja la ventana abierta al terminar. La regla
                    # de /s : todo el comando va entre UNAS comillas mas, y cmd
                    # se limita a quitarlas. Sin esto, una ruta con espacios
                    # ('Mi unidad') rompe el analisis de la linea.
                    lanzamiento = 'cmd.exe /s /k "%s"' % comando
                else:
                    lanzamiento = partes
                env, quitadas = entorno_limpio()
                if quitadas:
                    linea('Entorno de Rhino neutralizado : %s'
                          % ', '.join(quitadas))
                # Popen y nada mas : ni wait() ni communicate(). Si esperaramos
                # al proceso, Rhino se quedaria congelado igual que antes.
                proc = subprocess.Popen(lanzamiento, cwd=PIPELINE,
                                        creationflags=banderas, env=env)
                sc.sticky[clave] = comando
                linea('Lanzado. PID %d' % proc.pid)
                linea('El avance se ve en la consola que acaba de abrirse.')
                if MANTENER_ABIERTA:
                    linea('La ventana queda abierta al terminar : leer ahi el')
                    linea('resultado o el error. Cerrarla con exit.')
                linea('Grasshopper queda libre : no espera al proceso.')
            except Exception as e:
                aviso('no se ha podido lanzar : %s' % e)
                aviso('Copiar la salida comando y pegarla en PowerShell.')

    linea('')
    linea('El script escribira en 01_DATOS/LADYBUG_SIM/%s/%s/' % (zona, _version))
    linea('y un informe en DOCS/INFORMES/informe_ladybug_%s_%s.md'
          % (zona, _version))

info = '\n'.join(_msg)
