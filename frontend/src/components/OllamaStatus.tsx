import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { WarningCircle } from '@phosphor-icons/react';
import { fetchHealth } from '../api';
import type { EstadoModelo } from '../types';

const EASE = [0.22, 1, 0.36, 1] as const;

export const OllamaStatus: React.FC = () => {
  const [isOk, setIsOk] = useState<boolean | null>(null);
  const [modelCount, setModelCount] = useState(0);
  const [faltantes, setFaltantes] = useState<string[]>([]);

  useEffect(() => {
    let mounted = true;
    const check = async () => {
      const res = await fetchHealth();
      if (!mounted) return;
      setIsOk(res.ollama);
      setModelCount(res.models.length);
      const req = Object.values(res.modelosRequeridos) as EstadoModelo[];
      setFaltantes(req.filter((m) => !m.instalado).map((m) => m.nombre));
    };
    check();
    const interval = setInterval(check, 10000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  if (isOk === null) {
    return <span className="pill"><span className="skeleton" style={{ width: 84, height: 12 }} /></span>;
  }

  const hayFaltantes = isOk && faltantes.length > 0;
  const titulo = !isOk
    ? 'Ollama no responde en localhost:11434'
    : hayFaltantes
      ? `Faltan modelos: ${faltantes.join(', ')} — instálalos con "ollama pull <modelo>"`
      : `${modelCount} modelo(s) disponibles`;

  return (
    <motion.div className="pill" title={titulo} initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.25, ease: EASE }}>
      <span className={`dot ${isOk ? (hayFaltantes ? 'off' : 'on') : 'off'}`} />
      <span>{!isOk ? 'Ollama offline' : hayFaltantes ? 'Faltan modelos' : 'Ollama activo'}</span>
      <AnimatePresence>
        {hayFaltantes && (
          <motion.span
            initial={{ opacity: 0, scale: 0.6, width: 0 }} animate={{ opacity: 1, scale: 1, width: 14 }} exit={{ opacity: 0, scale: 0.6, width: 0 }}
            transition={{ duration: 0.2, ease: EASE }} style={{ display: 'inline-flex', overflow: 'hidden' }}>
            <WarningCircle size={14} weight="fill" color="var(--warning)" />
          </motion.span>
        )}
      </AnimatePresence>
    </motion.div>
  );
};
