import { useState } from 'react';
import { Pentagon, Plus, Pencil, Trash2, MapPin, Crosshair, ImageDown, Loader2 } from 'lucide-react';
import { Panel } from './Panel';
import { Button } from '../../common/Button';
import { Modal } from '../../common/Modal';
import { useApp } from '../../../store/AppContext';
import { aoiApi } from '../../../services/api';
import type { AOI, Measurement } from '../../../types';
import {
  formatArea, formatDistance, calculatePolygonArea, calculatePolygonPerimeter,
  geometryToLatLngs, geometryBBox,
} from '../../../utils/geoUtils';

interface AOIPanelProps {
  aois: AOI[];
  measurements: Measurement[];
  onDelete: (id: string) => void;
  onUpdate: (id: string, data: { name?: string; description?: string }) => Promise<void>;
  onFlyTo: (aoi: AOI) => void;
  baseTileUrl?: string;
  onClose: () => void;
}

export function AOIPanel({
  aois, measurements, onDelete, onUpdate, onFlyTo, baseTileUrl, onClose,
}: AOIPanelProps) {
  const {
    drawMode, setDrawMode, drawingVertices, selectedAoiId, setSelectedAoiId,
  } = useApp();
  const isDrawing = drawMode === 'polygon';
  const selected = aois.find((a) => a.id === selectedAoiId) ?? null;

  return (
    <Panel
      title="Areas of Interest"
      icon={<Pentagon size={16} />}
      onClose={onClose}
      footer={
        <Button
          variant={isDrawing ? 'active' : 'primary'}
          size="md"
          className="w-full justify-center"
          icon={isDrawing ? <Pencil size={14} /> : <Plus size={14} />}
          onClick={() => setDrawMode(isDrawing ? 'none' : 'polygon')}
        >
          {isDrawing ? 'Drawing — double-click to finish' : 'Draw new area'}
        </Button>
      }
    >
      <div className="p-3 space-y-3">
        {isDrawing && (
          <div className="bg-blue-950/50 border border-blue-700/40 rounded-lg p-2.5 text-[11px] text-blue-300 space-y-1">
            <p>Click on the map to add vertices · double-click to finish.</p>
            {drawingVertices.length >= 3 && (
              <p className="text-emerald-400 font-mono text-[10px]">
                {drawingVertices.length} pts · {formatArea(calculatePolygonArea(drawingVertices))} ·{' '}
                {formatDistance(calculatePolygonPerimeter(drawingVertices))}
              </p>
            )}
          </div>
        )}

        {selected ? (
          <AOIDetails
            aoi={selected}
            measurements={measurements}
            baseTileUrl={baseTileUrl}
            onBack={() => setSelectedAoiId(null)}
            onFlyTo={() => onFlyTo(selected)}
            onUpdate={onUpdate}
          />
        ) : aois.length === 0 && !isDrawing ? (
          <p className="text-xs text-slate-500 text-center py-8 leading-relaxed">
            No areas yet.<br />Draw one to measure it and load imagery.
          </p>
        ) : (
          <div className="space-y-1">
            {aois.map((aoi) => (
              <AOIRow
                key={aoi.id}
                aoi={aoi}
                onSelect={() => setSelectedAoiId(aoi.id)}
                onDelete={() => onDelete(aoi.id)}
                onFlyTo={() => onFlyTo(aoi)}
              />
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}

function AOIRow({
  aoi, onSelect, onDelete, onFlyTo,
}: { aoi: AOI; onSelect: () => void; onDelete: () => void; onFlyTo: () => void }) {
  const area = calculatePolygonArea(geometryToLatLngs(aoi.geometry));
  return (
    <div
      onClick={onSelect}
      className="group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer hover:bg-slate-700/60 text-slate-300 transition-colors"
    >
      <MapPin size={12} className="shrink-0 opacity-70" />
      <div className="flex-1 min-w-0">
        <p className="text-xs truncate font-medium">{aoi.name}</p>
        <p className="text-[10px] text-slate-500">{formatArea(area)}</p>
      </div>
      <button
        onClick={(e) => { e.stopPropagation(); onFlyTo(); }}
        className="opacity-0 group-hover:opacity-100 text-blue-400 hover:text-blue-300 transition-all p-0.5"
        title="Fly to area"
      >
        <Crosshair size={13} />
      </button>
      <button
        onClick={(e) => { e.stopPropagation(); onDelete(); }}
        className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-300 transition-all p-0.5"
        title="Delete"
      >
        <Trash2 size={12} />
      </button>
    </div>
  );
}

function AOIDetails({
  aoi, measurements, baseTileUrl, onBack, onFlyTo, onUpdate,
}: {
  aoi: AOI; measurements: Measurement[]; baseTileUrl?: string;
  onBack: () => void; onFlyTo: () => void;
  onUpdate: (id: string, data: { name?: string; description?: string }) => Promise<void>;
}) {
  const { sessionId, addNotification } = useApp();
  const [exporting, setExporting] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(aoi.name);
  const [editDescription, setEditDescription] = useState(aoi.description ?? '');
  const [saving, setSaving] = useState(false);
  const latLngs = geometryToLatLngs(aoi.geometry);
  const area = calculatePolygonArea(latLngs);
  const perimeter = calculatePolygonPerimeter(latLngs);
  const bbox = geometryBBox(aoi.geometry);

  // Prefer backend-computed measurements when available.
  const backendArea = measurements.find((m) => m.type === 'area');
  const backendPerim = measurements.find((m) => m.type === 'perimeter');

  const openEdit = () => {
    setEditName(aoi.name);
    setEditDescription(aoi.description ?? '');
    setEditing(true);
  };

  const saveEdit = async () => {
    if (!editName.trim()) return;
    setSaving(true);
    try {
      await onUpdate(aoi.id, {
        name: editName.trim(),
        description: editDescription.trim(),
      });
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const exportImage = async () => {
    if (!sessionId) return;
    setExporting(true);
    try {
      const res = await fetch(aoiApi.imageUrl(sessionId, aoi.id, baseTileUrl));
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `aoi_${aoi.name.replace(/[^\w.-]+/g, '_')}.png`; a.click();
      URL.revokeObjectURL(url);
    } catch {
      addNotification({ type: 'error', message: 'Could not export AOI image' });
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={onBack} className="text-[11px] text-blue-400 hover:text-blue-300">← All areas</button>
        <button
          onClick={onFlyTo}
          className="flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300"
          title="Fly to area"
        >
          <Crosshair size={12} /> Zoom to area
        </button>
      </div>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-100 truncate">{aoi.name}</h3>
          {aoi.description && <p className="text-xs text-slate-400 mt-0.5">{aoi.description}</p>}
        </div>
        <button
          onClick={openEdit}
          className="shrink-0 flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300"
          title="Edit name & description"
        >
          <Pencil size={12} /> Edit
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Stat label="Area" value={backendArea ? formatArea(backendArea.value) : formatArea(area)} />
        <Stat label="Perimeter" value={backendPerim ? formatDistance(backendPerim.value) : formatDistance(perimeter)} />
      </div>

      <div>
        <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1.5">Bounding box</p>
        <div className="bg-slate-900/50 rounded-lg p-2.5 font-mono text-[11px] text-slate-300 grid grid-cols-2 gap-y-1 gap-x-3">
          {([['W', bbox[0]], ['E', bbox[2]], ['S', bbox[1]], ['N', bbox[3]]] as [string, number][]).map(([k, v]) => (
            <div key={k} className="flex justify-between">
              <span className="text-slate-500">{k}</span><span>{v.toFixed(4)}</span>
            </div>
          ))}
        </div>
      </div>

      <Button
        variant="secondary" size="md" className="w-full justify-center"
        icon={exporting ? <Loader2 size={14} className="animate-spin" /> : <ImageDown size={14} />}
        disabled={exporting}
        onClick={exportImage}
      >
        {exporting ? 'Exporting…' : 'Export AOI image'}
      </Button>

      <Modal
        open={editing}
        onClose={() => setEditing(false)}
        title="Edit Area of Interest"
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>Cancel</Button>
            <Button variant="primary" size="sm" loading={saving} disabled={!editName.trim()} onClick={saveEdit}>
              Save changes
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs text-slate-400">Name</label>
            <input
              autoFocus type="text" value={editName}
              onChange={(e) => setEditName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && saveEdit()}
              className="w-full bg-slate-700 border border-slate-600 focus:border-blue-500 rounded-lg px-3 py-2 text-sm text-slate-100 outline-none transition-colors"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-slate-400">Description <span className="text-slate-600">(optional)</span></label>
            <textarea
              value={editDescription} rows={2}
              onChange={(e) => setEditDescription(e.target.value)}
              className="w-full bg-slate-700 border border-slate-600 focus:border-blue-500 rounded-lg px-3 py-2 text-sm text-slate-100 outline-none transition-colors resize-none"
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-700/50 rounded-lg px-3 py-2">
      <p className="text-[10px] text-slate-400 mb-0.5">{label}</p>
      <p className="text-sm font-semibold text-slate-100">{value}</p>
    </div>
  );
}
