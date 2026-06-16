import type { ReactNode } from 'react';

/** Full-screen, map-centric shell. The map fills the viewport; everything else
 *  floats over it (Google-Maps / Earth-Engine style). */
export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="relative w-full h-screen overflow-hidden bg-slate-900">
      {children}
    </div>
  );
}
