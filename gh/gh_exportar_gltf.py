"""
Exporta capas bakeadas de Rhino a glTF binario (.glb) con atributos
de user text embebidos en 'extras' por nodo.
Ejecutar fuera de Rhino: VSCode / terminal, con rhino3dm + pygltflib instalados.
[SOURCE: ninguna — script propio, fuera del alcance de FUENTES_VALIDADAS_TFM.md]
"""

import os
import rhino3dm
from pygltflib import (
    GLTF2, Scene, Node, Mesh, Primitive, Buffer, BufferView, Accessor,
    Asset, FLOAT, UNSIGNED_INT, ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER
)
import numpy as np

# --- Configuración -----------------------------------------------------
RUTA_3DM = r"G:\Mi unidad\TFM_UTCI_Lavapies_2026\04_VISUALIZACION\Modelo_3D\Rhino\TFM_Lavapies_19_09_26_ML +Urba.3dm"
RUTA_GLB = r"G:\Mi unidad\TFM_UTCI_Lavapies_2026\04_VISUALIZACION\Modelo_3D\web\maqueta_lavapies.glb"

CAPAS_INCLUIDAS = [
    "Urba::Arboles",
    "Urba::Suelos",
    "Urba::Edificios",
    "ML::UTCI_Segmentos",
    "LB::MRT_Puntos_v6",
]

# --- Utilidades ----------------------------------------------------------

def capa_incluida(nombre_capa_completo):
    """Verdadero si el objeto pertenece a una de las capas (o subcapas) incluidas."""
    return any(
        nombre_capa_completo == c or nombre_capa_completo.startswith(c + "::")
        for c in CAPAS_INCLUIDAS
    )


def a_malla(geometria):
    """Convierte a Mesh si hace falta; None si no es convertible."""
    if isinstance(geometria, rhino3dm.Mesh):
        return geometria
    if isinstance(geometria, (rhino3dm.Brep, rhino3dm.Extrusion)):
        # rhino3dm standalone no trae motor de mallado: se omite el objeto.
        return None
    return None


def user_text_dict(attrs):
    """Extrae todos los pares clave/valor de user text de un objeto."""
    d = {}
    try:
        for k, v in attrs.GetUserStrings():
            d[k] = v
    except AttributeError:
        pass
    return d


# --- Lectura del .3dm ------------------------------------------------------

print("Leyendo .3dm (puede tardar según el volumen)...")
modelo = rhino3dm.File3dm.Read(RUTA_3DM)
if modelo is None:
    print("Existe:", os.path.exists(RUTA_3DM))
    print("Version rhino3dm:", rhino3dm.__version__)
    raise SystemExit("Lectura fallida — verificar ruta o cerrar el archivo en Rhino")

capas = {c.Index: c for c in modelo.Layers}
id_a_capa = {c.Id: c for c in modelo.Layers}


def ruta_capa_por_id(capa):
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


objetos_validos = []  # (mesh, nombre_capa, atributos_dict)

for obj in modelo.Objects:
    capa = capas.get(obj.Attributes.LayerIndex)
    if capa is None:
        continue
    nombre_capa = ruta_capa_por_id(capa)
    if not capa_incluida(nombre_capa):
        continue
    malla = a_malla(obj.Geometry)
    if malla is None or len(malla.Vertices) == 0:
        continue
    attrs = user_text_dict(obj.Attributes)
    attrs["_layer"] = nombre_capa
    objetos_validos.append((malla, nombre_capa, attrs))

print(f"Objetos exportables: {len(objetos_validos)}")

# --- Construcción del glTF ------------------------------------------------

os.makedirs(os.path.dirname(RUTA_GLB), exist_ok=True)

gltf = GLTF2(asset=Asset(version="2.0"), scenes=[Scene(nodes=[])], scene=0)
gltf.buffers = []
gltf.bufferViews = []
gltf.accessors = []
gltf.meshes = []
gltf.nodes = []

buffer_bytes = bytearray()

for malla, nombre_capa, attrs in objetos_validos:
    verts = np.array(
        [[v.X, v.Y, v.Z] for v in malla.Vertices], dtype=np.float32
    )
    faces = []
    for f in malla.Faces:
        a, b, c, d = f
        if c == d:
            faces.append([a, b, c])
        else:
            faces.append([a, b, c])
            faces.append([a, c, d])
    idx = np.array(faces, dtype=np.uint32).flatten()

    if len(idx) == 0:
        continue

    offset_v = len(buffer_bytes)
    buffer_bytes.extend(verts.tobytes())
    offset_i = len(buffer_bytes)
    buffer_bytes.extend(idx.tobytes())
    while len(buffer_bytes) % 4 != 0:
        buffer_bytes.extend(b"\x00")

    bv_v = BufferView(
        buffer=0, byteOffset=offset_v, byteLength=int(verts.nbytes),
        target=ARRAY_BUFFER,
    )
    bv_i = BufferView(
        buffer=0, byteOffset=offset_i, byteLength=int(idx.nbytes),
        target=ELEMENT_ARRAY_BUFFER,
    )
    gltf.bufferViews.append(bv_v)
    idx_bv = len(gltf.bufferViews) - 1
    gltf.bufferViews.append(bv_i)
    idx_bi = len(gltf.bufferViews) - 1

    acc_v = Accessor(
        bufferView=idx_bv, componentType=FLOAT, count=len(verts),
        type="VEC3",
        min=verts.min(axis=0).tolist(), max=verts.max(axis=0).tolist(),
    )
    acc_i = Accessor(
        bufferView=idx_bi, componentType=UNSIGNED_INT, count=len(idx),
        type="SCALAR",
    )
    gltf.accessors.append(acc_v)
    acc_idx_v = len(gltf.accessors) - 1
    gltf.accessors.append(acc_i)
    acc_idx_i = len(gltf.accessors) - 1

    prim = Primitive(attributes={"POSITION": acc_idx_v}, indices=acc_idx_i)
    mesh = Mesh(primitives=[prim])
    gltf.meshes.append(mesh)
    mesh_idx = len(gltf.meshes) - 1

    nombre_nodo = attrs.get("id") or attrs.get("id_3d") or nombre_capa
    node = Node(mesh=mesh_idx, name=str(nombre_nodo), extras=attrs)
    gltf.nodes.append(node)
    gltf.scenes[0].nodes.append(len(gltf.nodes) - 1)

gltf.buffers.append(Buffer(byteLength=len(buffer_bytes)))
gltf.set_binary_blob(bytes(buffer_bytes))

gltf.save_binary(RUTA_GLB)
print(f"Exportado: {RUTA_GLB}")