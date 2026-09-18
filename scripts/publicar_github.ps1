# publicar_github.ps1 — crea el repositorio en GitHub y sube el código.
# Ejecutar UNA vez desde PowerShell, en la carpeta del repositorio.
#   cd "G:\Mi unidad\TFM_UTCI_Lavapies_2026\04_VISUALIZACION\Modelo_3D\pipeline"
#   .\scripts\publicar_github.ps1
#
# Requiere git y, para crear el repositorio sin pasar por el navegador, gh
# (https://cli.github.com/). Sin gh, crear el repositorio a mano en GitHub y
# lanzar sólo la parte 'git remote add' + 'git push'.

$ErrorActionPreference = 'Stop'
$NOMBRE  = 'tfm-maqueta-utci'
$USUARIO = 'benoitcourbin'
$DESC    = 'Maqueta 3D urbana + simulacion UTCI Ladybug — TFM Zigurat/UB'

if (-not (Test-Path '.git')) {
    git init
    git branch -M main
}
git add .
git commit -m "Cadena parametrizada: rutas, proveedores, pasos, manifiesto e informes" 2>$null

if (Get-Command gh -ErrorAction SilentlyContinue) {
    gh auth status 2>$null; if ($LASTEXITCODE -ne 0) { gh auth login }
    gh repo create "$USUARIO/$NOMBRE" --public --description $DESC --source . --remote origin --push
} else {
    Write-Host "gh no esta instalado. Crear el repositorio en https://github.com/new con el nombre $NOMBRE y luego:"
    Write-Host "  git remote add origin https://github.com/$USUARIO/$NOMBRE.git"
    Write-Host "  git push -u origin main"
}
