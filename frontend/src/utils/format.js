export function formatTime(value) {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hour = String(date.getHours()).padStart(2, '0')
  const minute = String(date.getMinutes()).padStart(2, '0')
  const second = String(date.getSeconds()).padStart(2, '0')
  
  return `${year}-${month}-${day} ${hour}:${minute}:${second}`
}

export function conversationAvatar(chat) {
  const base = import.meta.env.BASE_URL || './'
  if (chat?.conversation_kind === 'me') {
    return `${base}avatars/me.svg`
  }
  if (chat?.chat_type === 'group' || chat?.chat_type === 'room') {
    return `${base}avatars/group.svg`
  }
  return `${base}avatars/user.svg`
}

export function defaultConversationName(chat) {
  if (chat?.display_name) {
    return chat.display_name
  }

  if (chat?.conversation_kind === 'me') {
    return chat?.chat_name || '我'
  }

  const externalId = chat?.external_chat_id || chat?.sender_id || chat?.chat_id || ''
  if (chat?.chat_type === 'group' || chat?.chat_type === 'room') {
    return chat?.chat_name || buildConversationLabel('群聊', externalId, chat?.created_at || chat?.last_at || chat?.last_message_at)
  }
  if (chat?.chat_type === 'user' || chat?.chat_type === 'single') {
    return displayUserName(chat?.sender_display_name || chat?.sender_name, chat?.sender_id || externalId)
  }

  return displayUserName(chat?.sender_display_name || chat?.sender_name, chat?.sender_id || chat?.chat_id)
}

export function buildConversationLabel(kind, seed, createdAt) {
  return `${kind} ${timeToken(createdAt)} ${stableSuffix(seed)}`
}

export function displayUserName(name, id) {
  if (name && name !== id && !looksLikeWeComId(name)) {
    return name
  }

  if (!id) {
    return name || '未知用户'
  }

  if (id.length <= 10) {
    return `企微用户 ${id}`
  }

  return `企微用户 ${id.slice(0, 8)}`
}

export function timeToken(value) {
  if (!value) {
    return '0000-0000'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '0000-0000'
  }

  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hour = String(date.getHours()).padStart(2, '0')
  const minute = String(date.getMinutes()).padStart(2, '0')
  return `${month}${day}-${hour}${minute}`
}

export function stableSuffix(value, length = 4) {
  const text = String(value || '').trim()
  if (!text) {
    return '0000'
  }

  let hash = 0
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash * 131) + text.charCodeAt(index)) >>> 0
  }
  return hash.toString(16).toUpperCase().padStart(length, '0').slice(0, length)
}

export function looksLikeWeComId(value) {
  if (!value || typeof value !== 'string') {
    return false
  }

  return /^(wo|wm|wb|wr)[A-Za-z0-9_-]{12,}$/.test(value) || /^[A-Za-z0-9_-]{24,}$/.test(value)
}

export function formatBytes(value) {
  const bytes = Number(value || 0)
  if (bytes < 1024) {
    return `${bytes} B`
  }
  const units = ['KB', 'MB', 'GB', 'TB']
  let size = bytes / 1024
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(size >= 10 ? 1 : 2)} ${units[index]}`
}

export function getAgentLabel(providerKey, agents) {
  if (!providerKey) {
    return '-'
  }
  const agent = agents.find((item) => item.provider_key === providerKey)
  return agent?.label || agent?.provider_name || providerKey
}

export function formatTimeOnly(value) {
  if (!value) return '--'
  try {
    return new Date(value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return String(value).slice(11, 19)
  }
}

export function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export function renderInlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/__([^_\n]+)__/g, '<strong>$1</strong>')
    .replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
    .replace(/_([^_\n]+)_/g, '<em>$1</em>')
}

function parseTableCells(line) {
  const trimmed = String(line || '').trim().replace(/^\|/, '').replace(/\|$/, '')
  return trimmed.split('|').map((cell) => cell.trim())
}

function isTableSeparator(line) {
  return /^\s*\|?[\s:|-]+\|[\s:|-]+\|?\s*$/.test(String(line || ''))
}

function isBlockStart(line, nextLine = '') {
  return (
    /^\s{0,3}#{1,6}\s+\S/.test(line)
    || /^\s{0,3}(```|~~~)/.test(line)
    || /^\s{0,3}>\s+\S/.test(line)
    || /^\s{0,3}[-*+]\s+\S/.test(line)
    || /^\s{0,3}\d+\.\s+\S/.test(line)
    || /^\s{0,3}---+\s*$/.test(line)
    || (line.includes('|') && isTableSeparator(nextLine))
  )
}

export function renderMarkdown(text) {
  const lines = String(text || '').replace(/\r\n/g, '\n').split('\n')
  const html = []
  let index = 0
  let listType = ''
  let inCode = false
  let codeLines = []

  const closeList = () => {
    if (!listType) return
    html.push(`</${listType}>`)
    listType = ''
  }

  while (index < lines.length) {
    const line = lines[index]

    if (/^\s{0,3}(```|~~~)/.test(line)) {
      closeList()
      if (inCode) {
        html.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
        codeLines = []
        inCode = false
      } else {
        inCode = true
      }
      index += 1
      continue
    }

    if (inCode) {
      codeLines.push(line)
      index += 1
      continue
    }

    if (!line.trim()) {
      closeList()
      index += 1
      continue
    }

    const tableNext = lines[index + 1] || ''
    if (line.includes('|') && isTableSeparator(tableNext)) {
      closeList()
      const headers = parseTableCells(line)
      const rows = []
      index += 2
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        rows.push(parseTableCells(lines[index]))
        index += 1
      }
      html.push(
        '<table><thead><tr>'
        + headers.map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join('')
        + '</tr></thead><tbody>'
        + rows.map((row) => (
          '<tr>'
          + row.map((cell) => `<td>${renderInlineMarkdown(cell)}</td>`).join('')
          + '</tr>'
        )).join('')
        + '</tbody></table>',
      )
      continue
    }

    const heading = line.match(/^\s{0,3}(#{1,6})\s+(.+)$/)
    if (heading) {
      closeList()
      const level = heading[1].length
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`)
      index += 1
      continue
    }

    if (/^\s{0,3}---+\s*$/.test(line)) {
      closeList()
      html.push('<hr>')
      index += 1
      continue
    }

    const quote = line.match(/^\s{0,3}>\s+(.+)$/)
    if (quote) {
      closeList()
      html.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`)
      index += 1
      continue
    }

    const unordered = line.match(/^\s{0,3}[-*+]\s+(.+)$/)
    if (unordered) {
      if (listType !== 'ul') {
        closeList()
        listType = 'ul'
        html.push('<ul>')
      }
      html.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`)
      index += 1
      continue
    }

    const ordered = line.match(/^\s{0,3}\d+\.\s+(.+)$/)
    if (ordered) {
      if (listType !== 'ol') {
        closeList()
        listType = 'ol'
        html.push('<ol>')
      }
      html.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`)
      index += 1
      continue
    }

    closeList()
    const paragraph = [line.trim()]
    while (
      index + 1 < lines.length
      && lines[index + 1].trim()
      && !isBlockStart(lines[index + 1], lines[index + 2] || '')
    ) {
      index += 1
      paragraph.push(lines[index].trim())
    }
    html.push(`<p>${paragraph.map(renderInlineMarkdown).join('<br>')}</p>`)
    index += 1
  }

  closeList()
  if (inCode) {
    html.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
  }
  return html.join('')
}
