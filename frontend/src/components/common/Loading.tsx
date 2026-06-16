
import { Loader2 } from 'lucide-react';

export function Loading({ message = 'Loading...' }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 text-slate-400 py-8">
      <Loader2 size={20} className="animate-spin" />
      <span className="text-xs">{message}</span>
    </div>
  );
}

export function FullscreenLoading({ message }: { message?: string }) {
  return (
    <div className="fixed inset-0 flex flex-col items-center justify-center gap-3 bg-slate-900 z-50">
      <div className="flex items-center gap-2 text-blue-400 text-lg font-bold mb-2">
        <span>Horus Maps</span>
      </div>
      <Loading message={message ?? 'Initializing...'} />
    </div>
  );
}
