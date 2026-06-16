import { useState, useRef, useEffect } from 'react';
import { Search, Satellite, MapPin, X, Loader2, Crosshair } from 'lucide-react';
import { geocodingApi } from '../../services/api';

interface GeoResult {
  lat: string;
  lon: string;
  display_name: string;
  type?: string;
  addresstype?: string;
}

interface SearchBarProps {
  /** Fly to a location and drop a marker. */
  onSelect: (lat: number, lng: number, label: string) => void;
}

const COORD_RE = /^\s*(-?\d{1,2}(?:\.\d+)?)\s*[,\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*$/;

function parseCoord(q: string): [number, number] | null {
  const m = q.match(COORD_RE);
  if (!m) return null;
  const lat = parseFloat(m[1]), lng = parseFloat(m[2]);
  if (lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180) return [lat, lng];
  return null;
}

/** Floating Google-Maps style search: place names + "lat,lng" coordinates. */
export function SearchBar({ onSelect }: SearchBarProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<GeoResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1); // keyboard-highlighted row
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abort = useRef<AbortController | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const coord = parseCoord(query);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!wrapperRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleInput = (q: string) => {
    setQuery(q);
    setActive(-1);
    if (timer.current) clearTimeout(timer.current);
    abort.current?.abort();
    if (!q.trim() || parseCoord(q)) { setResults([]); setOpen(!!parseCoord(q)); return; }

    timer.current = setTimeout(async () => {
      setSearching(true);
      abort.current = new AbortController();
      try {
        const data = (await geocodingApi.search(q, abort.current.signal)) as GeoResult[];
        setResults(data.slice(0, 8));
        setOpen(true);
      } catch { /* aborted or failed */ }
      finally { setSearching(false); }
    }, 350);
  };

  const goCoord = () => {
    if (!coord) return;
    onSelect(coord[0], coord[1], `${coord[0].toFixed(4)}, ${coord[1].toFixed(4)}`);
    setOpen(false);
  };

  const pick = (r: GeoResult) => {
    const label = r.display_name.split(',')[0];
    onSelect(parseFloat(r.lat), parseFloat(r.lon), label);
    setQuery(label);
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === 'Enter') {
      if (coord) goCoord();
      else if (results[active >= 0 ? active : 0]) pick(results[active >= 0 ? active : 0]);
    } else if (e.key === 'Escape') { setOpen(false); }
  };

  return (
    <div ref={wrapperRef} className="w-[20rem] max-w-[calc(100vw-2rem)]">
      <div className="flex items-center bg-slate-800/95 backdrop-blur border border-slate-700 hover:border-slate-500 focus-within:border-blue-500 rounded-full pl-3 pr-2 h-11 gap-2 shadow-xl transition-colors">
        <Satellite size={16} className="text-blue-400 shrink-0" />
        <input
          type="text"
          value={query}
          onChange={(e) => handleInput(e.target.value)}
          onFocus={() => (results.length > 0 || coord) && setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder="Search place or lat, lng…"
          className="flex-1 bg-transparent text-sm text-slate-100 placeholder-slate-500 outline-none min-w-0"
        />
        {searching
          ? <Loader2 size={15} className="text-slate-400 animate-spin shrink-0" />
          : query
            ? <button onClick={() => { setQuery(''); setResults([]); setOpen(false); }}>
                <X size={15} className="text-slate-500 hover:text-slate-300 transition-colors" />
              </button>
            : <Search size={15} className="text-slate-500 shrink-0" />
        }
      </div>

      {open && (coord || results.length > 0) && (
        <div className="mt-1.5 bg-slate-800/97 backdrop-blur border border-slate-700 rounded-2xl shadow-2xl overflow-hidden max-h-[60vh] overflow-y-auto">
          {/* Coordinate quick-action */}
          {coord && (
            <button
              onClick={goCoord}
              className="w-full flex items-center gap-2.5 px-3.5 py-2.5 hover:bg-slate-700/70 text-left transition-colors border-b border-slate-700/60"
            >
              <Crosshair size={14} className="text-emerald-400 shrink-0" />
              <div className="min-w-0">
                <p className="text-xs text-slate-200">Go to coordinate</p>
                <p className="text-[11px] text-slate-500">{coord[0].toFixed(5)}, {coord[1].toFixed(5)}</p>
              </div>
            </button>
          )}

          {results.map((r, i) => (
            <button
              key={`${r.lat}-${r.lon}-${i}`}
              onClick={() => pick(r)}
              onMouseEnter={() => setActive(i)}
              className={`w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left transition-colors
                ${i === active ? 'bg-slate-700/70' : 'hover:bg-slate-700/70'}`}
            >
              <MapPin size={13} className="text-blue-400 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="text-xs text-slate-200 truncate">{r.display_name.split(',')[0]}</p>
                <p className="text-[11px] text-slate-500 truncate">
                  {r.display_name.split(',').slice(1).join(',').trim()}
                </p>
              </div>
              {(r.addresstype || r.type) && (
                <span className="shrink-0 text-[9px] uppercase tracking-wide text-slate-400 bg-slate-900/60 rounded px-1.5 py-0.5">
                  {r.addresstype || r.type}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
