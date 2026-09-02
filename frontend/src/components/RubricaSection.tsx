import { useState, useEffect } from 'react';
import { UploadSimple, FileText, CheckCircle, Spinner, Trash } from '@phosphor-icons/react';
import { motion, AnimatePresence } from 'framer-motion';
import { listRubricas, uploadRubrica, activateRubrica, deleteRubrica } from '../api';
import type { Rubrica } from '../types';

interface Props {
  activePath: string | null;
  onActiveChange: (r: Rubrica | null) => void;
}

const EASE = [0.22, 1, 0.36, 1] as const;

export const RubricaSection: React.FC<Props> = ({ activePath, onActiveChange }) => {
  const [rubricas, setRubricas] = useState<Rubrica[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState('');
  const [deletingPath, setDeletingPath] = useState<string | null>(null);

  const fetchList = async () => {
    try {
      const data = await listRubricas();
      setRubricas(data);
      const yaActiva = data.find((r) => r.activa);
      if (yaActiva && !activePath) onActiveChange(yaActiva);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => { fetchList(); /* eslint-disable-next-line */ }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      setIsUploading(true);
      setProgress('Iniciando subida...');
      try {
        const nueva = await uploadRubrica(file, (d) => { if (d.message) setProgress(d.message); });
        await fetchList();
        if (nueva?.ruta) onActiveChange(nueva);
      } catch (err) {
        console.error(err);
        setProgress('Error al procesar la rúbrica.');
      } finally {
        setIsUploading(false);
        setTimeout(() => setProgress(''), 1500);
      }
    }
    e.target.value = '';
  };

  const handleActivate = async (r: Rubrica) => {
    if (isUploading) return;
    try {
      await activateRubrica(r.ruta);
      onActiveChange(r);
    } catch (err) { console.error(err); }
  };

  const handleDelete = async (e: React.MouseEvent, r: Rubrica) => {
    e.stopPropagation();
    if (isUploading || deletingPath) return;
    if (!window.confirm(`¿Eliminar la rúbrica "${r.nombre_archivo}"? Esta acción no se puede deshacer.`)) return;
    setDeletingPath(r.ruta);
    try {
      await deleteRubrica(r.ruta);
      setRubricas((prev) => prev.filter((x) => x.ruta !== r.ruta));
      if (activePath === r.ruta) onActiveChange(null);
    } catch (err) {
      console.error(err);
      alert('No se pudo eliminar la rúbrica.');
    } finally {
      setDeletingPath(null);
    }
  };

  return (
    <section className="section" id="rubrica">
      <div className="section-head">
        <span className="section-num">01</span>
        <div>
          <h2 className="section-title">Rúbrica de corrección</h2>
          <p className="section-desc">Sube el PDF con la solución o los criterios, o reutiliza una guardada.</p>
        </div>
      </div>

      <label className="drop glass" style={{ marginBottom: 20 }}>
        <input type="file" accept="application/pdf" onChange={handleUpload} disabled={isUploading} />
        <span className="drop-icon">
          {isUploading
            ? <Spinner size={24} className="spin" color="var(--violet)" />
            : <UploadSimple size={24} color="var(--violet)" weight="bold" />}
        </span>
        {isUploading ? (
          <p style={{ color: 'var(--violet)', fontWeight: 600 }}>{progress || 'Procesando...'}</p>
        ) : (
          <>
            <p style={{ color: 'var(--text)', fontWeight: 700, marginBottom: 4 }}>Arrastra o haz clic para subir una rúbrica PDF</p>
            <p style={{ fontSize: 13, color: 'var(--text-faint)' }}>{progress || 'Se generan embeddings locales para la búsqueda de criterios'}</p>
          </>
        )}
      </label>

      {rubricas.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {rubricas.map((r, i) => {
            const active = activePath === r.ruta;
            return (
              <motion.button
                key={r.ruta}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05, duration: 0.3, ease: EASE }}
                whileTap={{ scale: 0.99 }}
                onClick={() => handleActivate(r)}
                className="row"
                style={{
                  textAlign: 'left', width: '100%', cursor: 'pointer',
                  borderColor: active ? 'var(--border-strong)' : undefined,
                  background: active ? 'var(--card-hover)' : undefined,
                }}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: 13, minWidth: 0 }}>
                  <span style={{
                    width: 36, height: 36, borderRadius: 10, flexShrink: 0, display: 'grid', placeItems: 'center',
                    background: active ? 'var(--grad-soft)' : 'rgba(255,255,255,0.05)',
                    transition: `background var(--dur-base) ${EASE.join()}`,
                  }}>
                    <FileText size={18} weight={active ? 'fill' : 'regular'} color={active ? 'var(--violet)' : 'var(--text-faint)'} />
                  </span>
                  <span style={{ minWidth: 0 }}>
                    <span style={{ display: 'block', fontWeight: 700, fontSize: 14, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {r.nombre_archivo}
                    </span>
                    <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>
                      {r.total_chunks} fragmentos{r.fecha_creacion ? ` · ${r.fecha_creacion}` : ''}
                    </span>
                  </span>
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
                  <AnimatePresence>
                    {active && (
                      <motion.span
                        initial={{ opacity: 0, scale: 0.6 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.6 }}
                        transition={{ duration: 0.2, ease: EASE }}
                        style={{ display: 'inline-flex', marginRight: 4 }}
                      >
                        <CheckCircle size={20} weight="fill" color="var(--violet)" />
                      </motion.span>
                    )}
                  </AnimatePresence>
                  <span
                    role="button"
                    aria-label={`Eliminar rúbrica ${r.nombre_archivo}`}
                    className="btn-icon danger"
                    style={{ opacity: deletingPath === r.ruta ? 0.5 : 1 }}
                    onClick={(e) => handleDelete(e, r)}
                  >
                    <Trash size={15} weight="bold" />
                  </span>
                </span>
              </motion.button>
            );
          })}
        </div>
      )}
    </section>
  );
};
