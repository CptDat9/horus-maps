import { useEffect, useState } from 'react';
import type { Map as LeafletMap } from 'leaflet';

type Props = {
  mapRef: LeafletMap | null;
  activeLayerId?: string;
  activeLayerName?: string;
};

type MapInfo = {
  zoom: number;
  lat: number;
  lng: number;
  metersPerPixel: number;
  viewWidthKm: number;
  viewHeightKm: number;
  altitudeKm: number;
};

const EARTH_CIRCUMFERENCE_M = 40075016.686;
const TILE_SIZE = 256;
const CAMERA_FOV_DEG = 45;

function getMetersPerPixel(lat: number, zoom: number) {
  return (
    (EARTH_CIRCUMFERENCE_M * Math.cos((lat * Math.PI) / 180)) /
    (TILE_SIZE * Math.pow(2, zoom))
  );
}

function getApproxAltitude(viewHeightMeters: number) {
  const fovRad = (CAMERA_FOV_DEG * Math.PI) / 180;
  return viewHeightMeters / (2 * Math.tan(fovRad / 2));
}

export function MapZoomInfo({ mapRef, activeLayerId, activeLayerName }: Props) {
  const [info, setInfo] = useState<MapInfo | null>(null);

  useEffect(() => {
    if (!mapRef) return;

    const updateInfo = () => {
      const zoom = mapRef.getZoom();
      const center = mapRef.getCenter();
      const size = mapRef.getSize();

      const metersPerPixel = getMetersPerPixel(center.lat, zoom);
      const viewWidthMeters = size.x * metersPerPixel;
      const viewHeightMeters = size.y * metersPerPixel;
      const altitudeMeters = getApproxAltitude(viewHeightMeters);

      setInfo({
        zoom,
        lat: center.lat,
        lng: center.lng,
        metersPerPixel,
        viewWidthKm: viewWidthMeters / 1000,
        viewHeightKm: viewHeightMeters / 1000,
        altitudeKm: altitudeMeters / 1000,
      });
    };

    updateInfo();

    mapRef.on('zoom move resize zoomend moveend', updateInfo);

    return () => {
      mapRef.off('zoom move resize zoomend moveend', updateInfo);
    };
  }, [mapRef]);

  if (!info) return null;

  const isSentinel = activeLayerId?.toLowerCase().includes('sentinel');

  return (
    <div className="absolute bottom-6 left-1/2 z-[900] -translate-x-1/2 pointer-events-none">
      <div className="flex max-w-[calc(100vw-320px)] items-center gap-2 overflow-hidden rounded-full border border-slate-600 bg-slate-950/80 px-3 py-1.5 text-[11px] text-slate-200 shadow-lg backdrop-blur">
        <span className="font-semibold text-cyan-300 whitespace-nowrap">
          Map
        </span>

        <span className="font-mono whitespace-nowrap">
          z<span className="text-yellow-300">{info.zoom.toFixed(2)}</span>
        </span>

        <span className="h-3 w-px bg-slate-600" />

        <span className="font-mono whitespace-nowrap">
          {info.metersPerPixel.toFixed(2)} m/px
        </span>

        <span className="h-3 w-px bg-slate-600" />

        <span className="font-mono whitespace-nowrap">
          view {info.viewWidthKm.toFixed(1)}×{info.viewHeightKm.toFixed(1)} km
        </span>

        <span className="h-3 w-px bg-slate-600" />

        <span className="font-mono whitespace-nowrap">
          height≈{info.altitudeKm.toFixed(1)} km
        </span>

        <span className="h-3 w-px bg-slate-600" />

        <span className="font-mono text-slate-400 whitespace-nowrap">
          {info.lat.toFixed(4)}, {info.lng.toFixed(4)}
        </span>

        {activeLayerName && (
          <>
            <span className="h-3 w-px bg-slate-600" />
            <span className="max-w-[160px] truncate text-slate-400">
              {activeLayerName}
            </span>
          </>
        )}

        {isSentinel && (
          <>
            <span className="h-3 w-px bg-slate-600" />
            <span className="text-orange-300 whitespace-nowrap">
              S2≈10m/px
            </span>
          </>
        )}
      </div>
    </div>
  );
}