# tfm-maqueta-utci

Cadena reproducible para generar una **maqueta 3D urbana** (suelo, edificios,
arbolado) y alimentar una simulación **UTCI con Ladybug / Radiance**.

Desarrollada sobre Lavapiés (Madrid) para el TFM del Máster en IA aplicada a la
construcción (Zigurat / UB). Está parametrizada por zona: otro barrio de Madrid
sólo necesita un fichero de configuración.

**Código aquí. Datos en Google Drive.** Este repositorio no contiene ningún
ráster ni maqueta: sólo el código y la configuración de zonas.

## Fuente de referencia

La copia de referencia del código es la carpeta del Drive del equipo
`TFM_UTCI_Lavapies_2026/02_CODIGO/pipeline/`. **No se edita el código en
GitHub**: se edita en el Drive y se publica con `colab/publicar_github.ipynb`.

## Uso

En Colab, el cuaderno `colab/TFM_Maqueta.ipynb` monta el Drive, actualiza el
repositorio y lanza la cadena. En local:

```bash
git clone https://github.com/benoitcourbin/tfm-maqueta-utci.git
cd tfm-maqueta-utci
pip install -r requirements.txt
python run_maqueta.py --zona lavapies
```

La ejecución **no se detiene ante un fallo**: cada paso queda registrado y el
informe final dice qué falta y cómo obtenerlo a mano.

```
DOCS/INFORMES/informe_ejecucion_<zona>.md    qué ha pasado y qué hacer
MAQUETA/<zona>/manifest_<zona>.json          lo que lee Grasshopper
```

## Publicar cambios en GitHub (cualquier miembro del equipo)

Requisitos, una sola vez: ser colaborador del repositorio, tener el acceso
directo `TFM_UTCI_Lavapies_2026` en *Mi unidad* y un token de GitHub guardado
en los Secretos de Colab con el nombre `GITHUB_TOKEN`.

1. Abrir `colab/publicar_github.ipynb` y ejecutar la celda **1 · Control**:
   muestra los cambios, no envía nada.
2. Revisar la lista. Escribir el mensaje y ejecutar la celda **2 · Publicar**.

## Estructura

```
config/zonas/<zona>.json      centro, distritos, umbrales; bbox y EAP derivados
config/zonas/ml/              fichas de zona exportadas por el cuaderno ML
config/especies_arbolado.json forma de copa y ratio de follaje por especie (hipótesis)
src/tfm/rutas.py              arborescencia del Drive; deriva bbox, origen_local y EAP
src/tfm/estado.py             pasos, manifiesto, informe de incidencias
src/tfm/proveedores/madrid.py catálogo de fuentes de una ciudad
src/tfm/pasos/capas_nb.py     ejecuta las capas del cuaderno verificado
src/tfm/pasos/suelo.py        suelo unificado (viario + relleno + bordillos)
src/tfm/pasos/arbolado.py     inventario municipal → arboles_<zona>_clean.csv
run_maqueta.py                orquestador
exportar_resultados.py        Ladybug → Drive (original + CSV)
gh/                           componentes GHPython (Rhino 8)
colab/TFM_Maqueta.ipynb       punto de entrada en Colab
colab/publicar_github.ipynb   publicación Drive → GitHub
```

## Nueva zona

1. Copiar `config/zonas/lavapies.json` a `<zona>.json`. Ajustar `zona`,
   `centro {lat, lon}`, `radio_m` y `distritos`. Si el equipo ML ha exportado
   la ficha de zona, dejarla en `config/zonas/ml/` y escribir su nombre en
   `zona_ml`. **Borrar** `bbox`, `origen_local` y `eap`: `rutas.py` los deriva.
   - bbox = `dsm_extension` de la ficha ML, la extensión exacta de los rásters
     de SOLWEIG (en Lavapiés, 1 402 m de lado: **no** es centro ± 600 m);
     sin ficha, cuadrado de lado 2 × `radio_m` centrado en `centro`;
   - EAP = `centro`; `origen_local` = su proyección en EPSG:25830.

   Un valor presente en el json prevalece sobre el derivado: Lavapiés conserva
   sus valores explícitos mientras el run v5 sea la referencia.
2. `python run_maqueta.py --zona <zona>`.
3. En Grasshopper, escribir el nombre de la zona en el componente `gh_cache`.

Otra ciudad necesita además un módulo en `src/tfm/proveedores/`: las URLs y los
formatos cambian. Hoy sólo existe `madrid.py`.

## Grasshopper

| Componente | Papel |
|---|---|
| `gh/gh_cache.py` | lee el manifiesto y entrega rutas, EAP y bbox de la zona |
| `gh/gh_load_suelo.py` | suelo (sustituye topo + viario); salida `suelo` para el drapeado |
| `gh/gh_load_edificios.py` | LOD1 + superestructuras en un solo componente |
| `gh/gh_load_arboles.py` | arbolado |
| `gh/Drape_CurvesOnMesh.py` | proyecta los ejes de calle sobre el suelo |
| `gh/gh_puntos_utci.py` | malla de sensores por tramo |
| `gh/gh_utci_lavapies.py` | lee los resultados Ladybug, agrega por tramo y une con el GeoJSON ML |
| `gh/gh_exportar.py` | lanzador de `exportar_resultados.py` desde Grasshopper |
| `gh/gh_exportar_ifc.py`, `gh/gh_exportar_gltf.py` | exportaciones IFC y glTF — pendientes de documentar |

El bake de las capas se hace con EleFront.

## Fuentes de datos

Madrid: Geoportal (Multipatch 3D, T03 Viario, MDT, MDS), Catastro INSPIRE e
inventario de arbolado de datos.madrid.es (conjunto 300761-0).
El catálogo con las URLs exactas está en `src/tfm/proveedores/madrid.py`.

## Licencia

MIT para el código. Los datos siguen la licencia de cada organismo.
