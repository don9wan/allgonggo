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
  linkareer: "링커리어",
  jasoseol: "자소설닷컴",
  catch: "캐치",
  groupby: "그룹바이",
};

const SOURCE_FAVICONS: Record<string, string> = {
  wanted: "https://www.wanted.co.kr/favicon.ico",
  linkareer: "https://linkareer.com/favicon.ico",
  jasoseol: "https://jasoseol.com/favicon.ico",
  catch: "https://www.catch.co.kr/favicon.ico",
  groupby: "https://groupby.kr/favicon.ico",
};

export function JobCard({ job, status, onSave, isLastSeen }: Props) {
  const markViewed = useJobStore((s) => s.markViewed);
  const hideJob = useJobStore((s) => s.hideJob);
  const [exiting, setExiting] = useState(false);

  const isViewed = status === "viewed" || status === "last_seen";
  const isSmall = isViewed;

  const borderColor = (() => {
    if (isLastSeen) return "var(--color-state-last-seen)";
    if (status === "viewed") return "var(--color-state-viewed)";
    return "var(--color-border)";
  })();

  const handleCardClick = () => {
    if (job.sources.length === 0) return;
    window.open(job.sources[0].url, "_blank", "noopener,noreferrer");
    markViewed(job.id);
  };

  const handleSourceClick = (e: React.MouseEvent, url: string) => {
    e.stopPropagation();
    window.open(url, "_blank", "noopener,noreferrer");
    markViewed(job.id);
  };

  const handleSave = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!onSave) return;
    setExiting(true);
    setTimeout(() => onSave(job), 300);
  };

  const handleHide = (e: React.MouseEvent) => {
    e.stopPropagation();
    setExiting(true);
    setTimeout(() => hideJob(job), 300);
  };

  return (
    <div
      className={`job-card${isSmall ? " job-card--small" : ""}${exiting ? " job-card--exit" : ""}`}
      style={{ borderColor }}
      data-id={job.id}
      onClick={handleCardClick}
    >
      <div className="job-card__header">
        <p className="job-card__company">{job.company}</p>
        <h3 className="job-card__title">{job.title}</h3>
      </div>

      {!isSmall && (
        <div className="job-card__meta">
          {job.location && <span>{job.location}</span>}
          {job.experience && <span>{job.experience}</span>}
          {job.employment_type && <span>{job.employment_type}</span>}
        </div>
      )}

      <div className="job-card__footer">
        <div className="job-card__footer-left">
          <div className="job-card__sources">
            {job.sources.map((src) => (
              <button
                key={src.id}
                className="job-card__source-btn"
                onClick={(e) => handleSourceClick(e, src.url)}
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
        <div className="job-card__actions">
          {onSave && (
            <button className="job-card__save-btn" onClick={handleSave} title="저장">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
              </svg>
            </button>
          )}
          <button className="job-card__hide-btn" onClick={handleHide} title="안 보기">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
              <path d="M10 11v6M14 11v6" />
              <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
