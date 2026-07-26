import { create } from 'zustand';
import { message } from 'antd';
import * as runtimeApi from '@/api/runtime';
import type { Agent } from '@/api/agents';
import type { Bot } from '@/api/bots';

// ── Core runtime state (mirrors Vue useRuntimeCore + useRuntimeConsole) ──

interface BotStatus {
  running: boolean;
  pid: number | null;
}

interface BotPagination {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

interface RuntimeState {
  // Core
  activeBotKey: string;
  activeView: string;
  status: unknown;
  bots: Bot[];
  botStatuses: Record<string, BotStatus>;
  agents: Agent[];
  loading: boolean;

  // Bot
  loadingBots: boolean;
  savingBot: boolean;
  startingBots: Set<string>;
  stoppingBots: Set<string>;
  botKeyword: string;
  botPagination: BotPagination;

  // Data
  dataOverview: unknown;
  tokenUsage: unknown;
  optimizingData: boolean;

  // System / platform
  platformSettings: Record<string, unknown>;

  // Actions — Core
  setActiveView: (view: string) => void;
  setActiveBotKey: (key: string) => void;
  ensureActiveBot: () => void;

  // Actions — Bots
  loadBots: () => Promise<void>;
  loadBotsConfig: (page?: number, pageSize?: number, keyword?: string) => Promise<boolean>;
  handleSaveBot: (bot: Record<string, unknown>, mode?: 'add' | 'edit') => Promise<boolean>;
  handleToggleBot: (botKey: string, isActive: boolean) => Promise<boolean>;
  handleDeleteBots: (botKeys: string[]) => Promise<boolean>;
  handleStartBot: (botKey: string) => Promise<boolean>;
  handleStopBot: (botKey: string) => Promise<boolean>;
  selectBot: (botKey: string) => Promise<void>;

  // Actions — Agents
  loadAgents: () => Promise<void>;

  // Actions — Data
  loadDataOverview: () => Promise<void>;
  loadTokenUsage: () => Promise<void>;
  optimizeData: () => Promise<boolean>;

  // Actions — System
  loadPlatformSettings: () => Promise<void>;
  savePlatformSettings: (settings: Record<string, unknown>) => Promise<boolean>;
  exitSystem: () => Promise<boolean>;

  // Actions — Lifecycle
  refreshAll: () => Promise<void>;
  initialize: () => Promise<void>;
  dispose: () => void;
}

export const useRuntimeStore = create<RuntimeState>((set, get) => ({
  // ── Initial state ──
  activeBotKey: '',
  activeView: 'control',
  status: null,
  bots: [],
  botStatuses: {},
  agents: [],
  loading: false,

  loadingBots: false,
  savingBot: false,
  startingBots: new Set(),
  stoppingBots: new Set(),
  botKeyword: '',
  botPagination: { total: 0, page: 1, page_size: 10, total_pages: 1 },

  dataOverview: null,
  tokenUsage: null,
  optimizingData: false,

  platformSettings: {},

  // ── Core actions ──
  setActiveView: (view) => set({ activeView: view }),
  setActiveBotKey: (key) => set({ activeBotKey: key }),

  ensureActiveBot: () => {
    const { bots, activeBotKey } = get();
    if (!bots.length) {
      set({ activeBotKey: '' });
      return;
    }
    if (!bots.some((bot) => bot.bot_key === activeBotKey)) {
      set({ activeBotKey: bots[0].bot_key });
    }
  },

  // ── Bot actions ──
  loadBots: async () => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result: any = await runtimeApi.getBots({ include_deleted: true });
      set({ bots: result.bots || [], botStatuses: result.statuses || {} });
      get().ensureActiveBot();
    } catch (error) {
      message.error(String(error));
    }
  },

  loadBotsConfig: async (page = 1, pageSize = 10, keyword) => {
    set({ loadingBots: true });
    try {
      const kw = keyword !== undefined ? keyword : get().botKeyword;
      if (keyword !== undefined) set({ botKeyword: kw });
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const response: any = await runtimeApi.getBots({ page, page_size: pageSize, keyword: kw });
      if (response?.bots) {
        set({
          bots: response.bots,
          botStatuses: response.statuses || {},
          botPagination: {
            total: response.total || 0,
            page: response.page || 1,
            page_size: response.page_size || 10,
            total_pages: response.total_pages || 1,
          },
        });
      }
      return true;
    } catch (error) {
      message.error(String(error));
      return false;
    } finally {
      set({ loadingBots: false });
    }
  },

  handleSaveBot: async (bot, mode = 'add') => {
    set({ savingBot: true });
    try {
      await runtimeApi.saveBot(bot, mode);
      const { botPagination } = get();
      await get().loadBotsConfig(botPagination.page, botPagination.page_size);
      message.success('Bot 已保存');
      return true;
    } catch (error) {
      message.error(String(error));
      return false;
    } finally {
      set({ savingBot: false });
    }
  },

  handleToggleBot: async (botKey, isActive) => {
    try {
      await runtimeApi.toggleBot(botKey, isActive);
      const { botPagination } = get();
      await get().loadBotsConfig(botPagination.page, botPagination.page_size);
      return true;
    } catch (error) {
      message.error(String(error));
      return false;
    }
  },

  handleDeleteBots: async (botKeys) => {
    try {
      await runtimeApi.batchDeleteBots(botKeys);
      const { botPagination } = get();
      await get().loadBotsConfig(botPagination.page, botPagination.page_size);
      message.success('Bot 已删除');
      return true;
    } catch (error) {
      message.error(String(error));
      return false;
    }
  },

  handleStartBot: async (botKey) => {
    const { startingBots } = get();
    const next = new Set(startingBots);
    next.add(botKey);
    set({ startingBots: next });
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result: any = await runtimeApi.startNamedBot(botKey);
      const { botPagination } = get();
      await get().loadBotsConfig(botPagination.page, botPagination.page_size);
      const warnings = Array.isArray(result?.warnings) ? result.warnings.filter(Boolean) : [];
      warnings.forEach((m: string) => message.warning(m));
      message.success('Bot 已启动');
      return true;
    } catch (error) {
      message.error(String(error));
      return false;
    } finally {
      const s = new Set(get().startingBots);
      s.delete(botKey);
      set({ startingBots: s });
    }
  },

  handleStopBot: async (botKey) => {
    const { stoppingBots } = get();
    const next = new Set(stoppingBots);
    next.add(botKey);
    set({ stoppingBots: next });
    try {
      await runtimeApi.stopNamedBot(botKey);
      const { botPagination } = get();
      await get().loadBotsConfig(botPagination.page, botPagination.page_size);
      message.success('Bot 已停止');
      return true;
    } catch (error) {
      message.error(String(error));
      return false;
    } finally {
      const s = new Set(get().stoppingBots);
      s.delete(botKey);
      set({ stoppingBots: s });
    }
  },

  selectBot: async (botKey) => {
    set({ activeBotKey: botKey });
    // Chat loading is handled by useChats hook
  },

  // ── Agent actions ──
  loadAgents: async () => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result: any = await runtimeApi.getAgents();
      set({ agents: result.agents || result || [] });
    } catch (error) {
      message.error(String(error));
    }
  },

  // ── Data actions ──
  loadDataOverview: async () => {
    try {
      const overview = await runtimeApi.getDataOverview();
      set({ dataOverview: overview });
    } catch (error) {
      message.error(String(error));
    }
  },

  loadTokenUsage: async () => {
    try {
      const usage = await runtimeApi.getTokenUsage();
      set({ tokenUsage: usage });
    } catch (error) {
      message.error(String(error));
    }
  },

  optimizeData: async () => {
    set({ optimizingData: true });
    try {
      await runtimeApi.optimizeDatabase();
      message.success('数据优化完成');
      await get().loadDataOverview();
      return true;
    } catch (error) {
      message.error(String(error));
      return false;
    } finally {
      set({ optimizingData: false });
    }
  },

  // ── System actions ──
  loadPlatformSettings: async () => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const settings: any = await runtimeApi.getPlatformSettings();
      set({ platformSettings: settings || {} });
    } catch (error) {
      message.error(String(error));
    }
  },

  savePlatformSettings: async (settings) => {
    try {
      await runtimeApi.savePlatformSettings(settings);
      message.success('平台设置已保存');
      return true;
    } catch (error) {
      message.error(String(error));
      return false;
    }
  },

  exitSystem: async () => {
    try {
      await runtimeApi.exitSystem();
      return true;
    } catch (error) {
      message.error(String(error));
      return false;
    }
  },

  // ── Lifecycle ──
  refreshAll: async () => {
    set({ loading: true });
    try {
      await Promise.all([
        get().loadBots(),
        get().loadAgents(),
      ]);
    } finally {
      set({ loading: false });
    }
  },

  initialize: async () => {
    await get().refreshAll();
    await get().loadPlatformSettings();
  },

  dispose: () => {
    set({
      activeBotKey: '',
      activeView: 'control',
      status: null,
      bots: [],
      botStatuses: {},
      agents: [],
      dataOverview: null,
      tokenUsage: null,
      platformSettings: {},
    });
  },
}));
