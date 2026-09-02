import { useEffect, useRef, useState } from 'react';
import { UploadSimple, Spinner, ArrowRight, FilePdf, CheckCircle, LockSimple, XCircle, Files, Eye, Trash, Broom } from '@phosphor-icons/react';
import { motion, AnimatePresence } from 'framer-motion';
import { agregarACola, obtenerCola, eliminarDeCola, limpiarCola } from '../api';
import type { Rubrica, JobCola } from '../types';

interface Props {
  rubricaActiva: Rubrica | null;
  onVerResultado: (id: string) => void;
}

const POLL_ACTIVO_MS = 1500;
const POLL_INACTIVO_MS = 6000;
const EASE = [0.22, 1, 0.36, 1] as const;

export const CorregirSection: React.FC<Props> = ({ rubricaActiva, onVerResultado }) => {
  const [estudiante, setEstudiante] = useState('');
  const [titulo, setTitulo] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [cola, setCola] = useState<JobCola[]>([]);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const locked = !rubricaActiva;
  const esLote = files.length > 1;

  useEffect(() => {
    let cancelado = false;

    const poll = async () => {
      try {
        const data = await obtenerCola();
        if (cancelado) return;
        setCola(data);
        const hayActivos = data.some((j) => j.estado === 'pendiente' || j.estado === 'procesando');
        timeoutRef.current = setTimeout(poll, hayActivos ? POLL_ACTIVO_MS : POLL_INACTIVO_MS);
      } catch (err) {
        console.error(err);
        if (!cancelado) timeoutRef.current = setTimeout(poll, POLL_INACTIVO_MS);
      }
    };

    poll();
    return () => { cancelado = true; if (timeoutRef.current) clearTimeout(timeoutRef.current); };
  }, []);

  const refrescarCola = async () => {
    try { setCola(await obtenerCola()); } catch (err) { console.error(err); }
  };

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) setFiles(Array.from(e.target.files));
    setAddError(null);
  };

  const handleAgregar = async () => {
    if (files.length === 0) return;
    setAdding(true);
    setAddError(null);
    try {
      await agregarACola(files, titulo.trim() || 'Examen', estudiante.trim());
      setFiles([]);
      setEstudiante('');
      await refrescarCola();
    } catch (err: any) {
      console.error(err);
      setAddError(err?.message || 'No se pudo añadir a la cola.');
    } finally {
      setAdding(false);
    }
  };

  const handleEliminar = async (id: string) => {
    try {
      await eliminarDeCola(id);
      setCola((prev) => prev.filter((j) => j.id !== id));
    } catch (err) {
      console.error(err);
      alert('No se pudo eliminar (puede que ya se esté procesando).');
    }
  };

  const handleLimpiar = async () => {
    try {
      await limpiarCola();
      setCola((prev) => prev.filter((j) => j.estado === 'pendiente' || j.estado === 'procesando'));
    } catch (err) { console.error(err); }
  };

  const hayCompletados = cola.some((j) => j.estado === 'hecho' || j.estado === 'error');

  return (
    <section className={`section ${locked ? 'locked' : ''}`} id="corregir">
      <div className="section-head">
        <span className="section-num">02</span>
        <div>
          <h2 className="section-title">Corregir examen</h2>
          <p className="section-desc">
            {locked
              ? 'Selecciona primero una rúbrica arriba para desbloquear este paso.'
              : `Rúbrica activa: ${rubricaActiva!.nombre_archivo}. Sube uno o varios exámenes: se corrigen en cola, uno detrás de otro.`}
          </p>
        </div>
        {locked && <LockSimple size={20} color="var(--text-faint)" style={{ marginLeft: 'auto' }} />}
      </div>

      <div className="glass" style={{ padding: 22, marginBottom: cola.length > 0 ? 16 : 0 }}>
        <div className="row-resp" style={{ display: 'flex', gap: 14, marginBottom: 18 }}>
          <div style={{ flex: 1 }}>
            <label className="field-label">Estudiante {esLote && <span style={{ color: 'var(--text-faint)', fontWeight: 500 }}>(se toma del nombre de archivo)</span>}</label>
            <input className="input" placeholder="Opcional — ej. Juan Pérez" value={estudiante}
              onChange={(e) => setEstudiante(e.target.value)} disabled={adding || locked || esLote} />
          </div>
          <div style={{ flex: 1 }}>
            <label className="field-label">Asignatura / título</label>
            <input className="input" placeholder="Opcional — ej. Física" value={titulo}
              onChange={(e) => setTitulo(e.target.value)} disabled={adding || locked} />
          </div>
        </div>

        <label className="drop" style={{ marginBottom: files.length ? 18 : 0 }}>
          <input type="file" accept="application/pdf" multiple onChange={handleFile} disabled={adding || locked} />
          <span className="drop-icon">
            {files.length > 1
              ? <Files size={24} weight="fill" color="var(--cyan)" />
              : files.length === 1
                ? <FilePdf size={24} weight="fill" color="var(--cyan)" />
                : <UploadSimple size={24} weight="bold" color="var(--text-faint)" />}
          </span>
          {files.length > 1 ? (
            <p style={{ color: 'var(--text)', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <CheckCircle size={16} weight="fill" color="var(--success)" /> {files.length} exámenes seleccionados
            </p>
          ) : files.length === 1 ? (
            <p style={{ color: 'var(--text)', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <CheckCircle size={16} weight="fill" color="var(--success)" /> {files[0].name}
            </p>
          ) : (
            <>
              <p style={{ color: 'var(--text)', fontWeight: 700 }}>Arrastra o haz clic para subir el examen PDF</p>
              <p style={{ fontSize: 13, color: 'var(--text-faint)', marginTop: 4 }}>Puedes seleccionar varios a la vez: se irán encolando y corrigiendo poco a poco</p>
            </>
          )}
        </label>

        <AnimatePresence>
          {addError && (
            <motion.p
              initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2, ease: EASE }}
              style={{ fontSize: 13, color: 'var(--error)', marginTop: 14, overflow: 'hidden' }}
            >
              {addError}
            </motion.p>
          )}
        </AnimatePresence>

        <motion.button className="btn btn-primary" style={{ width: '100%', marginTop: 18 }}
          onClick={handleAgregar} disabled={files.length === 0 || adding || locked}
          whileHover={{ scale: files.length === 0 || adding || locked ? 1 : 1.015, y: -1 }}
          whileTap={{ scale: files.length === 0 || adding || locked ? 1 : 0.985, y: 0 }}
          transition={{ duration: 0.15, ease: EASE }}>
          {adding
            ? <><Spinner size={18} className="spin" /> Añadiendo a la cola...</>
            : esLote
              ? <>Añadir {files.length} exámenes a la cola <ArrowRight size={18} weight="bold" /></>
              : <>Añadir a la cola <ArrowRight size={18} weight="bold" /></>}
        </motion.button>
      </div>

      <AnimatePresence>
        {cola.length > 0 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2, ease: EASE }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <h3 style={{ fontSize: 15 }}>Cola de corrección</h3>
              <AnimatePresence>
                {hayCompletados && (
                  <motion.button
                    initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}
                    transition={{ duration: 0.15, ease: EASE }}
                    className="btn btn-secondary" style={{ padding: '7px 12px', fontSize: 12.5 }} onClick={handleLimpiar}>
                    <Broom size={14} weight="bold" /> Limpiar completados
                  </motion.button>
                )}
              </AnimatePresence>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <AnimatePresence initial={false}>
                {cola.map((job) => (
                  <motion.div key={job.id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                    transition={{ duration: 0.25, ease: EASE }}
                    className="row"
                    style={{ background: job.estado === 'procesando' ? 'var(--card-hover)' : undefined }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                      {job.estado === 'pendiente' && <span style={{ width: 14, height: 14, borderRadius: '50%', border: '2px solid var(--border-strong)', flexShrink: 0 }} />}
                      {job.estado === 'procesando' && <Spinner size={15} className="spin" color="var(--violet)" style={{ flexShrink: 0 }} />}
                      {job.estado === 'hecho' && <CheckCircle size={16} weight="fill" color="var(--success)" style={{ flexShrink: 0 }} />}
                      {job.estado === 'error' && <XCircle size={16} weight="fill" color="var(--error)" style={{ flexShrink: 0 }} />}
                      <span style={{ minWidth: 0 }}>
                        <span style={{ display: 'block', fontSize: 13.5, fontWeight: 600, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {job.estudiante}
                        </span>
                        <span style={{ fontSize: 12, color: job.estado === 'error' ? 'var(--error)' : 'var(--text-faint)' }}>
                          {job.estado === 'error' ? job.mensaje
                            : job.estado === 'hecho' ? 'Completado'
                            : job.estado === 'procesando' ? (job.mensaje || 'Procesando...')
                            : 'En espera en la cola...'}
                        </span>
                      </span>
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                      {job.estado === 'hecho' && job.nota_final !== null && (
                        <span style={{ fontWeight: 800, fontSize: 14, color: 'var(--text)', marginRight: 4 }}>
                          {job.nota_final.toFixed(1)}<span style={{ color: 'var(--text-faint)' }}>/{job.nota_maxima?.toFixed(0)}</span>
                        </span>
                      )}
                      {job.estado === 'hecho' && job.resultado_id && (
                        <button className="btn-icon" title="Ver resultado" onClick={() => onVerResultado(job.resultado_id!)}>
                          <Eye size={15} weight="bold" />
                        </button>
                      )}
                      {job.estado !== 'procesando' && (
                        <button className="btn-icon danger" title="Quitar de la cola" onClick={() => handleEliminar(job.id)}>
                          <Trash size={15} weight="bold" />
                        </button>
                      )}
                    </span>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
};
