import { useRef, useState } from 'react';
import { X, GripVertical } from 'lucide-react';
import type { ReactNode } from 'react';

interface PanelProps {
  title: string;
  icon?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}

/**
 * Contextual floating card — shown while a tool is active. Draggable by its
 * header so it never stays stuck under the search bar / other controls.
 */
export function Panel({ title, icon, onClose, children, footer }: PanelProps) {
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const drag = useRef<{ px: number; py: number; ox: number; oy: number } | null>(null);

  const onPointerDown = (e: React.PointerEvent) => {
    // Don't start a drag from the close button.
    if ((e.target as HTMLElement).closest('button[aria-label="Close"]')) return;
    drag.current = { px: e.clientX, py: e.clientY, ox: pos.x, oy: pos.y };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    setPos({ x: drag.current.ox + (e.clientX - drag.current.px), y: drag.current.oy + (e.clientY - drag.current.py) });
  };
  const endDrag = () => { drag.current = null; };

  return (
    <div
      className="w-72 max-w-[calc(100vw-2rem)] flex flex-col max-h-[calc(100vh-7rem)] bg-slate-800/97 backdrop-blur border border-slate-700 rounded-2xl shadow-2xl overflow-hidden"
      style={{ transform: `translate(${pos.x}px, ${pos.y}px)` }}
    >
      <div
        className="flex items-center gap-2 px-4 py-3 border-b border-slate-700/70 shrink-0 cursor-move select-none touch-none"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onDoubleClick={() => setPos({ x: 0, y: 0 })}
        title="Kéo để di chuyển · nhấp đúp để đưa về vị trí cũ"
      >
        <GripVertical size={14} className="text-slate-500 shrink-0 -ml-1" />
        {icon && <span className="text-blue-400 shrink-0">{icon}</span>}
        <h2 className="text-sm font-semibold text-slate-100 flex-1 truncate">{title}</h2>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-200 transition-colors p-0.5" aria-label="Close">
          <X size={16} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">{children}</div>
      {footer && <div className="px-4 py-3 border-t border-slate-700/70 shrink-0">{footer}</div>}
    </div>
  );
}
