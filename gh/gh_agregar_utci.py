# -*- coding: utf-8 -*-
"""
gh_agregar_utci.py — GHPython (Rhino 8 / Python 3, ScriptEditor)
TFM UTCI Lavapies — moyenne des capteurs par tramo, deposee sur le point median

Se branche apres la simulation. Prend une valeur par capteur, la moyenne par
ID_Segmento, et rend le resultat aligne sur pt_medio.

ENTREES DU COMPOSANT : 4
    valores    (List, float)  une valeur par capteur — MRT ou UTCI
    id_seg     (List, str)    ID_Segmento par capteur, sortie de gh_puntos_utci
    id_medio   (List, str)    ID_Segmento par point median, meme composant
    filtrar    (Item, bool)   True (defaut) : ecarte les sentinelles et les
                              valeurs hors bornes avant de moyenner

SORTIES : val_medio · n_usados · id_out · info
    val_medio  moyenne par tramo, ALIGNEE sur pt_medio (null si aucune valeur)
    n_usados   nombre de capteurs retenus par tramo, aligne
    id_out     copie de id_medio, pour brancher sur EleFront sans risque de
               desalignement
    info       rapport de controle

POURQUOI UNE MOYENNE ARITHMETIQUE SIMPLE
Les capteurs sont equidistants et centres sur chaque sous-tramo — fractions
(j + 0,5)/n de la longueur d'arc. La moyenne arithmetique est donc la regle du
point median appliquee a l'integrale de ligne du tramo. L'operateur d'agregation
n'est pas un choix a defendre devant un tribunal : il se deduit de la geometrie
du semis. Une mediane ou une ponderation par longueur seraient, elles, des
choix arbitraires.

FILTRES
SOLWEIG ecrit -999 comme sentinelle d'absence de donnee, et l'equipe ML applique
un filtre d'aberrants [5, 70] °C sur la MRT (5 °C minimum nocturne plausible en
ete, 70 °C limite superieure de pythermalcomfort.utci()). On reproduit les deux
pour que les distributions restent comparables. Une seule sentinelle dans une
moyenne la rend irrecuperable.
"""

# ============================ REGLAGES ======================================
V_MIN, V_MAX = 5.0, 70.0   # bornes de plausibilite, celles du dataset ML
SENTINELA    = -900.0      # toute valeur inferieure est une sentinelle
DECIMALES    = 2
# ============================================================================

import Grasshopper

G = globals()
def _lista(k):
    v = G.get(k)
    return v if isinstance(v, list) else ([v] if v is not None else [])

_val = _lista('valores')
_ids = [str(x) for x in _lista('id_seg')]
_idm = [str(x) for x in _lista('id_medio')]
_filtrar = G.get('filtrar')
_filtrar = True if _filtrar is None else bool(_filtrar)

_lineas, _avisos = [], []
def linea(t): _lineas.append(str(t))
def aviso(t):
    _avisos.append(str(t)); _lineas.append('AVISO: ' + str(t))

val_medio, n_usados, id_out = [], [], []

if len(_val) != len(_ids):
    aviso('valores (%d) et id_seg (%d) n\'ont pas la meme longueur : '
          'l\'appariement est faux. Verifier que les deux viennent du meme run.'
          % (len(_val), len(_ids)))

# --------------------------------------------------- accumulation par tramo
suma, cuenta = {}, {}
n_sent = n_fuera = n_nulo = 0

for i in range(min(len(_val), len(_ids))):
    v = _val[i]
    if v is None:
        n_nulo += 1
        continue
    try:
        v = float(v)
    except Exception:
        n_nulo += 1
        continue
    if _filtrar:
        if v < SENTINELA:
            n_sent += 1
            continue
        if not (V_MIN <= v <= V_MAX):
            n_fuera += 1
            continue
    k = _ids[i]
    suma[k] = suma.get(k, 0.0) + v
    cuenta[k] = cuenta.get(k, 0) + 1

# --------------------------------------------- restitution alignee sur id_medio
n_vacio = 0
for k in _idm:
    c = cuenta.get(k, 0)
    id_out.append(k)
    n_usados.append(c)
    if c:
        val_medio.append(round(suma[k] / c, DECIMALES))
    else:
        val_medio.append(None)
        n_vacio += 1

# ------------------------------------------------------------------ rapport
linea('Capteurs en entree : %d | tramos en sortie : %d' % (len(_val), len(_idm)))
if _filtrar:
    linea('Filtres : sentinelles (< %.0f) %d | hors [%.0f, %.0f] %d | nuls %d'
          % (SENTINELA, n_sent, V_MIN, V_MAX, n_fuera, n_nulo))
else:
    linea('Filtres desactives : %d valeurs nulles ecartees quand meme' % n_nulo)
linea('Tramos sans aucune valeur : %d' % n_vacio)

ok = [v for v in val_medio if v is not None]
if ok:
    ok_ord = sorted(ok)
    q = lambda p: ok_ord[min(len(ok_ord) - 1, int(p * len(ok_ord)))]
    linea('Valeur moyennee : min %.2f | p10 %.2f | mediane %.2f | p90 %.2f | max %.2f'
          % (ok_ord[0], q(0.10), q(0.50), q(0.90), ok_ord[-1]))
    usados = [c for c in n_usados if c > 0]
    linea('Capteurs par tramo : min %d | max %d | moyenne %.2f'
          % (min(usados), max(usados), float(sum(usados)) / len(usados)))
    linea('Tramos a 1 seul capteur : %d (%.1f %%)'
          % (usados.count(1), 100.0 * usados.count(1) / len(usados)))

sobrantes = set(_ids) - set(_idm)
if sobrantes:
    aviso('%d ID_Segmento presents dans id_seg mais absents de id_medio : '
          'leurs capteurs sont ignores.' % len(sobrantes))

linea('')
linea('val_medio est aligne sur pt_medio : brancher les deux sur le meme')
linea('EleFront Attributes, sans greffe ni aplatissement.')

info = '\n'.join(_lineas)

try:
    for a in _avisos:
        ghenv.Component.AddRuntimeMessage(
            Grasshopper.Kernel.GH_RuntimeMessageLevel.Warning, a)
except Exception:
    pass
