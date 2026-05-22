import { useEffect, useRef, useState } from "react";
import { useJobStore } from "../store/jobStore";
import "./Navbar.css";

interface Props {
  onOpenSaved: () => void;
  searchValue: string;
  onSearchChange: (v: string) => void;
}

export function Navbar({ onOpenSaved, searchValue, onSearchChange }: Props) {
  const { savedJobs, hideViewed, toggleHideViewed } = useJobStore();
  const [inputValue, setInputValue] = useState(searchValue);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // 외부(필터 초기화 등)에서 searchValue 변경 시 동기화
  useEffect(() => {
    setInputValue(searchValue);
  }, [searchValue]);

  useEffect(() => {
    return () => clearTimeout(debounceRef.current);
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value;
    setInputValue(v);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => onSearchChange(v), 300);
  };

  const handleClear = () => {
    setInputValue("");
    clearTimeout(debounceRef.current);
    onSearchChange("");
  };

  const newSaved = savedJobs.filter((j) => j.status === "saved").length;

  return (
    <nav className="navbar">
      <div className="navbar__inner">
        <div className="navbar__left">
          <span className="navbar__logo">올공고</span>
          <label className="navbar__toggle" title="이미 확인한 공고 보지 않기">
            <span className="navbar__toggle-label">확인한 공고 숨기기</span>
            <div
              className={`toggle-switch${hideViewed ? " toggle-switch--on" : ""}`}
              onClick={toggleHideViewed}
            >
              <div className="toggle-switch__knob" />
            </div>
          </label>
        </div>

        <div className="navbar__center">
          <div className="navbar__search">
            <svg
              className="navbar__search-icon"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
            <input
              type="text"
              className="navbar__search-input"
              placeholder="직무명, 회사명, 기술스택"
              value={inputValue}
              onChange={handleChange}
            />
            {inputValue && (
              <button
                className="navbar__search-clear"
                onClick={handleClear}
                aria-label="검색어 지우기"
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                >
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
        </div>

        <div className="navbar__right">
          <button
            className="navbar__saved-btn"
            onClick={onOpenSaved}
            title="저장함"
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
            </svg>
            {newSaved > 0 && (
              <span className="navbar__badge">
                {newSaved > 99 ? "99+" : newSaved}
              </span>
            )}
          </button>
        </div>
      </div>
    </nav>
  );
}
