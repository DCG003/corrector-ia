import { useEffect, useState } from 'react';
import { DownloadSimple, CaretDown, ArrowCounterClockwise, Sparkle, PencilSimple, FloppyDisk, CheckCircle } from '@phosphor-icons/react';
import { motion, AnimatePresence } from 'framer-motion';
import type { ResultadoExamen, Evaluacion } from '../types';
import { descargarInforme, updateHistorialItem } from '../api';
import { StatusBadge } from './StatusBadge';

interface Props {
  resultado: ResultadoExamen;
  onReset: () => void;
  onUpdated?: (res: ResultadoExamen) => void;
  backLabel?: string;
}

const EASE = [0.22, 1, 0.36, 1] as const;
const gradeColor = (pct: number) => (pct >= 0.9 ? '#34d399' : pct >= 0.5 ? '#d4d4d8' : '#fb7185');

const calcularNota = (evaluaciones: Evaluacion[]) => {
  const obtenida = evaluaciones.reduce((s, e) => s + Number(e.puntuacion_obtenida || 0), 0);
  const maxima = evaluaciones.reduce((s, e) => s + Number(e.puntuacion_maxima || 0), 0);
  return maxima > 0 ? Math.round((obtenida / maxima) * 10 * 10) / 10 : 0;
};

const ScoreGauge: React.FC<{ nota: number; max: number }> = ({ nota, max }) => {
  const pct = max > 0 ? Math.max(0, Math.min(1, nota / max)) : 0;
  const r = 50, circ = 2 * Math.PI * r, color = gradeColor(pct);
  return (
    <div style={{ position: 'relative', width: 124, height: 124, flexShrink: 0 }}>
      <svg width="124" height="124" style={{ transform: 'rotate(-90deg)' }}>
        <defs>
          <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#fafafa" />
            <stop offset="100%" stopColor="#a1a1aa" />
          </linearGradient>
        </defs>
        <circle cx="62" cy="62" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="9" />
        <motion.circle
          cx="62" cy="62" r={r} fill="none"
          stroke={pct >= 0.5 ? 'url(#gaugeGrad)' : color}
          strokeWidth="9" strokeLinecap="round" strokeDasharray={circ}
          initial={false}
          animate={{ strokeDashoffset: circ * (1 - pct) }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
        />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontSize: 32, fontWeight: 800, color: 'var(--text)', lineHeight: 1 }}>{nota.toFixed(1)}</span>
        <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>/ {max.toFixed(0)}</span>
      </div>
    </div>
  );
};

const ESTADOS: Evaluacion['estado'][] = ['CORRECTO', 'PARCIAL', 'INCORRECTO'];

const EvalCard: React.FC<{
  e: Evaluacion;
  index: number;
  onChange: (index: number, cambios: Partial<Evaluacion>) => void;
}> = ({ e, index, onChange }) => {
  const [open, setOpen] = useState(false);

  return (
    <div className="glass" style={{ overflow: 'hidden' }}>
      <button onClick={() => setOpen(!open)} className="eval-header"
        style={{ width: '100%', padding: '15px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, textAlign: 'left', cursor: 'pointer' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 13, minWidth: 0 }}>
          <motion.span animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.25, ease: EASE }} style={{ display: 'grid', placeItems: 'center', color: 'var(--text-faint)' }}>
            <CaretDown size={16} weight="bold" />
          </motion.span>
          <span style={{ minWidth: 0 }}>
            <span style={{ display: 'block', fontWeight: 700, fontSize: 14.5, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {e.pregunta || `Pregunta ${index + 1}`}
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>Página {e.pagina}</span>
          </span>
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
          <StatusBadge status={e.estado} />
          <span style={{ fontWeight: 800, fontSize: 14, color: 'var(--text-dim)' }}>
            {e.puntuacion_obtenida}<span style={{ color: 'var(--text-faint)' }}>/{e.puntuacion_maxima}</span>
          </span>
        </span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: EASE }} style={{ overflow: 'hidden' }}>
            <div style={{ padding: '4px 18px 18px', borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 15, marginTop: 2 }}>
              {e.enunciado && <Field title="Enunciado"><p style={{ fontSize: 14, color: 'var(--text-dim)' }}>{e.enunciado}</p></Field>}
              <Field title="Respuesta del alumno">
                <div style={{ padding: '12px 14px', background: 'rgba(0,0,0,0.25)', borderRadius: 'var(--r-md)', border: '1px solid var(--border)', fontSize: 14, color: 'var(--text-dim)', whiteSpace: 'pre-wrap' }}>
                  {e.respuesta_alumno || '—'}
                </div>
              </Field>
              {e.que_esta_mal && (
                <div style={{
                  padding: '14px 16px',
                  background: e.estado === 'CORRECTO' ? 'var(--success-soft)' : 'var(--error-soft)',
                  borderLeft: `3px solid ${e.estado === 'CORRECTO' ? 'var(--success)' : 'var(--error)'}`,
                  borderRadius: '0 var(--r-md) var(--r-md) 0',
                }}>
                  <h5 style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6, color: e.estado === 'CORRECTO' ? 'var(--success)' : 'var(--error)' }}>
                    {e.estado === 'CORRECTO' ? 'Comentario' : 'Corrección'}
                  </h5>
                  <p style={{ fontSize: 14, color: 'var(--text)' }}>{e.que_esta_mal}</p>
                </div>
              )}
              {e.criterio_rubrica && <Field title="Criterio aplicado"><p style={{ fontSize: 13, color: 'var(--text-faint)' }}>{e.criterio_rubrica}</p></Field>}

              <Field title="Corrección manual del profesor">
                <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                  <select
                    className="input"
                    style={{ width: 'auto', padding: '9px 12px', fontSize: 13 }}
                    value={e.estado}
                    onChange={(ev) => onChange(index, { estado: ev.target.value as Evaluacion['estado'] })}
                  >
                    {ESTADOS.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <input
                      type="number"
                      className="input"
                      style={{ width: 76, padding: '9px 10px', fontSize: 13, textAlign: 'right' }}
                      min={0}
                      max={e.puntuacion_maxima}
                      step={0.25}
                      value={e.puntuacion_obtenida}
                      onChange={(ev) => {
                        const val = Math.max(0, Math.min(Number(ev.target.value) || 0, e.puntuacion_maxima));
                        onChange(index, { puntuacion_obtenida: val });
                      }}
                    />
                    <span style={{ fontSize: 13, color: 'var(--text-faint)' }}>/ {e.puntuacion_maxima} pts</span>
                  </div>
                </div>
              </Field>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

const Field: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div>
    <h5 style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-faint)', marginBottom: 6 }}>{title}</h5>
    {children}
  </div>
);

export const ResultadosSection: React.FC<Props> = ({ resultado, onReset, onUpdated, backLabel = 'Corregir otro' }) => {
  const [downloading, setDownloading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [evaluaciones, setEvaluaciones] = useState<Evaluacion[]>(resultado.evaluaciones);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setEvaluaciones(resultado.evaluaciones);
    setDirty(false);
  }, [resultado]);

  const { datos_examen: d } = resultado;
  const notaFinal = dirty ? calcularNota(evaluaciones) : d.nota_final;
  const pct = d.nota_maxima > 0 ? notaFinal / d.nota_maxima : 0;
  const estado = pct >= 0.9 ? 'Excelente' : pct >= 0.7 ? 'Aprobado' : pct >= 0.5 ? 'Suficiente' : 'Suspenso';

  const handleChangeEval = (index: number, cambios: Partial<Evaluacion>) => {
    setEvaluaciones((prev) => prev.map((ev, i) => (i === index ? { ...ev, ...cambios } : ev)));
    setDirty(true);
    setSaved(false);
  };

  const handleGuardar = async () => {
    if (!resultado.id) return;
    setSaving(true);
    try {
      const datosActualizados = { ...d, nota_final: calcularNota(evaluaciones) };
      const actualizado = await updateHistorialItem(resultado.id, { ...resultado, datos_examen: datosActualizados, evaluaciones });
      onUpdated?.(actualizado);
      setDirty(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      console.error(err);
      alert('No se pudieron guardar los cambios.');
    } finally {
      setSaving(false);
    }
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const datosParaPdf = dirty ? { ...d, nota_final: calcularNota(evaluaciones) } : d;
      const blob = await descargarInforme({ ...resultado, datos_examen: datosParaPdf, evaluaciones });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `informe_${(d.estudiante || 'alumno').replace(/\s+/g, '_')}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) { console.error(err); alert('Error al descargar el informe'); }
    finally { setDownloading(false); }
  };

  return (
    <motion.section className="section" id="resultados" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: EASE }}>
      <div className="section-head">
        <span className="section-num">03</span>
        <div>
          <h2 className="section-title">Resultados</h2>
          <p className="section-desc">{d.titulo} · {d.estudiante} · {d.fecha}</p>
        </div>
        <AnimatePresence>
          {(resultado.editado || dirty) && (
            <motion.span
              initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.2, ease: EASE }}
              className="badge" style={{ background: 'var(--card-solid)', color: 'var(--text-dim)', borderColor: 'var(--border-strong)', marginLeft: 'auto', flexShrink: 0 }}>
              <PencilSimple size={12} weight="bold" /> {dirty ? 'Sin guardar' : 'Editado'}
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      {/* Panel de nota */}
      <div className="glass" style={{ display: 'flex', alignItems: 'center', gap: 26, padding: 24, marginBottom: 16 }}>
        <ScoreGauge nota={notaFinal} max={d.nota_maxima} />
        <div style={{ flex: 1 }}>
          <span className="badge" style={{ background: 'var(--accent-soft)', color: gradeColor(pct), borderColor: 'var(--accent-line)', marginBottom: 12 }}>{estado}</span>
          <div className="stats-resp" style={{ display: 'flex', gap: 28 }}>
            <div>
              <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--text)' }}>{evaluaciones.length}</div>
              <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>preguntas</div>
            </div>
            <div>
              <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--text)' }}>{Math.round(pct * 100)}%</div>
              <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>de acierto</div>
            </div>
          </div>
        </div>
      </div>

      {d.resumen && (
        <div className="glass" style={{ padding: 20, marginBottom: 26 }}>
          <h3 style={{ fontSize: 15, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Sparkle size={17} weight="fill" color="var(--violet)" /> Resumen general
          </h3>
          <p style={{ fontSize: 14, color: 'var(--text-dim)' }}>{d.resumen}</p>
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <h3 style={{ fontSize: 16 }}>Detalle por pregunta</h3>
        <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>Abre una pregunta para corregir la nota manualmente</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 11, marginBottom: 20 }}>
        {evaluaciones.map((e, i) => (
          <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
            <EvalCard e={e} index={i} onChange={handleChangeEval} />
          </motion.div>
        ))}
      </div>

      {resultado.id && (
        <AnimatePresence>
          {dirty && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.25, ease: EASE }} style={{ overflow: 'hidden' }}>
              <div className="glass" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '14px 18px', marginBottom: 20, borderColor: 'var(--border-strong)' }}>
                <span style={{ fontSize: 13.5, color: 'var(--text-dim)' }}>Hay cambios de nota sin guardar en el historial.</span>
                <motion.button className="btn btn-primary" style={{ padding: '9px 16px', fontSize: 13.5 }} onClick={handleGuardar} disabled={saving}
                  whileHover={{ scale: saving ? 1 : 1.02, y: -1 }} whileTap={{ scale: saving ? 1 : 0.98, y: 0 }} transition={{ duration: 0.15, ease: EASE }}>
                  <FloppyDisk size={15} weight="bold" /> {saving ? 'Guardando...' : 'Guardar cambios'}
                </motion.button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      )}
      <AnimatePresence>
        {saved && (
          <motion.p
            initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2, ease: EASE }}
            style={{ fontSize: 12.5, color: 'var(--success)', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 20, overflow: 'hidden' }}>
            <CheckCircle size={14} weight="fill" /> Cambios guardados en el historial.
          </motion.p>
        )}
      </AnimatePresence>

      <div className="row-resp" style={{ display: 'flex', gap: 12 }}>
        <motion.button className="btn btn-secondary" onClick={onReset} style={{ flexShrink: 0 }}
          whileHover={{ y: -1 }} whileTap={{ scale: 0.98, y: 0 }} transition={{ duration: 0.15, ease: EASE }}>
          <ArrowCounterClockwise size={16} weight="bold" /> {backLabel}
        </motion.button>
        <motion.button className="btn btn-primary" style={{ flex: 1 }} onClick={handleDownload} disabled={downloading}
          whileHover={{ scale: downloading ? 1 : 1.01, y: downloading ? 0 : -1 }} whileTap={{ scale: downloading ? 1 : 0.99, y: 0 }}
          transition={{ duration: 0.15, ease: EASE }}>
          <DownloadSimple size={18} weight="bold" />
          {downloading ? 'Generando PDF...' : 'Descargar informe PDF'}
        </motion.button>
      </div>
    </motion.section>
  );
};
