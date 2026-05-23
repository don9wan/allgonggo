import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchJobs } from "../api/jobs";
import { JobCard, JobCardSkeleton } from "../components/JobCard";
import { useJobStore } from "../store/jobStore";
import type { Job, CardStatus, SavedJob } from "../types/job";
import "./FeedPage.css";

interface Props {
  returnedJob: SavedJob | null;
  onClearReturned: () => void;
}

export function FeedPage({ returnedJob, onClearReturned }: Props) {
  const { filters, viewedIds, lastSeenId, hideViewed, savedJobs, saveJob } = useJobStore();
  const savedIds = new Set(savedJobs.map((j) => j.id));

  const [page, setPage] = useState(1);
  const [allJobs, setAllJobs] = useState<Job[]>([]);
  const loaderRef = useRef<HTMLDivElement>(null);

  const { data, isFetching, isError } = useQuery({
    queryKey: ["jobs", filters, page],
    queryFn: () => fetchJobs(filters, page, 20),
    placeholderData: (prev) => prev,
    retry: 2,
    retryDelay: 1500,
  });

  useEffect(() => {
    setPage(1);
    setAllJobs([]);
  }, [filters]);

  useEffect(() => {
    if (data?.jobs) {
      if (page === 1) {
        setAllJobs(data.jobs);
      } else {
        setAllJobs((prev) => {
          const existingIds = new Set(prev.map((j) => j.id));
          const newJobs = data.jobs.filter((j) => !existingIds.has(j.id));
          return [...prev, ...newJobs];
        });
      }
    }
  }, [data, page]);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && data?.has_next && !isFetching) {
          setPage((p) => p + 1);
        }
      },
      { threshold: 0.1 }
    );
    if (loaderRef.current) observer.observe(loaderRef.current);
    return () => observer.disconnect();
  }, [data?.has_next, isFetching]);

  const displayJobs = useMemo(() => {
    let jobs = allJobs.filter((j) => !savedIds.has(j.id));

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

  return (
    <main className="feed-page">
      <div className="feed-page__inner">
        {data?.total !== undefined && (
          <p className="feed-page__count">최근 2주 내 올라온 공고 {data.total.toLocaleString()}건</p>
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

        {!isError && displayJobs.length === 0 && !isFetching && (
          <div className="feed-page__empty">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
            <p>공고를 찾을 수 없습니다</p>
            <span>검색어나 필터를 조정해보세요</span>
          </div>
        )}

        {isFetching && allJobs.length === 0 ? (
          <div className="feed-page__list">
            {Array.from({ length: 5 }).map((_, i) => (
              <JobCardSkeleton key={i} />
            ))}
          </div>
        ) : (
          <div className="feed-page__list">
            {displayJobs.map((job) => {
              const status = getStatus(job);
              return (
                <JobCard
                  key={job.id}
                  job={job}
                  status={status}
                  isLastSeen={job.id === lastSeenId}
                  onSave={handleSave}
                />
              );
            })}
          </div>
        )}

        {isFetching && allJobs.length > 0 && (
          <div className="feed-page__spinner">
            <div className="spinner" />
          </div>
        )}

        <div ref={loaderRef} style={{ height: 1 }} />
      </div>
    </main>
  );
}
