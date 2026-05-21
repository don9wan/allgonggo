import axios from "axios";
import type { FilterState, JobListResponse } from "../types/job";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

const client = axios.create({ baseURL: API_BASE });

export async function fetchJobs(
  filters: Partial<FilterState>,
  page = 1,
  size = 20
): Promise<JobListResponse> {
  const params: Record<string, string> = { page: String(page), size: String(size) };

  if (filters.q) params.q = filters.q;
  if (filters.location?.length) params.location = filters.location.join(",");
  if (filters.experience?.length) params.experience = filters.experience.join(",");
  if (filters.employment_type?.length) params.employment_type = filters.employment_type.join(",");
  if (filters.source?.length) params.source = filters.source.join(",");

  const { data } = await client.get<JobListResponse>("/jobs", { params });
  return data;
}
