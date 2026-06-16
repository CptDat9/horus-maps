import { useEffect } from 'react';
import { Polygon, Polyline, Circle, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import { useApp } from '../../store/AppContext';

interface DrawLayerProps {
  onComplete: (latLngs: [number, number][]) => void;
}

export function DrawLayer({ onComplete }: DrawLayerProps) {
  const { drawMode, setDrawMode, drawingVertices, setDrawingVertices } = useApp();
  const isDrawing = drawMode === 'polygon';

  const map = useMapEvents({
    click(e) {
      if (!isDrawing) return;
      setDrawingVertices([...drawingVertices, [e.latlng.lat, e.latlng.lng]]);
    },
    dblclick(e) {
      if (!isDrawing) return;
      L.DomEvent.stop(e);
      if (drawingVertices.length >= 3) {
        onComplete(drawingVertices);
        setDrawingVertices([]);
        setDrawMode('none');
      }
    },
    mousemove() {
      // cursor changes via CSS class on map container
    },
  });

  // Disable / re-enable double-click zoom while in draw mode
  useEffect(() => {
    if (isDrawing) {
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
  }, [isDrawing, map]);

  if (!isDrawing || drawingVertices.length === 0) return null;

  return (
    <>
      {/* Connecting line between vertices */}
      <Polyline
        positions={drawingVertices}
        pathOptions={{ color: '#3b82f6', weight: 2, dashArray: '6 4', opacity: 0.9 }}
      />

      {/* Preview filled polygon (3+ vertices) */}
      {drawingVertices.length >= 3 && (
        <Polygon
          positions={drawingVertices}
          pathOptions={{ color: '#3b82f6', fillColor: '#3b82f6', fillOpacity: 0.15, weight: 1.5, opacity: 0.7 }}
        />
      )}

      {/* Vertex dots */}
      {drawingVertices.map(([lat, lng], i) => (
        <Circle
          key={i}
          center={[lat, lng]}
          radius={20}
          pathOptions={{ color: '#3b82f6', fillColor: '#3b82f6', fillOpacity: 1, weight: 1 }}
        />
      ))}
    </>
  );
}
