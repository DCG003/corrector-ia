<#
.SYNOPSIS
    Instalador de Corrector IA: prepara el entorno de Python, el frontend y
    descarga los modelos de Ollama necesarios.

.DESCRIPTION
    Ejecuta, en este orden:
      1. Comprueba los requisitos (Python 3.10+, Node.js 18+, Ollama).
      2. Crea el entorno virtual .venv e instala las dependencias de Python.
      3. Instala el OCR opcional (glmocr) para exámenes escaneados.
      4. Instala las dependencias del frontend con npm.
      5. Descarga de Ollama los modelos: evaluador, embeddings y OCR.

    El script es idempotente: se puede volver a lanzar sin problemas.

.PARAMETER ModeloEvaluador
    Modelo de Ollama que puntúa las respuestas. Por defecto 'gemma3:12b'
    (recomendado con 12 GB de VRAM o más). Con menos VRAM usa 'gemma3:4b'.

.PARAMETER SinOcr
    No instala el OCR (ni el paquete glmocr ni el modelo glm-ocr). Ahorra unos
    5 GB de descarga. Solo podrás corregir PDFs digitales, no escaneados.

.PARAMETER SoloDependencias
    Instala Python/npm pero no descarga ningún modelo de Ollama.

.PARAMETER SoloModelos
    Solo descarga los modelos de Ollama, sin tocar Python ni npm.

.EXAMPLE
    .\install.ps1
    Instalación completa con la configuración recomendada.

.EXAMPLE
    .\install.ps1 -ModeloEvaluador gemma3:4b
    Instalación para equipos con poca VRAM (menos de 12 GB).

.EXAMPLE
    .\install.ps1 -SinOcr
    Instalación ligera, sin soporte para exámenes escaneados.
#>
[CmdletBinding()]
param(
    [string]$ModeloEvaluador = "gemma3:12b",
    [string]$ModeloEmbedding = "embeddinggemma",
    [string]$ModeloOcr = "glm-ocr",
    [switch]$SinOcr,
    [switch]$SoloDependencias,
    [switch]$SoloModelos
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$Raiz = $PSScriptRoot
if (-not $Raiz) { $Raiz = (Get-Location).Path }

# ------------------------------------------------------------------ utilidades
$script:Avisos = @()

function Write-Titulo($texto) {
    Write-Host ""
    Write-Host "  $texto" -ForegroundColor White
    Write-Host "  $('-' * $texto.Length)" -ForegroundColor DarkGray
}
function Write-Paso($texto)  { Write-Host "  ->  $texto" -ForegroundColor Gray }
function Write-Ok($texto)    { Write-Host "  OK  $texto" -ForegroundColor Green }
function Write-Aviso($texto) {
    Write-Host "  !!  $texto" -ForegroundColor Yellow
    $script:Avisos += $texto
}
function Write-Fallo($texto) { Write-Host "  XX  $texto" -ForegroundColor Red }

function Test-Comando($nombre) {
    $cmd = Get-Command $nombre -ErrorAction SilentlyContinue
    return $null -ne $cmd
}

function Get-VersionNumerica($texto) {
    # Extrae "3.12.2" de una cadena tipo "Python 3.12.2" y lo devuelve como [version]
    $m = [regex]::Match($texto, '(\d+)\.(\d+)(\.(\d+))?')
    if (-not $m.Success) { return $null }
    $patch = "0"
    if ($m.Groups[4].Success) { $patch = $m.Groups[4].Value }
    return [version]("{0}.{1}.{2}" -f $m.Groups[1].Value, $m.Groups[2].Value, $patch)
}

Write-Host ""
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host "    Corrector IA - instalacion del entorno" -ForegroundColor Cyan
Write-Host "  ============================================" -ForegroundColor Cyan

# ------------------------------------------------------------------ 1. requisitos
Write-Titulo "1. Comprobando requisitos"

# --- Python
$PythonExe = $null
$PythonArgsPrefijo = @()
foreach ($candidato in @("py", "python", "python3")) {
    if (-not (Test-Comando $candidato)) { continue }
    $salida = ""
    try {
        if ($candidato -eq "py") {
            $salida = (& $candidato -3 --version) | Out-String
        } else {
            $salida = (& $candidato --version) | Out-String
        }
    } catch {
        continue
    }
    $ver = Get-VersionNumerica $salida
    if ($null -ne $ver -and $ver -ge [version]"3.10.0") {
        $PythonExe = $candidato
        if ($candidato -eq "py") { $PythonArgsPrefijo = @("-3") }
        Write-Ok "Python $ver detectado ($candidato)"
        break
    }
}
if (-not $PythonExe -and -not $SoloModelos) {
    Write-Fallo "No se ha encontrado Python 3.10 o superior."
    Write-Host "      Instalalo desde https://www.python.org/downloads/ marcando 'Add to PATH'."
    exit 1
}

# --- Node
if (Test-Comando "node") {
    $verNode = $null
    try { $verNode = Get-VersionNumerica ((& node --version) | Out-String) } catch {}
    if ($null -ne $verNode -and $verNode -ge [version]"18.0.0") {
        Write-Ok "Node.js $verNode detectado"
    } else {
        Write-Aviso "Node.js $verNode es antiguo; se recomienda la version 18 o superior."
    }
} elseif (-not $SoloModelos) {
    Write-Fallo "No se ha encontrado Node.js (necesario para el frontend)."
    Write-Host "      Instalalo desde https://nodejs.org/"
    exit 1
}

# --- Ollama
$TieneOllama = Test-Comando "ollama"
if ($TieneOllama) {
    Write-Ok "Ollama detectado"
} else {
    Write-Aviso "No se ha encontrado Ollama. Descargalo en https://ollama.com/download"
    Write-Host "      Sin Ollama la app arranca, pero no puede corregir nada."
}

# --- VRAM (informativo)
if (Test-Comando "nvidia-smi") {
    try {
        $vramTexto = (& nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | Select-Object -First 1)
        $vramGb = [math]::Round(([int]$vramTexto) / 1024, 1)
        Write-Ok "GPU NVIDIA con $vramGb GB de VRAM"
        if ($vramGb -lt 11 -and $ModeloEvaluador -eq "gemma3:12b") {
            Write-Aviso "Con menos de 12 GB de VRAM conviene usar el modelo ligero:"
            Write-Host "      .\install.ps1 -ModeloEvaluador gemma3:4b" -ForegroundColor DarkGray
        }
    } catch {
        Write-Paso "No se ha podido leer la VRAM (no es un problema)."
    }
} else {
    Write-Paso "Sin GPU NVIDIA detectada: la correccion funcionara por CPU (mas lenta)."
}

# ------------------------------------------------------------------ 2-4. dependencias
if (-not $SoloModelos) {

    Write-Titulo "2. Entorno virtual de Python"
    $VenvPython = Join-Path $Raiz ".venv\Scripts\python.exe"
    if (Test-Path $VenvPython) {
        Write-Ok "El entorno .venv ya existe"
    } else {
        Write-Paso "Creando .venv ..."
        & $PythonExe @PythonArgsPrefijo -m venv (Join-Path $Raiz ".venv")
        if ($LASTEXITCODE -ne 0) { Write-Fallo "No se pudo crear el entorno virtual."; exit 1 }
        Write-Ok "Entorno virtual creado"
    }

    Write-Paso "Actualizando pip ..."
    & $VenvPython -m pip install --upgrade pip --quiet
    if ($LASTEXITCODE -ne 0) { Write-Aviso "No se pudo actualizar pip; se continua igualmente." }

    Write-Paso "Instalando dependencias de requirements.txt ..."
    & $VenvPython -m pip install -r (Join-Path $Raiz "requirements.txt")
    if ($LASTEXITCODE -ne 0) { Write-Fallo "Fallo al instalar las dependencias de Python."; exit 1 }
    Write-Ok "Dependencias de Python instaladas"

    Write-Titulo "3. OCR para examenes escaneados (opcional)"
    if ($SinOcr) {
        Write-Paso "Omitido por -SinOcr. Solo se podran corregir PDFs digitales."
    } else {
        Write-Paso "Instalando glmocr (arrastra torch, puede tardar varios minutos) ..."
        & $VenvPython -m pip install -r (Join-Path $Raiz "requirements-ocr.txt")
        if ($LASTEXITCODE -ne 0) {
            Write-Aviso "No se pudo instalar el OCR. La app funcionara solo con PDFs digitales."
        } else {
            Write-Ok "OCR instalado"
        }
    }

    Write-Titulo "4. Dependencias del frontend"
    Push-Location (Join-Path $Raiz "frontend")
    try {
        Write-Paso "Ejecutando npm install ..."
        npm install
        if ($LASTEXITCODE -ne 0) { Write-Fallo "Fallo 'npm install'."; exit 1 }
        Write-Ok "Dependencias del frontend instaladas"
    } finally {
        Pop-Location
    }
}

# ------------------------------------------------------------------ 5. modelos
if (-not $SoloDependencias) {
    Write-Titulo "5. Modelos de Ollama"

    if (-not $TieneOllama) {
        Write-Aviso "Ollama no esta instalado: se omite la descarga de modelos."
        Write-Host "      Instalalo y vuelve a lanzar:  .\install.ps1 -SoloModelos" -ForegroundColor DarkGray
    } else {
        # Asegurar que el servidor responde antes de descargar
        $servidorOk = $false
        for ($i = 0; $i -lt 3; $i++) {
            try {
                Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 5 -UseBasicParsing | Out-Null
                $servidorOk = $true
                break
            } catch {
                if ($i -eq 0) {
                    Write-Paso "Arrancando el servidor de Ollama ..."
                    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
                }
                Start-Sleep -Seconds 4
            }
        }
        if ($servidorOk) {
            Write-Ok "Servidor de Ollama disponible"
        } else {
            Write-Aviso "El servidor de Ollama no responde en localhost:11434."
            Write-Host "      Abre la app de Ollama y relanza:  .\install.ps1 -SoloModelos" -ForegroundColor DarkGray
        }

        $modelos = @(
            @{ nombre = $ModeloEvaluador; rol = "evaluador (puntua las respuestas)" },
            @{ nombre = $ModeloEmbedding; rol = "embeddings (busca criterios en la rubrica)" }
        )
        if (-not $SinOcr) {
            $modelos += @{ nombre = $ModeloOcr; rol = "OCR (lee examenes escaneados)" }
        }

        foreach ($m in $modelos) {
            Write-Paso "Descargando '$($m.nombre)' - $($m.rol)"
            ollama pull $m.nombre
            if ($LASTEXITCODE -ne 0) {
                Write-Aviso "No se pudo descargar '$($m.nombre)'. Reintenta con: ollama pull $($m.nombre)"
            } else {
                Write-Ok "'$($m.nombre)' listo"
            }
        }
    }
}

# ------------------------------------------------------------------ resumen
Write-Host ""
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host "    Instalacion terminada" -ForegroundColor Cyan
Write-Host "  ============================================" -ForegroundColor Cyan

if ($script:Avisos.Count -gt 0) {
    Write-Host ""
    Write-Host "  Avisos pendientes:" -ForegroundColor Yellow
    foreach ($a in $script:Avisos) { Write-Host "    - $a" -ForegroundColor Yellow }
}

if ($ModeloEvaluador -ne "gemma3:12b") {
    Write-Host ""
    Write-Host "  Recuerda exportar el modelo elegido antes de arrancar el backend:" -ForegroundColor DarkGray
    Write-Host "    `$env:MODELO_GEMMA = `"$ModeloEvaluador`"" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  Para arrancar la aplicacion, en dos terminales:" -ForegroundColor White
Write-Host ""
Write-Host "    # 1) Backend" -ForegroundColor DarkGray
Write-Host "    .\.venv\Scripts\python.exe server.py"
Write-Host ""
Write-Host "    # 2) Frontend" -ForegroundColor DarkGray
Write-Host "    cd frontend; npm run dev"
Write-Host ""
Write-Host "  Y abre http://localhost:5173 en el navegador." -ForegroundColor White
Write-Host "  En la carpeta 'ejemplos' tienes una rubrica y dos examenes para probar." -ForegroundColor DarkGray
Write-Host ""
