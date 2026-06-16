import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  SplitSquareHorizontal, Calendar, Loader2, ArrowLeftRight, Pentagon, Crosshair,
} from 'lucide-react';
import { Panel } from './Panel';
import { Button } from '../../common/Button';
import { useApp } from '../../../store/AppContext';
import { stacApi } from '../../../services/api';
import type { AOI, STACItem, ComparisonView, ComparisonSide } from '../../../types';
import { geometryBBox } from '../../../utils/geoUtils';

const GOOGLE = 'google';   // sentinel-value for "current Google imagery"
const SENTINEL_NATIVE = 15;
const GOOGLE_NATIVE = 20;

const fmtDate = (dt?: string | null) =>
  dt ? new Date(dt).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }) : '—';

interface ComparePanelProps {
  selectedAoi: AOI | null;
  baseTileUrl?: string;
  onOpenViewer: (v: ComparisonView) => void;
  onNeedAOI: () => void;
  onFlyTo: (aoi: AOI) => void;
  onClose: () => void;
}

export function ComparePanel({
  selectedAoi, baseTileUrl, onOpenViewer, onNeedAOI, onFlyTo, onClose,
}: ComparePanelProps) {
  const { addNotification } = useApp();
  const [leftSel, setLeftSel] = useState('');
  const [rightSel, setRightSel] = useState('');
  const [building, setBuilding] = useState(false);

  const today = new Date().toISOString().slice(0, 10);
  const yearAgo = new Date(Date.now() - 365 * 864e5).toISOString().slice(0, 10);
  const [from, setFrom] = useState(yearAgo);
  const [to, setTo] = useState(today);

  const { data: scenes = [], isLoading: scenesLoading } = useQuery({
    queryKey: ['stac-items', selectedAoi?.id, from, to],
    queryFn: async () => {
      if (!selectedAoi) return [];
      const res = await stacApi.search({
        collections: ['sentinel-2-l2a'],
        bbox: geometryBBox(selectedAoi.geometry),
        datetime: `${from}T00:00:00Z/${to}T23:59:59Z`,
        limit: 50,
      }) as { features: STACItem[] };
      return (res.features ?? []).sort(
        (a, b) => new Date(b.properties.datetime ?? 0).getTime()
                - new Date(a.properties.datetime ?? 0).getTime()
      );
    },
    enabled: !!selectedAoi,
  });

  // Pre-select newest (After) + oldest (Before) Sentinel scenes once loaded.
  useEffect(() => {
    if (scenes.length >= 2 && !leftSel && !rightSel) {
      setRightSel(scenes[0].id);
      setLeftSel(scenes[scenes.length - 1].id);
    }
  }, [scenes, leftSel, rightSel]);

  // Resolve a selection ('google' | sentinel item id) → a comparison side.
  const resolveSide = async (sel: string): Promise<ComparisonSide | null> => {
    if (sel === GOOGLE) {
      if (!baseTileUrl) return null;
      return { tileUrl: baseTileUrl, imageUrl: null, label: 'Google (current)', nativeZoom: GOOGLE_NATIVE };
    }
    const item = scenes.find((s) => s.id === sel);
    const { tile_url } = await stacApi.itemTileUrl(sel);
    return { tileUrl: tile_url, imageUrl: null, label: `Sentinel-2 · ${fmtDate(item?.properties.datetime)}`, nativeZoom: SENTINEL_NATIVE };
  };

  const compare = async () => {
    if (!selectedAoi || !leftSel || !rightSel) return;
    setBuilding(true);
    try {
      const [left, right] = await Promise.all([resolveSide(leftSel), resolveSide(rightSel)]);
      if (!left || !right) throw new Error('missing side');
      onOpenViewer({ title: selectedAoi.name, bbox: geometryBBox(selectedAoi.geometry), left, right });
    } catch {
      addNotification({ type: 'error', message: 'Could not build comparison' });
    } finally {
      setBuilding(false);
    }
  };

  // Options for each side: current Google + every Sentinel scene by date.
  const options = useMemo(() => ([
    ...(baseTileUrl ? [{ value: GOOGLE, label: 'Google — current' }] : []),
    ...scenes.map((s) => ({ value: s.id, label: `Sentinel-2 · ${fmtDate(s.properties.datetime)}` })),
  ]), [scenes, baseTileUrl]);

  if (!selectedAoi) {
    return (
      <Panel title="Compare in time" icon={<SplitSquareHorizontal size={16} />} onClose={onClose}>
        <div className="p-4 flex flex-col items-center gap-3 text-center py-10">
          <Pentagon size={26} className="text-slate-600" />
          <p className="text-xs text-slate-400 leading-relaxed">
            Select or draw an Area of Interest first, then compare two scenes over it.
          </p>
          <Button variant="primary" size="sm" icon={<Pentagon size={13} />} onClick={onNeedAOI}>
            Go to areas
          </Button>
        </div>
      </Panel>
    );
  }

  return (
    <Panel
      title="Compare in time"
      icon={<SplitSquareHorizontal size={16} />}
      onClose={onClose}
      footer={
        <Button
          variant="primary" size="md" className="w-full justify-center"
          icon={building ? <Loader2 size={14} className="animate-spin" /> : <ArrowLeftRight size={14} />}
          loading={building}
          disabled={!leftSel || !rightSel || leftSel === rightSel}
          onClick={compare}
        >
          Compare
        </Button>
      }
    >
      <div className="p-3 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] text-slate-500 flex-1">
            Pick two scenes over <span className="text-slate-300">{selectedAoi.name}</span> — Sentinel-2
            by date or current Google. Side-by-side, synced zoom.
          </p>
          <button onClick={() => onFlyTo(selectedAoi)}
            className="shrink-0 flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300" title="Fly to area">
            <Crosshair size={12} /> Go to area
          </button>
        </div>

        {/* Sentinel time window */}
        <div className="space-y-1">
          <label className="text-[11px] text-slate-400 flex items-center gap-1">
            <Calendar size={11} /> Sentinel time range
          </label>
          <div className="flex items-center gap-1.5">
            <input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)}
              className="flex-1 bg-slate-900 border border-slate-700 focus:border-blue-500 rounded-lg px-2 py-1.5 text-[11px] text-slate-200 outline-none" />
            <span className="text-slate-500 text-[11px]">→</span>
            <input type="date" value={to} min={from} max={today} onChange={(e) => setTo(e.target.value)}
              className="flex-1 bg-slate-900 border border-slate-700 focus:border-blue-500 rounded-lg px-2 py-1.5 text-[11px] text-slate-200 outline-none" />
          </div>
        </div>

        {scenesLoading ? (
          <div className="flex items-center gap-2 text-xs text-slate-400 py-2">
            <Loader2 size={13} className="animate-spin" /> Searching imagery…
          </div>
        ) : (
          [
            { label: 'Before / Left', val: leftSel, set: setLeftSel },
            { label: 'After / Right', val: rightSel, set: setRightSel },
          ].map(({ label, val, set }) => (
            <div key={label} className="space-y-1">
              <label className="text-[11px] text-slate-400">{label}</label>
              <select
                value={val}
                onChange={(e) => set(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 focus:border-blue-500 rounded-lg px-2.5 py-2 text-xs text-slate-200 outline-none"
              >
                <option value="">Choose scene…</option>
                {options.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          ))
        )}

        {scenes.length === 0 && !scenesLoading && (
          <p className="text-[11px] text-slate-500">
            No Sentinel-2 in this range{baseTileUrl ? ' — you can still compare against current Google.' : '.'}
          </p>
        )}
      </div>
    </Panel>
  );
}
