import { useState, useCallback, useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Navbar } from "./components/Navbar";
import { FilterBar } from "./components/FilterBar";
import { FeedPage } from "./pages/FeedPage";
import { AdminPage } from "./pages/AdminPage";
import { SavedPanel } from "./components/SavedPanel";
import { HiddenPanel } from "./components/HiddenPanel";
import { useJobStore } from "./store/jobStore";
import type { SavedJob } from "./types/job";
import "./components/JobCard.css";
import "./App.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 2,
      retry: 1,
    },
  },
});

function useHash() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onHash = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return hash;
}

function ScrollToTopButton() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > 400);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <button
      className={`scroll-top-btn${visible ? " scroll-top-btn--visible" : ""}`}
      onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
      aria-label="맨 위로"
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M18 15l-6-6-6 6" />
      </svg>
    </button>
  );
}

function AppInner() {
  const { filters, setFilters, unsaveJob } = useJobStore();
  const [showSaved, setShowSaved] = useState(false);
  const [showHidden, setShowHidden] = useState(false);
  const [returnedJob, setReturnedJob] = useState<SavedJob | null>(null);
  const hash = useHash();

  const handleReturnToFeed = useCallback((job: SavedJob) => {
    unsaveJob(job.id);
    setReturnedJob(job);
    setShowSaved(false);
  }, [unsaveJob]);

  if (hash === "#admin") {
    return <AdminPage />;
  }

  return (
    <>
      <div className="app-header">
        <Navbar
          onOpenSaved={() => setShowSaved(true)}
          onOpenHidden={() => setShowHidden(true)}
          searchValue={filters.q}
          onSearchChange={(v) => setFilters({ q: v })}
        />
        <FilterBar />
      </div>
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
      {showHidden && (
        <HiddenPanel onClose={() => setShowHidden(false)} />
      )}
      <ScrollToTopButton />
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
