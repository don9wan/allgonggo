import { useJobStore } from "../store/jobStore";
import "./FilterBar.css";

const LOCATIONS = ["서울", "경기", "인천", "부산", "대구", "대전", "광주", "울산", "세종", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주", "재택/원격"];
const EXPERIENCES = ["신입", "인턴", "경력무관", "1년 이상", "2년 이상", "3년 이상"];
const EMPLOYMENT_TYPES = ["정규직", "계약직", "인턴"];
const SOURCES = [
  { value: "wanted", label: "원티드" },
  { value: "jumpit", label: "점핏" },
  { value: "programmers", label: "프로그래머스" },
  { value: "catch", label: "캐치" },
  { value: "groupby", label: "그룹바이" },
];

function MultiSelect({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: { value: string; label: string }[];
  selected: string[];
  onChange: (v: string[]) => void;
}) {
  const toggle = (val: string) => {
    if (selected.includes(val)) {
      onChange(selected.filter((v) => v !== val));
    } else {
      onChange([...selected, val]);
    }
  };

  return (
    <div className="filter-group">
      <span className="filter-group__label">{label}</span>
      <div className="filter-group__chips">
        {options.map((opt) => (
          <button
            key={opt.value}
            className={`filter-chip${selected.includes(opt.value) ? " filter-chip--active" : ""}`}
            onClick={() => toggle(opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function FilterBar() {
  const { filters, setFilters, resetFilters } = useJobStore();
  const hasFilters =
    filters.location.length > 0 ||
    filters.experience.length > 0 ||
    filters.employment_type.length > 0 ||
    filters.source.length > 0;

  return (
    <div className="filter-bar">
      <div className="filter-bar__inner">
        <MultiSelect
          label="근무지역"
          options={LOCATIONS.map((l) => ({ value: l, label: l }))}
          selected={filters.location}
          onChange={(v) => setFilters({ location: v })}
        />
        <MultiSelect
          label="경력"
          options={EXPERIENCES.map((e) => ({ value: e, label: e }))}
          selected={filters.experience}
          onChange={(v) => setFilters({ experience: v })}
        />
        <MultiSelect
          label="고용형태"
          options={EMPLOYMENT_TYPES.map((t) => ({ value: t, label: t }))}
          selected={filters.employment_type}
          onChange={(v) => setFilters({ employment_type: v })}
        />
        <MultiSelect
          label="출처"
          options={SOURCES}
          selected={filters.source}
          onChange={(v) => setFilters({ source: v })}
        />
        {hasFilters && (
          <button className="filter-reset-btn" onClick={resetFilters}>
            필터 초기화
          </button>
        )}
      </div>
    </div>
  );
}
