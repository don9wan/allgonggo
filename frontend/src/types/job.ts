export interface JobSource {
  id: string;
  source: "wanted" | "jumpit" | "programmers" | "catch" | "groupby";
  url: string;
}

export interface Job {
  id: string;
  title: string;
  company: string;
  location: string | null;
  experience: string | null;
  employment_type: string | null;
  is_active: boolean;
  crawled_at: string;
  sources: JobSource[];
}

export interface JobListResponse {
  jobs: Job[];
  total: number | null;
  page: number;
  size: number;
  has_next: boolean;
}

export type CardStatus =
  | "unread"
  | "viewed"
  | "last_seen"
  | "saved"
  | "applied"
  | "rejected";

export interface SavedJob extends Job {
  status: "saved" | "applied" | "rejected";
  savedAt: number;
}

export interface FilterState {
  q: string;
  location: string[];
  experience: string[];
  employment_type: string[];
  source: string[];
}
