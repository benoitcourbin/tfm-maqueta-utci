"""
Exporta capas bakeadas de Rhino a IFC4 (.ifc) vía ifcopenshell.api,
con atributos de user text en un Pset_TFM_UTCI y colores por capa/clave
en IfcStyledItem.
Ejecutar fuera de Rhino: VSCode / terminal.
[SOURCE: ninguna — script propio; API ifcopenshell verificada en
docs.ifcopenshell.org (pset, geometry.add_mesh_representation, style,
spatial.assign_container), fuera del alcance de FUENTES_VALIDADAS_TFM.md]
"""

import os
import rhino3dm
import ifcopenshell
import ifcopenshell.api.project
import ifcopenshell.api.root
import ifcopenshell.api.unit
import ifcopenshell.api.context
import ifcopenshell.api.aggregate
import ifcopenshell.api.spatial
import ifcopenshell.api.geometry
import ifcopenshell.api.pset
import ifcopenshell.api.style

# --- Configuración -----------------------------------------------------
RUTA_3DM = r"G:\Mi unidad\TFM_UTCI_Lavapies_2026\04_VISUALIZACION\Modelo_3D\Rhino\TFM_Lavapies_19_09_26_ML +Urba.3dm"
RUTA_IFC = r"G:\Mi unidad\TFM_UTCI_Lavapies_2026\04_VISUALIZACION\Modelo_3D\ifc\maqueta_lavapies.ifc"

# capa -> (IfcClass, PredefinedType o None, ObjectType o None)
CLASES_POR_CAPA = {
    "Urba::Suelos":         ("IfcGeographicElement",    "TERRAIN",     None),
    "Urba::Edificios":      ("IfcBuildingElementProxy", None,          None),
    "Urba::Arboles":        ("IfcGeographicElement",    "USERDEFINED", "Arbol"),
    "ML::UTCI_Segmentos":   ("IfcBuildingElementProxy", None,          "Sensor_UTCI"),
    "LB::MRT_Puntos_v6":    ("IfcBuildingElementProxy", None,          "Sensor_UTCI"),
}

# --- Colores por capa ------------------------------------------------------
# [SOURCE: capturas usuario — légendes GH "Key_material" (Suelos), "Copa/Tronco"
# (Arboles), "UTCI Stress Colors" (ML/LB)]
_PALETA_UTCI = {
    "no-data":                 (200, 200, 200),
    "Slight cold stress":      (0, 176, 80),
    "No thermal stress":       (146, 208, 80),
    "Moderate heat stress":    (255, 255, 0),
    "strong heat stress":      (255, 192, 0),
    "very strong heat stress": (255, 0, 0),
    "extreme heat stress":     (128, 0, 0),
}

COLOR_CONFIG = {
    "Urba::Suelos": (
        "material",
        {
            "hormigon_baldosa": (198, 193, 183),
            "hormigon":         (165, 163, 158),
            "adoquin_granito":  (105, 100, 95),
            "asfalto":          (45, 45, 48),
            "suelo":            (67, 145, 48),
        },
    ),
    "Urba::Arboles": (
        "clase",
        {
            "Copa":   (110, 207, 48),
            "Tronco": (108, 84, 0),
        },
    ),
    "ML::UTCI_Segmentos": ("Stress_Category", _PALETA_UTCI),
    "LB::MRT_Puntos_v6":  ("Stress_Category", _PALETA_UTCI),
    # "Urba::Edificios" : pas d'entrée → pas de style assigné, couleur par défaut du viewer
}

# --- Utilidades rhino3dm --------------------------------------------------

def a_malla(geometria):
    if isinstance(geometria, rhino3dm.Mesh):
        return geometria
    return None


def user_text_dict(attrs):
    d = {}
    try:
        for k, v in attrs.GetUserStrings():
            d[k] = v
    except AttributeError:
        pass
    return d


def ruta_capa_por_id(capa, id_a_capa):
    partes = [capa.Name]
    actual = capa
    while True:
        padre_id = actual.ParentLayerId
        if padre_id is None or str(padre_id) == "00000000-0000-0000-0000-000000000000":
            break
        actual = id_a_capa.get(padre_id)
        if actual is None:
            break
        partes.insert(0, actual.Name)
    return "::".join(partes)


def capa_incluida(nombre_capa_completo):
    return any(
        nombre_capa_completo == c or nombre_capa_completo.startswith(c + "::")
        for c in CLASES_POR_CAPA
    )


def capa_config(nombre_capa_completo):
    """Retourne la clé de CLASES_POR_CAPA correspondant à la capa (exacte ou parente)."""
    for c in CLASES_POR_CAPA:
        if nombre_capa_completo == c or nombre_capa_completo.startswith(c + "::"):
            return c
    return None


# --- Lectura del .3dm ------------------------------------------------------

print("Leyendo .3dm...")
modelo3dm = rhino3dm.File3dm.Read(RUTA_3DM)
if modelo3dm is None:
    print("Existe:", os.path.exists(RUTA_3DM))
    raise SystemExit("Lectura fallida — verificar ruta o cerrar el archivo en Rhino")

capas = {c.Index: c for c in modelo3dm.Layers}
id_a_capa = {c.Id: c for c in modelo3dm.Layers}

objetos_validos = []  # (mesh, nombre_capa, atributos_dict)
for obj in modelo3dm.Objects:
    capa = capas.get(obj.Attributes.LayerIndex)
    if capa is None:
        continue
    nombre_capa = ruta_capa_por_id(capa, id_a_capa)
    if not capa_incluida(nombre_capa):
        continue
    malla = a_malla(obj.Geometry)
    if malla is None or len(malla.Vertices) == 0:
        continue
    attrs = user_text_dict(obj.Attributes)
    attrs["_layer"] = nombre_capa
    objetos_validos.append((malla, nombre_capa, attrs))

print(f"Objetos exportables: {len(objetos_validos)}")

# --- Construcción del IFC ---------------------------------------------------

model = ifcopenshell.api.project.create_file()
project = ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name="TFM_Lavapies_UTCI")
ifcopenshell.api.unit.assign_unit(model)

model3d = ifcopenshell.api.context.add_context(model, context_type="Model")
body = ifcopenshell.api.context.add_context(
    model, context_type="Model", context_identifier="Body",
    target_view="MODEL_VIEW", parent=model3d,
)

site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Lavapies_1200x1200")
ifcopenshell.api.aggregate.assign_object(model, products=[site], relating_object=project)

estilos_cache = {}  # (nombre_capa_config, valor_clave) -> style entity


def obtener_estilo(nombre_capa, attrs):
    clave_config = capa_config(nombre_capa)
    config = COLOR_CONFIG.get(clave_config)
    if config is None:
        return None
    clave, paleta = config
    valor = attrs.get(clave)
    if valor is None:
        return None
    rgb = paleta.get(valor)
    if rgb is None:
        return None
    cache_key = (clave_config, valor)
    if cache_key in estilos_cache:
        return estilos_cache[cache_key]
    r, g, b = (c / 255.0 for c in rgb)
    style = ifcopenshell.api.style.add_style(model)
    ifcopenshell.api.style.add_surface_style(
        model, style=style, ifc_class="IfcSurfaceStyleShading",
        attributes={"SurfaceColour": {"Name": None, "Red": r, "Green": g, "Blue": b}},
    )
    estilos_cache[cache_key] = style
    return style


for i, (malla, nombre_capa, attrs) in enumerate(objetos_validos):
    clave_config = capa_config(nombre_capa)
    ifc_class, predefined_type, object_type = CLASES_POR_CAPA[clave_config]

    verts = [(v.X, v.Y, v.Z) for v in malla.Vertices]
    faces = []
    for f in malla.Faces:
        a, b_, c, d = f
        if c == d:
            faces.append((a, b_, c))
        else:
            faces.append((a, b_, c))
            faces.append((a, c, d))
    if not faces:
        continue

    nombre_obj = attrs.get("id") or attrs.get("id_3d") or f"{nombre_capa}_{i}"
    elemento = ifcopenshell.api.root.create_entity(model, ifc_class=ifc_class, name=str(nombre_obj))
    if predefined_type is not None:
        elemento.PredefinedType = predefined_type
    if object_type is not None:
        elemento.ObjectType = object_type

    representation = ifcopenshell.api.geometry.add_mesh_representation(
        model, context=body, vertices=[verts], faces=[faces],
    )
    ifcopenshell.api.geometry.assign_representation(model, product=elemento, representation=representation)
    ifcopenshell.api.geometry.edit_object_placement(model, product=elemento)
    ifcopenshell.api.spatial.assign_container(model, products=[elemento], relating_structure=site)

    if attrs:
        pset = ifcopenshell.api.pset.add_pset(model, product=elemento, name="Pset_TFM_UTCI")
        ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=attrs)

    estilo = obtener_estilo(nombre_capa, attrs)
    if estilo is not None:
        ifcopenshell.api.style.assign_representation_styles(
            model, shape_representation=representation, styles=[estilo],
        )

    if (i + 1) % 1000 == 0:
        print(f"  {i + 1}/{len(objetos_validos)}")

os.makedirs(os.path.dirname(RUTA_IFC), exist_ok=True)
model.write(RUTA_IFC)
print(f"Exportado: {RUTA_IFC}")