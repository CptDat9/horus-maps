
import { X, CheckCircle2, AlertCircle, Info, AlertTriangle } from 'lucide-react';
import { useApp } from '../../store/AppContext';

const ICONS = {
  success: <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />,
  error: <AlertCircle size={14} className="text-red-400 shrink-0" />,
  warning: <AlertTriangle size={14} className="text-yellow-400 shrink-0" />,
  info: <Info size={14} className="text-blue-400 shrink-0" />,
};

const BORDER = {
  success: 'border-emerald-700/50',
  error: 'border-red-700/50',
  warning: 'border-yellow-700/50',
  info: 'border-blue-700/50',
};

export function NotificationToasts() {
  const { notifications, removeNotification } = useApp();
  if (!notifications.length) return null;

  return (
    <div className="fixed bottom-5 right-5 z-[3000] flex flex-col gap-2 pointer-events-none">
      {notifications.map((n) => (
        <div
          key={n.id}
          className={`flex items-start gap-2.5 bg-slate-800 border ${BORDER[n.type]} rounded-xl px-3.5 py-2.5 shadow-2xl pointer-events-auto max-w-xs`}
        >
          {ICONS[n.type]}
          <p className="text-xs text-slate-200 flex-1 leading-relaxed">{n.message}</p>
          <button
            onClick={() => removeNotification(n.id)}
            className="text-slate-500 hover:text-slate-300 transition-colors"
          >
            <X size={12} />
          </button>
        </div>
      ))}
    </div>
  );
}
