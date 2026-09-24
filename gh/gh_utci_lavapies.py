# -*- coding: utf-8 -*-
"""
gh_utci_lavapies.py — Grasshopper, componente Python 3 (Rhino 8)
TFM UTCI Lavapies — COMPONENTE ÚNICO

Sustituye y deja obsoletos:
    assembler_resultats_lb.py   (script externo VSCode)
    Atributos_utci.py           (unión GeoJSON)
    gh_agregar_utci.py          (duplicado)

=============================================================================
CADENA COMPLETA, UNA SOLA AGREGACIÓN
=============================================================================
    .npy brutos
      | redistribución según _redist_info.json (MRT y UTCI NO están en el
      | mismo orden de sensores: es la trampa principal del recipe)
      | MRT = longwave_mrt + shortwave_mrt (la onda corta es un DELTA)
      v
    matrices alineadas, 43 758 sensores x 9 instantes
      | media por tramo, ignorando NaN
      v
    1 427 tramos
      | unión con el GeoJSON ML por ID_Segmento
      | D_MRT  = MRT_LB(hora_ml)  - MRT_SOLWEIG
      | D_UTCI = UTCI_LB(hora_ml) - UTCI_Real
      v
    keys / values / pt_out / color  ->  EleFront  ->  Bake

Una sola fuente, un solo orden: ya no hay que realinear nada aguas abajo.

=============================================================================
ENTRADAS (respetar los accesos: es lo que más a menudo rompe)
=============================================================================
    carpeta_auto   List  str      UTCIMap.env_conds (puede estar vacía)
    carpeta_sim    Item  str      Panel, ruta fija (respaldo)
    geojson        Item  str      ruta del GeoJSON ML
    claves_ml      List  str      lista blanca de atributos ML
    id_seg         List  str      FLATTEN — 1 por sensor
    pt_medio       List  Point3d  FLATTEN — 1 por trozo drapeado
    id_medio       List  str      FLATTEN — 1 por trozo drapeado
    horas          List  int      índices de columnas a exportar
    etiquetas      List  str      sufijo por instante, paralelo a horas
    hora_ml        Item  int      posición DENTRO de horas del instante de referencia ML
    escribir_csv   Item  bool
    _run           Item  bool

SALIDAS
    keys values id_out pt_out color categoria mrt utci n_capteurs info

numpy 2.0.2 está presente en el entorno de Rhino 8: sin directiva # r:
=============================================================================
"""

import os
import io
import csv
import json
import math
import time
import datetime

import numpy as np
import scriptcontext as sc
from System.Drawing import Color
from Rhino.Geometry import Point3d
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# ============================ AJUSTES =======================================
SUMA_MRT = ("longwave_mrt", "shortwave_mrt")
CLAVE_ML = "ID_Segmento"
REF_MRT_ML = "MRT_SOLWEIG"
REF_UTCI_ML = "UTCI_Real"
SENTINELA = -900.0      # los datasets ML codifican la ausencia con -999
V_MIN = 5.0             # límites de plausibilidad de los valores ML
V_MAX = 70.0
DECIMALES = 3
INT32_MAX = 2147483647

# Escala de estrés UTCI — idéntica al panel UTCI_STRESS_Cat del lienzo.
# Límites SUPERIORES exclusivos; la última categoría recoge todo lo que queda por encima.
ESCALA = [
    (9.0, "slight cold stress", (0, 176, 80)),
    (26.0, "no thermal stress", (146, 208, 80)),
    (32.0, "moderate heat stress", (255, 255, 0)),
    (38.0, "strong heat stress", (255, 192, 0)),
    (46.0, "very strong heat stress", (255, 0, 0)),
    (1e9, "extreme heat stress", (128, 0, 0)),
]
SIN_DATO = ("no-data", (200, 200, 200))
# ============================================================================


def _clasificar(v):
    """Valor UTCI -> (categoría, rgb). NaN y centinelas -> no-data."""
    if v is None or (isinstance(v, float) and v != v) or v <= SENTINELA:
        return SIN_DATO
    for tope, nombre, rgb in ESCALA:
        if v < tope:
            return nombre, rgb
    return ESCALA[-1][1], ESCALA[-1][2]


def _net(v):
    """Devuelve un valor aceptado por GH_Structure.Add(System.Object, GH_Path).

    - int fuera de [-2^31, 2^31-1] -> str (u_osm, v, IDs_origen: 10 cifras)
    - NaN / Inf -> None (EleFront no sabe escribirlos)
    - list / dict -> str
    """
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, int):
        return v if -INT32_MAX - 1 <= v <= INT32_MAX else str(v)
    if isinstance(v, float):
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(v, (list, tuple, dict)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _ml_valido(v):
    """¿Valor ML utilizable para calcular una diferencia?"""
    if v is None or isinstance(v, (bool, str)):
        return False
    try:
        f = float(v)
    except Exception:
        return False
    if math.isnan(f) or math.isinf(f):
        return False
    return SENTINELA < f and V_MIN <= f <= V_MAX


# --------------------------------------------------------------- lectura
def _cargar_json(ruta):
    with io.open(ruta, "r", encoding="utf-8-sig", errors="replace") as f:
        return json.load(f)


def _leer_matriz(ruta):
    """TRAMPA: en initial_results\\conditions, los ficheros llamados 0.csv,
    1.csv... son BINARIOS NumPy. np.load reconoce el formato por los bytes
    mágicos, no por la extensión. El texto solo es un respaldo."""
    try:
        a = np.load(ruta, allow_pickle=False)
    except Exception:
        a = np.loadtxt(ruta, delimiter=",", ndmin=2, encoding="utf-8")
    return np.atleast_2d(a)


def _leer_fuente(carpeta, indice):
    for ext in (".npy", ".csv"):
        ruta = os.path.join(carpeta, "%d%s" % (indice, ext))
        if os.path.isfile(ruta):
            return _leer_matriz(ruta)
    raise IOError("Fichero fuente %d no encontrado en %s" % (indice, carpeta))


def _matriz_condiciones(cond, nombre, n_fuentes):
    carpeta = os.path.join(cond, nombre)
    if not os.path.isdir(carpeta):
        raise IOError("Carpeta ausente: %s" % carpeta)
    bloques = [_leer_fuente(carpeta, i) for i in range(n_fuentes)]
    anchos = set(b.shape[1] for b in bloques)
    if len(anchos) != 1:
        raise ValueError("%s: columnas heterogéneas (%s)"
                         % (nombre, sorted(anchos)))
    return bloques


def _etiquetas_recipe(info, n_pasos):
    ap = (info or {}).get("analysis_period") or {}
    h0, h1 = ap.get("st_hour"), ap.get("end_hour")
    paso = ap.get("timestep", 1) or 1
    if h0 is None or h1 is None:
        return ["t%02d" % i for i in range(n_pasos)]
    out = []
    for h in range(int(h0), int(h1) + 1):
        for k in range(int(paso)):
            out.append("%02dh" % h if paso == 1
                       else "%02dh%02d" % (h, int(60 * k / paso)))
    return out if len(out) == n_pasos else ["t%02d" % i for i in range(n_pasos)]


def _resolver_base(auto, manual):
    """Carpeta de simulación: salida en vivo de UTCIMap si es utilizable, si no el Panel.

    UTCIMap.env_conds apunta a una SUBcarpeta. Se sube hasta la carpeta que
    contiene a la vez initial_results y results.

    TRAMPA conocida: al reabrir el .ghx las salidas de UTCIMap están vacías
    (_run = False, rutas no persistidas). De ahí el respaldo en el Panel.
    """

    def _raiz(ruta):
        if not ruta:
            return None
        d = str(ruta).strip().strip('"')
        if os.path.isfile(d):
            d = os.path.dirname(d)
        for _ in range(6):
            if (os.path.isdir(os.path.join(d, "initial_results"))
                    and os.path.isdir(os.path.join(d, "results"))):
                return d
            padre = os.path.dirname(d)
            if padre == d:
                break
            d = padre
        return None

    cand = auto if isinstance(auto, (list, tuple)) else [auto]
    for c in cand:
        r = _raiz(c)
        if r:
            return r, "UTCIMap (run en curso)"
    r = _raiz(manual)
    if r:
        return r, "Panel (ruta fija)"
    raise RuntimeError(
        "Ninguna carpeta de simulación utilizable.\n  UTCIMap: %s\n  Panel  "
        ": %s\nLa carpeta debe contener 'initial_results' Y 'results'."
        % ((list(cand)[:1] or ["vacío"])[0], manual or "vacío"))


# ------------------------------------------------------------- procesado
def _construir(base, escribir):
    """Reconstruye MRT y UTCI en el orden de referencia de grids_info.json."""
    t0 = time.time()
    cond = os.path.join(base, "initial_results", "conditions")
    dir_utci = os.path.join(base, "results", "temperature")

    grids = _cargar_json(os.path.join(cond, "grids_info.json"))
    redist = _cargar_json(os.path.join(cond, "_redist_info.json"))
    ruta_info = os.path.join(cond, "results_info.json")
    info_ap = _cargar_json(ruta_info) if os.path.isfile(ruta_info) else None

    if len(grids) != len(redist):
        raise RuntimeError("grids_info (%d) y _redist_info (%d) divergen."
                           % (len(grids), len(redist)))
    if any(a.get("identifier") != b.get("identifier")
           for a, b in zip(grids, redist)):
        raise RuntimeError("grids_info y _redist_info no están en el "
                           "mismo orden: alineación de sensores no fiable.")

    n_cap = sum(g.get("count", 0) for g in grids)
    n_fuentes = 1 + max(d["identifier"] for e in redist for d in e["dist_info"])

    bloques = None
    for nombre in SUMA_MRT:
        b = _matriz_condiciones(cond, nombre, n_fuentes)
        if bloques is None:
            bloques = b
        elif [x.shape for x in b] != [x.shape for x in bloques]:
            raise RuntimeError("%s y %s: dimensiones incompatibles." % SUMA_MRT)
        else:
            bloques = [x + y for x, y in zip(bloques, b)]
    n_pasos = bloques[0].shape[1]

    mrt_m = np.empty((n_cap, n_pasos), dtype=np.float32)
    orden = []
    fila = 0
    for g, e in zip(grids, redist):
        ident = g.get("full_id") or g.get("identifier")
        rango = 0
        for d in e["dist_info"]:
            src = bloques[d["identifier"]]
            a, b = int(d["st_ln"]), int(d["end_ln"])
            trozo = src[a:b + 1]
            mrt_m[fila:fila + len(trozo)] = trozo
            for k in range(len(trozo)):
                orden.append((ident, rango + k))
            fila += len(trozo)
            rango += len(trozo)
    if fila != n_cap:
        raise RuntimeError("MRT: %d filas para %d sensores." % (fila, n_cap))

    idx = {}
    for f in os.listdir(dir_utci):
        raiz, ext = os.path.splitext(f)
        if ext.lower() in (".npy", ".csv"):
            idx[raiz] = os.path.join(dir_utci, f)

    utci_m = np.empty((n_cap, n_pasos), dtype=np.float32)
    fila = 0
    ausentes = []
    for g in grids:
        claves = [g.get("full_id"), g.get("identifier"), g.get("name")]
        ruta = next((idx[c] for c in claves if c and c in idx), None)
        cnt = g.get("count", 0)
        if ruta is None:
            ausentes.append(claves[0])
            utci_m[fila:fila + cnt] = np.nan
            fila += cnt
            continue
        a = _leer_matriz(ruta)
        if a.shape[1] != n_pasos and a.size % n_pasos == 0:
            a = a.reshape(-1, n_pasos)
        if a.shape[0] != cnt:
            raise RuntimeError("Malla %s: %d filas leídas para %d anunciadas."
                               % (claves[0], a.shape[0], cnt))
        utci_m[fila:fila + cnt] = a
        fila += cnt
    if fila != n_cap:
        raise RuntimeError("UTCI: %d filas para %d sensores." % (fila, n_cap))
    if mrt_m.shape != utci_m.shape:
        raise RuntimeError("MRT %s y UTCI %s: formas distintas."
                           % (mrt_m.shape, utci_m.shape))

    etiq = _etiquetas_recipe(info_ap, n_pasos)

    escritos = []
    if escribir:
        salida = os.path.join(base, "RESULT_REUNIDOS_CSV")
        if not os.path.isdir(salida):
            os.makedirs(salida)

        def _csv(matriz, ruta, prefijo):
            with io.open(ruta, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["%s_%s" % (prefijo, s) for s in etiq])
                for r in matriz:
                    w.writerow([("" if np.isnan(v) else
                                 round(float(v), DECIMALES)) for v in r])
            escritos.append(os.path.basename(ruta))

        _csv(mrt_m, os.path.join(salida, "LB_MRT.csv"), "MRT_LB")
        _csv(utci_m, os.path.join(salida, "LB_UTCI.csv"), "UTCI_LB")
        ruta_o = os.path.join(salida, "LB_orden_grids.csv")
        with io.open(ruta_o, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["fila", "grid_id", "rango_en_grid"])
            for i, (ident, r) in enumerate(orden):
                w.writerow([i, ident, r])
        escritos.append("LB_orden_grids.csv")

        # Las claves de LB_metadata.json se conservan tal cual (en francés):
        # otros scripts pueden leerlas.
        meta = {
            "generado": datetime.datetime.now().isoformat(timespec="seconds"),
            "carpeta_simulacion": base,
            "n_capteurs": int(n_cap), "n_grilles": len(grids),
            "n_pas_de_temps": int(n_pasos), "etiquetas": etiq,
            "periode_analyse": (info_ap or {}).get("analysis_period"),
            "unite": (info_ap or {}).get("unit"),
            "mrt_composantes": list(SUMA_MRT),
            "grilles_sans_utci": len(ausentes),
            "controle_mrt": {"min": float(np.nanmin(mrt_m)),
                             "med": float(np.nanmedian(mrt_m)),
                             "max": float(np.nanmax(mrt_m))},
            "controle_utci": {"min": float(np.nanmin(utci_m)),
                              "med": float(np.nanmedian(utci_m)),
                              "max": float(np.nanmax(utci_m))},
        }
        with io.open(os.path.join(salida, "LB_metadata.json"), "w",
                     encoding="utf-8") as f:
            f.write(json.dumps(meta, indent=2, ensure_ascii=False))
        escritos.append("LB_metadata.json")

    return {"mrt": mrt_m, "utci": utci_m, "n_cap": int(n_cap),
            "n_grilles": len(grids), "n_pasos": int(n_pasos),
            "etiquetas": etiq, "ausentes": len(ausentes),
            "escritos": escritos, "seg": time.time() - t0}


def _media_por_grupo(m, inverso, n_grupos):
    """Media por grupo IGNORANDO los NaN.

    Dividir por el efectivo TOTAL subestimaría los tramos en los que una malla
    no tiene fichero UTCI. Se divide por el efectivo VÁLIDO.
    """
    n_pasos = m.shape[1]
    out = np.full((n_grupos, n_pasos), np.nan, dtype=np.float64)
    for j in range(n_pasos):
        col = m[:, j].astype(np.float64)
        val = ~np.isnan(col)
        suma = np.bincount(inverso, weights=np.where(val, col, 0.0),
                           minlength=n_grupos)
        cnt = np.bincount(inverso, weights=val.astype(np.float64),
                          minlength=n_grupos)
        ok = cnt > 0
        out[ok, j] = suma[ok] / cnt[ok]
    return out


def _cargar_ml(ruta, blanca):
    """GeoJSON ML -> {ID_Segmento: {clave: valor}} + orden de aparición."""
    if not ruta or not os.path.isfile(str(ruta).strip().strip('"')):
        return {}, [], []
    d = _cargar_json(str(ruta).strip().strip('"'))
    feats = d.get("features", d if isinstance(d, list) else [])
    tabla, orden_ml = {}, []
    disponibles = []
    for f in feats:
        p = (f or {}).get("properties") or {}
        k = p.get(CLAVE_ML)
        if k is None:
            continue
        if not disponibles:
            disponibles = [c for c in p.keys() if c != CLAVE_ML]
        sel = blanca if blanca else disponibles
        tabla[str(k)] = dict((c, p.get(c)) for c in sel if c in p)
        orden_ml.append(str(k))
    return tabla, orden_ml, disponibles


def _rango_natural(s):
    """Orden natural: Lav_Seg_2 antes que Lav_Seg_10."""
    p = str(s).rsplit("_", 1)
    return int(p[1]) if len(p) == 2 and p[1].isdigit() else 10 ** 9


# ------------------------------------------------------------------ main
keys = DataTree[object]()
values = DataTree[object]()
mrt = DataTree[object]()
utci = DataTree[object]()
id_out, pt_out, color, categoria = [], [], [], []
n_capteurs = 0
info = "Poner _run en True para leer los resultados."

if _run:
    base, origen_ruta = _resolver_base(carpeta_auto, carpeta_sim)

    # ---- caché: se invalida si cambia la carpeta o si se reescribe grids_info
    ruta_g = os.path.join(base, "initial_results", "conditions",
                          "grids_info.json")
    clave = (base, os.path.getmtime(ruta_g) if os.path.isfile(ruta_g) else 0,
             bool(escribir_csv))
    if sc.sticky.get("_lb_clave") == clave:
        d = sc.sticky["_lb_datos"]
        origen = "caché"
    else:
        d = _construir(base, bool(escribir_csv))
        sc.sticky["_lb_clave"] = clave
        sc.sticky["_lb_datos"] = d
        origen = "lectura de disco"

    # ---- CONTROL BLOQUEANTE: ¿la malla Honeybee es la de GH?
    n_ids = len(id_seg) if id_seg else 0
    if not n_ids:
        raise RuntimeError("id_seg está vacío: agregación por tramo imposible.")
    if n_ids != d["n_cap"]:
        raise RuntimeError(
            "ALINEACIÓN ROTA: %d sensores en los resultados Ladybug, %d "
            "valores en id_seg.\nLa malla enviada a Honeybee no es la "
            "de Puntos_UTCI.py. Cualquier agregación por tramo sería falsa.\n"
            "Comprobar también que id_seg está en List Access Y Flatten."
            % (d["n_cap"], n_ids))

    # ---- agregación de las magnitudes por tramo
    claves_arr = np.array([str(s) for s in id_seg])
    unicos, inverso = np.unique(claves_arr, return_inverse=True)
    n_t = len(unicos)
    a_mrt = _media_por_grupo(d["mrt"], inverso, n_t)
    a_utci = _media_por_grupo(d["utci"], inverso, n_t)

    # ---- baricentro geométrico por tramo
    # pt_medio está agrupado por id_medio (1 por trozo drapeado), no por
    # id_seg (1 por sensor): las dos listas NO tienen la misma longitud.
    bary = {}
    if pt_medio and id_medio:
        if len(pt_medio) != len(id_medio):
            raise RuntimeError(
                "pt_medio (%d) e id_medio (%d) no tienen la misma longitud."
                % (len(pt_medio), len(id_medio)))
        acc = {}
        for p, k in zip(pt_medio, id_medio):
            if p is None:
                continue
            s = acc.setdefault(str(k), [0.0, 0.0, 0.0, 0])
            s[0] += p.X
            s[1] += p.Y
            s[2] += p.Z
            s[3] += 1
        for k, s in acc.items():
            if s[3]:
                bary[k] = Point3d(s[0] / s[3], s[1] / s[3], s[2] / s[3])

    # ---- unión con el GeoJSON ML
    blanca = [str(x).strip() for x in (claves_ml or []) if str(x).strip()]
    tabla_ml, orden_ml, dispo_ml = _cargar_ml(geojson, blanca)
    if not tabla_ml:
        raise RuntimeError("GeoJSON ML ilegible o sin '%s': %s"
                           % (CLAVE_ML, geojson))
    faltan = [str(s) for s in unicos if str(s) not in tabla_ml]
    if faltan:
        raise RuntimeError(
            "%d tramos de id_seg no figuran en el GeoJSON ML (p. ej. %s).\n"
            "Los dos conjuntos no describen el mismo barrio: comprobar que "
            "id_seg procede de %s."
            % (len(faltan), ", ".join(faltan[:5]), os.path.basename(str(geojson))))
    cols_ml = blanca if blanca else dispo_ml

    # ---- instantes a exportar como atributos
    hs = [int(h) for h in (horas or [])] or [d["n_pasos"] - 1]
    for h in hs:
        if not (0 <= h < d["n_pasos"]):
            raise RuntimeError("horas contiene %d, fuera del rango 0..%d"
                               % (h, d["n_pasos"] - 1))
    et = [str(e) for e in (etiquetas or [])]
    if len(et) != len(hs):
        et = [d["etiquetas"][h] for h in hs]
    r_ml = int(hora_ml) if hora_ml is not None else 0
    if not (0 <= r_ml < len(hs)):
        raise RuntimeError("hora_ml = %s fuera del rango 0..%d" % (hora_ml, len(hs) - 1))
    j_ml = hs[r_ml]

    # ---- orden de salida: el del GeoJSON, si no orden natural
    pos = dict((str(s), i) for i, s in enumerate(unicos))
    orden_t = [pos[s] for s in orden_ml if s in pos]
    if len(orden_t) != n_t:
        orden_t = sorted(range(n_t), key=lambda i: _rango_natural(unicos[i]))
        origen_orden = "orden natural"
    else:
        origen_orden = "orden del GeoJSON ML"

    # ---- construcción de los atributos, tramo a tramo
    sin_punto = 0
    reparto, n_dmrt, n_dutci = {}, 0, 0
    for rama, i in enumerate(orden_t):
        t = str(unicos[i])
        p = GH_Path(rama)

        mrt.AddRange([float(v) for v in a_mrt[i]], p)
        utci.AddRange([float(v) for v in a_utci[i]], p)
        id_out.append(t)

        pt = bary.get(t)
        if pt is None:
            sin_punto += 1
        pt_out.append(pt)

        u_ml = float(a_utci[i, j_ml])
        nombre, rgb = _clasificar(u_ml)
        categoria.append(nombre)
        color.append(Color.FromArgb(rgb[0], rgb[1], rgb[2]))
        reparto[nombre] = reparto.get(nombre, 0) + 1

        k_l = [CLAVE_ML]
        v_l = [t]

        ml = tabla_ml[t]
        for c in cols_ml:
            k_l.append(c)
            v_l.append(_net(ml.get(c)))

        for h, e in zip(hs, et):
            k_l.append("MRT_LB_%s" % e)
            v_l.append(_net(round(float(a_mrt[i, h]), DECIMALES)))
            k_l.append("UTCI_LB_%s" % e)
            v_l.append(_net(round(float(a_utci[i, h]), DECIMALES)))

        # diferencias en el instante de referencia ML — el objeto mismo del TFM
        ref_m, ref_u = ml.get(REF_MRT_ML), ml.get(REF_UTCI_ML)
        d_mrt = (round(float(a_mrt[i, j_ml]) - float(ref_m), DECIMALES)
                 if _ml_valido(ref_m) and not math.isnan(a_mrt[i, j_ml]) else None)
        d_utci = (round(u_ml - float(ref_u), DECIMALES)
                  if _ml_valido(ref_u) and not math.isnan(u_ml) else None)
        n_dmrt += 1 if d_mrt is not None else 0
        n_dutci += 1 if d_utci is not None else 0
        k_l += ["D_MRT", "D_UTCI", "Stress_LB"]
        v_l += [_net(d_mrt), _net(d_utci), nombre]

        keys.AddRange(k_l, p)
        values.AddRange(v_l, p)

    n_capteurs = d["n_cap"]
    info = "\n".join([
        "Carpeta: %s" % base,
        "Origen: %s | %s (%.1f s)" % (origen_ruta, origen, d["seg"]),
        "Mallas %d | sensores %d | instantes %d"
        % (d["n_grilles"], d["n_cap"], d["n_pasos"]),
        "Instantes del recipe: %s" % ", ".join(d["etiquetas"]),
        "Exportados: %s (referencia ML: %s)"
        % (", ".join("%s[%d]" % (e, h) for h, e in zip(hs, et)), et[r_ml]),
        "Orden: %s" % origen_orden,
        "Tramos: %d | sin punto medio: %d" % (len(id_out), sin_punto),
        "Atributos ML unidos: %d claves" % len(cols_ml),
        "D_MRT calculables: %d / %d   D_UTCI: %d / %d"
        % (n_dmrt, len(id_out), n_dutci, len(id_out)),
        "Mallas sin fichero UTCI: %d" % d["ausentes"],
        "MRT  mín %.2f | med %.2f | máx %.2f"
        % (np.nanmin(d["mrt"]), np.nanmedian(d["mrt"]), np.nanmax(d["mrt"])),
        "UTCI mín %.2f | med %.2f | máx %.2f"
        % (np.nanmin(d["utci"]), np.nanmedian(d["utci"]), np.nanmax(d["utci"])),
        "Reparto: " + " | ".join("%s %d" % (n, c) for n, c
                                 in sorted(reparto.items(),
                                           key=lambda x: -x[1])),
        "CSV escritos: %s" % (", ".join(d["escritos"]) or "ninguno"),
    ])