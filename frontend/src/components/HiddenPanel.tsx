import { useJobStore } from "../store/jobStore";
import "./HiddenPanel.css";

interface Props {
  onClose: () => void;
}

export function HiddenPanel({ onClose }: Props) {
  const { hiddenJobs, unhideJob } = useJobStore();

  return (
    <div className="hidden-overlay" onClick={onClose}>
      <div className="hidden-panel" onClick={(e) => e.stopPropagation()}>
        <div className="hidden-panel__header">
          <h2 className="hidden-panel__title">안 보는 공고 {hiddenJobs.length > 0 && `(${hiddenJobs.length})`}</h2>
          <button className="hidden-panel__close" onClick={onClose} title="닫기">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="hidden-panel__body">
          {hiddenJobs.length === 0 ? (
            <div className="hidden-panel__empty">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                <path d="M10 11v6M14 11v6" />
              </svg>
              <p>숨긴 공고가 없습니다</p>
              <span>공고 카드의 휴지통 버튼으로 숨길 수 있어요</span>
            </div>
          ) : (
            <div className="hidden-panel__list">
              {hiddenJobs.map((job) => (
                <div key={job.id} className="hidden-card">
                  <div className="hidden-card__info">
                    <p className="hidden-card__company">{job.company}</p>
                    <p className="hidden-card__title">{job.title}</p>
                  </div>
                  <button
                    className="hidden-card__restore"
                    onClick={() => unhideJob(job.id)}
                  >
                    복원
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
