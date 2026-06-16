import { useEffect } from 'react';
import { Polygon, Polyline, CircleMarker, Tooltip, useMapEvents } from 'react-leaflet';
import { useApp } from '../../store/AppContext';
import {
  calculatePathLength, calculatePolygonArea, formatArea, formatDistance,
} from '../../utils/geoUtils';

/**
 * Google-Earth style on-map measuring, independent of AOIs.
 *  - distance mode: open path, running length
 *  - area mode: closed polygon, area + perimeter
 * Click adds a vertex; the live total shows as a tooltip on the last point.
 */
export function MeasureLayer() {
  const { measureMode, measurePoints, setMeasurePoints } = useApp();
  const active = measureMode !== 'none';

  const map = useMapEvents({
    click(e) {
      if (!active) return;
      setMeasurePoints([...measurePoints, [e.latlng.lat, e.latlng.lng]]);
    },
    dblclick(e) {
      if (!active) return;
      // Swallow the event so the map does not zoom while finishing a shape.
      e.originalEvent.preventDefault();
    },
  });

  useEffect(() => {
    if (active) {
      map.doubleClickZoom.disable();
      map.getContainer().style.cursor = 'crosshair';
    } else {
      map.doubleClickZoom.enable();
      map.getContainer().style.cursor = '';
    }
    return () => {
      map.doubleClickZoom.enable();
      map.getContainer().style.cursor = '';
    };
  }, [active, map]);

  if (!active || measurePoints.length === 0) return null;

  const isArea = measureMode === 'area';
  const color = '#10b981'; // emerald
  const last = measurePoints[measurePoints.length - 1];

  const label = isArea
    ? (measurePoints.length >= 3 ? formatArea(calculatePolygonArea(measurePoints)) : 'Click to add points')
    : (measurePoints.length >= 2 ? formatDistance(calculatePathLength(measurePoints)) : 'Click to add points');

  return (
    <>
      {isArea && measurePoints.length >= 3 ? (
        <Polygon
          positions={measurePoints}
          pathOptions={{ color, fillColor: color, fillOpacity: 0.15, weight: 2, dashArray: '6 4' }}
        />
      ) : (
        <Polyline
          positions={measurePoints}
          pathOptions={{ color, weight: 2.5, dashArray: '6 4', opacity: 0.95 }}
        />
      )}

      {measurePoints.map(([lat, lng], i) => (
        <CircleMarker
          key={i}
          center={[lat, lng]}
          radius={4}
          pathOptions={{ color, fillColor: '#fff', fillOpacity: 1, weight: 2 }}
        />
      ))}

      <CircleMarker center={last} radius={0.1} pathOptions={{ opacity: 0, fillOpacity: 0 }}>
        <Tooltip permanent direction="top" offset={[0, -6]} className="measure-tip">
          {label}
        </Tooltip>
      </CircleMarker>
    </>
  );
}
