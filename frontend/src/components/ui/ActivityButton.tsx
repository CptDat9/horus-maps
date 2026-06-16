import { useState, useRef, useEffect } from 'react';
import {
  Activity, Loader2, CheckCircle2, XCircle, AlertCircle,
} from 'lucide-react';
import type { Task } from '../../types';

const statusIcon = (s: string) => ({
  pending: <Loader2 size={13} className="animate-spin text-yellow-400" />,
  running: <Loader2 size={13} className="animate-spin text-blue-400" />,
  completed: <CheckCircle2 size={13} className="text-emerald-400" />,
  failed: <XCircle size={13} className="text-red-400" />,
}[s] ?? <AlertCircle size={13} className="text-slate-400" />);

const TASK_LABELS: Record<string, string> = {
  extract_aoi: 'AOI extraction',
  temporal_comparison: 'Temporal comparison',
  detection: 'Object detection',
};

/** Background-task activity indicator + popover (RabbitMQ/SSE jobs). */
export function ActivityButton({ tasks }: { tasks: Task[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const active = tasks.filter((t) => t.status === 'running' || t.status === 'pending').length;

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        title="Background tasks"
        className={`relative w-11 h-11 rounded-2xl flex items-center justify-center shadow-xl border backdrop-blur transition-colors
          ${open ? 'bg-slate-700 border-slate-600 text-white' : 'bg-slate-800/95 border-slate-700 text-slate-200 hover:bg-slate-700/90'}`}
      >
        <Activity size={18} className={active > 0 ? 'text-blue-400' : ''} />
        {active > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 bg-blue-600 text-white text-[10px] rounded-full flex items-center justify-center font-medium">
            {active}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute top-full right-0 mt-2 w-72 bg-slate-800/97 backdrop-blur border border-slate-700 rounded-2xl shadow-2xl overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-700/70">
            <p className="text-xs font-semibold text-slate-100">Background tasks</p>
            <p className="text-[11px] text-slate-500">Async jobs via the message queue</p>
          </div>
          <div className="max-h-72 overflow-y-auto p-2 space-y-1.5">
            {tasks.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-6">No tasks yet.</p>
            ) : (
              [...tasks].reverse().map((t) => (
                <div key={t.id} className="bg-slate-900/50 rounded-lg px-3 py-2 space-y-1">
                  <div className="flex items-center gap-2">
                    {statusIcon(t.status)}
                    <span className="text-xs text-slate-200 font-medium truncate flex-1">
                      {TASK_LABELS[t.task_type] ?? t.task_type}
                    </span>
                    <span className="text-[10px] text-slate-500 capitalize">{t.status}</span>
                  </div>
                  {t.error_message && (
                    <p className="text-[11px] text-red-400 truncate">{t.error_message}</p>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
