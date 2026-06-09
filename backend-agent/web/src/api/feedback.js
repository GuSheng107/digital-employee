import { api } from './http'

export function getFeedbackStats(params = {}) {
  const query = new URLSearchParams()
  if (params.days) query.append('days', String(params.days))
  return api(`/api/feedback/stats?${query.toString()}`)
}

export function getFeedbackList(params = {}) {
  const query = new URLSearchParams()
  if (params.result) query.append('result', params.result)
  if (params.days) query.append('days', String(params.days))
  if (params.page) query.append('page', String(params.page))
  if (params.page_size) query.append('page_size', String(params.page_size))
  return api(`/api/feedback/list?${query.toString()}`)
}

export function getFeedbackListByMessage(params = {}) {
  const query = new URLSearchParams()
  if (params.result) query.append('result', params.result)
  if (params.days) query.append('days', String(params.days))
  if (params.page) query.append('page', String(params.page))
  if (params.page_size) query.append('page_size', String(params.page_size))
  return api(`/api/feedback/list-by-message?${query.toString()}`)
}

export function getFeedbackAlerts(params = {}) {
  const query = new URLSearchParams()
  if (params.days) query.append('days', String(params.days))
  if (params.page) query.append('page', String(params.page))
  if (params.page_size) query.append('page_size', String(params.page_size))
  return api(`/api/feedback/alerts?${query.toString()}`)
}
