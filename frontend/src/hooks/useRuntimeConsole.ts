import { useRuntimeStore } from '@/store/runtime';

/**
 * Main console hook — composes all runtime state.
 * Mirrors Vue's useRuntimeConsole composable.
 */
export function useRuntimeConsole() {
  const store = useRuntimeStore();

  return {
    // Core
    activeBotKey: store.activeBotKey,
    activeView: store.activeView,
    status: store.status,
    bots: store.bots,
    botStatuses: store.botStatuses,
    agents: store.agents,
    loading: store.loading,

    // Bot
    loadingBots: store.loadingBots,
    savingBot: store.savingBot,
    startingBots: store.startingBots,
    stoppingBots: store.stoppingBots,
    botKeyword: store.botKeyword,
    botPagination: store.botPagination,

    // Data
    dataOverview: store.dataOverview,
    tokenUsage: store.tokenUsage,
    optimizingData: store.optimizingData,

    // Platform
    platformSettings: store.platformSettings,

    // Core actions
    setActiveView: store.setActiveView,
    setActiveBotKey: store.setActiveBotKey,
    ensureActiveBot: store.ensureActiveBot,

    // Bot actions
    loadBots: store.loadBots,
    loadBotsConfig: store.loadBotsConfig,
    handleSaveBot: store.handleSaveBot,
    handleToggleBot: store.handleToggleBot,
    handleDeleteBots: store.handleDeleteBots,
    handleStartBot: store.handleStartBot,
    handleStopBot: store.handleStopBot,
    selectBot: store.selectBot,

    // Agent actions
    loadAgents: store.loadAgents,

    // Data actions
    loadDataOverview: store.loadDataOverview,
    loadTokenUsage: store.loadTokenUsage,
    optimizeData: store.optimizeData,

    // System actions
    loadPlatformSettings: store.loadPlatformSettings,
    savePlatformSettings: store.savePlatformSettings,
    exitSystem: store.exitSystem,

    // Lifecycle
    refreshAll: store.refreshAll,
    initialize: store.initialize,
    dispose: store.dispose,
  };
}
