export interface Rubrica {
  nombre_archivo: string;
  ruta: string;
  total_chunks: number;
  fecha_creacion: string;
  activa?: boolean;
}

export interface ApartadoEvaluado {
  apartado: string;
  puntuacion_maxima: number;
  puntuacion_obtenida: number;
  motivo: string;
}

export interface Evaluacion {
  pagina: number;
  pregunta: string;
  enunciado: string;
  respuesta_alumno: string;
  estado: 'CORRECTO' | 'PARCIAL' | 'INCORRECTO';
  puntuacion_obtenida: number;
  puntuacion_maxima: number;
  /** Desglose que suma la nota de la pregunta. Ausente en correcciones antiguas. */
  apartados?: ApartadoEvaluado[];
  que_esta_mal: string;
  criterio_rubrica: string;
}

export interface ResultadoExamen {
  id?: string;
  editado?: boolean;
  datos_examen: {
    titulo: string;
    estudiante: string;
    fecha: string;
    nota_final: number;
    nota_maxima: number;
    rubrica: string;
    resumen: string;
  };
  evaluaciones: Evaluacion[];
}

export interface HistorialItem {
  id: string;
  titulo: string;
  estudiante: string;
  fecha: string;
  nota_final: number;
  nota_maxima: number;
  num_preguntas: number;
  editado: boolean;
}

export interface EstadoModelo {
  nombre: string;
  instalado: boolean;
}

export interface JobCola {
  id: string;
  filename: string;
  estudiante: string;
  subject: string;
  estado: 'pendiente' | 'procesando' | 'hecho' | 'error';
  mensaje: string | null;
  resultado_id: string | null;
  nota_final: number | null;
  nota_maxima: number | null;
  creado: string;
}
