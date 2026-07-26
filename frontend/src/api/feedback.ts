import request from '@/utils/request';

export interface FeedbackStatsParams {
  days?: number;
}

export interface FeedbackListParams {
  result?: string;
  days?: number;
  page?: number;
  page_size?: number;
}

export function getFeedbackStats(params: FeedbackStatsParams = {}) {
  const query = new URLSearchParams();
  if (params.days) query.append('days', String(params.days));
  return request.get(`/feedback/stats?${query.toString()}`);
}

export function getFeedbackList(params: FeedbackListParams = {}) {
  const query = new URLSearchParams();
  if (params.result) query.append('result', params.result);
  if (params.days) query.append('days', String(params.days));
  if (params.page) query.append('page', String(params.page));
  if (params.page_size) query.append('page_size', String(params.page_size));
  return request.get(`/feedback/list?${query.toString()}`);
}

export function getFeedbackListByMessage(params: FeedbackListParams = {}) {
  const query = new URLSearchParams();
  if (params.result) query.append('result', params.result);
  if (params.days) query.append('days', String(params.days));
  if (params.page) query.append('page', String(params.page));
  if (params.page_size) query.append('page_size', String(params.page_size));
  return request.get(`/feedback/list-by-message?${query.toString()}`);
}

export function getFeedbackAlerts(params: FeedbackListParams = {}) {
  const query = new URLSearchParams();
  if (params.days) query.append('days', String(params.days));
  if (params.page) query.append('page', String(params.page));
  if (params.page_size) query.append('page_size', String(params.page_size));
  return request.get(`/feedback/alerts?${query.toString()}`);
}
