const BASE = '/api';

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => `HTTP ${res.status}`);
    throw new Error(text || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const sessionApi = {
  create: (data?: { metadata?: Record<string, unknown>; ttl_hours?: number }) =>
    req('/sessions', { method: 'POST', body: JSON.stringify(data ?? {}) }),
  get: (id: string) => req(`/sessions/${id}`),
};

export const layersApi = {
  list: () => req('/layers'),
};

export const stacApi = {
  listCollections: () => req('/stac/collections'),
  getCollection: (id: string) => req(`/stac/collections/${id}`),
  listItems: (collectionId: string, limit = 20) =>
    req(`/stac/collections/${collectionId}/items?limit=${limit}`),
  search: (data: {
    collections: string[];
    bbox?: number[];
    datetime?: string;
    limit?: number;
  }) => req('/stac/search', { method: 'POST', body: JSON.stringify(data) }),
  itemTileUrl: (itemId: string) =>
    req(`/stac/items/${encodeURIComponent(itemId)}/tile-url`) as Promise<{
      item_id: string; datetime: string | null; tile_url: string;
    }>,
};

export const aoiApi = {
  list: (sessionId: string, skip = 0, limit = 50) =>
    req(`/sessions/${sessionId}/aois?skip=${skip}&limit=${limit}`),
  get: (sessionId: string, aoiId: string) =>
    req(`/sessions/${sessionId}/aois/${aoiId}`),
  create: (sessionId: string, data: unknown) =>
    req(`/sessions/${sessionId}/aois`, { method: 'POST', body: JSON.stringify(data) }),
  update: (sessionId: string, aoiId: string, data: unknown) =>
    req(`/sessions/${sessionId}/aois/${aoiId}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (sessionId: string, aoiId: string) =>
    req(`/sessions/${sessionId}/aois/${aoiId}`, { method: 'DELETE' }),
  /** Full path (incl. /api) to export the AOI satellite image (PNG). */
  imageUrl: (sessionId: string, aoiId: string, tileUrl?: string) => {
    const q = tileUrl ? `?tile_url=${encodeURIComponent(tileUrl)}` : '';
    return `${BASE}/sessions/${sessionId}/aois/${aoiId}/image${q}`;
  },
};

export const measurementApi = {
  list: (sessionId: string, aoiId: string) =>
    req(`/sessions/${sessionId}/aois/${aoiId}/measurements`),
  create: (sessionId: string, aoiId: string, data: unknown) =>
    req(`/sessions/${sessionId}/aois/${aoiId}/measurements`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

export const comparisonApi = {
  list: (sessionId: string, aoiId: string) =>
    req(`/sessions/${sessionId}/aois/${aoiId}/comparisons`),
  get: (sessionId: string, aoiId: string, compId: string) =>
    req(`/sessions/${sessionId}/aois/${aoiId}/comparisons/${compId}`),
  create: (sessionId: string, aoiId: string, data: unknown) =>
    req(`/sessions/${sessionId}/aois/${aoiId}/comparisons`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

export const taskApi = {
  list: (sessionId: string, skip = 0, limit = 50) =>
    req(`/sessions/${sessionId}/tasks?skip=${skip}&limit=${limit}`),
  get: (sessionId: string, taskId: string) =>
    req(`/sessions/${sessionId}/tasks/${taskId}`),
};

export const detectionApi = {
  list: (sessionId: string, aoiId: string) =>
    req(`/sessions/${sessionId}/aois/${aoiId}/detections`),
  run: (sessionId: string, aoiId: string, data: unknown) =>
    req(`/sessions/${sessionId}/aois/${aoiId}/detections`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  clear: (sessionId: string, aoiId: string) =>
    req(`/sessions/${sessionId}/aois/${aoiId}/detections`, { method: 'DELETE' }),
  /** Detection-run history for the AOI (newest first). */
  runs: (sessionId: string, aoiId: string) =>
    req(`/sessions/${sessionId}/aois/${aoiId}/detections/runs`),
  /** Detections of a specific historical run. */
  runDetections: (sessionId: string, aoiId: string, runId: string) =>
    req(`/sessions/${sessionId}/aois/${aoiId}/detections/runs/${runId}`),
  deleteRun: (sessionId: string, aoiId: string, runId: string) =>
    req(`/sessions/${sessionId}/aois/${aoiId}/detections/runs/${runId}`, { method: 'DELETE' }),
  /** Full path (incl. /api) to the latest annotated preview PNG. */
  previewUrl: (sessionId: string, aoiId: string, bust?: number | string) =>
    `${BASE}/sessions/${sessionId}/aois/${aoiId}/detections/preview${bust ? `?t=${bust}` : ''}`,
  /** Full path to a specific run's annotated PNG. */
  runPreviewUrl: (sessionId: string, aoiId: string, runId: string) =>
    `${BASE}/sessions/${sessionId}/aois/${aoiId}/detections/runs/${runId}/preview`,
};

/** Nominatim geocoding — called directly, not through backend proxy */
export const geocodingApi = {
  search: async (query: string, signal?: AbortSignal) => {
    const params = new URLSearchParams({
      format: 'jsonv2',
      q: query,
      limit: '8',
      addressdetails: '1',
      'accept-language': 'vi,en',
    });
    const url = `https://nominatim.openstreetmap.org/search?${params}`;
    const res = await fetch(url, { headers: { 'Accept-Language': 'vi,en' }, signal });
    if (!res.ok) return [];
    return res.json();
  },
};
