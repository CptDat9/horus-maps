import { Pentagon, Ruler, SplitSquareHorizontal, Sparkles } from 'lucide-react';
import { useApp } from '../../store/AppContext';
import type { ActiveTool } from '../../types';

const TOOLS: { id: ActiveTool; Icon: typeof Ruler; label: string }[] = [
  { id: 'aoi', Icon: Pentagon, label: 'Area of Interest' },
  { id: 'measure', Icon: Ruler, label: 'Measure' },
  { id: 'compare', Icon: SplitSquareHorizontal, label: 'Compare in time' },
  { id: 'detect', Icon: Sparkles, label: 'AI Detection' },
];

/** Floating vertical tool dock (Google-Earth style). */
export function Toolbar() {
  const { activeTool, setActiveTool } = useApp();

  return (
    <div className="flex flex-col gap-1 bg-slate-800/95 backdrop-blur border border-slate-700 rounded-2xl p-1.5 shadow-xl">
      {TOOLS.map(({ id, Icon, label }) => {
        const active = activeTool === id;
        return (
          <button
            key={id}
            onClick={() => setActiveTool(active ? 'none' : id)}
            title={label}
            aria-label={label}
            className={`group relative w-10 h-10 rounded-xl flex items-center justify-center transition-colors
              ${active
                ? 'bg-blue-600 text-white'
                : 'text-slate-300 hover:bg-slate-700 hover:text-white'}`}
          >
            <Icon size={18} />
            <span className="pointer-events-none absolute left-full ml-2 px-2 py-1 rounded-md bg-slate-900 text-slate-100 text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity shadow-lg z-10">
              {label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
