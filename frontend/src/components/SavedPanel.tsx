import type { SavedJob } from "../types/job";
import { useJobStore } from "../store/jobStore";
import "./SavedPanel.css";

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

interface SavedCardProps {
  job: SavedJob;
  onReturn: (job: SavedJob) => void;
}

function SavedCard({ job, onReturn }: SavedCardProps) {
  const { setJobStatus } = useJobStore();

  const borderColor =
    job.status === "applied"
      ? "var(--color-state-applied)"
      : job.status === "rejected"
      ? "var(--color-state-rejected)"
      : "var(--color-border)";

  const toggleStatus = (status: "applied" | "rejected") => {
    if (job.status === status) {
      setJobStatus(job.id, "saved");
    } else {
      setJobStatus(job.id, status);
    }
  };

  return (
    <div className="saved-card" style={{ borderColor }}>
      <div className="saved-card__header">
        <div>
          <p className="saved-card__company">{job.company}</p>
          <h3 className="saved-card__title">{job.title}</h3>
        </div>
        <div className="saved-card__sources">
          {job.sources.map((src) => (
            <a
              key={src.id}
              href={src.url}
              target="_blank"
              rel="noopener noreferrer"
              className="saved-card__source-link"
              title={SOURCE_LABELS[src.source] || src.source}
            >
              <img
                src={SOURCE_FAVICONS[src.source] || ""}
                alt={SOURCE_LABELS[src.source] || src.source}
                width={24}
                height={24}
                onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
              />
            </a>
          ))}
        </div>
      </div>

      <div className="saved-card__meta">
        {job.location && <span>{job.location}</span>}
        {job.experience && <span>{job.experience}</span>}
        {job.employment_type && <span>{job.employment_type}</span>}
      </div>

      <div className="saved-card__actions">
        <button
          className={`saved-card__btn saved-card__btn--applied${job.status === "applied" ? " active" : ""}`}
          onClick={() => toggleStatus("applied")}
        >
          지원완료
        </button>
        <button
          className={`saved-card__btn saved-card__btn--rejected${job.status === "rejected" ? " active" : ""}`}
          onClick={() => toggleStatus("rejected")}
        >
          불합격
        </button>
        <button
          className="saved-card__btn saved-card__btn--return"
          onClick={() => onReturn(job)}
        >
          저장 취소
        </button>
      </div>
    </div>
  );
}

interface Props {
  onClose: () => void;
  onReturnToFeed: (job: SavedJob) => void;
}

export function SavedPanel({ onClose, onReturnToFeed }: Props) {
  const { savedJobs } = useJobStore();

  return (
    <div className="saved-overlay" onClick={onClose}>
      <div className="saved-panel" onClick={(e) => e.stopPropagation()}>
        <div className="saved-panel__header">
          <h2 className="saved-panel__title">저장함 {savedJobs.length > 0 && `(${savedJobs.length})`}</h2>
          <button className="saved-panel__close" onClick={onClose} title="닫기">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="saved-panel__body">
          {savedJobs.length === 0 ? (
            <div className="saved-panel__empty">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
              </svg>
              <p>저장된 공고가 없습니다</p>
              <span>관심 있는 공고의 저장 버튼을 눌러보세요</span>
            </div>
          ) : (
            <div className="saved-panel__list">
              {savedJobs.map((job) => (
                <SavedCard key={job.id} job={job} onReturn={onReturnToFeed} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
