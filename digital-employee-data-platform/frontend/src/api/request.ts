import axios from 'axios'

export interface ApiResponse<T> {
  success: boolean
  message: string
  data: T
}

export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export const request = axios.create({
  baseURL: apiBaseUrl,
  timeout: 10000,
})

request.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.message ||
      error.response?.data?.detail ||
      error.message ||
      '请求失败'
    return Promise.reject(new Error(message))
  },
)

export function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '请求失败'
}
