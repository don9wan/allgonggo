import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL || "/api";
const client = axios.create({ baseURL: API_BASE });

function headers(key: string) {
  return { "x-admin-key": key };
}

export async function getStatus(key: string) {
  const { data } = await client.get("/admin/status", { headers: headers(key) });
  return data;
}

export async function triggerCrawl(key: string) {
  const { data } = await client.post("/admin/crawl", null, { headers: headers(key) });
  return data;
}

export async function triggerWanted(key: string) {
  const { data } = await client.post("/admin/crawl/wanted", null, { headers: headers(key) });
  return data;
}

export async function getRecentJobs(key: string, limit = 30, source?: string) {
  const params: Record<string, string | number> = { limit };
  if (source) params.source = source;
  const { data } = await client.get("/admin/jobs/recent", { headers: headers(key), params });
  return data as {
    id: string;
    title: string;
    company: string;
    source: string;
    experience: string;
    employment_type: string;
    location: string;
    url: string;
  }[];
}

export async function debugWanted(key: string) {
  const { data } = await client.get("/admin/debug/wanted", { headers: headers(key) });
  return data;
}
