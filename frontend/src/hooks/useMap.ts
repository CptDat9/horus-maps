import { useState, useCallback } from 'react';
import type { Map as LeafletMap } from 'leaflet';

const DEFAULT_CENTER: [number, number] = [16.047079, 108.20623]; // Vietnam centroid
const DEFAULT_ZOOM = 6;

export function useMap() {
  const [mapRef, setMapRef] = useState<LeafletMap | null>(null);

  const flyTo = useCallback(
    (lat: number, lng: number, zoom = 13) => {
      mapRef?.flyTo([lat, lng], zoom, { duration: 1.2 });
    },
    [mapRef]
  );

  const resetView = useCallback(() => {
    mapRef?.flyTo(DEFAULT_CENTER, DEFAULT_ZOOM, { duration: 1.2 });
  }, [mapRef]);

  /** bbox: [minLng, minLat, maxLng, maxLat] */
  const fitBounds = useCallback(
    (bbox: [number, number, number, number]) => {
      mapRef?.fitBounds(
        [
          [bbox[1], bbox[0]],
          [bbox[3], bbox[2]],
        ],
        { padding: [48, 48] }
      );
    },
    [mapRef]
  );

  return { mapRef, setMapRef, flyTo, resetView, fitBounds };
}
