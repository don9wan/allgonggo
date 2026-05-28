import { useEffect, useMemo, useRef, useState } from "react";
import { useJobStore } from "../store/jobStore";
import logoSrc from "../assets/logo.svg";
import { trackSearchPerformed } from "../lib/analytics";
import "./Navbar.css";

const PLACEHOLDER_KEYWORDS = [
  '프론트엔드 개발자', '백엔드 개발자', '마케터', 'iOS 개발자',
  '안드로이드 개발자', '데이터 분석가', 'UX 디자이너', '서비스 기획자',
  '퍼포먼스 마케터', 'ML 엔지니어', '인사 담당자', '콘텐츠 마케터',
  '풀스택 개발자', 'DevOps 엔지니어', '브랜드 디자이너', 'PM',
  '재무·회계', '영업 담당자', '데이터 엔지니어', '전략 기획',
  'UI 디자이너', '사업 개발', '법무 담당자', '채용 담당자',
  '영상 편집자', 'CS 담당자', '투자 심사역', '에디터',
  '그로스 해커', 'QA 엔지니어', 'MD', '리서처',
  '공급망 관리', 'IR 담당자', '경영 기획', '광고 기획자',
  '파이썬 개발자', 'Java 개발자', '임베디드 개발자', 'DBA',
];

const CYCLE_MS = 1500;

function useCyclingPlaceholder(keywords: string[]) {
  const shuffled = useMemo(() => {
    const arr = [...keywords];
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const [index, setIndex] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setIndex((i) => (i + 1) % shuffled.length), CYCLE_MS);
    return () => clearInterval(t);
  }, [shuffled]);

  return shuffled[index];
}

interface Props {
  onOpenSaved: () => void;
  onOpenHidden: () => void;
  searchValue: string;
  onSearchChange: (v: string) => void;
}

export function Navbar({ onOpenSaved, onOpenHidden, searchValue, onSearchChange }: Props) {
  const { savedJobs } = useJobStore();
  const cyclingPlaceholder = useCyclingPlaceholder(PLACEHOLDER_KEYWORDS);
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
    debounceRef.current = setTimeout(() => {
      onSearchChange(v);
      if (v.trim().length > 0) trackSearchPerformed(v.trim());
    }, 300);
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
          <button className="navbar__logo" onClick={() => window.location.reload()}>
            <img className="navbar__logo-icon" src={logoSrc} alt="올공고 로고" width="18" height="18" />
            <span className="navbar__logo-text">올공고</span>
          </button>
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
              placeholder=""
              value={inputValue}
              onChange={handleChange}
            />
            {!inputValue && (
              <span key={cyclingPlaceholder} className="navbar__search-placeholder">
                {cyclingPlaceholder}
              </span>
            )}
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
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
            </svg>
            {newSaved > 0 && (
              <span className="navbar__badge">
                {newSaved > 99 ? "99+" : newSaved}
              </span>
            )}
          </button>
          <button
            className="navbar__hidden-btn"
            onClick={onOpenHidden}
            title="안 보는 공고"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
              <path d="M10 11v6M14 11v6" />
              <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
            </svg>
          </button>
        </div>
      </div>
    </nav>
  );
}
