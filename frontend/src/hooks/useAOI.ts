import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { aoiApi, measurementApi } from '../services/api';
import { useApp } from '../store/AppContext';
import type {
  AOI, AOICreate, AOIUpdate, AOIListResponse, MeasurementListResponse,
} from '../types';

export function useAOIs() {
  const { sessionId } = useApp();
  const qc = useQueryClient();

  const { data, isLoading } = useQuery<AOIListResponse>({
    queryKey: ['aois', sessionId],
    queryFn: () => {
      if (!sessionId) return Promise.resolve({ items: [], total: 0, page: 1, size: 50 });
      return aoiApi.list(sessionId) as Promise<AOIListResponse>;
    },
    enabled: !!sessionId,
  });

  const createMutation = useMutation({
    mutationFn: async (aoi: AOICreate) => {
      if (!sessionId) throw new Error('No session');
      return aoiApi.create(sessionId, aoi) as Promise<AOI>;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['aois', sessionId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (aoiId: string) => {
      if (!sessionId) throw new Error('No session');
      return aoiApi.delete(sessionId, aoiId);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['aois', sessionId] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: async ({ aoiId, data }: { aoiId: string; data: AOIUpdate }) => {
      if (!sessionId) throw new Error('No session');
      return aoiApi.update(sessionId, aoiId, data) as Promise<AOI>;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['aois', sessionId] });
    },
  });

  return {
    aois: data?.items ?? [],
    total: data?.total ?? 0,
    isLoading,
    createAOI: createMutation.mutateAsync,
    deleteAOI: deleteMutation.mutateAsync,
    updateAOI: updateMutation.mutateAsync,
    isCreating: createMutation.isPending,
  };
}

export function useMeasurements(aoiId: string | null) {
  const { sessionId } = useApp();

  const { data, isLoading } = useQuery<MeasurementListResponse>({
    queryKey: ['measurements', aoiId],
    queryFn: () => {
      if (!sessionId || !aoiId) return Promise.resolve({ items: [], total: 0 });
      return measurementApi.list(sessionId, aoiId) as Promise<MeasurementListResponse>;
    },
    enabled: !!sessionId && !!aoiId,
  });

  const qc = useQueryClient();

  const createMutation = useMutation({
    mutationFn: async (payload: { type: string; unit: string; metadata?: Record<string, unknown> }) => {
      if (!sessionId || !aoiId) throw new Error('Missing context');
      return measurementApi.create(sessionId, aoiId, payload);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['measurements', aoiId] });
    },
  });

  return {
    measurements: data?.items ?? [],
    isLoading,
    createMeasurement: createMutation.mutateAsync,
  };
}
