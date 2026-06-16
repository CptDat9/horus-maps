import { useEffect } from 'react';
import { MapContainer, TileLayer, Marker, useMap } from 'react-leaflet';
import L from 'leaflet';
import type { Map as LeafletMap } from 'leaflet';
import type { MapLayer, AOI, Detection } from '../../types';
import { DrawLayer } from './DrawLayer';
import { AOILayer } from './AOILayer';
import { MeasureLayer } from './MeasureLayer';
import { DetectionLayer } from './DetectionLayer';
import { useApp } from '../../store/AppContext';

// Fix Leaflet default marker icons in Vite
import markerIconUrl from 'leaflet/dist/images/marker-icon.png';
import markerIcon2xUrl from 'leaflet/dist/images/marker-icon-2x.png';
import markerShadowUrl from 'leaflet/dist/images/marker-shadow.png';

delete (L.Icon.Default.prototype as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconUrl: markerIconUrl,
  iconRetinaUrl: markerIcon2xUrl,
  shadowUrl: markerShadowUrl,
});

interface HorusMapProps {
  visibleLayers: MapLayer[];
  aois: AOI[];
  onMapReady: (map: LeafletMap) => void;
  onAOICreated: (latLngs: [number, number][]) => void;
  searchMarker: [number, number] | null;
  detections: Detection[];
  detectionsVisible: boolean;
}

/** Fires onMapReady once the map instance is available */
function MapReadyHandler({ onReady }: { onReady: (m: LeafletMap) => void }) {
  const map = useMap();
  useEffect(() => { onReady(map); }, [map, onReady]);
  return null;
}

export function HorusMap({
  visibleLayers, aois, onMapReady, onAOICreated, searchMarker,
  detections, detectionsVisible,
}: HorusMapProps) {
  const { selectedAoiId, setSelectedAoiId, setActiveTool } = useApp();

  return (
    <MapContainer
      center={[16.047079, 108.20623]}
      zoom={6}
      className="w-full h-full"
      zoomControl={false}
      attributionControl={true}
    >
      <MapReadyHandler onReady={onMapReady} />

      {visibleLayers.map((layer, idx) => {
        const isStac = layer.type === 'stac';
        // For STAC (Sentinel-2) let TiTiler render up to the layer's maxzoom
        // (bilinear → smooth); beyond that Leaflet up-samples the z18 tile.
        const maxNativeZoom = isStac
          ? Number((layer.options?.maxzoom as number) ?? 15)
          : undefined;
        return (
          <TileLayer
            key={layer.id}
            url={isStac ? `/api/tiles/${layer.id}/{z}/{x}/{y}` : layer.url}
            attribution={layer.name}
            maxZoom={20}
            maxNativeZoom={maxNativeZoom}
            tileSize={256}
            opacity={idx === 0 ? 1 : 0.95}
            zIndex={idx}
          />
        );
      })}

      <DrawLayer onComplete={onAOICreated} />
      <MeasureLayer />

      <AOILayer
        aois={aois}
        selectedId={selectedAoiId}
        onSelect={(id) => { setSelectedAoiId(id); setActiveTool('aoi'); }}
      />

      <DetectionLayer detections={detections} visible={detectionsVisible} />

      {searchMarker && <Marker position={searchMarker} />}
    </MapContainer>
  );
}
