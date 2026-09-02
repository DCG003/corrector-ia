import { CheckCircle, WarningCircle, XCircle } from '@phosphor-icons/react';

interface Props {
  status: 'CORRECTO' | 'PARCIAL' | 'INCORRECTO';
}

const config = {
  CORRECTO: { cls: 'badge-success', Icon: CheckCircle, label: 'Correcto' },
  PARCIAL: { cls: 'badge-warning', Icon: WarningCircle, label: 'Parcial' },
  INCORRECTO: { cls: 'badge-error', Icon: XCircle, label: 'Incorrecto' },
} as const;

export const StatusBadge: React.FC<Props> = ({ status }) => {
  const { cls, Icon, label } = config[status] ?? config.PARCIAL;
  return (
    <span className={`badge ${cls}`}>
      <Icon size={13} weight="fill" />
      {label}
    </span>
  );
};
