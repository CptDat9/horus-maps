export interface Session {
  id: string;
  session_id: string;
  metadata?: Record<string, unknown>;
  created_at: string;
  last_accessed: string;
  expires_at?: string;
}

export type GeoJSONPolygon = {
  type: 'Polygon';
  coordinates: number[][][];
};

export type GeoJSONMultiPolygon = {
  type: 'MultiPolygon';
  coordinates: number[][][][];
};

export type GeoJSONGeometry = GeoJSONPolygon | GeoJSONMultiPolygon;

export interface AOI {
  id: string;
  session_id: string;
  name: string;
  description?: string;
  properties?: Record<string, unknown>;
  geometry: GeoJSONGeometry;
  created_at: string;
  updated_at: string;
}

export interface AOICreate {
  name: string;
  description?: string;
  geometry: GeoJSONPolygon;
  properties?: Record<string, unknown>;
}

export interface AOIUpdate {
  name?: string;
  description?: string;
  properties?: Record<string, unknown>;
}

export interface AOIListResponse {
  items: AOI[];
  total: number;
  page: number;
  size: number;
}

export interface Measurement {
  id: string;
  session_id: string;
  aoi_id: string;
  type: 'area' | 'perimeter' | 'distance' | 'height';
  value: number;
  unit: string;
  geometry?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface MeasurementCreate {
  type: string;
  unit: string;
  geometry?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

export interface MeasurementListResponse {
  items: Measurement[];
  total: number;
}

export interface TemporalComparison {
  id: string;
  session_id: string;
  aoi_id: string;
  left_item_id: string;
  right_item_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  task_id?: string | null;
  comparison_result?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface MapLayer {
  id: string;
  name: string;
  type: 'tile' | 'stac';
  url: string;
  options?: Record<string, unknown>;
  is_active: boolean;
  display_order: number;
  created_at: string;
  updated_at: string;
}

export interface Task {
  id: string;
  session_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  task_type: string;
  payload?: Record<string, unknown>;
  result?: Record<string, unknown>;
  error_message?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface STACItem {
  type: 'Feature';
  stac_version: string;
  id: string;
  collection: string;
  geometry: GeoJSONGeometry;
  bbox: number[];
  properties: {
    datetime: string | null;
    collection: string;
    [key: string]: unknown;
  };
  assets: Record<string, { href: string; type?: string; title?: string }>;
  links?: Array<{ rel: string; href: string }>;
}

/** AI object-detection categories (mapped to DOTA classes on the backend). */
export type ObjectClass = 'all' | 'aircraft' | 'vessels' | 'vehicles';

export interface Detection {
  id: string;
  session_id: string;
  aoi_id: string;
  object_type: string;
  geometry: GeoJSONPolygon;
  confidence: number;
  properties?: Record<string, unknown>;
  created_at: string;
}

export interface DetectionListResponse {
  items: Detection[];
  total: number;
  run_id?: string | null;
}

/** One detection run (a history entry per AOI). */
export interface DetectionRun {
  id: string;
  aoi_id: string;
  count: number;
  classes?: number[] | null;
  meta?: Record<string, unknown> | null;
  created_at: string;
}

export interface DetectionRunListResponse {
  items: DetectionRun[];
  total: number;
}

export interface DetectionJob {
  classes?: number[];
  object_class?: ObjectClass;
  /** Active base-layer XYZ tile template — detection runs on the imagery shown. */
  tile_url?: string;
  zoom?: number;
  confidence?: number;
  iou?: number;
}

/** Full DOTA v1.0 class list the YOLO-OBB model knows (id → label). */
export const DOTA_CLASSES: { id: number; label: string }[] = [
  { id: 0, label: 'plane' },
  { id: 1, label: 'ship' },
  { id: 2, label: 'storage-tank' },
  { id: 3, label: 'baseball-diamond' },
  { id: 4, label: 'tennis-court' },
  { id: 5, label: 'basketball-court' },
  { id: 6, label: 'ground-track-field' },
  { id: 7, label: 'harbor' },
  { id: 8, label: 'bridge' },
  { id: 9, label: 'large-vehicle' },
  { id: 10, label: 'small-vehicle' },
  { id: 11, label: 'helicopter' },
  { id: 12, label: 'roundabout' },
  { id: 13, label: 'soccer-ball-field' },
  { id: 14, label: 'swimming-pool' },
];

/** Quick presets → DOTA class ids. */
export const CLASS_PRESETS: { key: ObjectClass; label: string; classes: number[] }[] = [
  { key: 'all', label: 'Movers', classes: [0, 1, 9, 10, 11] },
  { key: 'vehicles', label: 'Vehicles', classes: [9, 10] },
  { key: 'vessels', label: 'Vessels', classes: [1] },
  { key: 'aircraft', label: 'Aircraft', classes: [0, 11] },
];

export interface DetectionJobResponse {
  task_id: string;
  status: string;
  aoi_id: string;
  message: string;
}

export type DrawMode = 'none' | 'polygon';

/** Which floating tool/panel is currently open. Only one at a time (Google-Maps style). */
export type ActiveTool = 'none' | 'aoi' | 'measure' | 'compare' | 'detect';

/** Google-Earth style measurement: open path (distance) or closed shape (area). */
export type MeasureMode = 'none' | 'distance' | 'area';

/** A single scene shown in the comparison viewer. */
export interface ComparisonSide {
  /** Slippy tile template (reliable — used for the live map render). */
  tileUrl: string;
  /** Static AOI crop PNG (used for the Export button). */
  imageUrl: string | null;
  label: string;
  /** Native zoom of the source (Sentinel ~15, Google ~20) so each pane
   *  up-samples appropriately. */
  nativeZoom?: number;
}

/** Two-date comparison shown side-by-side in a synced zoomable viewer. */
export interface ComparisonView {
  title: string;
  /** AOI extent [minLng, minLat, maxLng, maxLat] — both maps fit to this. */
  bbox: [number, number, number, number];
  left: ComparisonSide;
  right: ComparisonSide;
}

export interface Notification {
  id: string;
  type: 'success' | 'error' | 'info' | 'warning';
  message: string;
  taskId?: string;
}
