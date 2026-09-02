import os
import json
import re
import requests
import time
import uuid
import threading
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from pydantic import BaseModel

# Importar módulos existentes del proyecto
from ocr import procesar_pdf_paginas
from rag_manager import (
    procesar_y_guardar_rubrica,
    buscar_criterios_relevantes,
    listar_rubricas_guardadas,
    liberar_modelo_ollama
)
from pdf_generator import generar_pdf_informe

# Crear directorios necesarios
os.makedirs("temp", exist_ok=True)
os.makedirs("rags", exist_ok=True)
os.makedirs("informes", exist_ok=True)
os.makedirs("resultados", exist_ok=True)

app = FastAPI(title="Exam Correction Assistant Backend")

# Habilitar CORS para el frontend Vite. Se permite cualquier puerto en
# localhost/127.0.0.1 (Vite cambia de puerto si el 5173 está ocupado) y,
# opcionalmente, orígenes extra vía la variable de entorno CORS_ORIGINS.
_cors_extra = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_extra,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelos de Ollama (configurables vía variables de entorno).
# El evaluador usa un modelo Gemma 3 (instruct, SIN razonamiento): produce JSON fiable.
# Se evita 'gemma4:e4b' (Gemma 3n con reasoning): su traza de pensamiento es larga e
# impredecible y a menudo deja el contenido vacío en preguntas largas.
# Por defecto 'gemma3:12b': mejor equilibrio calidad/velocidad probado en este equipo
# (RTX 4070 Ti SUPER 16 GB) — 0 fallos, ~7 s/pregunta, ~8 GB VRAM. Con el flujo en 2 fases
# (un solo modelo en VRAM a la vez) ya no agota memoria. En equipos con menos VRAM usa
# 'gemma3:4b' (más ligero) mediante la variable de entorno MODELO_GEMMA.
MODELO_GEMMA = os.getenv("MODELO_GEMMA", "gemma3:12b")
MODELO_EMBEDDING = os.getenv("MODELO_EMBEDDING", "embeddinggemma")
MODELO_OCR = os.getenv("MODELO_OCR", "glm-ocr:latest")

# Estado global de la aplicación (single-user)
active_rubric_data = None   # dict con los datos RAG cargados
active_rubric_path = None   # ruta al JSON de la rúbrica activa

RUTA_ACTIVA_PUNTERO = os.path.join("rags", ".active_rubric")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "30"))


def _ruta_temporal_segura(filename: str) -> str:
    """Devuelve una ruta temporal única y saneada para evitar colisiones y path traversal."""
    base = os.path.basename(filename or "archivo.pdf")
    base = re.sub(r'[^\w.\-]', '_', base) or "archivo.pdf"
    return os.path.join("temp", f"{int(time.time()*1000)}_{base}")


def _mismo_archivo(a: Optional[str], b: Optional[str]) -> bool:
    """Compara dos rutas de forma robusta ante separadores '/' vs '\\' (Windows)."""
    if not a or not b:
        return False
    return os.path.normpath(os.path.abspath(a)) == os.path.normpath(os.path.abspath(b))


async def _guardar_pdf_validado(file: UploadFile) -> str:
    """Guarda un UploadFile como PDF temporal, validando extensión y tamaño máximo.

    FastAPI no expone el tamaño antes de leer el archivo, así que se copia por
    bloques y se aborta en cuanto se supera el límite, sin cargar el archivo
    completo en memoria.
    """
    nombre = file.filename or "archivo.pdf"
    if not nombre.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se admiten archivos PDF.")

    temp_path = _ruta_temporal_segura(nombre)
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    total = 0
    try:
        with open(temp_path, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"El archivo supera el límite de {MAX_UPLOAD_MB} MB."
                    )
                buffer.write(chunk)
    except HTTPException:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    if total == 0:
        os.remove(temp_path)
        raise HTTPException(status_code=400, detail="El archivo subido está vacío.")
    return temp_path


def _guardar_puntero_activa(ruta: Optional[str]):
    """Persiste qué rúbrica está activa para que sobreviva a un reinicio del servidor."""
    try:
        if ruta:
            with open(RUTA_ACTIVA_PUNTERO, "w", encoding="utf-8") as f:
                f.write(ruta)
        elif os.path.exists(RUTA_ACTIVA_PUNTERO):
            os.remove(RUTA_ACTIVA_PUNTERO)
    except Exception as e:
        print(f"[Warn] No se pudo persistir la rúbrica activa: {e}")


def _cargar_rubrica_activa_al_iniciar():
    """Al arrancar el servidor, recupera la última rúbrica activa (si aún existe)."""
    global active_rubric_data, active_rubric_path
    try:
        if os.path.exists(RUTA_ACTIVA_PUNTERO):
            with open(RUTA_ACTIVA_PUNTERO, "r", encoding="utf-8") as f:
                ruta = f.read().strip()
            if ruta and os.path.exists(ruta):
                with open(ruta, "r", encoding="utf-8") as f:
                    active_rubric_data = json.load(f)
                active_rubric_path = ruta
                print(f"[Startup] Rúbrica activa restaurada: {ruta}")
    except Exception as e:
        print(f"[Warn] No se pudo restaurar la rúbrica activa: {e}")


@app.on_event("startup")
def _al_iniciar_servidor():
    _cargar_rubrica_activa_al_iniciar()


# ============================================================
# FUNCIONES NÚCLEO (portadas de asistente.py)
# ============================================================

def resolver_modelo_disponible(modelo_solicitado, host='http://localhost:11434'):
    """
    Obtiene el nombre exacto de un modelo de evaluación disponible en Ollama.
    Si el solicitado no está, prefiere un Gemma 3 instruct (sin razonamiento) y
    evita variantes 'e4b'/'e2b' (Gemma 3n con reasoning), poco fiables para JSON.
    """
    try:
        r = requests.get(f'{host}/api/tags', timeout=3)
        if r.status_code == 200:
            instalados = [m['name'] for m in r.json().get('models', [])]
            if modelo_solicitado in instalados or f'{modelo_solicitado}:latest' in instalados:
                return modelo_solicitado

            def es_razonador(nombre):
                n = nombre.lower()
                return 'e4b' in n or 'e2b' in n or 'deepseek-r1' in n

            # 1) Gemma 3 no-razonador
            for m in instalados:
                if 'gemma3' in m.lower() and not es_razonador(m):
                    return m
            # 2) Cualquier gemma no-razonador
            for m in instalados:
                if 'gemma' in m.lower() and not es_razonador(m):
                    return m
            # 3) Cualquier modelo no-razonador ni de OCR/embedding
            for m in instalados:
                ml = m.lower()
                if not es_razonador(m) and 'embed' not in ml and 'ocr' not in ml:
                    return m
            if instalados:
                return instalados[0]
    except Exception:
        pass
    return modelo_solicitado


# Palabras clave que encabezan una pregunta/apartado en distintos idiomas.
# Cubren ES/EN/FR/DE/IT/PT; se usan de forma insensible a mayúsculas/acentos donde aplica.
PALABRAS_ENCABEZADO = [
    # Español
    "Problema", "Cuestión", "Cuestion", "Pregunta", "Ejercicio", "Actividad",
    "Apartado", "Sección", "Seccion", "Tarea", "Parte",
    # Inglés
    "Problem", "Question", "Exercise", "Activity", "Task", "Section", "Part", "Item",
    # Francés
    "Problème", "Probleme", "Exercice", "Activité", "Activite", "Tâche", "Tache", "Partie",
    # Alemán
    "Aufgabe", "Frage", "Übung", "Uebung", "Teil", "Abschnitt",
    # Italiano
    "Domanda", "Esercizio", "Attività", "Attivita", "Compito", "Sezione",
    # Portugués
    "Questão", "Questao", "Pergunta", "Exercício", "Exercicio", "Atividade", "Tarefa",
]

# Indicadores de que un bloque de texto es realmente una pregunta (multilingüe).
PALABRAS_INDICADORAS = [
    "puntos", "punto", "respuesta", "demuestra", "calcule", "resuelva", "explica", "justifica",  # ES
    "points", "point", "answer", "prove", "calculate", "solve", "explain", "describe",           # EN
    "points", "réponse", "reponse", "démontrez", "calculez", "résolvez", "expliquez",            # FR
    "punkte", "antwort", "beweisen", "berechnen", "lösen", "erklären",                            # DE
    "punti", "risposta", "dimostra", "calcola", "risolvi", "spiega",                              # IT
    "pontos", "resposta", "demonstre", "calcule", "resolva", "explique",                          # PT
]

# Encabezados que NO son preguntas (metadatos de portada del examen), multilingüe.
PALABRAS_METADATOS = [
    "duración", "duration", "durée", "dauer", "durata", "duração",
    "convocatoria", "puntuación total", "total score", "total points",
    "note totale", "gesamtpunktzahl", "punteggio totale", "pontuação total",
]


def _construir_patron_encabezados():
    """Compila el patrón regex que reconoce el inicio de una pregunta en varios idiomas.

    NOTA: se evita deliberadamente un patrón tipo `\\bQ\\d+\\b` porque partiría el texto en
    cada `Q0`/`Q1`/`Q2` de contenidos STEM (álgebra de Boole, biestables JK, registros).
    """
    palabras = sorted(set(PALABRAS_ENCABEZADO), key=len, reverse=True)
    alternancia = "|".join(re.escape(p) for p in palabras)
    # Coincide con: "Pregunta 3", "Question 1:", o una lista numerada "3." / "3)" al inicio de línea.
    return rf'(?=(?:{alternancia})\s*[:\.\-\)]?\s*\d+|\n\s*\d+\s*[\.\)])'


_PATRON_ENCABEZADOS = _construir_patron_encabezados()
_PATRON_TITULO = rf'^((?:{"|".join(re.escape(p) for p in sorted(set(PALABRAS_ENCABEZADO), key=len, reverse=True))})\s*[:\.\-]?\s*\d+[^\n]*)'


def segmentar_preguntas_examen(paginas_extraidas):
    """Segmenta el texto del examen en bloques por pregunta, sin depender de un idioma concreto."""
    texto_con_paginas = []
    for p in paginas_extraidas:
        texto_con_paginas.append(f'\n[PÁGINA {p["pagina"]}]\n' + p['texto'])
    texto_total = '\n'.join(texto_con_paginas)

    bloques = re.split(_PATRON_ENCABEZADOS, texto_total, flags=re.MULTILINE | re.IGNORECASE)
    preguntas = []
    pagina_actual = 1
    for b in bloques:
        txt = b.strip()
        if not txt:
            continue
        match_pag = re.findall(r'\[PÁGINA (\d+)\]', txt)
        if match_pag:
            pagina_actual = int(match_pag[-1])
        txt_limpio = re.sub(r'\[PÁGINA \d+\]', '', txt).strip()

        match_titulo = re.search(_PATRON_TITULO, txt_limpio, re.IGNORECASE)
        txt_lower = txt_limpio.lower()
        if match_titulo:
            nombre_preg = match_titulo.group(1).split('\n')[0].strip()
            nombre_preg = re.sub(r'\s*\(.*?\)$', '', nombre_preg).strip()
            preguntas.append({'id': len(preguntas) + 1, 'pregunta': nombre_preg, 'pagina': pagina_actual, 'contenido': txt_limpio})
        elif len(txt_limpio) > 50 and any(kw in txt_lower for kw in PALABRAS_INDICADORAS):
            if not any(hw in txt_lower for hw in PALABRAS_METADATOS):
                preguntas.append({'id': len(preguntas) + 1, 'pregunta': f'#{len(preguntas) + 1}', 'pagina': pagina_actual, 'contenido': txt_limpio})

    # Fallback agnóstico al idioma: una "pregunta" por página si no se detectó estructura.
    if not preguntas:
        for i, p in enumerate(paginas_extraidas):
            if p['texto'].strip():
                preguntas.append({'id': i + 1, 'pregunta': f'#{i + 1}', 'pagina': p['pagina'], 'contenido': p['texto']})
    return preguntas


def parsear_json_robusto(respuesta_raw):
    """Parser ultra-robusto para la respuesta JSON del LLM."""
    if not respuesta_raw or not respuesta_raw.strip():
        return {}
    texto = respuesta_raw.strip()
    if '```' in texto:
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', texto)
        if match:
            texto = match.group(1).strip()
    try:
        data = json.loads(texto)
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    match_dict = re.search(r'\{[\s\S]*\}', texto)
    if match_dict:
        try:
            return json.loads(match_dict.group(0))
        except Exception:
            pass
    return {}


# Esquema JSON estructurado que Ollama fuerza en la salida del modelo.
# El modelo SOLO decide la evaluación; los campos largos (respuesta del alumno) los
# rellena Python, para que la salida sea corta y siempre válida.
#
# El modelo puntúa APARTADO POR APARTADO y es Python quien suma: pedirle una nota
# global hacía que citara bien la rúbrica y luego se inventara el número (por ejemplo,
# decía "0 puntos en b) y en c)" y aun así devolvía 0,9 sobre 1,5).
ESQUEMA_EVALUACION = {
    'type': 'object',
    'properties': {
        'estado': {'type': 'string', 'enum': ['CORRECTO', 'PARCIAL', 'INCORRECTO']},
        'apartados': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'apartado': {'type': 'string'},
                    'puntuacion_maxima': {'type': 'number'},
                    'puntuacion_obtenida': {'type': 'number'},
                    'motivo': {'type': 'string'},
                },
                'required': ['apartado', 'puntuacion_maxima', 'puntuacion_obtenida', 'motivo'],
            },
        },
        'puntuacion_obtenida': {'type': 'number'},
        'enunciado': {'type': 'string'},
        'que_esta_mal': {'type': 'string'},
        'criterio_rubrica': {'type': 'string'},
    },
    'required': ['estado', 'apartados', 'puntuacion_obtenida', 'que_esta_mal', 'criterio_rubrica'],
}


# Marcas que separan el enunciado de lo que escribió el alumno, en varios idiomas.
# Se exige inicio de línea y dos puntos para no confundirlas con frases del propio
# enunciado del tipo "Razona la respuesta.".
_PATRON_INICIO_RESPUESTA = re.compile(
    r'^[ \t]*(?:respuestas?|solución|solucion|answer|réponse|reponse|antwort|risposta|resposta)'
    r'(?:\s+\w+){0,3}?\s*:[ \t]*',
    re.IGNORECASE | re.MULTILINE,
)


def _extraer_respuesta_alumno(contenido: str) -> str:
    """Devuelve solo lo que escribió el alumno, si el examen marca dónde empieza.

    Si no hay ninguna marca reconocible se devuelve el bloque entero: para el informe
    es preferible mostrar de más que perder la respuesta.
    """
    m = _PATRON_INICIO_RESPUESTA.search(contenido or '')
    if not m:
        return contenido
    return (contenido[m.end():].strip() or contenido)


def _normalizar_apartados(apartados, puntuacion_maxima):
    """Limpia el desglose que devuelve el modelo y descarta filas de resumen.

    A veces, además de los apartados, el modelo añade una fila que repite el total de
    la pregunta ('único: 1,7/2'); contarla junto a los apartados falsearía la suma.
    """
    limpios = []
    for ap in (apartados or []):
        if not isinstance(ap, dict):
            continue
        try:
            maximo = max(0.0, float(ap.get('puntuacion_maxima', 0) or 0))
            obtenido = max(0.0, float(ap.get('puntuacion_obtenida', 0) or 0))
        except (TypeError, ValueError):
            continue
        limpios.append({
            'apartado': str(ap.get('apartado', '')).strip() or '—',
            'puntuacion_maxima': round(maximo, 2),
            'puntuacion_obtenida': round(min(obtenido, maximo) if maximo > 0 else obtenido, 2),
            'motivo': str(ap.get('motivo', '')).strip(),
        })

    if len(limpios) > 1 and puntuacion_maxima > 0:
        parciales = [a for a in limpios if a['puntuacion_maxima'] < puntuacion_maxima - 1e-6]
        if parciales:
            limpios = parciales
    return limpios


def _puntuacion_desde_apartados(apartados, puntuacion_maxima):
    """Suma los puntos por apartado ya normalizados. Devuelve None si no hay desglose.

    Si los máximos que propone el modelo no cuadran con el máximo real de la pregunta
    (que sale del enunciado y es la fuente de verdad), se reescala la proporción para
    respetarlo.
    """
    if not apartados:
        return None

    total_obtenido = sum(a['puntuacion_obtenida'] for a in apartados)
    total_maximo = sum(a['puntuacion_maxima'] for a in apartados)

    if total_maximo <= 0:
        return max(0.0, min(total_obtenido, puntuacion_maxima))
    proporcion = total_obtenido / total_maximo
    return max(0.0, min(proporcion * puntuacion_maxima, puntuacion_maxima))


def _estado_desde_puntuacion(obtenida, maxima):
    """Deriva el estado de la nota, para que insignia y puntos nunca se contradigan."""
    if maxima <= 0:
        return 'PARCIAL'
    proporcion = obtenida / maxima
    if proporcion >= 0.9:
        return 'CORRECTO'
    if proporcion > 0:
        return 'PARCIAL'
    return 'INCORRECTO'


def extraer_puntuacion_maxima(texto, defecto=1.0):
    """Extrae la puntuación máxima del enunciado ('(1,5 puntos)', '2 points', '0.5 pts'...)."""
    m = re.search(
        r'(\d+(?:[.,]\d+)?)\s*(?:puntos?|points?|punti|punkte?|pts?\.?|marks?|pontos?)',
        texto, re.IGNORECASE
    )
    if m:
        try:
            valor = float(m.group(1).replace(',', '.'))
            if 0 < valor <= 100:
                return valor
        except ValueError:
            pass
    return defecto


def evaluar_pregunta_con_gemma(info_pregunta, criterios_rag, modelo_gemma=None, host='http://localhost:11434', liberar_memoria=False, modelo_efectivo=None):
    """
    Evalúa una pregunta individual con el modelo vía la API nativa de Ollama (/api/chat),
    forzando salida JSON mediante un esquema estructurado (más fiable que response_format).

    - AGNÓSTICO AL IDIOMA: el modelo detecta el idioma del examen y responde en él.
    - La puntuación máxima se toma del enunciado (determinista), no del modelo.
    - `puntuacion_obtenida` del modelo se recorta al rango [0, máximo].
    """
    modelo_gemma = modelo_gemma or MODELO_GEMMA
    criterios_str = '\n---\n'.join(criterios_rag) if criterios_rag else 'No specific rubric provided; use general academic criteria.'
    puntuacion_maxima = extraer_puntuacion_maxima(info_pregunta['contenido'])

    system_message = (
        'You are an expert, FAIR academic grader. Grade the answer to ONE exam/assignment question '
        'against the grading criteria (rubric) provided.\n'
        'FAIRNESS RULES (very important):\n'
        '- The rubric may list POSSIBLE penalties (its "partial/incorrect" column). Apply a penalty ONLY if '
        'that specific error is ACTUALLY present in the student answer. Do NOT invent errors.\n'
        '- If the answer reaches the expected results and the reasoning is sound, award FULL marks and use CORRECTO.\n'
        '- Verify the actual work before deducting. When in doubt and the final results look right, be generous.\n'
        'LANGUAGE RULE: detect the language of the student answer and write ALL text fields '
        '(enunciado, que_esta_mal, criterio_rubrica, motivo) in that SAME language.\n'
        f'SCORING: the maximum score for this whole question is {puntuacion_maxima}.\n'
        '- Break the question into its parts (a, b, c...) and fill "apartados" with ONE entry per part. '
        'If the question has no parts, return a single entry with apartado = "único".\n'
        '- For each part set "puntuacion_maxima" (its share of the total, following the rubric) and '
        f'"puntuacion_obtenida". The parts\' maxima must add up to {puntuacion_maxima}.\n'
        '- Award each part INDEPENDENTLY. If the rubric says a specific error scores 0 in that part, put 0 there.\n'
        '- Do NOT compute the total yourself: the sum is done outside. Still fill "puntuacion_obtenida" at the '
        'top level with your best estimate of the total, used only as a fallback.\n'
        'In "que_esta_mal" explain concrete errors, or state clearly that the answer is correct. '
        'In "criterio_rubrica" state the applied criterion. In "enunciado" give a one-line summary of what the question asks.'
    )
    user_message = (
        f'GRADING RUBRIC / CRITERIA:\n{criterios_str}\n\n'
        f'--- QUESTION AND STUDENT ANSWER ---\n{info_pregunta["contenido"]}'
    )

    if modelo_efectivo is None:
        modelo_efectivo = resolver_modelo_disponible(modelo_gemma, host)

    def _fila(item):
        """Construye la evaluación final combinando la salida del modelo con datos deterministas."""
        # La nota sale de sumar los apartados; la global del modelo es solo el plan B.
        apartados = _normalizar_apartados(item.get('apartados'), puntuacion_maxima)
        obtenida = _puntuacion_desde_apartados(apartados, puntuacion_maxima)
        if obtenida is None:
            try:
                obtenida = float(item.get('puntuacion_obtenida', 0))
            except (TypeError, ValueError):
                obtenida = 0.0
            obtenida = max(0.0, min(obtenida, puntuacion_maxima))
        obtenida = round(obtenida, 2)

        return {
            'pagina': info_pregunta['pagina'],
            'pregunta': info_pregunta['pregunta'],
            'enunciado': (item.get('enunciado') or info_pregunta['contenido'][:140]).strip(),
            'respuesta_alumno': _extraer_respuesta_alumno(info_pregunta['contenido']),
            'estado': _estado_desde_puntuacion(obtenida, puntuacion_maxima),
            'puntuacion_obtenida': obtenida,
            'puntuacion_maxima': puntuacion_maxima,
            'apartados': apartados,
            'que_esta_mal': (item.get('que_esta_mal') or '').strip(),
            'criterio_rubrica': (item.get('criterio_rubrica') or '').strip(),
        }

    # Dos intentos: los modelos locales ocasionalmente devuelven contenido vacío.
    ultimo_intento = 1
    for intento in range(ultimo_intento + 1):
        try:
            res = requests.post(
                f'{host}/api/chat',
                json={
                    'model': modelo_efectivo,
                    'messages': [
                        {'role': 'system', 'content': system_message},
                        {'role': 'user', 'content': user_message},
                    ],
                    'stream': False,
                    'format': ESQUEMA_EVALUACION,
                    'options': {'temperature': 0.1, 'num_predict': 1200},
                    'keep_alive': 0 if liberar_memoria else '5m',
                },
                timeout=240,
            )
            if res.status_code == 200:
                contenido = res.json().get('message', {}).get('content', '').strip()
                item = parsear_json_robusto(contenido)
                if item and isinstance(item, dict) and item.get('estado'):
                    # Sin desglose la nota se decide "a ojo", que es justo lo que se quiere
                    # evitar: se reintenta una vez y, si sigue sin venir, se acepta igual
                    # antes que dejar la pregunta sin corregir.
                    tiene_apartados = isinstance(item.get('apartados'), list) and item['apartados']
                    if tiene_apartados or intento == ultimo_intento:
                        return _fila(item)
                    print(f'[Warn] Sin desglose por apartados, reintentando: {info_pregunta["pregunta"]}')
                else:
                    print(f'[Warn] Respuesta vacía/no válida (intento {intento + 1}) para {info_pregunta["pregunta"]}')
            else:
                print(f'[Warn] HTTP {res.status_code} evaluando {info_pregunta["pregunta"]}')
        except Exception as e:
            print(f'[Warn] Error evaluando {info_pregunta["pregunta"]} (intento {intento + 1}): {e}')

    # Fallback: no bloquea la corrección, pero deja claro que requiere revisión manual.
    return {
        'pagina': info_pregunta['pagina'],
        'pregunta': info_pregunta['pregunta'],
        'enunciado': info_pregunta['contenido'][:140],
        'respuesta_alumno': _extraer_respuesta_alumno(info_pregunta['contenido']),
        'estado': 'PARCIAL',
        'puntuacion_obtenida': 0.0,
        'puntuacion_maxima': puntuacion_maxima,
        'apartados': [],
        'que_esta_mal': 'No se pudo evaluar automáticamente esta pregunta; revísala manualmente frente a la solución.',
        'criterio_rubrica': 'Evaluación manual pendiente.',
    }


def generar_resumen_global(evaluaciones, modelo_efectivo, host='http://localhost:11434'):
    """
    Genera un comentario general de 2-3 frases en el MISMO idioma del examen,
    a partir de las evaluaciones por pregunta ya redactadas en ese idioma.
    Devuelve None si falla (el llamador aplicará un resumen numérico neutral).
    """
    if not evaluaciones:
        return None
    # Muestra representativa para que el modelo detecte el idioma y el desempeño.
    muestra = []
    for e in evaluaciones[:6]:
        muestra.append(
            f"[{e.get('estado', '')}] {e.get('pregunta', '')}: {str(e.get('que_esta_mal', ''))[:200]}"
        )
    muestra_str = '\n'.join(muestra)

    system_message = (
        'You are an expert academic grader writing a short overall assessment of a student\'s exam. '
        'Detect the language used in the per-question notes below and write your summary in that SAME language.'
    )
    user_message = f'Per-question grading notes:\n{muestra_str}\n\nWrite a 2-3 sentence overall assessment in the same language.'
    esquema = {'type': 'object', 'properties': {'resumen': {'type': 'string'}}, 'required': ['resumen']}
    try:
        res = requests.post(
            f'{host}/api/chat',
            json={
                'model': modelo_efectivo,
                'messages': [
                    {'role': 'system', 'content': system_message},
                    {'role': 'user', 'content': user_message},
                ],
                'stream': False,
                'format': esquema,
                'options': {'temperature': 0.3, 'num_predict': 400},
                'keep_alive': 0,
            },
            timeout=120,
        )
        if res.status_code == 200:
            raw = res.json().get('message', {}).get('content', '')
            data = parsear_json_robusto(raw)
            resumen = data.get('resumen') if isinstance(data, dict) else None
            if resumen:
                return resumen.strip()
    except Exception as e:
        print(f'[Warn] Error generando resumen global: {e}')
    return None


def _guardar_resultado_historial(resultado: dict, id_existente: Optional[str] = None) -> str:
    """Guarda (o actualiza) un resultado de corrección en resultados/ y devuelve su id."""
    id_res = id_existente or f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    ruta = os.path.join("resultados", f"{id_res}.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    return id_res


def _ruta_historial_segura(id_res: str) -> str:
    """Valida el id de historial (evita path traversal) y devuelve su ruta en disco."""
    if not re.fullmatch(r'[\w\-]+', id_res or ''):
        raise HTTPException(status_code=400, detail="Identificador de historial no válido.")
    ruta = os.path.join("resultados", f"{id_res}.json")
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="No se encontró ese resultado en el historial.")
    return ruta


# ============================================================
# API ENDPOINTS
# ============================================================

def _modelo_instalado(nombre_solicitado, instalados):
    """True si el modelo solicitado (con o sin tag ':latest') está entre los instalados."""
    if not nombre_solicitado:
        return True
    if nombre_solicitado in instalados or f"{nombre_solicitado}:latest" in instalados:
        return True
    base = nombre_solicitado.split(':')[0]
    return any(m.split(':')[0] == base for m in instalados)


@app.get("/api/health")
def health_check():
    """Verifica el estado del servidor, la conexión con Ollama y los modelos requeridos."""
    ollama_status = "offline"
    models = []
    try:
        r = requests.get('http://localhost:11434/api/tags', timeout=3)
        if r.status_code == 200:
            ollama_status = "online"
            models = [m['name'] for m in r.json().get('models', [])]
    except Exception:
        pass

    modelos_requeridos = {
        "evaluador": {"nombre": MODELO_GEMMA, "instalado": _modelo_instalado(MODELO_GEMMA, models)},
        "embedding": {"nombre": MODELO_EMBEDDING, "instalado": _modelo_instalado(MODELO_EMBEDDING, models)},
        "ocr": {"nombre": MODELO_OCR, "instalado": _modelo_instalado(MODELO_OCR, models)},
    } if ollama_status == "online" else {}

    return {
        "status": "ok",
        "ollama_status": ollama_status,
        "models": models,
        "modelos_requeridos": modelos_requeridos,
        "active_rubric": active_rubric_path
    }


@app.post("/api/rubrica/upload")
async def upload_rubrica(file: UploadFile = File(...)):
    """Sube un PDF de rúbrica, procesa embeddings con EmbeddingGemma y guarda en rags/."""
    global active_rubric_data, active_rubric_path

    temp_path = await _guardar_pdf_validado(file)

    def event_generator():
        global active_rubric_data, active_rubric_path
        try:
            def progreso_cb(msg):
                pass  # El progreso se envía a través de SSE directamente

            yield f"data: {json.dumps({'type': 'progress', 'message': 'Extrayendo texto del PDF de rúbrica...'})}\n\n"

            # procesar_y_guardar_rubrica(ruta_pdf, carpeta_salida, modelo_embedding, progreso_callback)
            ruta_json, datos_rag = procesar_y_guardar_rubrica(
                temp_path,
                carpeta_salida="rags",
                modelo_embedding=MODELO_EMBEDDING,
                progreso_callback=progreso_cb,
                nombre_original=file.filename
            )

            active_rubric_data = datos_rag
            active_rubric_path = ruta_json
            _guardar_puntero_activa(ruta_json)

            yield f"data: {json.dumps({'type': 'progress', 'message': 'Liberando memoria GPU...'})}\n\n"
            liberar_modelo_ollama(MODELO_EMBEDDING)

            result_info = {
                'type': 'done',
                'message': '¡Rúbrica procesada y guardada exitosamente!',
                'rubrica': {
                    'nombre_archivo': datos_rag.get('nombre_archivo', file.filename),
                    'ruta': ruta_json,
                    'total_chunks': datos_rag.get('total_chunks', 0),
                    'fecha_creacion': datos_rag.get('fecha_creacion', '')
                }
            }
            yield f"data: {json.dumps(result_info)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/rubrica/list")
def list_rubrics():
    """Lista las rúbricas guardadas en rags/."""
    rutas = listar_rubricas_guardadas("rags")
    rubricas_info = []
    for ruta in rutas:
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                data = json.load(f)
            rubricas_info.append({
                "nombre_archivo": data.get("nombre_archivo", os.path.basename(ruta)),
                "ruta": ruta,
                "total_chunks": data.get("total_chunks", 0),
                "fecha_creacion": data.get("fecha_creacion", ""),
                "activa": _mismo_archivo(ruta, active_rubric_path)
            })
        except Exception:
            rubricas_info.append({
                "nombre_archivo": os.path.basename(ruta),
                "ruta": ruta,
                "total_chunks": 0,
                "fecha_creacion": "",
                "activa": _mismo_archivo(ruta, active_rubric_path)
            })
    return {"rubricas": rubricas_info}


class ActivateRubricRequest(BaseModel):
    path: str

@app.post("/api/rubrica/activate")
def activate_rubric(request: ActivateRubricRequest):
    """Activa una rúbrica existente cargándola en memoria."""
    global active_rubric_data, active_rubric_path
    if not os.path.exists(request.path):
        raise HTTPException(status_code=404, detail="La rúbrica no existe en la ruta indicada.")
    try:
        with open(request.path, "r", encoding="utf-8") as f:
            active_rubric_data = json.load(f)
        active_rubric_path = request.path
        _guardar_puntero_activa(active_rubric_path)
        return {
            "message": "Rúbrica activada correctamente",
            "rubrica": {
                "nombre_archivo": active_rubric_data.get("nombre_archivo", ""),
                "ruta": active_rubric_path,
                "total_chunks": active_rubric_data.get("total_chunks", 0),
                "fecha_creacion": active_rubric_data.get("fecha_creacion", "")
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/rubrica")
def delete_rubric(path: str):
    """Elimina un archivo de rúbrica guardado en rags/. Si estaba activa, la desactiva."""
    global active_rubric_data, active_rubric_path

    ruta_abs = os.path.abspath(path)
    carpeta_abs = os.path.abspath("rags")
    if not ruta_abs.startswith(carpeta_abs + os.sep) or not ruta_abs.endswith("_rag.json"):
        raise HTTPException(status_code=400, detail="Ruta de rúbrica no válida.")
    if not os.path.exists(ruta_abs):
        raise HTTPException(status_code=404, detail="La rúbrica no existe.")

    os.remove(ruta_abs)
    if _mismo_archivo(active_rubric_path, ruta_abs):
        active_rubric_data = None
        active_rubric_path = None
        _guardar_puntero_activa(None)
    return {"message": "Rúbrica eliminada correctamente."}


def _inferir_nombre_estudiante(filename: str, indice: int) -> str:
    """Deriva un nombre de estudiante legible a partir del nombre de archivo.
    Ej.: 'juan_perez.pdf' -> 'Juan Perez'. Si no queda nada usable, usa 'Estudiante N'.
    """
    base = os.path.splitext(os.path.basename(filename or ""))[0]
    limpio = re.sub(r'[_\-.]+', ' ', base).strip()
    limpio = re.sub(r'\s+', ' ', limpio)
    return limpio.title() if limpio else f"Estudiante {indice + 1}"


def _pipeline_correccion(temp_path: str, student_name: str, subject: str, rubrica_data: dict):
    """Corrige UN examen (OCR → segmentación → RAG → evaluación con Gemma).

    Generador compartido con la cola de corrección: produce eventos de progreso
    (dicts, sin envolver en SSE) y termina con un evento
    {'type': 'result', 'resultado': {...}} que el llamador decide cómo emitir.

    Recibe `rubrica_data` explícito (no lee la global `active_rubric_data`) para
    que un trabajo ya encolado siga usando la rúbrica que estaba activa cuando
    se encoló, aunque el usuario active otra distinta mientras espera turno.
    """
    yield {'type': 'progress', 'message': 'Extrayendo texto del examen con OCR...'}
    paginas = procesar_pdf_paginas(temp_path, preferir_ocr=True)

    # Liberar el modelo de OCR de la VRAM antes de cargar embedder/evaluador.
    liberar_modelo_ollama(MODELO_OCR)

    yield {'type': 'progress', 'message': 'Segmentando preguntas del examen...'}
    preguntas = segmentar_preguntas_examen(paginas)

    total_preguntas = len(preguntas)
    yield {'type': 'progress', 'message': f'Se detectaron {total_preguntas} pregunta(s) en el examen.'}

    # Resolver el modelo una sola vez (evita llamadas repetidas a /api/tags).
    modelo_efectivo = resolver_modelo_disponible(MODELO_GEMMA)

    # ---- FASE 1: RAG de todas las preguntas con el embedder cargado ----
    # Se calculan primero todos los criterios y LUEGO se libera el embedder, para
    # no alternar entre el modelo de embeddings y el evaluador en cada pregunta
    # (ese intercambio agota la VRAM y puede tumbar Ollama en equipos modestos).
    yield {'type': 'progress', 'message': 'Buscando criterios de la rúbrica (RAG)...'}
    criterios_por_pregunta = []
    for q_info in preguntas:
        criterios_por_pregunta.append(
            buscar_criterios_relevantes(
                q_info["contenido"],
                rubrica_data,
                top_k=5,
                modelo_embedding=MODELO_EMBEDDING
            )
        )
    liberar_modelo_ollama(MODELO_EMBEDDING)

    # ---- FASE 2: evaluación con el modelo Gemma (único modelo en VRAM) ----
    evaluaciones = []
    for i, q_info in enumerate(preguntas):
        msg_eval = f'Evaluando {q_info["pregunta"]} ({i+1}/{total_preguntas})...'
        yield {'type': 'progress', 'message': msg_eval}

        res_eval = evaluar_pregunta_con_gemma(
            q_info,
            criterios_por_pregunta[i],
            modelo_gemma=MODELO_GEMMA,
            modelo_efectivo=modelo_efectivo
        )
        evaluaciones.append(res_eval)

        yield {'type': 'partial', 'evaluacion': res_eval, 'index': i}

    # Resumen general en el idioma del examen (antes de liberar el modelo).
    yield {'type': 'progress', 'message': 'Generando resumen general...'}
    resumen_ia = generar_resumen_global(evaluaciones, modelo_efectivo)

    # Liberar modelos de Ollama
    liberar_modelo_ollama(modelo_efectivo)
    liberar_modelo_ollama(MODELO_EMBEDDING)
    liberar_modelo_ollama(MODELO_OCR)

    # Calcular nota final
    nota_obtenida = sum(float(e.get("puntuacion_obtenida", 0)) for e in evaluaciones)
    nota_maxima = sum(float(e.get("puntuacion_maxima", 1.0)) for e in evaluaciones)
    if nota_maxima == 0:
        nota_maxima = 10.0
    nota_final_base10 = round((nota_obtenida / nota_maxima) * 10, 1)

    resumen_final = resumen_ia or (
        f"{student_name}: {nota_obtenida:.1f}/{nota_maxima:.1f} points "
        f"across {len(evaluaciones)} question(s) — final grade {nota_final_base10}/10."
    )

    resultado_final = {
        "datos_examen": {
            "titulo": subject,
            "estudiante": student_name,
            "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "nota_final": nota_final_base10,
            "nota_maxima": 10.0,
            "rubrica": rubrica_data.get("nombre_archivo", "Rúbrica RAG"),
            "resumen": resumen_final
        },
        "evaluaciones": evaluaciones
    }
    yield {'type': 'result', 'resultado': resultado_final}


# ============================================================
# COLA DE CORRECCIÓN (procesamiento en segundo plano)
# ============================================================
# Estado de la cola en memoria — coherente con el resto de la app (single-user,
# single-process). Un único hilo trabajador la procesa en secuencia porque el
# pipeline usa Ollama con una sola GPU compartida: evaluar en paralelo agotaría
# la VRAM. Subir más exámenes mientras el hilo trabaja simplemente los añade al
# final de la lista; el frontend consulta el estado con polling (GET /api/cola).
_cola_lock = threading.Lock()
_cola: List[dict] = []
_cola_worker_activo = False


def _job_publico(job: dict) -> dict:
    """Vista de un trabajo de la cola sin los campos internos (rutas de disco, rúbrica)."""
    return {k: v for k, v in job.items() if k not in ('temp_path', 'rubrica_data')}


def _procesar_cola():
    """Bucle del hilo trabajador: toma el primer trabajo pendiente y lo corrige."""
    global _cola_worker_activo
    while True:
        with _cola_lock:
            job = next((j for j in _cola if j['estado'] == 'pendiente'), None)
            if job is None:
                _cola_worker_activo = False
                return
            job['estado'] = 'procesando'
            job['mensaje'] = 'Iniciando...'

        try:
            resultado_final = None
            for ev in _pipeline_correccion(job['temp_path'], job['estudiante'], job['subject'], job['rubrica_data']):
                if ev['type'] == 'result':
                    resultado_final = ev['resultado']
                elif ev['type'] == 'progress':
                    with _cola_lock:
                        job['mensaje'] = ev['message']
                elif ev['type'] == 'partial':
                    with _cola_lock:
                        job['mensaje'] = f"Pregunta {ev['index'] + 1} evaluada"

            resultado_final['id'] = _guardar_resultado_historial(resultado_final)
            with _cola_lock:
                job['estado'] = 'hecho'
                job['mensaje'] = None
                job['resultado_id'] = resultado_final['id']
                job['nota_final'] = resultado_final['datos_examen']['nota_final']
                job['nota_maxima'] = resultado_final['datos_examen']['nota_maxima']
        except Exception as e:
            print(f"[Cola] Error corrigiendo '{job['filename']}': {e}")
            with _cola_lock:
                job['estado'] = 'error'
                job['mensaje'] = str(e)
        finally:
            if os.path.exists(job['temp_path']):
                os.remove(job['temp_path'])


def _asegurar_worker_activo():
    """Arranca el hilo trabajador si no hay uno ya corriendo."""
    global _cola_worker_activo
    with _cola_lock:
        if _cola_worker_activo:
            return
        _cola_worker_activo = True
    threading.Thread(target=_procesar_cola, daemon=True).start()


@app.post("/api/cola")
async def agregar_a_cola(
    files: List[UploadFile] = File(...),
    subject: str = Form("Examen"),
    student_name: Optional[str] = Form(None),
):
    """Añade uno o varios exámenes a la cola de corrección y devuelve de inmediato.

    Se procesan en segundo plano, uno detrás de otro; consulta el progreso con
    GET /api/cola. `student_name` solo se respeta si se sube un único archivo
    (con varios, el nombre de cada alumno se infiere de su nombre de archivo).
    La rúbrica activa se fija para cada trabajo en el momento de encolarlo.
    """
    if not active_rubric_data:
        raise HTTPException(status_code=400, detail="No hay ninguna rúbrica activa. Sube o activa una rúbrica primero.")
    if not files:
        raise HTTPException(status_code=400, detail="No se ha subido ningún archivo.")

    rubrica_snapshot = active_rubric_data
    nombre_manual = student_name.strip() if (student_name and len(files) == 1 and student_name.strip()) else None

    with _cola_lock:
        indice_base = len(_cola)

    nuevos = []
    try:
        for i, f in enumerate(files):
            temp_path = await _guardar_pdf_validado(f)
            job = {
                'id': f"job_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}",
                'filename': f.filename,
                'estudiante': nombre_manual or _inferir_nombre_estudiante(f.filename, indice_base + i),
                'subject': subject,
                'rubrica_data': rubrica_snapshot,
                'temp_path': temp_path,
                'estado': 'pendiente',
                'mensaje': None,
                'resultado_id': None,
                'nota_final': None,
                'nota_maxima': None,
                'creado': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            }
            with _cola_lock:
                _cola.append(job)
            nuevos.append(job)
    except HTTPException:
        for j in nuevos:
            if os.path.exists(j['temp_path']):
                os.remove(j['temp_path'])
        raise

    _asegurar_worker_activo()
    return {"agregados": [_job_publico(j) for j in nuevos]}


@app.get("/api/cola")
def obtener_cola():
    """Devuelve el estado actual de la cola de corrección (en orden de llegada)."""
    with _cola_lock:
        return {"cola": [_job_publico(j) for j in _cola]}


@app.delete("/api/cola/{job_id}")
def eliminar_de_cola(job_id: str):
    """Quita un trabajo de la cola. No se puede quitar uno que se está procesando."""
    with _cola_lock:
        job = next((j for j in _cola if j['id'] == job_id), None)
        if not job:
            raise HTTPException(status_code=404, detail="No se encontró ese elemento en la cola.")
        if job['estado'] == 'procesando':
            raise HTTPException(status_code=409, detail="No se puede eliminar un examen que se está corrigiendo ahora mismo.")
        _cola.remove(job)
    if job['estado'] == 'pendiente' and os.path.exists(job['temp_path']):
        os.remove(job['temp_path'])
    return {"message": "Eliminado de la cola."}


@app.post("/api/cola/limpiar")
def limpiar_cola():
    """Quita de la vista los trabajos ya terminados (hecho/error). No toca el historial."""
    with _cola_lock:
        antes = len(_cola)
        _cola[:] = [j for j in _cola if j['estado'] in ('pendiente', 'procesando')]
        quitados = antes - len(_cola)
    return {"eliminados": quitados}


@app.get("/api/historial")
def listar_historial():
    """Lista, más reciente primero, un resumen de todas las correcciones guardadas."""
    carpeta = "resultados"
    if not os.path.exists(carpeta):
        return {"historial": []}
    items = []
    for nombre in os.listdir(carpeta):
        if not nombre.endswith(".json"):
            continue
        ruta = os.path.join(carpeta, nombre)
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                data = json.load(f)
            d = data.get("datos_examen", {})
            items.append({
                "id": data.get("id", nombre[:-5]),
                "titulo": d.get("titulo", "Examen"),
                "estudiante": d.get("estudiante", "Estudiante"),
                "fecha": d.get("fecha", ""),
                "nota_final": d.get("nota_final", 0),
                "nota_maxima": d.get("nota_maxima", 10),
                "num_preguntas": len(data.get("evaluaciones", [])),
                "editado": bool(data.get("editado", False)),
            })
        except Exception:
            continue
    items.sort(key=lambda x: x["id"], reverse=True)
    return {"historial": items}


@app.get("/api/historial/{id_res}")
def obtener_historial(id_res: str):
    """Devuelve el resultado completo (datos_examen + evaluaciones) de una corrección guardada."""
    ruta = _ruta_historial_segura(id_res)
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


class UpdateHistorialRequest(BaseModel):
    datos_examen: dict
    evaluaciones: list

@app.put("/api/historial/{id_res}")
def actualizar_historial(id_res: str, request: UpdateHistorialRequest):
    """Guarda correcciones manuales del profesor (notas/estado ajustados) y recalcula la nota final."""
    _ruta_historial_segura(id_res)  # valida que exista

    nota_obtenida = sum(float(e.get("puntuacion_obtenida", 0)) for e in request.evaluaciones)
    nota_maxima = sum(float(e.get("puntuacion_maxima", 1.0)) for e in request.evaluaciones)
    nota_maxima = nota_maxima or 10.0
    nota_final_base10 = round((nota_obtenida / nota_maxima) * 10, 1)

    datos_examen = dict(request.datos_examen)
    datos_examen["nota_final"] = nota_final_base10
    datos_examen["nota_maxima"] = 10.0

    resultado = {
        "id": id_res,
        "datos_examen": datos_examen,
        "evaluaciones": request.evaluaciones,
        "editado": True,
    }
    _guardar_resultado_historial(resultado, id_existente=id_res)
    return resultado


@app.delete("/api/historial/{id_res}")
def eliminar_historial(id_res: str):
    """Elimina un resultado del historial de correcciones."""
    ruta = _ruta_historial_segura(id_res)
    os.remove(ruta)
    return {"message": "Resultado eliminado del historial."}


class GenerateReportRequest(BaseModel):
    datos_examen: dict
    evaluaciones: list

@app.post("/api/informe/generar")
def generar_informe(request: GenerateReportRequest):
    """Genera un informe PDF con los resultados de la evaluación."""
    try:
        timestamp = int(time.time())
        estudiante = request.datos_examen.get("estudiante", "Estudiante").replace(" ", "_")
        report_path = os.path.join("informes", f"Informe_{estudiante}_{timestamp}.pdf")

        # generar_pdf_informe(datos_examen, lista_evaluaciones, ruta_salida)
        generar_pdf_informe(request.datos_examen, request.evaluaciones, report_path)

        return FileResponse(
            path=report_path,
            filename=f"Informe_{estudiante}.pdf",
            media_type="application/pdf"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# PUNTO DE ENTRADA
# ============================================================

if __name__ == "__main__":
    import uvicorn
    print("🚀 Servidor FastAPI del Asistente de Corrección de Exámenes")
    print("   Backend: http://localhost:8000")
    print("   Docs:    http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
