import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { FilterState, Job, SavedJob } from "../types/job";

const DEFAULT_FILTERS: FilterState = {
  q: "",
  location: [],
  experience: [],
  employment_type: [],
  source: [],
};

interface JobStore {
  filters: FilterState;
  setFilters: (filters: Partial<FilterState>) => void;
  resetFilters: () => void;

  viewedIds: Set<string>;
  lastSeenId: string | null;
  markViewed: (id: string) => void;
  hideViewed: boolean;
  toggleHideViewed: () => void;

  savedJobs: SavedJob[];
  saveJob: (job: Job) => void;
  unsaveJob: (id: string) => void;
  setJobStatus: (id: string, status: "applied" | "rejected" | "saved") => void;
}

export const useJobStore = create<JobStore>()(
  persist(
    (set, get) => ({
      filters: DEFAULT_FILTERS,
      setFilters: (partial) =>
        set((s) => ({ filters: { ...s.filters, ...partial } })),
      resetFilters: () => set({ filters: DEFAULT_FILTERS }),

      viewedIds: new Set(),
      lastSeenId: null,
      markViewed: (id) => {
        set((s) => ({
          viewedIds: new Set([...s.viewedIds, id]),
          lastSeenId: id,
        }));
      },
      hideViewed: false,
      toggleHideViewed: () => set((s) => ({ hideViewed: !s.hideViewed })),

      savedJobs: [],
      saveJob: (job) => {
        if (get().savedJobs.find((j) => j.id === job.id)) return;
        set((s) => ({
          savedJobs: [
            { ...job, status: "saved", savedAt: Date.now() },
            ...s.savedJobs,
          ],
        }));
      },
      unsaveJob: (id) =>
        set((s) => ({ savedJobs: s.savedJobs.filter((j) => j.id !== id) })),
      setJobStatus: (id, status) =>
        set((s) => ({
          savedJobs: s.savedJobs.map((j) =>
            j.id === id ? { ...j, status } : j
          ),
        })),
    }),
    {
      name: "allgonggo-store",
      partialize: (s) => ({
        filters: s.filters,
        viewedIds: [...s.viewedIds],
        hideViewed: s.hideViewed,
        savedJobs: s.savedJobs,
        lastSeenId: s.lastSeenId,
      }),
      merge: (persisted: any, current) => ({
        ...current,
        ...persisted,
        viewedIds: new Set(persisted?.viewedIds ?? []),
      }),
    }
  )
);
