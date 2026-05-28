import { useCallback, useEffect, useMemo, useRef } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { fetchJobs } from "../api/jobs";
import { JobCard, JobCardSkeleton } from "../components/JobCard";
import { useJobStore } from "../store/jobStore";
import type { Job, CardStatus, SavedJob } from "../types/job";
import { trackFeedNextPage } from "../lib/analytics";
import "./FeedPage.css";

interface Props {
  returnedJob: SavedJob | null;
  onClearReturned: () => void;
}

export function FeedPage({ returnedJob, onClearReturned }: Props) {
  const { filters, viewedIds, lastSeenId, hideViewed, savedJobs, saveJob, hiddenJobs, resetFilters, toggleHideViewed } = useJobStore();
  const savedIds = new Set(savedJobs.map((j) => j.id));
  const hiddenIds = new Set(hiddenJobs.map((j) => j.id));

  const loaderRef = useRef<HTMLDivElement>(null);

  const { data, isFetching, isFetchingNextPage, fetchNextPage, hasNextPage, isError } =
    useInfiniteQuery({
      queryKey: ["jobs", filters],
      queryFn: ({ pageParam }) => fetchJobs(filters, pageParam as number, 20),
      initialPageParam: 1,
      getNextPageParam: (lastPage) =>
        lastPage.has_next ? lastPage.page + 1 : undefined,
      retry: 2,
      retryDelay: 1500,
    });

  const allJobs: Job[] = data?.pages.flatMap((p) => p.jobs) ?? [];
  const total = data?.pages[0]?.total ?? null;
  const isInitialLoading = isFetching && allJobs.length === 0;

  const handleLoadMore = useCallback(() => {
    const nextPageNum = (data?.pages.length ?? 0) + 1;
    trackFeedNextPage(nextPageNum);
    fetchNextPage();
  }, [data?.pages.length, fetchNextPage]);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
          handleLoadMore();
        }
      },
      { threshold: 0.1 }
    );
    if (loaderRef.current) observer.observe(loaderRef.current);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, handleLoadMore]);

  const displayJobs = useMemo(() => {
    let jobs = allJobs.filter((j) => !savedIds.has(j.id) && !hiddenIds.has(j.id));

    if (returnedJob) {
      const alreadyIn = jobs.find((j) => j.id === returnedJob.id);
      if (!alreadyIn) {
        jobs = [returnedJob, ...jobs];
      }
    }

    if (hideViewed) {
      jobs = jobs.filter((j) => !viewedIds.has(j.id) || j.id === returnedJob?.id);
    }

    return jobs;
  }, [allJobs, savedIds, returnedJob, hideViewed, viewedIds]);

  const getStatus = (job: Job): CardStatus => {
    if (savedIds.has(job.id)) return "saved";
    if (job.id === lastSeenId) return "last_seen";
    if (viewedIds.has(job.id)) return "viewed";
    return "unread";
  };

  const handleSave = (job: Job) => {
    saveJob(job);
    if (returnedJob?.id === job.id) onClearReturned();
  };

  const hasActiveFilters =
    !!filters.q ||
    filters.location.length > 0 ||
    filters.experience.length > 0 ||
    filters.employment_type.length > 0 ||
    filters.source.length > 0 ||
    hideViewed;

  const handleResetAll = () => {
    resetFilters();
    if (hideViewed) toggleHideViewed();
  };

  return (
    <main className="feed-page">
      <div className="feed-page__inner">
        {total !== null && (
          <p className="feed-page__count">
            {filters.q ? (
              <><span className="feed-page__count-query">'{filters.q}'</span> 결과 {total.toLocaleString()}건</>
            ) : (
              `최근 4주 내 올라온 공고 ${total.toLocaleString()}건`
            )}
          </p>
        )}

        {isError && (
          <div className="feed-page__empty">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 8v4m0 4h.01" />
            </svg>
            <p>서버에 연결할 수 없습니다</p>
            <span>잠시 후 다시 시도해주세요</span>
          </div>
        )}

        {isInitialLoading ? (
          <div className="feed-page__list">
            {Array.from({ length: 5 }).map((_, i) => (
              <JobCardSkeleton key={i} />
            ))}
          </div>
        ) : (
          <div className="feed-page__list">
            {!isError && displayJobs.length === 0 && !isFetching && (
              <div className="feed-page__empty">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.35-4.35" />
                </svg>
                <p>공고를 찾을 수 없습니다</p>
                <span>검색어나 필터를 조정해보세요</span>
                {hasActiveFilters && (
                  <button className="feed-page__reset-btn" onClick={handleResetAll}>
                    필터 초기화
                  </button>
                )}
              </div>
            )}
            {displayJobs.map((job, i) => {
              const status = getStatus(job);
              return (
                <JobCard
                  key={job.id}
                  job={job}
                  status={status}
                  isLastSeen={job.id === lastSeenId}
                  onSave={handleSave}
                  index={i}
                />
              );
            })}
          </div>
        )}

        {isFetchingNextPage && (
          <div className="feed-page__spinner">
            <div className="spinner" />
          </div>
        )}

        <div ref={loaderRef} style={{ height: 1 }} />
      </div>
    </main>
  );
}
