import { createRuntimeCore, disposeRuntimeCore } from './useRuntimeCore'
import { useBots } from './useBots'
import { useChats, disposeChats } from './useChats'
import { useAgents } from './useAgents'
import { useSkills } from './useSkills'
import { useMcp } from './useMcp'
import { useData } from './useData'
import { useSystem } from './useSystem'

export function useRuntimeConsole() {
  const core = createRuntimeCore()
  const bots = useBots()
  const chats = useChats()
  const agents = useAgents()
  const skills = useSkills()
  const mcp = useMcp()
  const data = useData()
  const system = useSystem()

  function dispose() {
    system.stopPolling()
    disposeChats()
    disposeRuntimeCore()
  }

  return {
    ...core,
    ...bots,
    ...chats,
    ...agents,
    ...skills,
    ...mcp,
    ...data,
    ...system,
    dispose,
  }
}
