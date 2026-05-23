import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useJobStore } from "../store/jobStore";
import "./FilterBar.css";

const FILTER_CONFIGS = [
  {
    key: "location" as const,
    label: "근무지역",
    options: [
      "서울", "경기", "인천", "부산", "대구", "대전",
      "광주", "울산", "세종", "강원", "충북", "충남",
      "전북", "전남", "경북", "경남", "제주", "재택/원격",
    ].map((l) => ({ value: l, label: l })),
    wide: true,
  },
  {
    key: "experience" as const,
    label: "경력",
    options: ["신입", "인턴", "경력무관"].map((e) => ({ value: e, label: e })),
    wide: false,
  },
  {
    key: "employment_type" as const,
    label: "고용형태",
    options: ["정규직", "계약직", "인턴"].map((t) => ({ value: t, label: t })),
    wide: false,
  },
  {
    key: "source" as const,
    label: "출처",
    options: [
      { value: "wanted", label: "원티드" },
      { value: "jumpit", label: "점핏" },
      { value: "catch", label: "캐치" },
      { value: "groupby", label: "그룹바이" },
    ],
    wide: false,
  },
];

type FilterKey = (typeof FILTER_CONFIGS)[number]["key"];

function FilterDropdown({
  label,
  options,
  selected,
  onChange,
  isOpen,
  onToggle,
  wide,
}: {
  label: string;
  options: { value: string; label: string }[];
  selected: string[];
  onChange: (v: string[]) => void;
  isOpen: boolean;
  onToggle: () => void;
  wide: boolean;
}) {
  const btnRef = useRef<HTMLButtonElement>(null);
  const [panelPos, setPanelPos] = useState<{ top: number; left: number } | null>(null);

  // 데스크탑에서만 버튼 위치 계산 (모바일은 CSS로 bottom sheet 처리)
  useEffect(() => {
    if (isOpen && btnRef.current && window.innerWidth > 767) {
      const rect = btnRef.current.getBoundingClientRect();
      setPanelPos({ top: rect.bottom + 8, left: rect.left });
    } else {
      setPanelPos(null);
    }
  }, [isOpen]);

  const toggle = (val: string) => {
    if (selected.includes(val)) {
      onChange(selected.filter((v) => v !== val));
    } else {
      onChange([...selected, val]);
    }
  };

  const hasSelection = selected.length > 0;

  return (
    <div className={`filter-dropdown${isOpen ? " filter-dropdown--open" : ""}`}>
      <button
        ref={btnRef}
        className={`filter-btn${hasSelection ? " filter-btn--active" : ""}`}
        onClick={onToggle}
      >
        <span className="filter-btn__label">{label}</span>
        {hasSelection && (
          <span className="filter-btn__count">{selected.length}</span>
        )}
        <svg
          className={`filter-btn__chevron${isOpen ? " filter-btn__chevron--up" : ""}`}
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {isOpen && createPortal(
        <>
          <div className="filter-overlay" onClick={onToggle} />
          <div
            className={`filter-panel${wide ? " filter-panel--wide" : ""}`}
            style={
              panelPos
                ? { top: panelPos.top, left: panelPos.left }
                : undefined
            }
          >
            <div className="filter-panel__header">
              <span className="filter-panel__title">{label}</span>
              {hasSelection && (
                <button
                  className="filter-panel__clear"
                  onClick={() => onChange([])}
                >
                  선택 해제
                </button>
              )}
            </div>
            <div
              className={`filter-panel__options${wide ? " filter-panel__options--grid" : ""}`}
            >
              {options.map((opt) => {
                const active = selected.includes(opt.value);
                return (
                  <button
                    key={opt.value}
                    className={`filter-option${active ? " filter-option--active" : ""}`}
                    onClick={() => toggle(opt.value)}
                  >
                    <span className="filter-option__check">
                      {active && (
                        <svg
                          width="11"
                          height="11"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="3"
                        >
                          <path d="M20 6 9 17l-5-5" />
                        </svg>
                      )}
                    </span>
                    <span>{opt.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </>,
        document.body
      )}
    </div>
  );
}

export function FilterBar() {
  const { filters, setFilters, resetFilters, hideViewed, toggleHideViewed } = useJobStore();
  const [openKey, setOpenKey] = useState<FilterKey | null>(null);
  const barRef = useRef<HTMLDivElement>(null);

  const hasFilters =
    filters.location.length > 0 ||
    filters.experience.length > 0 ||
    filters.employment_type.length > 0 ||
    filters.source.length > 0 ||
    hideViewed;

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const target = e.target as Element;
      // 포털로 렌더링된 패널 내부 클릭은 무시 (옵션 선택 시 닫히지 않도록)
      if (target.closest(".filter-panel")) return;
      if (barRef.current && !barRef.current.contains(target)) {
        setOpenKey(null);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenKey(null);
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, []);

  const getSelected = (key: FilterKey): string[] => filters[key];

  return (
    <div className="filter-bar" ref={barRef}>
      <div className="filter-bar__inner">
        <button
          className={`filter-btn filter-btn--toggle${hideViewed ? " filter-btn--active" : ""}`}
          onClick={toggleHideViewed}
          title={hideViewed ? "확인한 공고 숨기는 중" : "확인한 공고 보이는 중"}
        >
          {hideViewed ? (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
              <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
              <path d="M10.73 10.73A3 3 0 0 0 14.83 14"/>
              <line x1="1" y1="1" x2="23" y2="23"/>
            </svg>
          ) : (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
              <circle cx="12" cy="12" r="3"/>
            </svg>
          )}
        </button>
        {FILTER_CONFIGS.map((config) => (
          <FilterDropdown
            key={config.key}
            label={config.label}
            options={config.options}
            selected={getSelected(config.key)}
            onChange={(v) => setFilters({ [config.key]: v })}
            isOpen={openKey === config.key}
            onToggle={() =>
              setOpenKey((prev) => (prev === config.key ? null : config.key))
            }
            wide={config.wide}
          />
        ))}
        {hasFilters && (
          <button
            className="filter-reset-btn"
            onClick={() => {
              resetFilters();
              if (hideViewed) toggleHideViewed();
              setOpenKey(null);
            }}
          >
            초기화
          </button>
        )}
      </div>
    </div>
  );
}
