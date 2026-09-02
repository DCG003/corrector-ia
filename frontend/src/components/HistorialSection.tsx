import { useEffect, useState } from 'react';
import { ClockCounterClockwise, Eye, Trash, PencilSimple, ArrowsClockwise } from '@phosphor-icons/react';
import { motion, AnimatePresence } from 'framer-motion';
import type { HistorialItem } from '../types';
import { listHistorial, deleteHistorialItem } from '../api';

interface Props {
  onView: (id: string) => void;
}

const EASE = [0.22, 1, 0.36, 1] as const;
const gradeColor = (pct: number) => (pct >= 0.9 ? 'var(--success)' : pct >= 0.5 ? 'var(--text-dim)' : 'var(--error)');

export const HistorialSection: React.FC<Props> = ({ onView }) => {
  const [items, setItems] = useState<HistorialItem[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchList = async () => {
    try {
      setItems(await listHistorial());
    } catch (err) {
      console.error(err);
      setItems([]);
    }
  };

  useEffect(() => { fetchList(); }, []);

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchList();
    setTimeout(() => setRefreshing(false), 300);
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!window.confirm('¿Eliminar esta corrección del historial? Esta acción no se puede deshacer.')) return;
    setDeletingId(id);
    try {
      await deleteHistorialItem(id);
      setItems((prev) => (prev || []).filter((i) => i.id !== id));
    } catch (err) {
      console.error(err);
      alert('No se pudo eliminar el resultado.');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <section className="section" id="historial">
      <div className="section-head">
        <span className="section-num"><ClockCounterClockwise size={14} weight="bold" /></span>
        <div>
          <h2 className="section-title">Historial de correcciones</h2>
          <p className="section-desc">Exámenes corregidos anteriormente. Se guardan localmente aunque cierres la pestaña.</p>
        </div>
        <button className="btn btn-secondary" style={{ marginLeft: 'auto', padding: '9px 14px', fontSize: 13 }} onClick={handleRefresh}>
          <motion.span animate={{ rotate: refreshing ? 360 : 0 }} transition={{ duration: 0.5, ease: EASE }} style={{ display: 'inline-flex' }}>
            <ArrowsClockwise size={15} weight="bold" />
          </motion.span>
          Actualizar
        </button>
      </div>

      {items === null && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 64, borderRadius: 'var(--r-lg)' }} />)}
        </div>
      )}

      {items !== null && items.length === 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3, ease: EASE }} className="glass" style={{ padding: 32, textAlign: 'center' }}>
          <p style={{ color: 'var(--text-faint)', fontSize: 14 }}>Todavía no has corregido ningún examen.</p>
        </motion.div>
      )}

      {items !== null && items.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <AnimatePresence initial={false}>
            {items.map((item, i) => {
              const pct = item.nota_maxima > 0 ? item.nota_final / item.nota_maxima : 0;
              return (
                <motion.button
                  key={item.id}
                  layout
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                  transition={{ delay: Math.min(i * 0.04, 0.3), duration: 0.3, ease: EASE }}
                  whileHover={{ x: 2 }}
                  whileTap={{ scale: 0.99 }}
                  onClick={() => onView(item.id)}
                  className="row"
                  style={{ textAlign: 'left', width: '100%', cursor: 'pointer' }}
                >
                  <span style={{ display: 'flex', alignItems: 'center', gap: 13, minWidth: 0 }}>
                    <span style={{
                      width: 42, height: 42, borderRadius: 12, flexShrink: 0, display: 'grid', placeItems: 'center',
                      background: 'var(--card-solid)', border: '1px solid var(--border)', fontWeight: 800, fontSize: 13.5,
                      color: gradeColor(pct),
                    }}>
                      {item.nota_final.toFixed(1)}
                    </span>
                    <span style={{ minWidth: 0 }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontWeight: 700, fontSize: 14, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {item.estudiante}
                        </span>
                        {item.editado && (
                          <span title="Editado manualmente" style={{ display: 'inline-flex' }}>
                            <PencilSimple size={12} weight="bold" color="var(--text-faint)" />
                          </span>
                        )}
                      </span>
                      <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>
                        {item.titulo} · {item.num_preguntas} pregunta(s) · {item.fecha}
                      </span>
                    </span>
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
                    <span className="btn-icon" title="Ver detalle">
                      <Eye size={16} weight="bold" />
                    </span>
                    <span
                      className="btn-icon danger"
                      style={{ opacity: deletingId === item.id ? 0.5 : 1 }}
                      title="Eliminar del historial"
                      onClick={(e) => handleDelete(e, item.id)}
                    >
                      <Trash size={16} weight="bold" />
                    </span>
                  </span>
                </motion.button>
              );
            })}
          </AnimatePresence>
        </div>
      )}
    </section>
  );
};
