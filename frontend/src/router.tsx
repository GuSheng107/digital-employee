/* eslint-disable react-refresh/only-export-components */
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import Layout from './components/Layout';
import { AuthGuard, GuestGuard } from './components/AuthGuard';
import PageLoader from './components/PageLoader';
import LoginView from './pages/LoginView';

const ControlView = lazy(() => import('./pages/control-view/ControlView'));
const AgentConfigView = lazy(() => import('./pages/AgentConfigView'));
const BotConfigView = lazy(() => import('./pages/BotConfigView'));
const ProjectLogsView = lazy(() => import('./pages/ProjectLogsView'));
const DataManagementView = lazy(() => import('./pages/DataManagementView'));
const SkillsConfigView = lazy(() => import('./pages/SkillsConfigView'));
const McpConfigView = lazy(() => import('./pages/mcp-config-view/McpConfigView'));
const FeedbackStatsView = lazy(() => import('./pages/FeedbackStatsView'));
const MemoryManagementView = lazy(() => import('./pages/memory-management-view/MemoryManagementView'));
const TaskManagementView = lazy(() => import('./pages/task-management-view/TaskManagementView'));
const SystemSettingsView = lazy(() => import('./pages/SystemSettingsView'));
const ConversationsView = lazy(() => import('./pages/conversations-view/ConversationsView'));
const DataPlatformDashboard = lazy(() => import('./pages/data-platform-dashboard/DataPlatformDashboard'));
const DataPlatformDataItems = lazy(() => import('./pages/data-platform-data-items/DataPlatformDataItems'));
const DataPlatformSystemConfig = lazy(() => import('./pages/data-platform-system-config/DataPlatformSystemConfig'));

export const router = createBrowserRouter([
  { path: '/login', element: (<GuestGuard><LoginView /></GuestGuard>) },
  {
    path: '/', element: (<AuthGuard><Layout /></AuthGuard>),
    children: [
      { index: true, element: <Suspense fallback={<PageLoader />}><ControlView /></Suspense> },
      { path: 'agent', element: <Suspense fallback={<PageLoader />}><AgentConfigView /></Suspense> },
      { path: 'bot', element: <Suspense fallback={<PageLoader />}><BotConfigView /></Suspense> },
      { path: 'chats', element: <Suspense fallback={<PageLoader />}><ConversationsView /></Suspense> },
      { path: 'mcp', element: <Suspense fallback={<PageLoader />}><McpConfigView /></Suspense> },
      { path: 'skills', element: <Suspense fallback={<PageLoader />}><SkillsConfigView /></Suspense> },
      { path: 'project-logs', element: <Suspense fallback={<PageLoader />}><ProjectLogsView /></Suspense> },
      { path: 'data', element: <Suspense fallback={<PageLoader />}><DataManagementView /></Suspense> },
      { path: 'feedback', element: <Suspense fallback={<PageLoader />}><FeedbackStatsView /></Suspense> },
      { path: 'memory', element: <Suspense fallback={<PageLoader />}><MemoryManagementView /></Suspense> },
      { path: 'tasks', element: <Suspense fallback={<PageLoader />}><TaskManagementView /></Suspense> },
      { path: 'settings', element: <Suspense fallback={<PageLoader />}><SystemSettingsView /></Suspense> },
      { path: 'data-platform/dashboard', element: <Suspense fallback={<PageLoader />}><DataPlatformDashboard /></Suspense> },
      { path: 'data-platform/data-items', element: <Suspense fallback={<PageLoader />}><DataPlatformDataItems /></Suspense> },
      { path: 'data-platform/system-config', element: <Suspense fallback={<PageLoader />}><DataPlatformSystemConfig /></Suspense> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
]);
