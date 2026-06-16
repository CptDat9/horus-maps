import { Polygon, Tooltip } from 'react-leaflet';
import type { Detection } from '../../types';
import { geometryToLatLngs } from '../../utils/geoUtils';

/** Colour per object family — kept consistent with the DetectPanel legend. */
export function detectionColor(objectType: string): string {
  if (objectType === 'plane' || objectType === 'helicopter') return '#34d399'; // emerald
  if (objectType === 'ship') return '#22d3ee'; // cyan
  if (objectType.endsWith('vehicle')) return '#f472b6'; // pink
  return '#fbbf24'; // amber (other DOTA classes)
}

interface DetectionLayerProps {
  detections: Detection[];
  visible: boolean;
}

/**
 * Renders YOLO-OBB detections as oriented polygons. Lives in the overlayPane
 * (z 400) so it stays on top of the comparison swipe, like the AOI layer.
 */
export function DetectionLayer({ detections, visible }: DetectionLayerProps) {
  if (!visible) return null;
  return (
    <>
      {detections.map((d) => {
        const positions = geometryToLatLngs(d.geometry);
        if (positions.length < 3) return null;
        const color = detectionColor(d.object_type);
        return (
          <Polygon
            key={d.id}
            positions={positions}
            pathOptions={{ color, fillColor: color, fillOpacity: 0.18, weight: 2 }}
          >
            <Tooltip direction="top" offset={[0, -2]} opacity={1}>
              <span className="text-xs font-medium">
                {d.object_type} · {(d.confidence * 100).toFixed(0)}%
              </span>
            </Tooltip>
          </Polygon>
        );
      })}
    </>
  );
}
