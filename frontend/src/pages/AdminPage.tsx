import { useState, useEffect, useCallback } from "react";
import { getStatus, triggerCrawl, triggerWanted, triggerJumpit, triggerCatch, triggerGroupby, getRecentJobs, debugWanted } from "../api/admin";
import "./AdminPage.css";

type Status = {
  db: { jobs: number; job_sources: number };
  crawlers: Record<string, { active: boolean; note: string }>;
};

type Job = {
  id: string;
  title: string;
  company: string;
  source: string;
  experience: string;
  employment_type: string;
  location: string;
  url: string;
};

export function AdminPage() {
  const [key, setKey] = useState(() => localStorage.getItem("admin_key") || "");
  const [keyInput, setKeyInput] = useState(key);
  const [status, setStatus] = useState<Status | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(false);
  const [crawling, setCrawling] = useState(false);
  const [debugResult, setDebugResult] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [lastCrawl, setLastCrawl] = useState<string | null>(null);

  const load = useCallback(async (adminKey: string) => {
    if (!adminKey) return;
    setLoading(true);
    setError("");
    try {
      const [s, j] = await Promise.all([
        getStatus(adminKey),
        getRecentJobs(adminKey, 50),
      ]);
      setStatus(s);
      setJobs(j);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(`로드 실패: ${msg}`);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleKeySubmit = () => {
    localStorage.setItem("admin_key", keyInput);
    setKey(keyInput);
    load(keyInput);
  };

  useEffect(() => {
    if (key) load(key);
  }, [key, load]);

  const handleCrawlAll = async () => {
    setCrawling(true);
    setError("");
    try {
      await triggerCrawl(key);
      setLastCrawl(new Date().toLocaleTimeString("ko-KR"));
      setTimeout(() => load(key), 3000);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(`크롤링 실패: ${msg}`);
    } finally {
      setCrawling(false);
    }
  };

  const handleCrawlWanted = async () => {
    setCrawling(true);
    setError("");
    try {
      const result = await triggerWanted(key);
      setLastCrawl(new Date().toLocaleTimeString("ko-KR"));
      alert(`원티드 크롤링 완료: ${result.count}건\n샘플: ${result.sample?.map((j: { title: string }) => j.title).join(", ") || "-"}`);
      load(key);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(`원티드 크롤링 실패: ${msg}`);
    } finally {
      setCrawling(false);
    }
  };

  const handleCrawlSingle = async (name: string, fn: () => Promise<{ count: number; sample: { title: string }[] }>) => {
    setCrawling(true);
    setError("");
    try {
      const result = await fn();
      setLastCrawl(new Date().toLocaleTimeString("ko-KR"));
      alert(`${name} 크롤링 완료: ${result.count}건\n샘플: ${result.sample?.map((j) => j.title).join(", ") || "-"}`);
      load(key);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(`${name} 크롤링 실패: ${msg}`);
    } finally {
      setCrawling(false);
    }
  };

  const handleDebugWanted = async () => {
    setError("");
    try {
      const r = await debugWanted(key);
      setDebugResult(JSON.stringify(r, null, 2));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(`디버그 실패: ${msg}`);
    }
  };

  const filteredJobs = sourceFilter
    ? jobs.filter((j) => j.source === sourceFilter)
    : jobs;

  if (!key) {
    return (
      <div className="admin-login">
        <div className="admin-login-box">
          <h2>관리자 로그인</h2>
          <input
            type="password"
            placeholder="Admin Key"
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleKeySubmit()}
          />
          <button onClick={handleKeySubmit}>입력</button>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <header className="admin-header">
        <h1>올공고 관리자</h1>
        <button className="btn-sm" onClick={() => { localStorage.removeItem("admin_key"); setKey(""); }}>
          로그아웃
        </button>
      </header>

      {error && <div className="admin-error">{error}</div>}

      <div className="admin-grid">
        <section className="admin-card">
          <h2>DB 현황</h2>
          {loading ? (
            <p>로딩 중...</p>
          ) : status ? (
            <>
              <div className="stat-row"><span>공고 수</span><strong>{status.db.jobs.toLocaleString()}건</strong></div>
              <div className="stat-row"><span>소스 행</span><strong>{status.db.job_sources.toLocaleString()}건</strong></div>
            </>
          ) : <p>-</p>}
          <button className="btn-sm" onClick={() => load(key)} disabled={loading}>새로고침</button>
        </section>

        <section className="admin-card">
          <h2>크롤러 상태</h2>
          {status?.crawlers ? (
            <ul className="crawler-list">
              {Object.entries(status.crawlers).map(([name, info]) => (
                <li key={name} className={info.active ? "active" : "inactive"}>
                  <span className="crawler-dot">{info.active ? "●" : "○"}</span>
                  <strong>{name}</strong>
                  <small>{info.note}</small>
                </li>
              ))}
            </ul>
          ) : <p>-</p>}
        </section>

        <section className="admin-card">
          <h2>크롤링 실행</h2>
          {lastCrawl && <p className="last-crawl">마지막 실행: {lastCrawl}</p>}
          <div className="btn-group">
            <button className="btn-primary" onClick={handleCrawlAll} disabled={crawling}>
              {crawling ? "실행 중..." : "전체 크롤링"}
            </button>
          </div>
          <div className="btn-group">
            <button className="btn-secondary" onClick={handleCrawlWanted} disabled={crawling}>
              원티드
            </button>
            <button className="btn-secondary" onClick={() => handleCrawlSingle("점핏", () => triggerJumpit(key))} disabled={crawling}>
              점핏
            </button>
            <button className="btn-secondary" onClick={() => handleCrawlSingle("캐치", () => triggerCatch(key))} disabled={crawling}>
              캐치
            </button>
            <button className="btn-secondary" onClick={() => handleCrawlSingle("그룹바이", () => triggerGroupby(key))} disabled={crawling}>
              그룹바이
            </button>
          </div>
          <button className="btn-sm" onClick={handleDebugWanted}>원티드 API 디버그</button>
          {debugResult && (
            <pre className="debug-output">{debugResult}</pre>
          )}
        </section>
      </div>

      <section className="admin-jobs">
        <div className="jobs-header">
          <h2>최근 공고 ({filteredJobs.length}건)</h2>
          <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
            <option value="">전체 소스</option>
            <option value="wanted">원티드</option>
            <option value="jumpit">점핏</option>
            <option value="programmers">프로그래머스</option>
            <option value="catch">캐치</option>
            <option value="groupby">그룹바이</option>
          </select>
        </div>
        <div className="jobs-table-wrap">
          <table className="jobs-table">
            <thead>
              <tr>
                <th>제목</th>
                <th>회사</th>
                <th>소스</th>
                <th>경력</th>
                <th>고용형태</th>
                <th>지역</th>
              </tr>
            </thead>
            <tbody>
              {filteredJobs.map((j) => (
                <tr key={j.id}>
                  <td><a href={j.url} target="_blank" rel="noopener noreferrer">{j.title}</a></td>
                  <td>{j.company}</td>
                  <td><span className={`source-badge ${j.source}`}>{j.source}</span></td>
                  <td>{j.experience}</td>
                  <td>{j.employment_type}</td>
                  <td>{j.location}</td>
                </tr>
              ))}
              {filteredJobs.length === 0 && (
                <tr><td colSpan={6} style={{ textAlign: "center", padding: "2rem", color: "#888" }}>
                  공고 없음
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
