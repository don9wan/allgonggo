const RE_BRACKET = /\[.*?\]/g;
const RE_YEAR = /20\d{2}년도?/g;
const RE_HALF = /[상하]반기/g;
const RE_WS = /\s+/g;

export function normalizeTitle(title: string): string {
  const normalized = title
    .replace(RE_BRACKET, " ")
    .replace(RE_YEAR, " ")
    .replace(RE_HALF, " ")
    .replace(RE_WS, " ")
    .trim();
  return normalized.length >= 3 ? normalized : title;
}

export function relativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - date.getTime()) / 86_400_000);

  if (diffDays === 0) return "오늘";
  if (diffDays === 1) return "어제";
  if (diffDays < 7) return `${diffDays}일 전`;
  if (diffDays < 14) return "1주 전";
  return `${Math.floor(diffDays / 7)}주 전`;
}
