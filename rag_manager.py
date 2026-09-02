import os
import re
import json
import math
import requests
import fitz  # PyMuPDF
from datetime import datetime

OLLAMA_HOST = "http://localhost:11434"

def liberar_modelo_ollama(modelo, host=OLLAMA_HOST):
    """Descarga el modelo especificado de la VRAM/RAM de Ollama inmediatamente (keep_alive: 0)."""
    if not modelo:
        return
    try:
        requests.post(f"{host}/api/generate", json={"model": modelo, "keep_alive": 0}, timeout=5)
        print(f"[Ollama Memory] Modelo '{modelo}' liberado de la memoria.")
    except Exception as e:
        print(f"[Ollama Memory Warning] Error al intentar liberar '{modelo}': {e}")

def obtener_embedding(texto, modelo="embeddinggemma", host=OLLAMA_HOST, liberar_memoria=False):
    """
    Obtiene el vector embedding para un texto dado utilizando Ollama.
    Intenta primero la ruta /api/embed (recomendada) y como fallback /api/embeddings.
    """
    url = f"{host}/api/embed"
    payload = {
        "model": modelo,
        "input": texto,
        "keep_alive": 0 if liberar_memoria else "5m"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if "embeddings" in data and len(data["embeddings"]) > 0:
                if liberar_memoria:
                    liberar_modelo_ollama(modelo, host)
                return data["embeddings"][0]
            
        # Fallback a /api/embeddings si /api/embed no responde adecuadamente
        url_fallback = f"{host}/api/embeddings"
        payload_fallback = {"model": modelo, "prompt": texto, "keep_alive": 0 if liberar_memoria else "5m"}
        res_fb = requests.post(url_fallback, json=payload_fallback, timeout=30)
        if res_fb.status_code == 200:
            data_fb = res_fb.json()
            if liberar_memoria:
                liberar_modelo_ollama(modelo, host)
            return data_fb.get("embedding", [])
    except Exception as e:
        print(f"[RAG Error] Error al obtener embedding con el modelo '{modelo}': {e}")
    
    return []

def extraer_texto_pdf(ruta_pdf):
    """Extrae el texto completo de un archivo PDF."""
    if not os.path.exists(ruta_pdf):
        raise FileNotFoundError(f"No existe el PDF en {ruta_pdf}")
    
    doc = fitz.open(ruta_pdf)
    texto_total = []
    for num_pag, pagina in enumerate(doc):
        t = pagina.get_text("text").strip()
        if t:
            texto_total.append(f"--- PÁGINA {num_pag + 1} ---\n" + t)
    doc.close()
    
    return "\n\n".join(texto_total)

def fragmentar_texto(texto, tamano_chunk=500, solapamiento=100):
    """
    Divide un texto largo en fragmentos (chunks) con solapamiento
    para evitar cortar ideas o criterios pedagógicos a la mitad.
    """
    lineas = texto.split('\n')
    chunks = []
    chunk_actual = []
    longitud_actual = 0
    
    for linea in lineas:
        linea_clean = linea.strip()
        if not linea_clean:
            continue
        
        chunk_actual.append(linea_clean)
        longitud_actual += len(linea_clean) + 1
        
        if longitud_actual >= tamano_chunk:
            texto_chunk = "\n".join(chunk_actual)
            chunks.append(texto_chunk)
            
            # Mantener las últimas líneas para el solapamiento
            recorte = []
            acc = 0
            for l in reversed(chunk_actual):
                recorte.insert(0, l)
                acc += len(l) + 1
                if acc >= solapamiento:
                    break
            chunk_actual = recorte
            longitud_actual = sum(len(l) + 1 for l in chunk_actual)
            
    if chunk_actual:
        chunks.append("\n".join(chunk_actual))
        
    return chunks if chunks else [texto]

def procesar_y_guardar_rubrica(ruta_pdf, carpeta_salida="rags", modelo_embedding="embeddinggemma",
                               progreso_callback=None, nombre_original=None):
    """
    Procesa un PDF de rúbrica, extrae texto, calcula embeddings con embeddinggemma
    y guarda el archivo JSON resultante en la carpeta `rags/`.
    Al finalizar, libera la memoria ocupada por el modelo de embeddings en Ollama.

    `nombre_original` es el nombre con el que el usuario subió el archivo. Se usa para
    nombrar la rúbrica de cara al usuario, porque `ruta_pdf` apunta a una copia temporal
    con un prefijo de marca de tiempo que no tiene sentido mostrar en la interfaz.
    """
    os.makedirs(carpeta_salida, exist_ok=True)

    nombre_visible = os.path.basename(nombre_original or ruta_pdf)
    nombre_base = os.path.splitext(nombre_visible)[0]
    # Saneado: el nombre llega de una subida del usuario y acaba siendo una ruta.
    nombre_base = re.sub(r'[^\w.\-]', '_', nombre_base) or "rubrica"
    ruta_json = os.path.join(carpeta_salida, f"{nombre_base}_rag.json")
    
    if progreso_callback:
        progreso_callback("Extrayendo texto del PDF de rúbrica...")
    texto_rubrica = extraer_texto_pdf(ruta_pdf)
    
    if progreso_callback:
        progreso_callback("Fragmentando texto de la rúbrica...")
    chunks = fragmentar_texto(texto_rubrica)
    
    chunks_con_embeddings = []
    total_chunks = len(chunks)
    
    for i, c in enumerate(chunks):
        if progreso_callback:
            progreso_callback(f"Generando embeddings ({i+1}/{total_chunks}) con {modelo_embedding}...")
        vec = obtener_embedding(c, modelo=modelo_embedding)
        chunks_con_embeddings.append({
            "id": i,
            "texto": c,
            "vector": vec
        })
        
    datos_rag = {
        "nombre_archivo": nombre_visible,
        "ruta_original": ruta_pdf,
        "fecha_creacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "modelo_embedding": modelo_embedding,
        "total_chunks": total_chunks,
        "chunks": chunks_con_embeddings
    }
    
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(datos_rag, f, ensure_ascii=False, indent=2)
        
    # Liberar memoria en Ollama al terminar todo el lote de embeddings
    liberar_modelo_ollama(modelo_embedding)

    if progreso_callback:
        progreso_callback(f"¡Rúbrica guardada exitosamente en {ruta_json} y modelo liberado de memoria!")
        
    return ruta_json, datos_rag

def coseno_similitud(vec1, vec2):
    """Calcula la similitud coseno entre dos vectores numéricos."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

def buscar_criterios_relevantes(texto_consulta, datos_rag, top_k=3, modelo_embedding="embeddinggemma"):
    """
    Busca los fragmentos más relevantes de la rúbrica RAG para el texto de un examen dado.
    """
    if not datos_rag or "chunks" not in datos_rag:
        return []
    
    vec_query = obtener_embedding(texto_consulta, modelo=modelo_embedding)
    if not vec_query:
        # Fallback: devolver los primeros top_k chunks si falla el embedding
        return [item["texto"] for item in datos_rag["chunks"][:top_k]]
    
    puntuados = []
    for item in datos_rag["chunks"]:
        vec_chunk = item.get("vector", [])
        score = coseno_similitud(vec_query, vec_chunk)
        puntuados.append((score, item["texto"]))
        
    puntuados.sort(key=lambda x: x[0], reverse=True)
    criterios = [texto for score, texto in puntuados[:top_k]]
    return criterios

def listar_rubricas_guardadas(carpeta_salida="rags"):
    """Lista los archivos RAG guardados en la carpeta rags."""
    if not os.path.exists(carpeta_salida):
        return []
    archivos = [f for f in os.listdir(carpeta_salida) if f.endswith("_rag.json")]
    return [os.path.join(carpeta_salida, f) for f in archivos]
