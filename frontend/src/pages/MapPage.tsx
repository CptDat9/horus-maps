import { useCallback, useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AppLayout } from '../components/layout/AppLayout';
import { HorusMap } from '../components/map/HorusMap';
import { MapControls } from '../components/map/MapControls';
import { ComparisonViewer } from '../components/ui/ComparisonViewer';
import { SearchBar } from '../components/ui/SearchBar';
import { Toolbar } from '../components/ui/Toolbar';
import { LayerSwitcher } from '../components/ui/LayerSwitcher';
import { ActivityButton } from '../components/ui/ActivityButton';
import { AOIPanel } from '../components/ui/panels/AOIPanel';
import { MeasurePanel } from '../components/ui/panels/MeasurePanel';
import { ComparePanel } from '../components/ui/panels/ComparePanel';
import { DetectPanel } from '../components/ui/panels/DetectPanel';
import { NotificationToasts } from '../components/ui/NotificationToast';
import { FullscreenLoading } from '../components/common/Loading';
import { Modal } from '../components/common/Modal';
import { Button } from '../components/common/Button';
import { useLayers } from '../hooks/useLayers';
import { useAOIs, useMeasurements } from '../hooks/useAOI';
import { useDetections } from '../hooks/useDetections';
import { useMap } from '../hooks/useMap';
import { useApp } from '../store/AppContext';
import { latLngsToGeometry, geometryBBox } from '../utils/geoUtils';
import { taskApi, measurementApi } from '../services/api';
import type { AOI, Task } from '../types';

export function MapPage() {
  const {
    sessionId, isSessionLoading,
    activeTool, setActiveTool,
    selectedAoiId, setSelectedAoiId,
    comparisonView, setComparisonView,
    drawMode, setDrawMode,
    measureMode, clearMeasure,
    addNotification,
  } = useApp();

  const layers = useLayers();
  const activeBase = layers.baseLayers.find((l) => l.id === layers.activeBaseId) ?? null;
  const { aois, createAOI, updateAOI, deleteAOI, isCreating } = useAOIs();
  const { measurements } = useMeasurements(selectedAoiId);
  const { detections } = useDetections(selectedAoiId);
  const { mapRef, setMapRef, flyTo, resetView, fitBounds } = useMap();
  const qc = useQueryClient();

  const [searchMarker, setSearchMarker] = useState<[number, number] | null>(null);
  const [detectionsVisible, setDetectionsVisible] = useState(true);
  const [pendingLatLngs, setPendingLatLngs] = useState<[number, number][] | null>(null);
  const [aoiName, setAoiName] = useState('');
  const [aoiDescription, setAoiDescription] = useState('');

  const { data: tasks = [] } = useQuery<Task[]>({
    queryKey: ['tasks', sessionId],
    queryFn: () => (sessionId ? (taskApi.list(sessionId) as Promise<Task[]>) : Promise.resolve([])),
    enabled: !!sessionId,
    refetchInterval: 5000,
  });

  const selectedAoi = aois.find((a) => a.id === selectedAoiId) ?? null;

  /* ── Handlers ─────────────────────────────────────────── */

  const handleAOIComplete = useCallback((latLngs: [number, number][]) => {
    setPendingLatLngs(latLngs);
    setAoiName(`AOI ${aois.length + 1}`);
  }, [aois.length]);

  const handleUpdateAOI = useCallback(async (id: string, data: { name?: string; description?: string }) => {
    try {
      await updateAOI({ aoiId: id, data });
      addNotification({ type: 'success', message: 'Area updated' });
    } catch {
      addNotification({ type: 'error', message: 'Failed to update area' });
    }
  }, [updateAOI, addNotification]);

  const handleSaveAOI = async () => {
    if (!pendingLatLngs || !aoiName.trim() || !sessionId) return;
    try {
      const geometry = latLngsToGeometry(pendingLatLngs);
      const newAoi = await createAOI({
        name: aoiName.trim(),
        description: aoiDescription.trim() || undefined,
        geometry,
      });

      await Promise.allSettled([
        measurementApi.create(sessionId, newAoi.id, { type: 'area', unit: 'sqkm' }),
        measurementApi.create(sessionId, newAoi.id, { type: 'perimeter', unit: 'km' }),
      ]);
      qc.invalidateQueries({ queryKey: ['measurements', newAoi.id] });

      setSelectedAoiId(newAoi.id);
      setActiveTool('aoi');
      addNotification({ type: 'success', message: `Area "${aoiName.trim()}" created` });

      const lats = pendingLatLngs.map((p) => p[0]);
      const lngs = pendingLatLngs.map((p) => p[1]);
      fitBounds([Math.min(...lngs), Math.min(...lats), Math.max(...lngs), Math.max(...lats)]);
    } catch (err) {
      addNotification({ type: 'error', message: 'Failed to create area' });
      console.error(err);
    } finally {
      setPendingLatLngs(null);
      setAoiName('');
      setAoiDescription('');
    }
  };

  const handleDeleteAOI = async (id: string) => {
    try {
      await deleteAOI(id);
      if (selectedAoiId === id) setSelectedAoiId(null);
      addNotification({ type: 'success', message: 'Area deleted' });
    } catch {
      addNotification({ type: 'error', message: 'Failed to delete area' });
    }
  };

  const handleSearch = (lat: number, lng: number, _label: string) => {
    setSearchMarker([lat, lng]);
    flyTo(lat, lng, 13);
  };

  const handleReset = () => {
    setSearchMarker(null);
    resetView();
  };

  const flyToAOI = useCallback((aoi: AOI) => {
    fitBounds(geometryBBox(aoi.geometry));
    setSelectedAoiId(aoi.id);
  }, [fitBounds, setSelectedAoiId]);

  // Escape backs out of the most "active" interaction, in priority order:
  // close the comparison viewer → cancel a draw → clear a measurement → close panel.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (comparisonView) setComparisonView(null);
      else if (drawMode === 'polygon') { setDrawMode('none'); setPendingLatLngs(null); }
      else if (measureMode !== 'none') clearMeasure();
      else if (activeTool !== 'none') setActiveTool('none');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [comparisonView, setComparisonView, drawMode, measureMode, activeTool, setDrawMode, clearMeasure, setActiveTool]);

  /* ── Render ───────────────────────────────────────────── */

  if (isSessionLoading) return <FullscreenLoading message="Initializing session…" />;

  return (
    <AppLayout>
      {/* Map fills the viewport */}
      <div className="absolute inset-0">
        <HorusMap
          visibleLayers={layers.visibleLayers}
          aois={aois}
          onMapReady={setMapRef}
          onAOICreated={handleAOIComplete}
          searchMarker={searchMarker}
          detections={detections}
          detectionsVisible={detectionsVisible}
        />
        <MapControls mapRef={mapRef} onResetView={handleReset} />

        {sessionId && (
          <div className="absolute bottom-2 left-1/2 -translate-x-1/2 z-[450] text-[10px] text-slate-400 font-mono pointer-events-none">
            session {sessionId.slice(0, 8)}
          </div>
        )}
      </div>

      {/* Search — top-left */}
      <div className="absolute top-4 left-4 z-[1100]">
        <SearchBar onSelect={handleSearch} />
      </div>

      {/* Tool dock + active panel — left */}
      <div className="absolute left-4 top-[4.75rem] z-[1100] flex items-start gap-2">
        <Toolbar />
        {activeTool === 'aoi' && (
          <AOIPanel
            aois={aois}
            measurements={measurements}
            onDelete={handleDeleteAOI}
            onUpdate={handleUpdateAOI}
            onFlyTo={flyToAOI}
            baseTileUrl={activeBase?.type === 'tile' ? activeBase.url : undefined}
            onClose={() => setActiveTool('none')}
          />
        )}
        {activeTool === 'measure' && <MeasurePanel onClose={() => setActiveTool('none')} />}
        {activeTool === 'compare' && (
          <ComparePanel
            selectedAoi={selectedAoi}
            baseTileUrl={activeBase?.type === 'tile' ? activeBase.url : undefined}
            onOpenViewer={setComparisonView}
            onNeedAOI={() => setActiveTool('aoi')}
            onFlyTo={flyToAOI}
            onClose={() => setActiveTool('none')}
          />
        )}
        {activeTool === 'detect' && (
          <DetectPanel
            selectedAoi={selectedAoi}
            detectionsVisible={detectionsVisible}
            onToggleVisible={() => setDetectionsVisible((v) => !v)}
            onNeedAOI={() => setActiveTool('aoi')}
            onFlyTo={flyToAOI}
            baseLayerName={activeBase?.name ?? 'Map'}
            baseTileUrl={activeBase?.type === 'tile' ? activeBase.url : undefined}
            onClose={() => setActiveTool('none')}
          />
        )}
      </div>

      {/* Layer switcher — bottom-left */}
      <div className="absolute bottom-5 left-4 z-[1100]">
        <LayerSwitcher
          baseLayers={layers.baseLayers}
          activeBaseId={layers.activeBaseId}
          setActiveBase={layers.setActiveBase}
          overlayLayers={layers.overlayLayers}
          visibleOverlayIds={layers.visibleOverlayIds}
          toggleOverlay={layers.toggleOverlay}
        />
      </div>

      {/* Activity / tasks — top-right */}
      <div className="absolute top-4 right-4 z-[1100]">
        <ActivityButton tasks={tasks} />
      </div>

      <NotificationToasts />

      {/* Side-by-side comparison viewer (zoom + export) */}
      {comparisonView && (
        <ComparisonViewer view={comparisonView} onClose={() => setComparisonView(null)} />
      )}

      {/* AOI naming modal */}
      <Modal
        open={!!pendingLatLngs}
        onClose={() => { setPendingLatLngs(null); setAoiName(''); setAoiDescription(''); }}
        title="Save Area of Interest"
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => { setPendingLatLngs(null); setAoiName(''); setAoiDescription(''); }}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" loading={isCreating} disabled={!aoiName.trim()} onClick={handleSaveAOI}>
              Save area
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs text-slate-400">Name</label>
            <input
              autoFocus
              type="text"
              value={aoiName}
              onChange={(e) => setAoiName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSaveAOI()}
              className="w-full bg-slate-700 border border-slate-600 focus:border-blue-500 rounded-lg px-3 py-2 text-sm text-slate-100 outline-none transition-colors"
              placeholder="e.g. Hanoi City Center"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-slate-400">Description <span className="text-slate-600">(optional)</span></label>
            <textarea
              value={aoiDescription}
              onChange={(e) => setAoiDescription(e.target.value)}
              rows={2}
              className="w-full bg-slate-700 border border-slate-600 focus:border-blue-500 rounded-lg px-3 py-2 text-sm text-slate-100 outline-none transition-colors resize-none"
              placeholder="What is this area? e.g. airport apron, parking lot…"
            />
          </div>
          {pendingLatLngs && (
            <p className="text-xs text-slate-500">
              {pendingLatLngs.length} vertices · area and perimeter are calculated automatically.
            </p>
          )}
        </div>
      </Modal>
    </AppLayout>
  );
}
