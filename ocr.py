import os
import fitz  # PyMuPDF

try:
    from glmocr import GlmOcr
    GLMOCR_DISPONIBLE = True
except ImportError:
    GLMOCR_DISPONIBLE = False

def extraer_texto_pagina_fitz(documento_fitz, numero_pagina):
    """Extrae texto directo usando PyMuPDF (fitz) como fallback rápido."""
    pagina = documento_fitz.load_page(numero_pagina)
    texto = pagina.get_text("text")
    return texto.strip()

def procesar_pdf_paginas(ruta_pdf, preferir_ocr=True, config_path="config.yaml"):
    """
    Procesa un archivo PDF página por página (soporta 1 o múltiples páginas)
    y devuelve una lista de diccionarios con el número de página y texto extraído.
    """
    if not os.path.exists(ruta_pdf):
        raise FileNotFoundError(f"No se encontró el archivo PDF: {ruta_pdf}")

    documento = fitz.open(ruta_pdf)
    total_paginas = len(documento)
    resultados = []
    
    temp_dir = "./temp_pdf_images"
    os.makedirs(temp_dir, exist_ok=True)

    parser = None
    if preferir_ocr and GLMOCR_DISPONIBLE and os.path.exists(config_path):
        try:
            parser = GlmOcr(config_path=config_path, layout_device="cuda")
        except Exception as e:
            print(f"[OCR Warning] No se pudo inicializar GlmOcr: {e}. Usando PyMuPDF fitz.")

    try:
        for numero_pagina in range(total_paginas):
            print(f"Procesando página {numero_pagina + 1} de {total_paginas}...")
            texto_pagina = ""
            
            # Intentar primero con GLM-OCR si está activo
            if parser is not None:
                try:
                    pagina = documento.load_page(numero_pagina)
                    matriz_zoom = fitz.Matrix(2.0, 2.0)
                    pixmap = pagina.get_pixmap(matrix=matriz_zoom)
                    
                    ruta_img_temp = os.path.join(temp_dir, f"pagina_temp_{numero_pagina + 1}.png")
                    pixmap.save(ruta_img_temp)
                    
                    res_ocr = parser.parse(ruta_img_temp)
                    texto_pagina = res_ocr.markdown_result
                    
                    if os.path.exists(ruta_img_temp):
                        os.remove(ruta_img_temp)
                except Exception as err:
                    print(f"[OCR Warning] Error al procesar página {numero_pagina + 1} con GLM-OCR: {err}")
                    texto_pagina = ""

            # Fallback si el texto OCR está vacío o si no se usó GLM-OCR
            if not texto_pagina or not texto_pagina.strip():
                texto_pagina = extraer_texto_pagina_fitz(documento, numero_pagina)

            resultados.append({
                "pagina": numero_pagina + 1,
                "texto": texto_pagina.strip()
            })
    finally:
        if parser is not None and hasattr(parser, '__exit__'):
            try:
                parser.__exit__(None, None, None)
            except Exception:
                pass
        documento.close()
        if os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except Exception:
                pass

    return resultados

def procesar_pdf_con_glmocr(ruta_pdf, ruta_txt_salida="resultado_final.txt"):
    """
    Función original para procesar todo un PDF con GLM-OCR y guardarlo en TXT.
    """
    paginas = procesar_pdf_paginas(ruta_pdf, preferir_ocr=True)
    with open(ruta_txt_salida, "w", encoding="utf-8") as archivo_txt:
        for item in paginas:
            num = item["pagina"]
            txt = item["texto"]
            archivo_txt.write(f"========================================\n")
            archivo_txt.write(f"          PÁGINA {num} \n")
            archivo_txt.write(f"========================================\n\n")
            archivo_txt.write(txt)
            archivo_txt.write("\n\n")
    print(f"\n¡Proceso finalizado! Todo el texto extraído se ha guardado en: {ruta_txt_salida}")

if __name__ == "__main__":
    archivo_pdf_entrada = "mi_libro.pdf"
    archivo_texto_salida = "resultados_extraccion.txt"
    if os.path.exists(archivo_pdf_entrada):
        procesar_pdf_con_glmocr(archivo_pdf_entrada, archivo_texto_salida)
    else:
        print(f"Error: No se encontró el archivo '{archivo_pdf_entrada}'. Revisa la ruta.")