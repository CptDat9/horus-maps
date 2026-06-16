
import { Polygon, Tooltip } from 'react-leaflet';
import type { AOI } from '../../types';
import { geometryToLatLngs } from '../../utils/geoUtils';

interface AOILayerProps {
  aois: AOI[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function AOILayer({ aois, selectedId, onSelect }: AOILayerProps) {
  return (
    <>
      {aois.map((aoi) => {
        const positions = geometryToLatLngs(aoi.geometry);
        if (positions.length < 3) return null;

        const selected = aoi.id === selectedId;

        return (
          <Polygon
            key={aoi.id}
            positions={positions}
            pathOptions={{
              color: selected ? '#f59e0b' : '#3b82f6',
              fillColor: selected ? '#f59e0b' : '#3b82f6',
              fillOpacity: selected ? 0.22 : 0.1,
              weight: selected ? 2.5 : 1.5,
              opacity: selected ? 1 : 0.8,
            }}
            eventHandlers={{ click: () => onSelect(aoi.id) }}
          >
            <Tooltip sticky direction="top" offset={[0, -4]}>
              <span className="text-xs font-medium">{aoi.name}</span>
            </Tooltip>
          </Polygon>
        );
      })}
    </>
  );
}
