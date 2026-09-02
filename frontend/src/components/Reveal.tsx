import { motion } from 'framer-motion';
import type { ReactNode } from 'react';

interface Props {
  children: ReactNode;
  delay?: number;
}

/** Anima el contenido al entrar en el viewport (aparece desde abajo con fundido). */
export const Reveal: React.FC<Props> = ({ children, delay = 0 }) => (
  <motion.div
    initial={{ opacity: 0, y: 24 }}
    whileInView={{ opacity: 1, y: 0 }}
    viewport={{ once: true, margin: '-60px' }}
    transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1], delay }}
  >
    {children}
  </motion.div>
);
