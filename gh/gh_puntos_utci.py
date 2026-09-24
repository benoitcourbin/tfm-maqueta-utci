# -*- coding: utf-8 -*-
"""
gh_puntos_utci.py — GHPython (Rhino 8 / Python 3, ScriptEditor)
TFM UTCI Lavapies — sembrado de los sensores sobre los tramos SOLWEIG

Sustituye al componente "Curve Middle" de la cadena ML_UTCI. Se conecta despues
de Drape_CurvesOnMesh y antes del Move (Unit Z x 1.1).

ENTRADAS DEL COMPONENTE : 2
    curvas  (List, Curve)  los tramos drapeados sobre la topografia
    ids     (List, str)    ID_Segmento, MISMO orden que curvas

SALIDAS : pts · id_seg · pt_medio · id_medio · n_pts · info
    pts       sensores, lista plana
    id_seg    ID_Segmento repetido una vez por sensor, alineado con pts
              -> agrupacion aguas abajo con un simple Member Index / Create Set
    pt_medio  UN punto por tramo, en su mitad. Lista plana.
              Es el portador de la media de los n sensores del tramo, y
              el marcador clicable en Rhino.
    id_medio  ID_Segmento, alineado con pt_medio
    n_pts     numero de sensores por tramo, alineado con curvas

pt_medio y pts son DOS SALIDAS DISTINTAS, incluso cuando coinciden.
En los 851 tramos de menos de 25 m el sensor unico cae exactamente en la
mitad : si los dos se bakearan en la misma capa, ya no se sabria cual se
clica. Bakearlos en dos capas separadas.

REGLA DE SEMBRADO
    n = max(1, round(L / PASO_M))
    Los puntos se colocan en las fracciones de longitud de arco (j + 0,5) / n,
    es decir en la MITAD de cada sub-tramo, no en sus extremos.
    Dos consecuencias :
      - para n = 1 el punto cae exactamente en la mitad del tramo : el
        comportamiento de Curve Middle se conserva para los tramos cortos ;
      - la media aritmetica de los n puntos es la regla del punto medio
        aplicada a la integral de linea. El operador de agregacion ya no es
        una eleccion que defender, se deduce de la geometria del sembrado.
    Ningun punto cae en un nudo de calle, donde dos tramos se juntan y
    donde el valor se contaria dos veces.

MEDIDA QUE JUSTIFICA PASO_M = 25 (1 427 tramos, 47 708 m)
    longitud mediana 19,3 m, pero p75 48,1 | p90 85,3 | max 246,7 m
    23,4 % de los tramos superan 50 m y llevan 60,6 % del viario lineal
    -> un punto medio unico solo es representativo del tramo mediano
    paso 25 m -> 2 368 sensores (x1,7), max 10 puntos en un tramo
    851 tramos de menos de 25 m conservan su punto medio unico

API Rhino : Curve.GetLength, Curve.DivideByCount, Curve.PointAt [SOURCE: GH-01]
"""

# ============================ AJUSTES =======================================
PASO_M   = 25.0   # longitud objetivo entre sensores. 0 = un solo punto (mitad).
N_MAX    = 20     # guardarrail : nunca mas de N_MAX sensores en un tramo
L_MIN_M  = 0.5    # tramo mas corto : ignorado (ruido de la fuente)
# ============================================================================

import Rhino.Geometry as rg
import Grasshopper

G = globals()
_c = G.get('curvas')
_c = _c if isinstance(_c, list) else ([_c] if _c else [])
_i = G.get('ids')
_i = _i if isinstance(_i, list) else ([_i] if _i else [])

_lineas, _avisos = [], []
def linea(t): _lineas.append(str(t))
def aviso(t):
    _avisos.append(str(t)); _lineas.append('AVISO: ' + str(t))

if _i and len(_i) != len(_c):
    aviso('curvas (%d) e ids (%d) no tienen la misma longitud : '
          'los ID quedaran desalineados.' % (len(_c), len(_i)))

pts, id_seg, n_pts = [], [], []
pt_medio, id_medio = [], []
_largos, n_corto = [], 0

for k, crv in enumerate(_c):
    if crv is None:
        n_pts.append(0); continue
    L = crv.GetLength()
    if L < L_MIN_M:
        n_corto += 1
        n_pts.append(0)
        continue

    # Punto medio : portador de la media aguas abajo, uno por tramo.
    ident = str(_i[k]) if k < len(_i) else str(k)
    pt_medio.append(crv.PointAtNormalizedLength(0.5))
    id_medio.append(ident)

    n = 1 if PASO_M <= 0 else max(1, int(round(L / PASO_M)))
    n = min(n, N_MAX)

    # DivideByCount corta por longitud de arco igual. Pidiendo 2n
    # divisiones y reteniendo solo los parametros de indice impar, se
    # obtienen las fracciones (2j+1)/(2n) = (j+0,5)/n : las mitades.
    ts = crv.DivideByCount(2 * n, True)
    if not ts:
        pts.append(crv.PointAtNormalizedLength(0.5)); id_seg.append(ident)
        n_pts.append(1); _largos.append(L)
        continue

    ts = list(ts)
    for j in range(n):
        idx = 2 * j + 1
        if idx >= len(ts):
            break
        pts.append(crv.PointAt(ts[idx]))
        id_seg.append(ident)
    n_pts.append(n)
    _largos.append(L)

# ------------------------------------------------------------------ informe
linea('Tramos de entrada : %d | sensores : %d | puntos medios : %d'
      % (len(_c), len(pts), len(pt_medio)))
if len(pt_medio) != len(set(id_medio)):
    aviso('id_medio contiene duplicados : dos tramos comparten un ID_Segmento.')
if n_corto:
    linea('Tramos ignorados (L < %.1f m) : %d' % (L_MIN_M, n_corto))
if _largos:
    _largos.sort()
    q = lambda p: _largos[min(len(_largos) - 1, int(p * len(_largos)))]
    linea('Longueur des tramos : mediane %.1f | p75 %.1f | p90 %.1f | max %.1f m'
          % (q(0.50), q(0.75), q(0.90), _largos[-1]))
if n_pts:
    ok = [v for v in n_pts if v > 0]
    if ok:
        linea('Sensores por tramo : min %d | max %d | media %.2f'
              % (min(ok), max(ok), float(sum(ok)) / len(ok)))
        linea('Tramos con un solo punto (= Curve Middle) : %d (%.1f %%)'
              % (ok.count(1), 100.0 * ok.count(1) / len(ok)))
linea('Paso de sembrado : %.1f m | tope %d sensores por tramo' % (PASO_M, N_MAX))
linea('')
linea('Agregacion aguas abajo : media de los sensores con el mismo id_seg,')
linea('deposee sur le pt_medio du meme ID (voir gh_agregar_utci.py).')
linea('Al ser los puntos equidistantes y centrados, esa media es la regla del')
linea('point median appliquee a l\'integrale de ligne du tramo.')

info = '\n'.join(_lineas)

try:
    for a in _avisos:
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, a)
except Exception:
    pass
