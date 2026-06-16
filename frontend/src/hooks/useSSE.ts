import { useEffect, useRef } from 'react';
import { useApp } from '../store/AppContext';
import { useQueryClient } from '@tanstack/react-query';

/** Subscribe to task SSE updates. Automatically cleans up on unmount or taskId change. */
export function useTaskSSE(taskId: string | null) {
  const { addNotification, sessionId } = useApp();
  const qc = useQueryClient();
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!taskId) return;

    const es = new EventSource(`/api/sse/tasks/${taskId}`);
    esRef.current = es;

    const handleUpdate = (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      if (data.status === 'completed') {
        addNotification({ type: 'success', message: `Task completed`, taskId });
        qc.invalidateQueries({ queryKey: ['tasks', sessionId] });
        es.close();
      } else if (data.status === 'failed') {
        addNotification({
          type: 'error',
          message: `Task failed: ${data.error_message ?? 'Unknown error'}`,
          taskId,
        });
        qc.invalidateQueries({ queryKey: ['tasks', sessionId] });
        es.close();
      }
    };

    es.addEventListener('update', handleUpdate);
    es.addEventListener('done', handleUpdate);
    es.addEventListener('stream_end', () => es.close());
    es.onerror = () => es.close();

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [taskId, addNotification, sessionId, qc]);
}
