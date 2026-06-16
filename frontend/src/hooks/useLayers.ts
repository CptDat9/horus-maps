import { useQuery } from '@tanstack/react-query';
import { useState, useEffect, useMemo } from 'react';
import { layersApi } from '../services/api';
import type { MapLayer } from '../types';

/**
 * Google-Maps style layer model:
 *  - exactly ONE base layer is shown at a time (radio)
 *  - any number of analysis overlays can be toggled on top (checkbox)
 *
 * Base layers include open tile sources the backend may not seed (Google),
 * defined here so the switcher always offers them per the project brief.
 */
const CLIENT_BASE_LAYERS: MapLayer[] = [
  {
    id: 'google-satellite',
    name: 'Google Satellite',
    type: 'tile',
    url: 'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
    is_active: true,
    display_order: 1,
    created_at: '', updated_at: '',
  },
  {
    id: 'google-hybrid',
    name: 'Google Hybrid',
    type: 'tile',
    url: 'https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
    is_active: false,
    display_order: 2,
    created_at: '', updated_at: '',
  },
  {
    id: 'osm',
    name: 'OpenStreetMap',
    type: 'tile',
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    is_active: false,
    display_order: 3,
    created_at: '', updated_at: '',
  },
];

export function useLayers() {
  const { data, isLoading } = useQuery<MapLayer[]>({
    queryKey: ['layers'],
    queryFn: async () => {
      try {
        const result = await layersApi.list();
        const arr = Array.isArray(result) ? result : (result as { layers?: MapLayer[] })?.layers ?? [];
        return arr as MapLayer[];
      } catch {
        return [];
      }
    },
    staleTime: 5 * 60_000,
  });

  /** Merge backend layers with the client base set, de-duplicating by id. */
  const { baseLayers, overlayLayers } = useMemo(() => {
    const backend = data ?? [];
    const seen = new Set<string>();
    const bases: MapLayer[] = [];
    const overlays: MapLayer[] = [];

    // Backend tile layers are bases; backend STAC layers are analysis overlays.
    for (const l of backend) {
      if (seen.has(l.id)) continue;
      seen.add(l.id);
      (l.type === 'tile' ? bases : overlays).push(l);
    }
    // Add any client base layers the backend didn't provide (e.g. Google).
    for (const l of CLIENT_BASE_LAYERS) {
      if (!seen.has(l.id)) { seen.add(l.id); bases.push(l); }
    }

    bases.sort((a, b) => a.display_order - b.display_order);
    overlays.sort((a, b) => a.display_order - b.display_order);
    return { baseLayers: bases, overlayLayers: overlays };
  }, [data]);

  const [activeBaseId, setActiveBaseId] = useState<string>('google-satellite');
  const [visibleOverlayIds, setVisibleOverlayIds] = useState<Set<string>>(new Set());

  // Once layers resolve, ensure a valid base is selected.
  useEffect(() => {
    if (baseLayers.length && !baseLayers.some((l) => l.id === activeBaseId)) {
      const firstActive = baseLayers.find((l) => l.is_active) ?? baseLayers[0];
      setActiveBaseId(firstActive.id);
    }
  }, [baseLayers, activeBaseId]);

  const toggleOverlay = (id: string) => {
    setVisibleOverlayIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const activeBase = baseLayers.find((l) => l.id === activeBaseId) ?? baseLayers[0] ?? null;
  const visibleOverlays = overlayLayers.filter((l) => visibleOverlayIds.has(l.id));

  /** Render order: base first (bottom), overlays on top. */
  const visibleLayers = useMemo(
    () => (activeBase ? [activeBase, ...visibleOverlays] : visibleOverlays),
    [activeBase, visibleOverlays]
  );

  return {
    baseLayers,
    overlayLayers,
    activeBaseId,
    setActiveBase: setActiveBaseId,
    visibleOverlayIds,
    toggleOverlay,
    visibleLayers,
    isLoading,
  };
}
