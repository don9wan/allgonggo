import { useState, useCallback } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Navbar } from "./components/Navbar";
import { FilterBar } from "./components/FilterBar";
import { FeedPage } from "./pages/FeedPage";
import { SavedPanel } from "./components/SavedPanel";
import { useJobStore } from "./store/jobStore";
import type { SavedJob } from "./types/job";
import "./components/JobCard.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 2,
      retry: 1,
    },
  },
});

function AppInner() {
  const { filters, setFilters, unsaveJob } = useJobStore();
  const [showSaved, setShowSaved] = useState(false);
  const [returnedJob, setReturnedJob] = useState<SavedJob | null>(null);

  const handleReturnToFeed = useCallback((job: SavedJob) => {
    unsaveJob(job.id);
    setReturnedJob(job);
    setShowSaved(false);
  }, [unsaveJob]);

  return (
    <>
      <Navbar
        onOpenSaved={() => setShowSaved(true)}
        searchValue={filters.q}
        onSearchChange={(v) => setFilters({ q: v })}
      />
      <FilterBar />
      <FeedPage
        returnedJob={returnedJob}
        onClearReturned={() => setReturnedJob(null)}
      />
      {showSaved && (
        <SavedPanel
          onClose={() => setShowSaved(false)}
          onReturnToFeed={handleReturnToFeed}
        />
      )}
    </>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppInner />
    </QueryClientProvider>
  );
}
