import axios, { type AxiosInstance, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { message } from 'antd';
import { useUserStore } from '../store/user';

const request: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('token');
    if (token && config.headers) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

request.interceptors.response.use(
  (response: AxiosResponse) => {
    const { data } = response;
    if (data.code !== 200) {
      message.error(data.message || '业务请求失败');
      return Promise.reject(new Error(data.message || 'Error'));
    }
    return data.data;
  },
  (error) => {
    if (error.response) {
      const { status, data } = error.response;
      switch (status) {
        case 401:
          message.error('登录状态已过期，请重新登录');
          useUserStore.getState().clearUserInfo();
          localStorage.removeItem('token');
          break;
        case 403:
          message.error('您没有权限访问该资源');
          break;
        case 500:
          message.error('服务器内部错误，请稍后再试');
          break;
        default:
          message.error(data?.message || '网络请求异常');
          break;
      }
    } else if (error.message.includes('timeout')) {
      message.error('请求超时，请检查网络连接');
    } else {
      message.error('无法连接到服务器');
    }
    return Promise.reject(error);
  }
);

export default request;
