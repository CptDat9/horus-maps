import { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  SplitSquareHorizontal, Calendar, Loader2, ArrowLeftRight, Pentagon, Crosshair, History,
} from 'lucide-react';
import { Panel } from './Panel';
import { Button } from '../../common/Button';
import { useApp } from '../../../store/AppContext';
import { stacApi, comparisonApi } from '../../../services/api';
import { useTaskSSE } from '../../../hooks/useSSE';
import type { AOI, STACItem, ComparisonView, ComparisonSide, TemporalComparison } from '../../../types';
import { geometryBBox } from '../../../utils/geoUtils';

const GOOGLE = 'google';   // sentinel-value for "current Google imagery"
const SENTINEL_NATIVE = 15;
const GOOGLE_NATIVE = 20;

const fmtDate = (dt?: string | null) =>
  dt ? new Date(dt).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }) : '—';

// Shape of the background task's result (built by the backend _temporal_comparison
// handler): each side's AOI-cropped image + slippy tile URL.
interface ComparisonSideResult {
  item_id: string;
  datetime: string | null;
  tile_url: string | null;
  image_url: string | null;
  snapshot_url?: string | null;
}
interface ComparisonResult {
  bbox?: number[];
  left?: ComparisonSideResult;
  right?: ComparisonSideResult;
}

const statusLabel = (s: string) =>
  s === 'completed' ? 'Ready' : s === 'failed' ? 'Failed' : s === 'running' ? 'Building…' : 'Queued';

// Fraction of the AOI bbox covered by a scene's footprint bbox. A scene that
// only clips the AOI (low coverage) renders mostly nodata (blank) in the
// snapshot and the synced viewer, so we keep only scenes that truly cover it.
function aoiCoverage(aoiBox: number[], featBbox?: number[]): number {
  if (!featBbox || featBbox.length < 4) return 0;
  const [aMinX, aMinY, aMaxX, aMaxY] = aoiBox;
  const fMinX = featBbox[0];
  const fMinY = featBbox[1];
  const fMaxX = featBbox[featBbox.length - 2];
  const fMaxY = featBbox[featBbox.length - 1];
  const ix = Math.max(0, Math.min(aMaxX, fMaxX) - Math.max(aMinX, fMinX));
  const iy = Math.max(0, Math.min(aMaxY, fMaxY) - Math.max(aMinY, fMinY));
  const aoiArea = (aMaxX - aMinX) * (aMaxY - aMinY);
  return aoiArea > 0 ? (ix * iy) / aoiArea : 0;
}

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
  const { addNotification, sessionId } = useApp();
  const qc = useQueryClient();
  const [leftSel, setLeftSel] = useState('');
  const [rightSel, setRightSel] = useState('');
  const [building, setBuilding] = useState(false);
  const [trackTaskId, setTrackTaskId] = useState<string | null>(null);

  // Track the background comparison build; toasts + invalidation come for free.
  useTaskSSE(trackTaskId);

  // History of comparisons saved for this AOI (newest first). Polls while any
  // entry is still building so the status flips to "Ready" on its own.
  const { data: history = [], isLoading: historyLoading, isError: historyError } = useQuery({
    queryKey: ['comparisons', sessionId, selectedAoi?.id],
    queryFn: () =>
      comparisonApi.list(sessionId!, selectedAoi!.id) as Promise<TemporalComparison[]>,
    enabled: !!sessionId && !!selectedAoi,
    refetchInterval: (q) => {
      const rows = q.state.data as TemporalComparison[] | undefined;
      return rows?.some((c) => c.status === 'pending' || c.status === 'running') ? 4000 : false;
    },
  });

  const today = new Date().toISOString().slice(0, 10);
  // Default window spans a few years back so "Before" can reach real history;
  // the From picker has no min, so users can go further still.
  const defaultFrom = new Date(Date.now() - 3 * 365 * 864e5).toISOString().slice(0, 10);
  const [from, setFrom] = useState(defaultFrom);
  const [to, setTo] = useState(today);

  const { data: scenes = [], isLoading: scenesLoading } = useQuery({
    queryKey: ['stac-items', selectedAoi?.id, from, to],
    queryFn: async () => {
      if (!selectedAoi) return [];
      const aoiBox = geometryBBox(selectedAoi.geometry);
      const res = await stacApi.search({
        collections: ['sentinel-2-l2a'],
        bbox: aoiBox,
        datetime: `${from}T00:00:00Z/${to}T23:59:59Z`,
        limit: 100,
      }) as { features: STACItem[] };
      const feats = res.features ?? [];
      // Only scenes that actually cover the AOI (≥90%); a scene that merely
      // clips it renders mostly blank. Fall back to all if none qualify (e.g.
      // the AOI straddles a scene boundary) so comparison still works.
      const covering = feats.filter((f) => aoiCoverage(aoiBox, f.bbox) >= 0.9);
      return (covering.length ? covering : feats).sort(
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

      // Persist to history + build the AOI-cropped images on the worker. Only
      // when both sides are real Sentinel scenes ('google' isn't a STAC item).
      if (sessionId && leftSel !== GOOGLE && rightSel !== GOOGLE) {
        try {
          const comp = (await comparisonApi.create(sessionId, selectedAoi.id, {
            left_item_id: leftSel,
            right_item_id: rightSel,
          })) as TemporalComparison;
          if (comp.task_id) setTrackTaskId(comp.task_id);
          qc.invalidateQueries({ queryKey: ['comparisons', sessionId, selectedAoi.id] });
          addNotification({ type: 'info', message: 'Comparison saved — building in background' });
        } catch (e) {
          addNotification({
            type: 'error',
            message: `Could not save comparison: ${(e as Error).message}`,
          });
        }
      }
    } catch {
      addNotification({ type: 'error', message: 'Could not build comparison' });
    } finally {
      setBuilding(false);
    }
  };

  // Re-open the side-by-side viewer from a saved (completed) comparison.
  const openFromHistory = (r: ComparisonResult) => {
    if (!selectedAoi || !r.left?.tile_url || !r.right?.tile_url) return;
    onOpenViewer({
      title: selectedAoi.name,
      bbox: (r.bbox as ComparisonView['bbox']) ?? geometryBBox(selectedAoi.geometry),
      left: { tileUrl: r.left.tile_url, imageUrl: r.left.image_url, label: `Sentinel-2 · ${fmtDate(r.left.datetime)}`, nativeZoom: SENTINEL_NATIVE },
      right: { tileUrl: r.right.tile_url, imageUrl: r.right.image_url, label: `Sentinel-2 · ${fmtDate(r.right.datetime)}`, nativeZoom: SENTINEL_NATIVE },
    });
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

        <div className="space-y-1.5 pt-2 border-t border-slate-800">
          <label className="text-[11px] text-slate-400 flex items-center gap-1">
            <History size={11} /> Recent comparisons{history.length > 0 ? ` (${history.length})` : ''}
          </label>
          {historyLoading ? (
            <p className="text-[11px] text-slate-500 flex items-center gap-1">
              <Loader2 size={11} className="animate-spin" /> Loading…
            </p>
          ) : historyError ? (
            <p className="text-[11px] text-amber-400">Could not load comparison history.</p>
          ) : history.length === 0 ? (
            <p className="text-[11px] text-slate-500">
              No comparisons yet for this area — run one above to save it here.
            </p>
          ) : (
            <div className="space-y-1 max-h-44 overflow-auto">
              {history.map((c) => {
                const r = c.comparison_result as ComparisonResult | undefined;
                const label =
                  r?.left && r?.right
                    ? `${fmtDate(r.left.datetime)} → ${fmtDate(r.right.datetime)}`
                    : `${c.left_item_id.slice(0, 10)}… → ${c.right_item_id.slice(0, 10)}…`;
                const ready = c.status === 'completed' && !!r?.left?.tile_url && !!r?.right?.tile_url;
                return (
                  <div
                    key={c.id}
                    className="flex items-center justify-between gap-2 bg-slate-900/60 border border-slate-800 rounded-lg px-2 py-1.5"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      {(r?.left?.snapshot_url || r?.right?.snapshot_url) && (
                        <img
                          src={(r?.left?.snapshot_url || r?.right?.snapshot_url) as string}
                          alt=""
                          loading="lazy"
                          className="w-9 h-9 shrink-0 rounded object-cover border border-slate-700"
                        />
                      )}
                      <div className="min-w-0">
                        <p className="text-[11px] text-slate-300 truncate">{label}</p>
                        <p className="text-[10px] text-slate-500">{statusLabel(c.status)}</p>
                      </div>
                    </div>
                    {ready && (
                      <button
                        onClick={() => openFromHistory(r as ComparisonResult)}
                        className="shrink-0 text-[11px] text-blue-400 hover:text-blue-300"
                      >
                        View
                      </button>
                    )}
                    {(c.status === 'pending' || c.status === 'running') && (
                      <Loader2 size={12} className="shrink-0 animate-spin text-slate-500" />
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}
