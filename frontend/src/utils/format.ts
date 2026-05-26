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

export function splitHighlight(
  text: string,
  query: string
): Array<{ part: string; match: boolean }> {
  if (!query.trim()) return [{ part: text, match: false }];
  const tokens = query
    .split(/\s+/)
    .filter(Boolean)
    .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!tokens.length) return [{ part: text, match: false }];
  const splitRegex = new RegExp(`(${tokens.join("|")})`, "gi");
  const matchRegex = new RegExp(`^(${tokens.join("|")})$`, "i");
  return text
    .split(splitRegex)
    .filter((p) => p.length > 0)
    .map((part) => ({ part, match: matchRegex.test(part) }));
}
