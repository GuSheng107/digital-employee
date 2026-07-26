import request from '@/utils/request';

export function getSkills() {
  return request.get('/skills');
}

export function parseSkills(file: File) {
  const body = new FormData();
  body.append('file', file);
  return request.post('/skills/parse', body, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

export function uploadSkills(file: File | null, displayNames: Record<string, string> = {}, type: string = 'new', skillName: string = '') {
  const body = new FormData();
  body.append('type', type);
  if (skillName) body.append('skill_name', skillName);
  if (file) body.append('file', file);
  if (displayNames && Object.keys(displayNames).length) {
    body.append('display_names', JSON.stringify(displayNames));
  }
  return request.post('/skills/upload', body, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

export function setSkillEnabled(skillName: string, enabled: boolean) {
  return request.post(`/skills/${encodeURIComponent(skillName)}/enabled`, { enabled });
}

export function deleteSkill(skillName: string) {
  return request.delete(`/skills/${encodeURIComponent(skillName)}`);
}

export function getMcpTools() {
  return request.get('/mcp/tools');
}

export function refreshMcpTools() {
  return request.post('/mcp/tools/refresh');
}

export async function getMcpServers() {
  return request.get('/mcp/servers');
}

export async function getMcpServer(serverId: string) {
  return request.get(`/mcp/servers/${encodeURIComponent(serverId)}`);
}

export async function saveMcpServer(serverData: Record<string, unknown>) {
  return request.post('/mcp/servers', serverData);
}

export async function deleteMcpServer(serverId: string) {
  return request.delete(`/mcp/servers/${encodeURIComponent(serverId)}`);
}

export async function toggleMcpServer(serverId: string, isActive: boolean) {
  return request.post(`/mcp/servers/${encodeURIComponent(serverId)}/toggle`, { is_active: isActive });
}

export async function importMcpServers(importData: Record<string, unknown>) {
  return request.post('/mcp/servers/import', importData);
}

export async function testMcpServerConnection(serverId: string) {
  return request.post(`/mcp/servers/${encodeURIComponent(serverId)}/test-connection`);
}
