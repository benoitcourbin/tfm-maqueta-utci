# tfm-maqueta-utci

Cadena reproducible para generar una **maqueta 3D urbana** (suelo, edificios,
arbolado) y alimentar una simulación **UTCI con Ladybug / Radiance**.

Desarrollada sobre Lavapiés (Madrid) para el TFM del Máster en IA aplicada a la
construcción (Zigurat / UB). Está parametrizada por zona: otro barrio de Madrid
sólo necesita un fichero de configuración.

**Código aquí. Datos en Google Drive.** Este repositorio no contiene ningún
ráster ni maqueta: sólo el código, la configuración de zonas y los informes.

## Uso

```bash
git clone https://github.com/benoitcourbin/tfm-maqueta-utci.git
cd tfm-maqueta-utci
pip install -r requirements.txt

python run_maqueta.py --zona lavapies
```

En Colab, el cuaderno `colab/TFM_Maqueta.ipynb` hace las tres cosas: montar el
Drive, actualizar el repositorio y lanzar la cadena.

La ejecución **no se detiene ante un fallo**: cada paso queda registrado y el
informe final dice qué falta y cómo obtenerlo a mano.

```
DOCS/INFORMES/informe_ejecucion_<zona>.md    qué ha pasado y qué hacer
MAQUETA/<zona>/manifest_<zona>.json          lo que lee Grasshopper
```

## Estructura

```
config/zonas/<zona>.json      bbox, EAP, distritos, umbrales   ← lo único a editar
src/tfm/rutas.py              arborescencia del Drive
src/tfm/estado.py             pasos, manifiesto, informe de incidencias
src/tfm/proveedores/madrid.py catálogo de fuentes de una ciudad
src/tfm/pasos/capas_nb.py     ejecuta las capas del cuaderno verificado
src/tfm/pasos/suelo.py        suelo unificado (viario + relleno + bordillos)
run_maqueta.py                orquestador
exportar_resultados.py        Ladybug → Drive (original + CSV)
gh/                           componentes GHPython (Rhino 8)
colab/TFM_Maqueta.ipynb       punto de entrada en Colab
INFORMES/                     decisiones e informes del proyecto
```

## Nueva zona

1. Copiar `config/zonas/lavapies.json` a `<zona>.json` y ajustar `bbox`,
   `origen_local`, `eap`, `distritos`.
2. `python run_maqueta.py --zona <zona>`.
3. En Grasshopper, escribir el nombre de la zona en el componente `gh_cache`.

Otra ciudad necesita además un módulo en `src/tfm/proveedores/`: las URLs y los
formatos cambian. Hoy sólo existe `madrid.py`.

## Grasshopper

| Componente | Papel |
|---|---|
| `gh/gh_cache.py` | lee el manifiesto y entrega las rutas de cada capa |
| `gh/gh_load_suelo.py` | suelo (sustituye topo + viario); salida `suelo` para el drapeado |
| `gh/gh_load_edificios.py` | LOD1 + superestructuras en un solo componente |
| `gh/gh_load_arboles.py` | arbolado |

## Fuentes de datos

Madrid: Geoportal (Multipatch 3D, T03 Viario, MDT, MDS) y Catastro INSPIRE.
El catálogo con las URLs exactas está en `src/tfm/proveedores/madrid.py`.

## Licencia

MIT para el código. Los datos siguen la licencia de cada organismo.
