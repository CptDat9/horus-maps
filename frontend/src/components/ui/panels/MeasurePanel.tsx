import { Ruler, Spline, Pentagon, Eraser } from 'lucide-react';
import { Panel } from './Panel';
import { Button } from '../../common/Button';
import { useApp } from '../../../store/AppContext';
import type { MeasureMode } from '../../../types';
import {
  formatArea, formatDistance, calculatePathLength,
  calculatePolygonArea, calculatePolygonPerimeter,
} from '../../../utils/geoUtils';

export function MeasurePanel({ onClose }: { onClose: () => void }) {
  const { measureMode, setMeasureMode, measurePoints, clearMeasure } = useApp();

  const pts = measurePoints;
  const distance = calculatePathLength(pts);
  const area = pts.length >= 3 ? calculatePolygonArea(pts) : 0;
  const perimeter = pts.length >= 3 ? calculatePolygonPerimeter(pts) : 0;

  const modes: { id: MeasureMode; Icon: typeof Spline; label: string }[] = [
    { id: 'distance', Icon: Spline, label: 'Distance' },
    { id: 'area', Icon: Pentagon, label: 'Area' },
  ];

  return (
    <Panel title="Measure" icon={<Ruler size={16} />} onClose={onClose}>
      <div className="p-3 space-y-3">
        <div className="grid grid-cols-2 gap-1.5">
          {modes.map(({ id, Icon, label }) => {
            const active = measureMode === id;
            return (
              <button
                key={id}
                onClick={() => setMeasureMode(id)}
                className={`flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-medium transition-colors
                  ${active ? 'bg-emerald-600 text-white' : 'bg-slate-700/60 text-slate-300 hover:bg-slate-700'}`}
              >
                <Icon size={13} /> {label}
              </button>
            );
          })}
        </div>

        {measureMode === 'none' ? (
          <p className="text-xs text-slate-500 text-center py-4">Pick a mode, then click on the map.</p>
        ) : (
          <>
            <p className="text-[11px] text-slate-500">
              Click on the map to add points{measureMode === 'area' ? ' (3+ for a shape)' : ''}.
            </p>

            {measureMode === 'distance' ? (
              <Readout label="Total distance" value={pts.length >= 2 ? formatDistance(distance) : '—'} />
            ) : (
              <div className="space-y-1.5">
                <Readout label="Area" value={pts.length >= 3 ? formatArea(area) : '—'} />
                <Readout label="Perimeter" value={pts.length >= 3 ? formatDistance(perimeter) : '—'} />
              </div>
            )}

            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-center"
              icon={<Eraser size={13} />}
              disabled={pts.length === 0}
              onClick={() => clearMeasure()}
            >
              Clear
            </Button>
          </>
        )}
      </div>
    </Panel>
  );
}

function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between bg-emerald-950/30 border border-emerald-800/40 rounded-lg px-3 py-2.5">
      <span className="text-xs text-emerald-300/80">{label}</span>
      <span className="text-base font-semibold font-mono text-emerald-300">{value}</span>
    </div>
  );
}
