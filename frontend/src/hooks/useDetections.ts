import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { detectionApi } from '../services/api';
import { useApp } from '../store/AppContext';
import type {
  Detection, DetectionListResponse, DetectionJob, DetectionJobResponse,
  DetectionRun, DetectionRunListResponse,
} from '../types';

/** Detections (latest run) for an AOI + run history + job actions. */
export function useDetections(aoiId: string | null) {
  const { sessionId } = useApp();
  const qc = useQueryClient();

  const { data, isLoading } = useQuery<DetectionListResponse>({
    queryKey: ['detections', aoiId],
    queryFn: () => {
      if (!sessionId || !aoiId) return Promise.resolve({ items: [], total: 0 });
      return detectionApi.list(sessionId, aoiId) as Promise<DetectionListResponse>;
    },
    enabled: !!sessionId && !!aoiId,
  });

  const { data: runsData } = useQuery<DetectionRunListResponse>({
    queryKey: ['detection-runs', aoiId],
    queryFn: () => {
      if (!sessionId || !aoiId) return Promise.resolve({ items: [], total: 0 });
      return detectionApi.runs(sessionId, aoiId) as Promise<DetectionRunListResponse>;
    },
    enabled: !!sessionId && !!aoiId,
  });

  const run = useMutation({
    mutationFn: async (job: DetectionJob) => {
      if (!sessionId || !aoiId) throw new Error('Missing context');
      return detectionApi.run(sessionId, aoiId, job) as Promise<DetectionJobResponse>;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks', sessionId] });
    },
  });

  const clear = useMutation({
    mutationFn: async () => {
      if (!sessionId || !aoiId) throw new Error('Missing context');
      return detectionApi.clear(sessionId, aoiId);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['detections', aoiId] });
      qc.invalidateQueries({ queryKey: ['detection-runs', aoiId] });
    },
  });

  const deleteRun = useMutation({
    mutationFn: async (runId: string) => {
      if (!sessionId || !aoiId) throw new Error('Missing context');
      return detectionApi.deleteRun(sessionId, aoiId, runId);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['detections', aoiId] });
      qc.invalidateQueries({ queryKey: ['detection-runs', aoiId] });
    },
  });

  return {
    detections: (data?.items ?? []) as Detection[],
    latestRunId: data?.run_id ?? null,
    runs: (runsData?.items ?? []) as DetectionRun[],
    isLoading,
    runDetection: run.mutateAsync,
    isRunning: run.isPending,
    clearDetections: clear.mutateAsync,
    deleteRun: deleteRun.mutateAsync,
  };
}
