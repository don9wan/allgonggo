import posthog from 'posthog-js';

const POSTHOG_KEY = import.meta.env.VITE_POSTHOG_KEY as string;
const POSTHOG_HOST = 'https://us.i.posthog.com';

const LS = {
  UID: 'allgonggo_uid',
  FIRST_VISIT: 'allgonggo_first_visit',
  LAST_VISIT: 'allgonggo_last_visit',
  SESSION_COUNT: 'allgonggo_session_count',
  ACQUISITION_SOURCE: 'allgonggo_acquisition_source',
  UTM_SOURCE: 'allgonggo_utm_source',
  UTM_CAMPAIGN: 'allgonggo_utm_campaign',
};

// 페이지 로드 단위로 초기화되는 세션 클릭 카운터
let sessionClickCount = 0;

function uuid(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function getDistinctId(): string {
  let id = localStorage.getItem(LS.UID);
  if (!id) {
    id = uuid();
    localStorage.setItem(LS.UID, id);
  }
  return id;
}

function parseReferrer(referrer: string): string {
  if (!referrer) return 'direct';
  if (referrer.includes('threads.net')) return 'threads';
  if (referrer.includes('instagram.com')) return 'instagram';
  if (referrer.includes('twitter.com') || referrer.includes('x.com')) return 'twitter';
  if (referrer.includes('google.')) return 'google';
  if (referrer.includes('naver.com')) return 'naver';
  if (referrer.includes('kakao')) return 'kakao';
  return 'other';
}

function getUTMs() {
  const p = new URLSearchParams(window.location.search);
  return {
    utm_source: p.get('utm_source'),
    utm_medium: p.get('utm_medium'),
    utm_campaign: p.get('utm_campaign'),
  };
}

function commonProps() {
  return {
    acquisition_source: localStorage.getItem(LS.ACQUISITION_SOURCE) ?? 'direct',
    utm_source: localStorage.getItem(LS.UTM_SOURCE),
    utm_campaign: localStorage.getItem(LS.UTM_CAMPAIGN),
  };
}

export function initAnalytics() {
  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    autocapture: false,
    capture_pageview: false,
    capture_pageleave: false,
    persistence: 'localStorage',
  });
  posthog.identify(getDistinctId());
}

export function trackSessionStart() {
  const now = Date.now();
  const firstVisit = localStorage.getItem(LS.FIRST_VISIT);
  const lastVisit = localStorage.getItem(LS.LAST_VISIT);
  const sessionCount = parseInt(localStorage.getItem(LS.SESSION_COUNT) ?? '0', 10) + 1;

  const isNewUser = !firstVisit;
  const daysSinceLast = lastVisit
    ? Math.floor((now - parseInt(lastVisit, 10)) / 86_400_000)
    : null;

  if (!firstVisit) localStorage.setItem(LS.FIRST_VISIT, String(now));
  localStorage.setItem(LS.LAST_VISIT, String(now));
  localStorage.setItem(LS.SESSION_COUNT, String(sessionCount));

  const referrerSource = parseReferrer(document.referrer);
  const utms = getUTMs();

  // 최초 유입 채널은 첫 방문 기준으로만 저장 (이후 방문에서 덮어쓰지 않음)
  if (!localStorage.getItem(LS.ACQUISITION_SOURCE)) {
    const source = utms.utm_source ?? referrerSource;
    localStorage.setItem(LS.ACQUISITION_SOURCE, source);
    if (utms.utm_source) localStorage.setItem(LS.UTM_SOURCE, utms.utm_source);
    if (utms.utm_campaign) localStorage.setItem(LS.UTM_CAMPAIGN, utms.utm_campaign);
  }

  posthog.capture('session_started', {
    is_new_user: isNewUser,
    days_since_last_visit: daysSinceLast,
    total_sessions: sessionCount,
    referrer_source: referrerSource,
    ...commonProps(),
  });
}

export function trackJobClicked(params: {
  job_id: string;
  company: string;
  title: string;
  clicked_source: string;
  sources_count: number;
  click_type: 'card' | 'source_icon';
  job_status: string;
  position_in_feed: number;
  has_search: boolean;
  search_query: string;
  active_filters: string[];
}) {
  sessionClickCount += 1;
  posthog.capture('job_clicked', {
    ...params,
    session_click_count: sessionClickCount,
    ...commonProps(),
  });
}

export function trackJobSaved(params: {
  job_id: string;
  company: string;
  title: string;
  sources: string[];
  job_status: string;
  position_in_feed: number;
  has_search: boolean;
  search_query: string;
  active_filters: string[];
  total_saved_after: number;
}) {
  posthog.capture('job_saved', { ...params, ...commonProps() });
}

export function trackJobHidden(params: {
  job_id: string;
  company: string;
  job_status: string;
  position_in_feed: number;
  total_hidden_after: number;
}) {
  posthog.capture('job_hidden', { ...params, ...commonProps() });
}

export function trackSearchPerformed(query: string) {
  posthog.capture('search_performed', {
    query,
    query_length: query.length,
    ...commonProps(),
  });
}

export function trackFilterApplied(params: {
  filter_type: string;
  action: 'add' | 'remove' | 'clear_all';
  changed_value: string;
  selected_count: number;
}) {
  posthog.capture('filter_applied', { ...params, ...commonProps() });
}

export function trackHideViewedToggled(enabled: boolean) {
  posthog.capture('hide_viewed_toggled', { enabled, ...commonProps() });
}

export function trackFilterReset(params: { had_search: boolean; had_filter_types: string[] }) {
  posthog.capture('filter_reset', { ...params, ...commonProps() });
}

export function trackSavedPanelOpened(params: {
  saved_count: number;
  applied_count: number;
  rejected_count: number;
}) {
  posthog.capture('saved_panel_opened', { ...params, ...commonProps() });
}

export function trackHiddenPanelOpened(hidden_count: number) {
  posthog.capture('hidden_panel_opened', { hidden_count, ...commonProps() });
}

export function trackSavedJobStatusChanged(params: {
  job_id: string;
  company: string;
  from_status: string;
  to_status: string;
}) {
  posthog.capture('saved_job_status_changed', { ...params, ...commonProps() });
}

export function trackSavedJobReturnedToFeed(params: {
  job_id: string;
  company: string;
  had_status: string;
}) {
  posthog.capture('saved_job_returned_to_feed', { ...params, ...commonProps() });
}

export function trackHiddenJobRestored(params: { job_id: string; company: string }) {
  posthog.capture('hidden_job_restored', { ...params, ...commonProps() });
}

export function trackFeedNextPage(page_number: number) {
  posthog.capture('feed_next_page_loaded', { page_number, ...commonProps() });
}
