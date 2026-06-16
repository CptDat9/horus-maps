import { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Sparkles, Loader2, Crosshair, Pentagon, Eye, EyeOff, Trash2, Play,
  Download, ChevronDown, ChevronRight, SlidersHorizontal, Info, History,
} from 'lucide-react';
import { Panel } from './Panel';
import { Button } from '../../common/Button';
import { useApp } from '../../../store/AppContext';
import { useDetections } from '../../../hooks/useDetections';
import { detectionColor } from '../../map/DetectionLayer';
import { taskApi, detectionApi } from '../../../services/api';
import { DOTA_CLASSES, CLASS_PRESETS } from '../../../types';
import type { AOI, Task } from '../../../types';

const DEFAULT_CLASSES = [9, 10]; // vehicles — safest default for urban/road scenes
                                 // (the "ship" class produces false positives over rivers/bridges)

const sameSet = (a: number[], b: number[]) =>
  a.length === b.length && a.every((x) => b.includes(x));

interface DetectPanelProps {
  selectedAoi: AOI | null;
  detectionsVisible: boolean;
  onToggleVisible: () => void;
  onNeedAOI: () => void;
  onFlyTo: (aoi: AOI) => void;
  onClose: () => void;
  /** The map's active base-layer name + XYZ tile template (detection imagery). */
  baseLayerName: string;
  baseTileUrl?: string;
}

type RunMeta = {
  zoom?: number; profile?: string; model?: string; source?: string; confidence?: number; iou?: number;
  tile?: number; overlap?: number; imgsz?: number; mosaic_size?: number[]; tiles_total?: number;
  tiles_failed?: number; elapsed_s?: number; count?: number; filtered_out?: number; note?: string | null;
};

export function DetectPanel({
  selectedAoi, detectionsVisible, onToggleVisible, onNeedAOI, onFlyTo, onClose,
  baseLayerName, baseTileUrl,
}: DetectPanelProps) {
  const { sessionId, addNotification } = useApp();
  const qc = useQueryClient();
  const {
    detections, runs, runDetection, isRunning, clearDetections, deleteRun,
  } = useDetections(selectedAoi?.id ?? null);

  const [classes, setClasses] = useState<number[]>(DEFAULT_CLASSES);
  const [confidence, setConfidence] = useState(0.08);
  const [iou, setIou] = useState(0.5);
  const [advanced, setAdvanced] = useState(false);
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);
  const [previewBust, setPreviewBust] = useState<number | null>(null);
  const [meta, setMeta] = useState<RunMeta | null>(null);
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);

  useEffect(() => { setPreviewBust(null); setMeta(null); setExpandedRunId(null); }, [selectedAoi?.id]);

  // Detections are persisted per-AOI in the DB. When an AOI that already has
  // saved results is opened, restore its annotated preview (bust by the newest
  // detection's timestamp so a re-run refreshes it).
  useEffect(() => {
    if (pendingTaskId || previewBust || detections.length === 0) return;
    const ts = new Date(detections[0].created_at).getTime();
    setPreviewBust(Number.isFinite(ts) ? ts : 1);
  }, [detections, pendingTaskId, previewBust]);

  const previewUrl =
    selectedAoi && sessionId && previewBust
      ? detectionApi.previewUrl(sessionId, selectedAoi.id, previewBust)
      : null;

  // Poll tasks while a job is in flight; also poll briefly on open so we can
  // re-attach to a detection still running from before (e.g. user navigated away).
  const { data: tasks = [] } = useQuery<Task[]>({
    queryKey: ['tasks', sessionId],
    queryFn: () => (sessionId ? (taskApi.list(sessionId) as Promise<Task[]>) : Promise.resolve([])),
    enabled: !!sessionId,
    refetchInterval: pendingTaskId ? 2000 : 5000,
  });

  // Re-attach to a detection job for THIS AOI that's still pending/running
  // (so reopening the panel keeps showing progress instead of "nothing").
  useEffect(() => {
    if (pendingTaskId || !selectedAoi) return;
    const running = tasks.find(
      (t) => t.task_type === 'detection'
        && (t.payload?.aoi_id as string) === selectedAoi.id
        && (t.status === 'pending' || t.status === 'running'),
    );
    if (running) setPendingTaskId(running.id);
  }, [tasks, pendingTaskId, selectedAoi]);

  useEffect(() => {
    if (!pendingTaskId) return;
    const t = tasks.find((x) => x.id === pendingTaskId);
    if (!t) return;
    if (t.status === 'completed') {
      qc.invalidateQueries({ queryKey: ['detections', selectedAoi?.id] });
      qc.invalidateQueries({ queryKey: ['detection-runs', selectedAoi?.id] });
      setMeta((t.result ?? null) as RunMeta | null);
      const n = (t.result?.count as number) ?? 0;
      addNotification({ type: 'success', message: `Detection done — ${n} object(s) found` });
      if (t.result?.has_preview) setPreviewBust(Date.now());
      if (selectedAoi && n > 0) onFlyTo(selectedAoi);
      setPendingTaskId(null);
    } else if (t.status === 'failed') {
      addNotification({ type: 'error', message: `Detection failed: ${t.error_message ?? 'unknown'}` });
      setPendingTaskId(null);
    }
  }, [tasks, pendingTaskId, selectedAoi, qc, addNotification, onFlyTo]);

  const counts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const d of detections) m[d.object_type] = (m[d.object_type] ?? 0) + 1;
    return Object.entries(m).sort((a, b) => b[1] - a[1]);
  }, [detections]);

  const busy = isRunning || !!pendingTaskId;
  const toggleClass = (id: number) =>
    setClasses((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id].sort((a, b) => a - b)));

  const handleRun = async () => {
    if (!selectedAoi || classes.length === 0) return;
    onFlyTo(selectedAoi);
    try {
      // Detect on the SAME imagery the map is showing (active base layer).
      const res = await runDetection({ classes, tile_url: baseTileUrl, confidence, iou });
      setPendingTaskId(res.task_id);
      addNotification({ type: 'info', message: 'Detection queued — running…' });
    } catch {
      addNotification({ type: 'error', message: 'Could not start detection' });
    }
  };

  const handleClear = async () => {
    try {
      await clearDetections();
      setPreviewBust(null); setMeta(null);
      addNotification({ type: 'success', message: 'Detections cleared' });
    } catch {
      addNotification({ type: 'error', message: 'Could not clear detections' });
    }
  };

  /* ---- No AOI selected ---- */
  if (!selectedAoi) {
    return (
      <Panel title="AI Detection" icon={<Sparkles size={16} />} onClose={onClose}>
        <div className="p-4 flex flex-col items-center gap-3 text-center py-10">
          <Pentagon size={26} className="text-slate-600" />
          <p className="text-xs text-slate-400 leading-relaxed">
            Select or draw an Area of Interest first, then detect objects in high-resolution
            satellite imagery over it.
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
      title="AI Detection"
      icon={<Sparkles size={16} />}
      onClose={onClose}
      footer={
        <Button
          variant="primary" size="md" className="w-full justify-center"
          icon={busy ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
          loading={busy}
          disabled={classes.length === 0}
          onClick={handleRun}
        >
          {busy ? 'Detecting…' : `Run detection (${classes.length})`}
        </Button>
      }
    >
      <div className="p-3 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] text-slate-500 flex-1">
            YOLO-OBB over <span className="text-slate-300">{selectedAoi.name}</span>.
          </p>
          <button onClick={() => onFlyTo(selectedAoi)}
            className="shrink-0 flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300" title="Fly to area">
            <Crosshair size={12} /> Go to area
          </button>
        </div>

        {/* Quick presets */}
        <div className="grid grid-cols-4 gap-1.5">
          {CLASS_PRESETS.map((p) => {
            const active = sameSet(classes, p.classes);
            return (
              <button key={p.key} onClick={() => setClasses([...p.classes])}
                className={`rounded-lg py-1.5 text-[10px] border transition-colors
                  ${active ? 'bg-blue-600/20 border-blue-500 text-blue-200'
                           : 'bg-slate-900/50 border-transparent text-slate-400 hover:bg-slate-700/50'}`}>
                {p.label}
              </button>
            );
          })}
        </div>

        {/* Imagery used = the active base layer (no separate picker) */}
        <div className="flex items-center gap-1.5 text-[11px] text-slate-400 bg-slate-900/40 rounded-lg px-2.5 py-1.5">
          <Sparkles size={12} className="text-blue-400 shrink-0" />
          <span className="flex-1">
            Detects on the current map layer: <span className="text-slate-200">{baseLayerName}</span>
          </span>
          <Hint text="AI chạy trên đúng ảnh nền bạn đang xem (base layer hiện tại). Đổi layer ở Layer Switcher nếu muốn nguồn khác." />
        </div>

        {/* Advanced class picker */}
        <div>
          <button onClick={() => setAdvanced((v) => !v)}
            className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-200">
            {advanced ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            Choose classes ({classes.length}/15)
          </button>
          {advanced && (
            <div className="mt-2 grid grid-cols-2 gap-1">
              {DOTA_CLASSES.map((c) => (
                <label key={c.id}
                  className="flex items-center gap-1.5 text-[10px] text-slate-300 cursor-pointer px-1.5 py-1 rounded hover:bg-slate-700/40">
                  <input type="checkbox" checked={classes.includes(c.id)} onChange={() => toggleClass(c.id)}
                    className="accent-blue-500" />
                  <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: detectionColor(c.label) }} />
                  <span className="truncate">{c.label}</span>
                </label>
              ))}
            </div>
          )}
        </div>

        {/* Confidence + IoU */}
        <div className="space-y-2">
          <div className="space-y-1">
            <label className="text-[11px] text-slate-400 flex justify-between">
              <span className="flex items-center gap-1">Confidence
                <Hint text="Ngưỡng tin cậy tối thiểu. Thấp (8–12%) bắt nhiều xe hơn nhưng nhiều box rác hơn; cao thì chắc chắn hơn nhưng dễ sót." />
              </span>
              <span className="text-slate-300">{(confidence * 100).toFixed(0)}%</span>
            </label>
            <input type="range" min={0.05} max={0.9} step={0.05} value={confidence}
              onChange={(e) => setConfidence(Number(e.target.value))} className="w-full accent-blue-500" />
          </div>
          <div className="space-y-1">
            <label className="text-[11px] text-slate-400 flex justify-between">
              <span className="flex items-center gap-1">IoU (overlap merge)
                <Hint text="Ngưỡng gộp khung chồng nhau (NMS). Bãi xe đông nên để cao (0.5–0.6) để các xe sát nhau không bị gộp mất." />
              </span>
              <span className="text-slate-300">{iou.toFixed(2)}</span>
            </label>
            <input type="range" min={0.1} max={0.9} step={0.05} value={iou}
              onChange={(e) => setIou(Number(e.target.value))} className="w-full accent-blue-500" />
          </div>
        </div>

        {/* Hint when the AOI was too large for vehicle-scale detail */}
        {meta?.note && (
          <p className="text-[11px] text-amber-300/90 bg-amber-900/20 border border-amber-700/40 rounded-lg px-2.5 py-2 leading-relaxed">
            {meta.note}
          </p>
        )}

        {/* Results: counts */}
        {detections.length > 0 && (
          <div className="pt-1 space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-[10px] text-slate-500 uppercase tracking-widest">{detections.length} detected</p>
              <div className="flex items-center gap-2">
                <button onClick={onToggleVisible} className="text-[11px] text-slate-300 hover:text-white"
                  title={detectionsVisible ? 'Hide on map' : 'Show on map'}>
                  {detectionsVisible ? <Eye size={13} /> : <EyeOff size={13} />}
                </button>
                <button onClick={handleClear} className="text-[11px] text-red-400 hover:text-red-300" title="Clear">
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
            <div className="space-y-1">
              {counts.map(([type, n]) => (
                <div key={type} className="flex items-center gap-2 bg-slate-900/50 rounded-lg px-2.5 py-1.5">
                  <span className="w-2.5 h-2.5 rounded-sm" style={{ background: detectionColor(type) }} />
                  <span className="text-[11px] text-slate-300 flex-1 capitalize">{type.replace('-', ' ')}</span>
                  <span className="text-[11px] text-slate-400">{n}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Parameters / diagnostics for the latest run */}
        {meta && (
          <div className="space-y-1">
            <p className="text-[10px] text-slate-500 uppercase tracking-widest flex items-center gap-1">
              <SlidersHorizontal size={11} /> Run parameters
            </p>
            <RunParams meta={meta} />
          </div>
        )}

        {/* Annotated image */}
        {previewUrl && (
          <div className="pt-1 space-y-1.5">
            <div className="flex items-center justify-between">
              <p className="text-[10px] text-slate-500 uppercase tracking-widest">Detected image</p>
              <a href={previewUrl} download className="flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300"
                title="Download annotated image">
                <Download size={12} /> Download
              </a>
            </div>
            <a href={previewUrl} target="_blank" rel="noreferrer" title="Open full size">
              <img src={previewUrl} alt="Detection result"
                className="w-full rounded-lg border border-slate-700 hover:border-slate-500 transition-colors" />
            </a>
          </div>
        )}

        {/* History of runs for this AOI */}
        {runs.length > 0 && sessionId && selectedAoi && (
          <div className="pt-1 space-y-1.5">
            <p className="text-[10px] text-slate-500 uppercase tracking-widest flex items-center gap-1">
              <History size={11} /> Run history ({runs.length})
            </p>
            {runs.map((r) => {
              const when = new Date(r.created_at).toLocaleString('en-GB', {
                day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
              });
              const isLatest = r.id === runs[0].id;
              const expanded = expandedRunId === r.id;
              return (
                <div key={r.id} className={`rounded-lg text-[11px]
                  ${isLatest ? 'bg-blue-600/15 border border-blue-500/40' : 'bg-slate-900/50'}`}>
                  <div className="flex items-center gap-2 px-2.5 py-1.5">
                    <button
                      onClick={() => setExpandedRunId(expanded ? null : r.id)}
                      className="flex items-center gap-1 flex-1 min-w-0 text-left text-slate-300 hover:text-white"
                      title="Show run parameters"
                    >
                      {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                      <span className="truncate">{when}</span>
                    </button>
                    <span className="text-slate-400">{r.count} obj</span>
                    <a href={detectionApi.runPreviewUrl(sessionId, selectedAoi.id, r.id)}
                      target="_blank" rel="noreferrer" title="View annotated image"
                      className="text-blue-400 hover:text-blue-300"><Eye size={13} /></a>
                    <button onClick={() => deleteRun(r.id)} title="Delete run"
                      className="text-red-400 hover:text-red-300"><Trash2 size={12} /></button>
                  </div>
                  {expanded && (
                    <div className="px-2.5 pb-2">
                      <RunParams meta={(r.meta ?? {}) as RunMeta} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {!previewUrl && detections.length === 0 && runs.length === 0 && !busy && (
          <p className="text-[11px] text-slate-500 py-1">No detections yet. Pick classes and run.</p>
        )}
      </div>
    </Panel>
  );
}

/** Tiny info icon with a hover popover ("chú thích bé bé"). */
function Hint({ text }: { text: string }) {
  return (
    <span className="relative inline-flex group align-middle">
      <Info size={11} className="text-slate-500 hover:text-blue-400 cursor-help" />
      <span className="pointer-events-none absolute left-1/2 -translate-x-1/2 bottom-full mb-1 w-44
                       bg-slate-900 text-slate-200 text-[10px] leading-snug rounded-lg p-2 shadow-xl
                       border border-slate-700 opacity-0 group-hover:opacity-100 transition-opacity z-50">
        {text}
      </span>
    </span>
  );
}

function RunParams({ meta }: { meta: RunMeta }) {
  return (
    <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px] text-slate-400 bg-slate-900/50 rounded-lg px-2.5 py-2">
      <Param k="Objects" v={meta.count} hint="Tổng số đối tượng phát hiện được." />
      <Param k="Zoom" v={meta.zoom} hint="Mức zoom ảnh vệ tinh được tải. Càng cao càng chi tiết (xe cần ~z20)." />
      <Param k="Imagery" v={meta.source} hint="Nguồn ảnh thực tế đưa vào model." />
      <Param k="Profile" v={meta.profile} hint="Cấu hình tự suy ra từ lớp đã chọn (zoom/tile/imgsz)." />
      <Param k="Model" v={meta.model} hint="Trọng số YOLO-OBB đang dùng." />
      <Param k="Confidence" v={meta.confidence != null ? `${Math.round(meta.confidence * 100)}%` : undefined} hint="Ngưỡng tin cậy đã dùng." />
      <Param k="IoU" v={meta.iou} hint="Ngưỡng gộp khung (NMS) đã dùng." />
      <Param k="Tile / overlap" v={meta.tile ? `${meta.tile}/${meta.overlap}` : undefined} hint="Kích thước ô cắt từ ảnh gốc / phần chồng lấn giữa các ô." />
      <Param k="Imgsz" v={meta.imgsz} hint="Kích thước ảnh đưa vào model. Lớn hơn tile → ô được phóng to giúp bắt vật nhỏ tốt hơn." />
      <Param k="Mosaic" v={meta.mosaic_size ? `${meta.mosaic_size[0]}×${meta.mosaic_size[1]}` : undefined} hint="Kích thước ảnh ghép (px) phủ toàn AOI." />
      <Param k="Tiles" v={meta.tiles_total != null ? `${meta.tiles_total - (meta.tiles_failed ?? 0)}/${meta.tiles_total}` : undefined} hint="Số ô tải thành công / tổng số ô." />
      <Param k="Filtered out" v={meta.filtered_out} hint="Số box bị loại vì sai kích thước thực tế hoặc dưới ngưỡng tin cậy theo lớp (chống báo nhầm)." />
      <Param k="Time" v={meta.elapsed_s != null ? `${meta.elapsed_s}s` : undefined} hint="Thời gian tải ảnh + suy luận." />
    </div>
  );
}

function Param({ k, v, hint }: { k: string; v: string | number | undefined | null; hint?: string }) {
  if (v === undefined || v === null) return null;
  return (
    <>
      <span className="text-slate-500 flex items-center gap-1">{k}{hint && <Hint text={hint} />}</span>
      <span className="text-right text-slate-300 truncate">{v}</span>
    </>
  );
}
