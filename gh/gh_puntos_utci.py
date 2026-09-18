# -*- coding: utf-8 -*-
"""
gh_puntos_utci.py — GHPython (Rhino 8 / Python 3, ScriptEditor)
TFM UTCI Lavapies — semis des capteurs sur les tramos SOLWEIG

Remplace le composant "Curve Middle" de la chaine ML_UTCI. Se branche apres
Drape_CurvesOnMesh et avant le Move (Unit Z x 1.1).

ENTREES DU COMPOSANT : 2
    curvas  (List, Curve)  les tramos drapes sur la topo
    ids     (List, str)    ID_Segmento, MEME ordre que curvas

SORTIES : pts · id_seg · pt_medio · id_medio · n_pts · info
    pts       capteurs, liste plate
    id_seg    ID_Segmento repete une fois par capteur, aligne sur pts
              -> regroupement aval par simple Member Index / Create Set
    pt_medio  UN point par tramo, en son milieu. Liste plate.
              C'est le porteur de la moyenne des n capteurs du tramo, et
              le marqueur clicable dans Rhino.
    id_medio  ID_Segmento, aligne sur pt_medio
    n_pts     nombre de capteurs par tramo, aligne sur curvas

pt_medio et pts sont DEUX SORTIES DISTINCTES, meme quand elles coincident.
Sur les 851 tramos de moins de 25 m le capteur unique tombe exactement au
milieu : si les deux etaient bakes sur le meme calque, on ne saurait plus
lequel on clique. Bakez-les sur deux calques separes.

REGLE DE SEMIS
    n = max(1, round(L / PASO_M))
    Les points sont places aux fractions de longueur d'arc (j + 0,5) / n,
    c'est-a-dire au MILIEU de chaque sous-tramo, pas a ses extremites.
    Deux consequences :
      - pour n = 1 le point tombe exactement au milieu du tramo : le
        comportement de Curve Middle est conserve pour les tramos courts ;
      - la moyenne arithmetique des n points est la regle du point median
        appliquee a l'integrale de ligne. L'operateur d'agregation n'est plus
        un choix a defendre, il decoule de la geometrie du semis.
    Aucun point ne tombe sur un noeud de rue, ou deux tramos se rejoignent et
    ou la valeur serait comptee deux fois.

MESURE QUI JUSTIFIE PASO_M = 25 (1 427 tramos, 47 708 m)
    longueur mediane 19,3 m, mais p75 48,1 | p90 85,3 | max 246,7 m
    23,4 % des tramos depassent 50 m et portent 60,6 % du viaire lineaire
    -> un point median unique n'est representatif que du tramo median
    pas 25 m -> 2 368 capteurs (x1,7), max 10 points sur un tramo
    851 tramos de moins de 25 m gardent leur point median unique

API Rhino : Curve.GetLength, Curve.DivideByCount, Curve.PointAt [SOURCE: GH-01]
"""

# ============================ REGLAGES ======================================
PASO_M   = 25.0   # longueur cible entre capteurs. 0 = un seul point (milieu).
N_MAX    = 20     # garde-fou : jamais plus de N_MAX capteurs sur un tramo
L_MIN_M  = 0.5    # tramo plus court : ignore (bruit de la source)
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
    aviso('curvas (%d) et ids (%d) n\'ont pas la meme longueur : '
          'les ID seront desalignes.' % (len(_c), len(_i)))

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

    # Point median : porteur de la moyenne aval, un par tramo.
    ident = str(_i[k]) if k < len(_i) else str(k)
    pt_medio.append(crv.PointAtNormalizedLength(0.5))
    id_medio.append(ident)

    n = 1 if PASO_M <= 0 else max(1, int(round(L / PASO_M)))
    n = min(n, N_MAX)

    # DivideByCount decoupe par longueur d'arc egale. En demandant 2n
    # divisions et en ne retenant que les parametres d'indice impair, on
    # obtient les fractions (2j+1)/(2n) = (j+0,5)/n : les milieux.
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

# ------------------------------------------------------------------ rapport
linea('Tramos en entree : %d | capteurs : %d | points medians : %d'
      % (len(_c), len(pts), len(pt_medio)))
if len(pt_medio) != len(set(id_medio)):
    aviso('id_medio contient des doublons : deux tramos partagent un ID_Segmento.')
if n_corto:
    linea('Tramos ignores (L < %.1f m) : %d' % (L_MIN_M, n_corto))
if _largos:
    _largos.sort()
    q = lambda p: _largos[min(len(_largos) - 1, int(p * len(_largos)))]
    linea('Longueur des tramos : mediane %.1f | p75 %.1f | p90 %.1f | max %.1f m'
          % (q(0.50), q(0.75), q(0.90), _largos[-1]))
if n_pts:
    ok = [v for v in n_pts if v > 0]
    if ok:
        linea('Capteurs par tramo : min %d | max %d | moyenne %.2f'
              % (min(ok), max(ok), float(sum(ok)) / len(ok)))
        linea('Tramos a 1 seul point (= Curve Middle) : %d (%.1f %%)'
              % (ok.count(1), 100.0 * ok.count(1) / len(ok)))
linea('Pas de semis : %.1f m | plafond %d capteurs par tramo' % (PASO_M, N_MAX))
linea('')
linea('Agregation aval : moyenne des capteurs partageant le meme id_seg,')
linea('deposee sur le pt_medio du meme ID (voir gh_agregar_utci.py).')
linea('Les points etant equidistants et centres, cette moyenne est la regle du')
linea('point median appliquee a l\'integrale de ligne du tramo.')

info = '\n'.join(_lineas)

try:
    for a in _avisos:
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, a)
except Exception:
    pass
