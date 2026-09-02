import type { Rubrica, ResultadoExamen, HistorialItem, EstadoModelo, JobCola } from './types';

const API_BASE = 'http://localhost:8000/api';

export const fetchHealth = async (): Promise<{
  status: string; ollama: boolean; models: string[]; modelosRequeridos: Record<string, EstadoModelo>;
}> => {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error('Network response was not ok');
    const data = await res.json();
    return {
      status: data.status ?? 'ok',
      ollama: data.ollama_status === 'online',
      models: data.models ?? [],
      modelosRequeridos: data.modelos_requeridos ?? {},
    };
  } catch (error) {
    return { status: 'error', ollama: false, models: [], modelosRequeridos: {} };
  }
};

export const listRubricas = async (): Promise<Rubrica[]> => {
  const res = await fetch(`${API_BASE}/rubrica/list`);
  if (!res.ok) throw new Error('Failed to list rubricas');
  const data = await res.json();
  return data.rubricas || [];
};

export const activateRubrica = async (path: string): Promise<{message: string}> => {
  const res = await fetch(`${API_BASE}/rubrica/activate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path })
  });
  if (!res.ok) throw new Error('Failed to activate rubrica');
  return res.json();
};

export const descargarInforme = async (resultado: ResultadoExamen): Promise<Blob> => {
  const res = await fetch(`${API_BASE}/informe/generar`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      datos_examen: resultado.datos_examen,
      evaluaciones: resultado.evaluaciones
    })
  });
  if (!res.ok) throw new Error('Failed to generate report');
  return res.blob();
};

// SSE over POST helper
async function fetchStream(url: string, options: RequestInit, onProgress: (data: any) => void): Promise<any> {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
  if (!res.body) throw new Error('ReadableStream not yet supported in this browser.');
  
  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let result = null;
  let buffer = '';

  const processLine = (line: string) => {
    if (!line.startsWith('data:')) return;
    const dataStr = line.slice(5).trim();
    if (!dataStr) return;
    try {
      const data = JSON.parse(dataStr);
      onProgress(data);
      if (data.type === 'done') {
        result = data.resultado || data.rubrica || data;
      }
    } catch (e) {
      console.error('Error parsing SSE data:', e);
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    // Acumular en un buffer: un evento SSE puede quedar partido entre chunks.
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? ''; // la última línea puede estar incompleta

    for (const line of lines) {
      processLine(line);
    }
  }

  // Procesar cualquier resto pendiente en el buffer.
  if (buffer) processLine(buffer);

  return result;
}

export const uploadRubrica = async (file: File, onProgress: (data: any) => void): Promise<Rubrica> => {
  const formData = new FormData();
  formData.append('file', file);
  return fetchStream(`${API_BASE}/rubrica/upload`, {
    method: 'POST',
    body: formData
  }, onProgress);
};

export const agregarACola = async (files: File[], subject: string, estudiante?: string): Promise<JobCola[]> => {
  const formData = new FormData();
  files.forEach((f) => formData.append('files', f));
  formData.append('subject', subject);
  if (estudiante && files.length === 1) formData.append('student_name', estudiante);

  const res = await fetch(`${API_BASE}/cola`, { method: 'POST', body: formData });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch { /* respuesta no-JSON */ }
    throw new Error(detail);
  }
  const data = await res.json();
  return data.agregados || [];
};

export const obtenerCola = async (): Promise<JobCola[]> => {
  const res = await fetch(`${API_BASE}/cola`);
  if (!res.ok) throw new Error('Failed to fetch cola');
  const data = await res.json();
  return data.cola || [];
};

export const eliminarDeCola = async (id: string): Promise<void> => {
  const res = await fetch(`${API_BASE}/cola/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete cola item');
};

export const limpiarCola = async (): Promise<void> => {
  const res = await fetch(`${API_BASE}/cola/limpiar`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to clear cola');
};

export const deleteRubrica = async (path: string): Promise<void> => {
  const res = await fetch(`${API_BASE}/rubrica?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete rubrica');
};

export const listHistorial = async (): Promise<HistorialItem[]> => {
  const res = await fetch(`${API_BASE}/historial`);
  if (!res.ok) throw new Error('Failed to list historial');
  const data = await res.json();
  return data.historial || [];
};

export const getHistorialItem = async (id: string): Promise<ResultadoExamen> => {
  const res = await fetch(`${API_BASE}/historial/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error('Failed to fetch historial item');
  return res.json();
};

export const updateHistorialItem = async (id: string, resultado: ResultadoExamen): Promise<ResultadoExamen> => {
  const res = await fetch(`${API_BASE}/historial/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ datos_examen: resultado.datos_examen, evaluaciones: resultado.evaluaciones }),
  });
  if (!res.ok) throw new Error('Failed to update historial item');
  return res.json();
};

export const deleteHistorialItem = async (id: string): Promise<void> => {
  const res = await fetch(`${API_BASE}/historial/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete historial item');
};
