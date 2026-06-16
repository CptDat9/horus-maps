import { useState } from 'react';
import { Layers, Check, Map as MapIcon, Satellite } from 'lucide-react';
import type { MapLayer } from '../../types';

interface LayerSwitcherProps {
  baseLayers: MapLayer[];
  activeBaseId: string;
  setActiveBase: (id: string) => void;
  overlayLayers: MapLayer[];
  visibleOverlayIds: Set<string>;
  toggleOverlay: (id: string) => void;
}

/** Google-Maps style base picker (single) + analysis overlay toggles (multi). */
export function LayerSwitcher({
  baseLayers, activeBaseId, setActiveBase,
  overlayLayers, visibleOverlayIds, toggleOverlay,
}: LayerSwitcherProps) {
  const [open, setOpen] = useState(false);
  const activeBase = baseLayers.find((l) => l.id === activeBaseId);

  return (
    <div className="relative">
      {open && (
        <div className="absolute bottom-full left-0 mb-2 w-60 bg-slate-800/97 backdrop-blur border border-slate-700 rounded-2xl shadow-2xl overflow-hidden">
          <div className="p-3 space-y-1">
            <p className="text-[10px] text-slate-500 uppercase tracking-widest px-1 mb-1">Base map</p>
            {baseLayers.map((l) => {
              const active = l.id === activeBaseId;
              return (
                <button
                  key={l.id}
                  onClick={() => setActiveBase(l.id)}
                  className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs transition-colors
                    ${active ? 'bg-blue-600/90 text-white' : 'text-slate-300 hover:bg-slate-700/70'}`}
                >
                  <MapIcon size={13} className="shrink-0 opacity-80" />
                  <span className="flex-1 text-left truncate">{l.name}</span>
                  {active && <Check size={13} className="shrink-0" />}
                </button>
              );
            })}
          </div>

          {overlayLayers.length > 0 && (
            <div className="p-3 pt-2 border-t border-slate-700/70 space-y-1">
              <p className="text-[10px] text-slate-500 uppercase tracking-widest px-1 mb-1">Satellite overlays</p>
              {overlayLayers.map((l) => {
                const on = visibleOverlayIds.has(l.id);
                return (
                  <button
                    key={l.id}
                    onClick={() => toggleOverlay(l.id)}
                    className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs transition-colors
                      ${on ? 'bg-emerald-900/40 text-emerald-300' : 'text-slate-400 hover:bg-slate-700/70'}`}
                  >
                    <Satellite size={13} className="shrink-0 opacity-80" />
                    <span className="flex-1 text-left truncate">{l.name}</span>
                    <span className={`w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0
                      ${on ? 'bg-emerald-500 border-emerald-500' : 'border-slate-500'}`}>
                      {on && <Check size={10} className="text-white" />}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        className={`flex items-center gap-2 h-11 pl-2.5 pr-3.5 rounded-2xl shadow-xl border backdrop-blur transition-colors
          ${open
            ? 'bg-slate-700 border-slate-600 text-white'
            : 'bg-slate-800/95 border-slate-700 text-slate-200 hover:bg-slate-700/90'}`}
      >
        <Layers size={17} className="text-blue-400" />
        <span className="text-xs font-medium max-w-[8rem] truncate">{activeBase?.name ?? 'Layers'}</span>
      </button>
    </div>
  );
}
