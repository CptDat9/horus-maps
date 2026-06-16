
import { Plus, Minus, Crosshair } from 'lucide-react';
import type { Map } from 'leaflet';

interface MapControlsProps {
  mapRef: Map | null;
  onResetView: () => void;
}

export function MapControls({ mapRef, onResetView }: MapControlsProps) {
  const btn = 'w-8 h-8 bg-slate-800/90 border border-slate-600 rounded-lg flex items-center justify-center text-slate-300 hover:bg-slate-700 hover:text-slate-100 transition-colors shadow-lg backdrop-blur-sm';

  return (
    <div className="absolute right-4 bottom-6 z-[1000] flex flex-col gap-1.5">
      <button className={btn} onClick={() => mapRef?.zoomIn()} title="Zoom in">
        <Plus size={13} />
      </button>
      <button className={btn} onClick={() => mapRef?.zoomOut()} title="Zoom out">
        <Minus size={13} />
      </button>
      <div className="h-px bg-slate-600/50 mx-1 my-0.5" />
      <button className={btn} onClick={onResetView} title="Reset view">
        <Crosshair size={13} />
      </button>
    </div>
  );
}
