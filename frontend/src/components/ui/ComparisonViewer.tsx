import { useEffect, useRef, useState } from 'react';
import { MapContainer, TileLayer, useMap } from 'react-leaflet';
import L, { type Map as LeafletMap } from 'leaflet';
import { X, Link2, Link2Off, Download, Maximize } from 'lucide-react';
import type { ComparisonView, ComparisonSide } from '../../types';

/* Reports the Leaflet instance up once it's ready, and fits it to the AOI. */
// Each source caps its own native zoom (Sentinel ~15, Google ~20) so neither is
// over-upscaled. Display can zoom up to MAX_ZOOM (Leaflet up-samples beyond native).
const DEFAULT_NATIVE_ZOOM = 15;
const MAX_ZOOM = 20;
const MAX_FIT_ZOOM = 17;

function MapHandle({
  bbox, onReady,
}: { bbox: [number, number, number, number]; onReady: (m: LeafletMap) => void }) {
  const map = useMap();
  useEffect(() => {
    const [minLng, minLat, maxLng, maxLat] = bbox;
    map.fitBounds([[minLat, minLng], [maxLat, maxLng]], { padding: [12, 12], maxZoom: MAX_FIT_ZOOM });
    onReady(map);
  }, [map, bbox, onReady]);
  return null;
}

/** Sharpest reconstruction for up-sampling 10 m Sentinel data: Lanczos. */
function withResampling(url: string): string {
  return url.includes('resampling=') ? url : `${url}&resampling=lanczos`;
}

function MapPane({
  side, bbox, onReady,
}: { side: ComparisonSide; bbox: [number, number, number, number]; onReady: (m: LeafletMap) => void }) {
  return (
    <div className="relative flex-1 min-w-0 bg-slate-950">
      <div className="absolute top-2 left-2 z-[500] px-2 py-1 rounded bg-black/65 text-white text-[11px] font-medium pointer-events-none">
        {side.label}
      </div>
      <MapContainer
        center={[0, 0]}
        zoom={2}
        maxZoom={MAX_ZOOM}
        zoomControl={false}
        attributionControl={false}
        className="w-full h-full"
      >
        <MapHandle bbox={bbox} onReady={onReady} />
        <TileLayer url={withResampling(side.tileUrl)} maxNativeZoom={side.nativeZoom ?? DEFAULT_NATIVE_ZOOM} maxZoom={MAX_ZOOM} tileSize={256} />
      </MapContainer>
    </div>
  );
}

async function exportImage(side: ComparisonSide) {
  if (!side.imageUrl) return;
  const filename = `horus_${side.label.replace(/[^\w.-]+/g, '_')}.png`;
  try {
    const res = await fetch(side.imageUrl);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  } catch {
    window.open(side.imageUrl, '_blank', 'noopener'); // CORS fallback
  }
}

/** Side-by-side comparison of two dated scenes on synced, zoomable maps. */
export function ComparisonViewer({ view, onClose }: { view: ComparisonView; onClose: () => void }) {
  const [linked, setLinked] = useState(true);
  const left = useRef<LeafletMap | null>(null);
  const right = useRef<LeafletMap | null>(null);
  const syncing = useRef(false);
  const linkedRef = useRef(linked);
  linkedRef.current = linked;

  // Mirror pan/zoom from one map to the other while "Sync" is on. A lock guards
  // against the echo (setView on B fires B's move → would loop back).
  useEffect(() => {
    const wire = (src: LeafletMap | null, dst: LeafletMap | null) => {
      if (!src || !dst) return () => {};
      const handler = () => {
        if (!linkedRef.current || syncing.current) return;
        syncing.current = true;
        dst.setView(src.getCenter(), src.getZoom(), { animate: false });
        syncing.current = false;
      };
      src.on('move zoom', handler);
      return () => src.off('move zoom', handler);
    };
    const offL = wire(left.current, right.current);
    const offR = wire(right.current, left.current);
    return () => { offL(); offR(); };
  }, [view]);

  const fitBoth = () => {
    const [minLng, minLat, maxLng, maxLat] = view.bbox;
    const b = L.latLngBounds([minLat, minLng], [maxLat, maxLng]);
    left.current?.fitBounds(b, { padding: [12, 12] });
    right.current?.fitBounds(b, { padding: [12, 12] });
  };

  return (
    <div className="fixed inset-0 z-[2000] bg-slate-900/95 backdrop-blur flex flex-col">
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-slate-700 shrink-0">
        <h2 className="text-sm font-semibold text-slate-100 flex-1 truncate">
          Compare · {view.title}
        </h2>
        <button onClick={() => setLinked((v) => !v)} title={linked ? 'Unlink pan/zoom' : 'Link pan/zoom'}
          className={`flex items-center gap-1 text-xs px-2 py-1 rounded-lg border transition-colors
            ${linked ? 'bg-blue-600/20 border-blue-500 text-blue-200' : 'border-slate-600 text-slate-300 hover:bg-slate-800'}`}>
          {linked ? <Link2 size={13} /> : <Link2Off size={13} />} Sync
        </button>
        <button onClick={fitBoth} title="Reset view"
          className="p-1.5 rounded-lg text-slate-300 hover:bg-slate-800"><Maximize size={16} /></button>
        <button onClick={onClose} title="Close" aria-label="Close"
          className="p-1.5 rounded-lg text-slate-300 hover:bg-slate-800 hover:text-white"><X size={18} /></button>
      </div>

      <div className="flex-1 flex gap-px bg-slate-700 min-h-0">
        <MapPane side={view.left} bbox={view.bbox} onReady={(m) => { left.current = m; }} />
        <MapPane side={view.right} bbox={view.bbox} onReady={(m) => { right.current = m; }} />
      </div>

      <div className="flex items-center justify-center gap-3 px-4 py-2.5 border-t border-slate-700 shrink-0">
        <span className="text-[11px] text-slate-500 mr-2">
          Sentinel-2 · 10 m/px · scroll to zoom, drag to pan{linked ? ' (synced)' : ''}
        </span>
        {view.left.imageUrl && (
          <button onClick={() => exportImage(view.left)}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-600 text-slate-200 hover:bg-slate-700">
            <Download size={13} /> {view.left.label}
          </button>
        )}
        {view.right.imageUrl && (
          <button onClick={() => exportImage(view.right)}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-600 text-slate-200 hover:bg-slate-700">
            <Download size={13} /> {view.right.label}
          </button>
        )}
      </div>
    </div>
  );
}
