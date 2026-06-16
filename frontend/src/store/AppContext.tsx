import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import { sessionApi } from '../services/api';
import type {
  Session, DrawMode, Notification, ActiveTool, MeasureMode, ComparisonView,
} from '../types';

const SESSION_KEY = 'horus_session_id';

interface AppState {
  session: Session | null;
  sessionId: string | null;
  isSessionLoading: boolean;

  /** Which floating panel/tool is open (only one at a time). */
  activeTool: ActiveTool;

  /** AOI polygon drawing. */
  drawMode: DrawMode;
  drawingVertices: [number, number][];
  selectedAoiId: string | null;

  /** Google-Earth style measuring (independent of AOI). */
  measureMode: MeasureMode;
  measurePoints: [number, number][];

  /** Active side-by-side comparison shown in the zoomable viewer (null = closed). */
  comparisonView: ComparisonView | null;

  notifications: Notification[];
}

interface AppActions {
  setActiveTool: (tool: ActiveTool) => void;
  setDrawMode: (mode: DrawMode) => void;
  setDrawingVertices: (v: [number, number][]) => void;
  setSelectedAoiId: (id: string | null) => void;
  setMeasureMode: (mode: MeasureMode) => void;
  setMeasurePoints: (v: [number, number][]) => void;
  clearMeasure: () => void;
  setComparisonView: (c: ComparisonView | null) => void;
  addNotification: (n: Omit<Notification, 'id'>) => void;
  removeNotification: (id: string) => void;
}

const AppContext = createContext<(AppState & AppActions) | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [isSessionLoading, setIsSessionLoading] = useState(true);

  const [activeTool, setActiveToolRaw] = useState<ActiveTool>('none');
  const [drawMode, setDrawModeRaw] = useState<DrawMode>('none');
  const [drawingVertices, setDrawingVertices] = useState<[number, number][]>([]);
  const [selectedAoiId, setSelectedAoiId] = useState<string | null>(null);

  const [measureMode, setMeasureModeRaw] = useState<MeasureMode>('none');
  const [measurePoints, setMeasurePoints] = useState<[number, number][]>([]);

  const [comparisonView, setComparisonView] = useState<ComparisonView | null>(null);
  const [notifications, setNotifications] = useState<Notification[]>([]);

  useEffect(() => {
    (async () => {
      try {
        const stored = localStorage.getItem(SESSION_KEY);
        if (stored) {
          try {
            const s = (await sessionApi.get(stored)) as Session;
            setSession(s);
            return;
          } catch {
            localStorage.removeItem(SESSION_KEY);
          }
        }
        const s = (await sessionApi.create({ ttl_hours: 24 })) as Session;
        localStorage.setItem(SESSION_KEY, s.id);
        setSession(s);
      } catch (err) {
        console.error('[Session] init failed', err);
      } finally {
        setIsSessionLoading(false);
      }
    })();
  }, []);

  const setDrawMode = useCallback((mode: DrawMode) => {
    setDrawModeRaw(mode);
    if (mode === 'none') setDrawingVertices([]);
  }, []);

  const setMeasureMode = useCallback((mode: MeasureMode) => {
    setMeasureModeRaw(mode);
    if (mode === 'none') setMeasurePoints([]);
  }, []);

  const clearMeasure = useCallback(() => {
    setMeasureModeRaw('none');
    setMeasurePoints([]);
  }, []);

  /** Open a tool/panel (exclusive). Tearing down whichever interactive mode we leave. */
  const setActiveTool = useCallback((tool: ActiveTool) => {
    if (tool !== 'aoi') { setDrawModeRaw('none'); setDrawingVertices([]); }
    if (tool !== 'measure') { setMeasureModeRaw('none'); setMeasurePoints([]); }
    setActiveToolRaw(tool);
  }, []);

  const addNotification = useCallback((n: Omit<Notification, 'id'>) => {
    const id = crypto.randomUUID();
    setNotifications((prev) => [...prev.slice(-4), { ...n, id }]);
    setTimeout(() => setNotifications((prev) => prev.filter((x) => x.id !== id)), 5000);
  }, []);

  const removeNotification = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((x) => x.id !== id));
  }, []);

  return (
    <AppContext.Provider
      value={{
        session,
        sessionId: session?.id ?? null,
        isSessionLoading,
        activeTool,
        drawMode,
        drawingVertices,
        selectedAoiId,
        measureMode,
        measurePoints,
        comparisonView,
        notifications,
        setActiveTool,
        setDrawMode,
        setDrawingVertices,
        setSelectedAoiId,
        setMeasureMode,
        setMeasurePoints,
        clearMeasure,
        setComparisonView,
        addNotification,
        removeNotification,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
