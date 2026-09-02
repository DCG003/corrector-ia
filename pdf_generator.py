import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

def generar_pdf_informe(datos_examen, lista_evaluaciones, ruta_salida="informe_correccion.pdf"):
    """
    Genera un informe PDF profesional con la corrección detallada del examen.
    
    :param datos_examen: dict con meta información ('titulo', 'estudiante', 'modelo', 'rubrica', 'nota_final', 'nota_maxima', 'resumen')
    :param lista_evaluaciones: lista de dicts por pregunta:
           [
             {
               "pagina": 1,
               "pregunta": "1",
               "enunciado": "...",
               "respuesta_alumno": "...",
               "estado": "Incorrecto" | "Correcto" | "Parcial",
               "puntuacion_obtenida": 2.5,
               "puntuacion_maxima": 5.0,
               "que_esta_mal": "Detalle explicativo de qué estuvo mal en la pregunta...",
               "criterio_rubrica": "...",
               "recomendacion": "..."
             }, ...
           ]
    :param ruta_salida: Ruta donde guardar el archivo PDF.
    """
    doc = SimpleDocTemplate(
        ruta_salida,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    style_titulo = ParagraphStyle(
        'TituloDoc',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1E293B'),
        alignment=TA_LEFT
    )
    
    style_subtitulo = ParagraphStyle(
        'SubtituloDoc',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#64748B'),
        alignment=TA_LEFT
    )
    
    style_seccion = ParagraphStyle(
        'SeccionHeader',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=colors.HexColor('#0F172A'),
        spaceBefore=12,
        spaceAfter=6
    )
    
    style_normal = ParagraphStyle(
        'NormalDoc',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor('#334155'),
        alignment=TA_LEFT
    )
    
    style_mal = ParagraphStyle(
        'QueEstaMal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor('#991B1B'),
        alignment=TA_LEFT
    )

    style_bien = ParagraphStyle(
        'QueEstaBien',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor('#166534'),
        alignment=TA_LEFT
    )

    story = []
    
    # Header Banner
    titulo = datos_examen.get("titulo", "Informe de Corrección de Examen")
    estudiante = datos_examen.get("estudiante", "Alumno / Desconocido")
    fecha = datos_examen.get("fecha", datetime.now().strftime("%d/%m/%Y %H:%M"))
    nota_final = datos_examen.get("nota_final", 0.0)
    nota_maxima = datos_examen.get("nota_maxima", 10.0)
    porcentaje = (nota_final / nota_maxima * 100) if nota_maxima > 0 else 0
    
    story.append(Paragraph(titulo, style_titulo))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Estudiante:</b> {estudiante} | <b>Fecha:</b> {fecha} | <b>Rúbrica RAG:</b> {datos_examen.get('rubrica', 'General')}", style_subtitulo))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2563EB'), spaceAfter=12))
    
    # Resumen de Nota Box
    color_nota = colors.HexColor('#16A34A') if porcentaje >= 60 else colors.HexColor('#DC2626')
    estado_general = "APROBADO" if porcentaje >= 60 else "NECESITA MEJORAR"
    
    resumen_data = [
        [
            Paragraph(f"<b>NOTA FINAL:</b> <font color='{color_nota.hexval()}' size=16><b>{nota_final:.1f} / {nota_maxima:.1f}</b></font> ({porcentaje:.1f}%)", style_normal),
            Paragraph(f"<b>ESTADO:</b> <font color='{color_nota.hexval()}'><b>{estado_general}</b></font>", style_normal)
        ]
    ]
    t_resumen = Table(resumen_data, colWidths=[340, 200])
    t_resumen.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#E2E8F0')),
        ('PADDING', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t_resumen)
    story.append(Spacer(1, 12))
    
    if datos_examen.get("resumen"):
        story.append(Paragraph("<b>Evaluación General del Profesor / Asistente IA:</b>", style_seccion))
        story.append(Paragraph(datos_examen.get("resumen"), style_normal))
        story.append(Spacer(1, 12))
        
    story.append(Paragraph("Detalle de Corrección por Pregunta (¿Qué está mal?)", style_seccion))
    story.append(Spacer(1, 6))
    
    # Table of evaluations
    for item in lista_evaluaciones:
        pag = item.get("pagina", 1)
        preg = item.get("pregunta", "?")
        enunciado = item.get("enunciado", "Pregunta")
        respuesta = item.get("respuesta_alumno", "Sin respuesta registrada.")
        estado = item.get("estado", "Pendiente").upper()
        p_obtenida = item.get("puntuacion_obtenida", 0.0)
        p_maxima = item.get("puntuacion_maxima", 0.0)
        que_mal = item.get("que_esta_mal", "No se especificaron errores.")
        criterio = item.get("criterio_rubrica", "Rúbrica estándar.")
        
        # Color badge
        if "CORRECTO" in estado and "INCORRECTO" not in estado and "PARCIAL" not in estado:
            bg_color = colors.HexColor('#DCFCE7')
            txt_color = '#15803D'
        elif "PARCIAL" in estado:
            bg_color = colors.HexColor('#FEF9C3')
            txt_color = '#A16207'
        else:
            bg_color = colors.HexColor('#FEE2E2')
            txt_color = '#B91C1C'

        card_header = [
            [
                Paragraph(f"<b>Página {pag} | Pregunta {preg}:</b> {enunciado}", style_normal),
                Paragraph(f"<font color='{txt_color}'><b>{estado}</b></font> ({p_obtenida:.1f}/{p_maxima:.1f} pts)", ParagraphStyle('R', parent=style_normal, alignment=TA_RIGHT))
            ]
        ]
        t_card_header = Table(card_header, colWidths=[380, 160])
        t_card_header.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), bg_color),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('PADDING', (0,0), (-1,-1), 6),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(t_card_header)
        
        card_content = [
            [Paragraph("<b>Respuesta del Alumno:</b>", style_normal)],
            [Paragraph(respuesta, style_normal)],
            [Spacer(1, 3)],
            [Paragraph("<b>¿Qué está mal / Análisis de Errores:</b>", style_normal)],
            [Paragraph(que_mal, style_mal if ("INCORRECTO" in estado or "PARCIAL" in estado) else style_bien)],
            [Spacer(1, 3)],
            [Paragraph(f"<b>Criterio RAG de la Rúbrica:</b> {criterio}", style_subtitulo)],
        ]
        
        t_card_content = Table(card_content, colWidths=[540])
        t_card_content.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#FFFFFF')),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('PADDING', (0,0), (-1,-1), 8),
            ('LEFTPADDING', (0,0), (-1,-1), 12),
        ]))
        
        story.append(t_card_content)
        story.append(Spacer(1, 10))
        
    doc.build(story)
    return ruta_salida

if __name__ == "__main__":
    test_datos = {
        "titulo": "Corrección de Examen de Programación Python",
        "estudiante": "Juan Pérez",
        "nota_final": 7.5,
        "nota_maxima": 10.0,
        "rubrica": "rubrica_python_rag.json",
        "resumen": "El alumno demuestra buen manejo de estructuras básicas pero falla en manejo de excepciones."
    }
    test_evals = [
        {
            "pagina": 1,
            "pregunta": "1",
            "enunciado": "Definición de variables y tipos de datos",
            "respuesta_alumno": "x = 10; y = 'hola'",
            "estado": "CORRECTO",
            "puntuacion_obtenida": 5.0,
            "puntuacion_maxima": 5.0,
            "que_esta_mal": "Ningún error detectado. La sintaxis y tipos son adecuados.",
            "criterio_rubrica": "Sintaxis correcta de asignación (5 pts)."
        },
        {
            "pagina": 2,
            "pregunta": "2",
            "enunciado": "Manejo de excepciones try/except",
            "respuesta_alumno": "try: a = 1/0 except: pass",
            "estado": "PARCIALMENTE CORRECTO",
            "puntuacion_obtenida": 2.5,
            "puntuacion_maxima": 5.0,
            "que_esta_mal": "Se utiliza un 'except' desnudo (bare except) y se ignora el error con 'pass', lo cual es una mala práctica según la rúbrica.",
            "criterio_rubrica": "Captura específica de ZeroDivisionError y manejo adecuado del error (5 pts)."
        }
    ]
    generar_pdf_informe(test_datos, test_evals, "test_informe.pdf")
    print("PDF de prueba creado exitosamente.")
