import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { GraduationCap, Sparkle, PencilLine, ClockCounterClockwise } from '@phosphor-icons/react';
import { OllamaStatus } from './components/OllamaStatus';
import { RubricaSection } from './components/RubricaSection';
import { CorregirSection } from './components/CorregirSection';
import { ResultadosSection } from './components/ResultadosSection';
import { HistorialSection } from './components/HistorialSection';
import { Reveal } from './components/Reveal';
import { getHistorialItem } from './api';
import type { Rubrica, ResultadoExamen } from './types';

type Vista = 'corregir' | 'historial';

const vistaInicial = (): Vista =>
  new URLSearchParams(window.location.search).get('vista') === 'historial' ? 'historial' : 'corregir';

const EASE = [0.22, 1, 0.36, 1] as const;

function App() {
  const [vista, setVista] = useState<Vista>(vistaInicial);
  const [rubricaActiva, setRubricaActiva] = useState<Rubrica | null>(null);
  const [detalle, setDetalle] = useState<ResultadoExamen | null>(null);

  const handleCambiarVista = (v: Vista) => {
    setVista(v);
    setDetalle(null);
    const url = new URL(window.location.href);
    if (v === 'historial') url.searchParams.set('vista', 'historial');
    else url.searchParams.delete('vista');
    window.history.replaceState({}, '', url);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Cualquier resultado (recién corregido en la cola, o uno antiguo del historial)
  // se revisa siempre en la misma pantalla: la pestaña Historial. Así hay un
  // único lugar para ver/editar una corrección, sin duplicar esa vista.
  const handleVerResultado = async (id: string) => {
    try {
      const res = await getHistorialItem(id);
      setVista('historial');
      setDetalle(res);
      const url = new URL(window.location.href);
      url.searchParams.set('vista', 'historial');
      window.history.replaceState({}, '', url);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      console.error(err);
      alert('No se pudo cargar ese resultado.');
    }
  };

  // Clave de la vista actual, para que AnimatePresence sepa cuándo cruzar-desvanecer.
  const vistaKey = vista === 'historial' && detalle ? 'detalle' : vista;

  return (
    <>
      <div className="bg-grid" aria-hidden />

      <header className="topbar">
        <div className="wrap topbar-inner">
          <motion.div className="brand" initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.4, ease: EASE }}>
            <span className="brand-logo">
              <GraduationCap size={20} color="#0a0a12" weight="fill" />
            </span>
            <div style={{ lineHeight: 1.2 }}>
              <div className="brand-name">Corrector <span className="gradient-text">IA</span></div>
              <div className="brand-sub">Corrección local · cualquier idioma</div>
            </div>
          </motion.div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div className="tabs">
              <button className={`tab ${vista === 'corregir' ? 'active' : ''}`} onClick={() => handleCambiarVista('corregir')}>
                {vista === 'corregir' && (
                  <motion.span className="tab-indicator" layoutId="tab-indicator" transition={{ type: 'spring', stiffness: 500, damping: 42, mass: 0.7 }} />
                )}
                <span className="tab-label"><PencilLine size={14} weight="bold" /> Corregir</span>
              </button>
              <button className={`tab ${vista === 'historial' ? 'active' : ''}`} onClick={() => handleCambiarVista('historial')}>
                {vista === 'historial' && (
                  <motion.span className="tab-indicator" layoutId="tab-indicator" transition={{ type: 'spring', stiffness: 500, damping: 42, mass: 0.7 }} />
                )}
                <span className="tab-label"><ClockCounterClockwise size={14} weight="bold" /> Historial</span>
              </button>
            </div>
            <OllamaStatus />
          </div>
        </div>
      </header>

      <main>
        <AnimatePresence mode="wait">
          {vista === 'corregir' && (
            <motion.section
              key="hero"
              className="hero"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25, ease: EASE }}
            >
              <div className="wrap">
                <Reveal>
                  <span className="hero-badge">
                    <span className="dot" /> 100% local con Ollama · privado
                  </span>
                </Reveal>
                <Reveal delay={0.05}>
                  <h1>
                    Corrige exámenes con IA<br />
                    <span className="gradient-text">en cualquier idioma</span>
                  </h1>
                </Reveal>
                <Reveal delay={0.1}>
                  <p>
                    Sube la rúbrica y uno o varios exámenes escaneados. Se corrigen en cola,
                    uno detrás de otro, y cada informe queda guardado con su nota.
                  </p>
                </Reveal>
              </div>
            </motion.section>
          )}
        </AnimatePresence>

        <div className="wrap" style={{ paddingTop: vista === 'historial' ? 40 : 0 }}>
          <AnimatePresence mode="wait">
            {vista === 'corregir' && (
              <motion.div
                key="corregir"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.3, ease: EASE }}
              >
                <Reveal>
                  <RubricaSection activePath={rubricaActiva?.ruta ?? null} onActiveChange={setRubricaActiva} />
                </Reveal>
                <Reveal>
                  <CorregirSection rubricaActiva={rubricaActiva} onVerResultado={handleVerResultado} />
                </Reveal>
              </motion.div>
            )}

            {vista === 'historial' && !detalle && (
              <motion.div
                key="historial"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.3, ease: EASE }}
              >
                <HistorialSection onView={handleVerResultado} />
              </motion.div>
            )}

            {vista === 'historial' && detalle && (
              <motion.div
                key="detalle"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.3, ease: EASE }}
              >
                <ResultadosSection
                  resultado={detalle}
                  onReset={() => setDetalle(null)}
                  onUpdated={setDetalle}
                  backLabel="Volver al historial"
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <footer className="wrap" style={{ padding: '48px 24px', textAlign: 'center', color: 'var(--text-faint)', fontSize: 13 }}>
          <div className="divider" style={{ marginBottom: 24 }} />
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <Sparkle size={14} weight="fill" color="var(--violet)" />
            Corrector IA · procesamiento local con Ollama
          </span>
        </footer>
      </main>
    </>
  );
}

export default App;
