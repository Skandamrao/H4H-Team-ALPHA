import { create } from 'zustand';
import type { Feature, ConflictRecord } from '../types';

interface AppState {
  projectId: string;
  setProjectId: (id: string) => void;
  features: Feature[];
  setFeatures: (f: Feature[]) => void;
  conflicts: ConflictRecord[];
  setConflicts: (c: ConflictRecord[]) => void;
  totalEvents: number;
  setTotalEvents: (n: number) => void;
}

export const useAppStore = create<AppState>((set) => ({
  projectId: 'proj-alpha',
  setProjectId: (id) => set({ projectId: id }),
  features: [],
  setFeatures: (features) => set({ features }),
  conflicts: [],
  setConflicts: (conflicts) => set({ conflicts }),
  totalEvents: 0,
  setTotalEvents: (totalEvents) => set({ totalEvents }),
}));

