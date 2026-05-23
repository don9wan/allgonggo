import { useState } from "react";
import type { Job, CardStatus } from "../types/job";
import { useJobStore } from "../store/jobStore";

export function JobCardSkeleton() {
  return (
    <div className="skeleton-card">
      <div className="skeleton-line skeleton-card__company" />
      <div className="skeleton-line skeleton-card__title" />
      <div className="skeleton-line skeleton-card__title-sm" />
      <div className="skeleton-line skeleton-card__meta" />
      <div className="skeleton-line skeleton-card__icon" />
    </div>
  );
}

interface Props {
  job: Job;
  status: CardStatus;
  onSave?: (job: Job) => void;
  isLastSeen: boolean;
}

const SOURCE_LABELS: Record<string, string> = {
  wanted: "원티드",
  jumpit: "점핏",
  programmers: "프로그래머스",
  catch: "캐치",
  groupby: "그룹바이",
};

const SOURCE_FAVICONS: Record<string, string> = {
  wanted: "https://www.wanted.co.kr/favicon.ico",
  jumpit: "https://jumpit.saramin.co.kr/favicon.ico",
  programmers: "https://programmers.co.kr/favicon.ico",
  catch: "https://www.catch.co.kr/favicon.ico",
  groupby: "https://www.groupby.kr/favicon.ico",
};

export function JobCard({ job, status, onSave, isLastSeen }: Props) {
  const markViewed = useJobStore((s) => s.markViewed);
  const [exiting, setExiting] = useState(false);

  const isViewed = status === "viewed" || status === "last_seen";
  const isSmall = isViewed;

  const borderColor = (() => {
    if (isLastSeen) return "var(--color-state-last-seen)";
    if (status === "viewed") return "var(--color-state-viewed)";
    return "var(--color-border)";
  })();

  const handleSourceClick = (url: string) => {
    window.open(url, "_blank", "noopener,noreferrer");
    markViewed(job.id);
  };

  const handleSave = () => {
    if (!onSave) return;
    setExiting(true);
    setTimeout(() => onSave(job), 300);
  };

  return (
    <div
      className={`job-card${isSmall ? " job-card--small" : ""}${exiting ? " job-card--exit" : ""}`}
      style={{ borderColor }}
      data-id={job.id}
    >
      <div className="job-card__header">
        <div>
          <p className="job-card__company">{job.company}</p>
          <h3 className="job-card__title">{job.title}</h3>
        </div>
        {!isSmall && onSave && (
          <button className="job-card__save-btn" onClick={handleSave} title="저장">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
            </svg>
          </button>
        )}
      </div>

      {!isSmall && (
        <div className="job-card__meta">
          {job.location && <span>{job.location}</span>}
          {job.experience && <span>{job.experience}</span>}
          {job.employment_type && <span>{job.employment_type}</span>}
        </div>
      )}

      <div className="job-card__footer">
        <div className="job-card__sources">
          {job.sources.map((src) => (
            <button
              key={src.id}
              className="job-card__source-btn"
              onClick={() => handleSourceClick(src.url)}
              title={SOURCE_LABELS[src.source] || src.source}
            >
              <img
                src={SOURCE_FAVICONS[src.source] || ""}
                alt={SOURCE_LABELS[src.source] || src.source}
                width={24}
                height={24}
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = "none";
                }}
              />
              {isSmall && <span className="job-card__source-label">{SOURCE_LABELS[src.source]}</span>}
            </button>
          ))}
        </div>
        {isLastSeen && (
          <span className="job-card__tag job-card__tag--last-seen">마지막으로 확인</span>
        )}
        {status === "viewed" && !isLastSeen && (
          <span className="job-card__tag job-card__tag--viewed">확인함</span>
        )}
      </div>
    </div>
  );
}
