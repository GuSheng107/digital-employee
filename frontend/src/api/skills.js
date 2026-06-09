import { api } from './http'

export function getSkills() {
  return api('/api/skills')
}

export function parseSkills(file) {
  const body = new FormData()
  body.append('file', file)
  return api('/api/skills/parse', { method: 'POST', body })
}

export function uploadSkills(file, displayNames = {}, type = 'new', skillName = '') {
  const body = new FormData()
  body.append('type', type)
  if (skillName) body.append('skill_name', skillName)
  if (file) body.append('file', file)
  if (displayNames && Object.keys(displayNames).length) {
    body.append('display_names', JSON.stringify(displayNames))
  }
  return api('/api/skills/upload', { method: 'POST', body })
}

export function setSkillEnabled(skillName, enabled) {
  return api(`/api/skills/${encodeURIComponent(skillName)}/enabled`, {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  })
}

export function deleteSkill(skillName) {
  return api(`/api/skills/${encodeURIComponent(skillName)}`, { method: 'DELETE' })
}

export function getMcpTools() {
  return api('/api/mcp/tools')
}

export function refreshMcpTools() {
  return api('/api/mcp/tools/refresh', { method: 'POST' })
}

export async function getMcpServers() {
  return api('/api/mcp/servers')
}

export async function getMcpServer(serverId) {
  return api(`/api/mcp/servers/${encodeURIComponent(serverId)}`)
}

export async function saveMcpServer(serverData) {
  return api('/api/mcp/servers', {
    method: 'POST',
    body: JSON.stringify(serverData),
  })
}

export async function deleteMcpServer(serverId) {
  return api(`/api/mcp/servers/${encodeURIComponent(serverId)}`, { method: 'DELETE' })
}

export async function toggleMcpServer(serverId, isActive) {
  return api(`/api/mcp/servers/${encodeURIComponent(serverId)}/toggle`, {
    method: 'POST',
    body: JSON.stringify({ is_active: isActive }),
  })
}

export async function importMcpServers(importData) {
  return api('/api/mcp/servers/import', {
    method: 'POST',
    body: JSON.stringify(importData),
  })
}

export async function testMcpServerConnection(serverId) {
  return api(`/api/mcp/servers/${encodeURIComponent(serverId)}/test-connection`, { method: 'POST' })
}
