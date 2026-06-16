const EARTH_R = 6371; // km
const toRad = (d: number) => (d * Math.PI) / 180;

/** Area in km² via Shoelace + WGS84 correction */
export function calculatePolygonArea(latLngs: [number, number][]): number {
  if (latLngs.length < 3) return 0;
  let area = 0;
  const n = latLngs.length;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    const [lat1, lng1] = latLngs[i];
    const [lat2, lng2] = latLngs[j];
    area +=
      toRad(lng2 - lng1) * (2 + Math.sin(toRad(lat1)) + Math.sin(toRad(lat2)));
  }
  return Math.abs((area * EARTH_R * EARTH_R) / 2);
}

/** Perimeter in km using Haversine */
export function calculatePolygonPerimeter(latLngs: [number, number][]): number {
  if (latLngs.length < 2) return 0;
  let total = 0;
  for (let i = 0; i < latLngs.length; i++) {
    const j = (i + 1) % latLngs.length;
    const [lat1, lng1] = latLngs[i];
    const [lat2, lng2] = latLngs[j];
    const dLat = toRad(lat2 - lat1);
    const dLng = toRad(lng2 - lng1);
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
    total += EARTH_R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }
  return total;
}

/** Length in km of an OPEN path (no closing segment) using Haversine */
export function calculatePathLength(latLngs: [number, number][]): number {
  if (latLngs.length < 2) return 0;
  let total = 0;
  for (let i = 0; i < latLngs.length - 1; i++) {
    const [lat1, lng1] = latLngs[i];
    const [lat2, lng2] = latLngs[i + 1];
    const dLat = toRad(lat2 - lat1);
    const dLng = toRad(lng2 - lng1);
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
    total += EARTH_R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }
  return total;
}

export function formatArea(km2: number): string {
  if (km2 < 0.001) return `${(km2 * 1e6).toFixed(0)} m²`;
  if (km2 < 1) return `${(km2 * 100).toFixed(2)} ha`;
  return `${km2.toFixed(3)} km²`;
}

export function formatDistance(km: number): string {
  if (km < 1) return `${(km * 1000).toFixed(0)} m`;
  return `${km.toFixed(3)} km`;
}

/** GeoJSON geometry → [[lat, lng], ...] (outer ring only) */
export function geometryToLatLngs(geometry: {
  type: string;
  coordinates: number[][][] | number[][][][];
}): [number, number][] {
  if (geometry.type === 'Polygon') {
    return (geometry.coordinates as number[][][])[0].map(([lng, lat]) => [lat, lng]);
  }
  if (geometry.type === 'MultiPolygon') {
    return (geometry.coordinates as number[][][][])[0][0].map(([lng, lat]) => [lat, lng]);
  }
  return [];
}

/** [[lat, lng], ...] → closed GeoJSON Polygon */
export function latLngsToGeometry(latLngs: [number, number][]): {
  type: 'Polygon';
  coordinates: number[][][];
} {
  if (latLngs.length < 3) throw new Error('Need at least 3 points');
  const ring = latLngs.map(([lat, lng]) => [lng, lat]);
  ring.push(ring[0]);
  return { type: 'Polygon', coordinates: [ring] };
}

/** [minLng, minLat, maxLng, maxLat] */
export function geometryBBox(geometry: {
  type: string;
  coordinates: number[][][] | number[][][][];
}): [number, number, number, number] {
  const coords: number[][] =
    geometry.type === 'Polygon'
      ? (geometry.coordinates as number[][][]).flat()
      : (geometry.coordinates as number[][][][]).flat(2);
  const lngs = coords.map((c) => c[0]);
  const lats = coords.map((c) => c[1]);
  return [Math.min(...lngs), Math.min(...lats), Math.max(...lngs), Math.max(...lats)];
}
