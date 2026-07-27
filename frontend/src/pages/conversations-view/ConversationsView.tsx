import { useEffect, useState, useRef, useCallback } from 'react';
import { Card, Button, Input, Tag, Switch, Progress, Upload, message, Space, Empty, Tooltip, Avatar } from 'antd';
import { EditOutlined, SendOutlined, PaperClipOutlined, LoadingOutlined, RobotOutlined, CompressOutlined } from '@ant-design/icons';
import { useRuntimeStore } from '@/store/runtime';
import { getChats, getChatDetail, deleteChats, updateChatDisplayName, markChatRead, compressChatContext, generateAiDraftStream, sendManualReply, type Chat, type ChatDetailResponse, type ChatListResponse } from '@/api/chats';
import { markAllBotChatsRead, type Bot } from '@/api/bots';
import { displayUserName, formatTime, conversationAvatar } from '@/utils/format';

export default function ConversationsView() {
  const { bots, botStatuses, activeBotKey, selectBot } = useRuntimeStore();

  const [chats, setChats] = useState<Chat[]>([]);
  const [activeChat, setActiveChat] = useState<Chat | null>(null);
  const [loadingChats, setLoadingChats] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [deleting, setDeleting] = useState(false);
  const [manualReply, setManualReply] = useState('');
  const [replyMode, setReplyMode] = useState<'manual' | 'ai'>('manual');
  const [sending, setSending] = useState(false);
  const [generatingAi, setGeneratingAi] = useState(false);
  const [compressing, setCompressing] = useState(false);
  const [attachments, setAttachments] = useState<File[]>([]);
  const [editingName, setEditingName] = useState(false);
  const [editNameVal, setEditNameVal] = useState('');
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [page, setPage] = useState(1);
  const msgListRef = useRef<HTMLDivElement>(null);
  const aiStreamRef = useRef<AbortController | null>(null);

  const scrollToBottom = () => setTimeout(() => { if (msgListRef.current) msgListRef.current.scrollTop = msgListRef.current.scrollHeight; }, 50);

  const loadChats = useCallback(async (p = 1, append = false) => {
    if (!activeBotKey) { setChats([]); return; }
    if (append) setLoadingMore(true); else setLoadingChats(true);
    try {
      const result = await getChats({ bot_key: activeBotKey, page: p, page_size: 20 }) as ChatListResponse;
      const list = result.chats || [];
      setChats((prev) => append ? [...prev, ...list] : list);
      setHasMore(list.length === 20);
      setPage(p);
    } catch (e) { message.error(String(e)); }
    finally { if (append) setLoadingMore(false); else setLoadingChats(false); }
  }, [activeBotKey]);

  const loadedOnce = useRef(false);
  useEffect(() => { if (!loadedOnce.current) { loadedOnce.current = true; loadChats(1); } }, [loadChats]);

  const handleSelectBot = async (key: string) => { selectBot(key); await loadChats(1); };

  const handleSelectChat = async (chatId: string) => {
    setLoadingDetail(true);
    try {
      const detail = await getChatDetail(chatId) as ChatDetailResponse;
      setActiveChat(detail.chat);
      setReplyMode(detail.chat?.reply_mode === 'ai' ? 'ai' : 'manual');
      scrollToBottom();
    } catch (e) { message.error(String(e)); }
    finally { setLoadingDetail(false); }
  };

  const handleDeleteSelected = async () => {
    setDeleting(true);
    try { await deleteChats(selectedIds); message.success('已删除'); setSelectedIds([]); loadChats(1); }
    catch (e) { message.error(String(e)); }
    finally { setDeleting(false); }
  };

  const handleSendReply = async () => {
    if (!manualReply.trim() && !attachments.length) return;
    if (!activeChat) return;
    setSending(true);
    try {
      if (attachments.length) {
        const fd = new FormData();
        fd.append('text', manualReply);
        attachments.forEach((f) => fd.append('files', f));
        await sendManualReply(activeChat.chat_id, fd);
      } else {
        await sendManualReply(activeChat.chat_id, { text: manualReply });
      }
      message.success('已发送');
      setManualReply('');
      setAttachments([]);
      handleSelectChat(activeChat.chat_id);
    } catch (e) { message.error(String(e)); }
    finally { setSending(false); }
  };

  const handleGenerateAi = async () => {
    if (!activeChat) return;
    setGeneratingAi(true);
    try {
      aiStreamRef.current?.abort();
      const controller = new AbortController();
      aiStreamRef.current = controller;
      const response = await generateAiDraftStream(activeChat.chat_id, {}, controller.signal);
      if (!response.ok) throw new Error('AI 生成失败');
      const reader = response.body?.getReader();
      if (!reader) throw new Error('No stream');
      const decoder = new TextDecoder();
      let draft = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        draft += decoder.decode(value, { stream: true });
        setManualReply(draft);
      }
    } catch (e: unknown) { if ((e as Error).name !== 'AbortError') message.error(String(e)); }
    finally { setGeneratingAi(false); }
  };

  const handleCancelAi = () => { aiStreamRef.current?.abort(); setGeneratingAi(false); };

  const handleCompress = async () => {
    if (!activeChat || compressing) return;
    setCompressing(true);
    try { await compressChatContext(activeChat.chat_id); message.success('上下文已压缩'); handleSelectChat(activeChat.chat_id); }
    catch (e) { message.error(String(e)); }
    finally { setCompressing(false); }
  };

  const handleLoadMore = () => { if (hasMore && !loadingMore) loadChats(page + 1, true); };

  const activeBotStatus = botStatuses[activeBotKey] || { running: false, pid: null };
  const canManualReply = !!activeChat && activeChat.conversation_status !== 'archived';
  const canUseAi = !!activeChat && activeBotStatus.running;

  const chatName = (c: Chat) => c.display_name || displayUserName(c.sender_name || c.sender_display_name, c.sender_id || c.chat_id) || '未知';

  return (
    <section>
      <Card className="panel" size="small" title={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>会话列表</span>
          <Button danger disabled={!selectedIds.length} loading={deleting} onClick={handleDeleteSelected}>删除选中 {selectedIds.length || ''}</Button>
        </div>
      } styles={{ body: { padding: 0, height: 'calc(100vh - 160px)', overflow: 'hidden' } }}>
        <div style={{ display: 'grid', gridTemplateColumns: '200px 300px minmax(0, 1fr)', height: '100%' }}>

          {/* Bot Column */}
          <div style={{ background: 'linear-gradient(180deg, #0f766e, #155e75 48%, #1d4ed8)', borderRight: '1px solid rgba(255,255,255,0.14)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ padding: '12px', color: '#e2f5f2', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
              BOT <strong style={{ display: 'block', fontSize: 14 }}>{bots.length} 个机器人</strong>
            </div>
            <div style={{ flex: 1, overflow: 'auto', padding: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {bots.map((bot) => {
                const status = botStatuses[bot.bot_key] || { running: false };
                return (
                  <button key={bot.bot_key}
                    onClick={() => handleSelectBot(bot.bot_key)}
                    style={{
                      display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 8, alignItems: 'center', width: '100%',
                      padding: 10, color: '#e2f5f2', textAlign: 'left', background: bot.bot_key === activeBotKey ? 'linear-gradient(135deg, rgba(255,255,255,0.18), rgba(96,165,250,0.28))' : 'rgba(255,255,255,0.08)',
                      border: `1px solid ${bot.bot_key === activeBotKey ? 'rgba(255,255,255,0.28)' : 'rgba(255,255,255,0.12)'}`,
                      borderRadius: 10, cursor: 'pointer', fontSize: 13, borderWidth: 0, fontFamily: 'inherit',
                      position: 'relative' as const,
                    }}>
                    <span style={{ width: 10, height: 10, borderRadius: '50%', background: status.running ? '#22c55e' : '#94a3b8', boxShadow: status.running ? '0 0 0 2px rgba(34,197,94,0.25)' : 'none' }} />
                    <strong style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{String(bot.name || bot.bot_key)}</strong>
                    {(bot as Bot).unread_total ? <span style={{ position: 'absolute', right: 6, top: 6, background: '#ef4444', color: '#fff', fontSize: 10, fontWeight: 700, borderRadius: 10, padding: '1px 6px', minWidth: 18, textAlign: 'center' }}>{((bot as Bot).unread_total || 0) > 99 ? '99+' : (bot as Bot).unread_total}</span> : null}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Conversation List */}
          <div style={{ borderRight: '1px solid #e5e7eb', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#fff' }}>
            <div style={{ padding: '12px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div><span style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' }}>消息列表</span>
                <strong style={{ display: 'block', fontSize: 14 }}>{chats.length} 个会话</strong></div>
              <Button size="small" onClick={() => activeBotKey && markAllBotChatsRead(activeBotKey).then(() => loadChats(1))}>批量已读</Button>
            </div>
            <div style={{ flex: 1, overflow: 'auto' }} onScroll={(e) => { const t = e.currentTarget; if (t.scrollHeight - t.scrollTop <= t.clientHeight + 50) handleLoadMore(); }}>
              {loadingChats ? <div style={{ padding: 24, textAlign: 'center' }}><LoadingOutlined /> 加载中...</div> :
                chats.length === 0 ? <Empty description="暂无会话" /> :
                  chats.map((chat) => (
                    <div key={chat.chat_id}
                      onClick={() => { handleSelectChat(chat.chat_id); if (chat.unread_count) markChatRead(chat.chat_id); }}
                      style={{
                        padding: '12px', cursor: 'pointer', borderBottom: '1px solid #f0f0f0',
                        background: chat.chat_id === activeChat?.chat_id ? '#eff6ff' : selectedIds.includes(chat.chat_id) ? '#fef3c7' : 'transparent',
                        display: 'flex', gap: 10, alignItems: 'flex-start',
                      }}>
                      <input type="checkbox" checked={selectedIds.includes(chat.chat_id)} onChange={(e) => {
                        e.stopPropagation();
                        setSelectedIds((p) => e.target.checked ? [...p, chat.chat_id] : p.filter((id) => id !== chat.chat_id));
                      }} style={{ marginTop: 4 }} />
                      <Avatar src={conversationAvatar(chat)} size={36} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <strong style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{chatName(chat)}</strong>
                          <span style={{ fontSize: 11, color: '#9ca3af' }}>{chat.last_message_at ? formatTime(chat.last_message_at).slice(11, 19) : ''}</span>
                        </div>
                        <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
                          {chat.chat_type === 'group' ? '群聊' : '用户'}
                          {chat.conversation_status === 'archived' && <Tag color="default" style={{ marginLeft: 4, fontSize: 10 }}>已归档</Tag>}
                          {chat.unread_count ? <Tag color="red" style={{ marginLeft: 4, fontSize: 10 }}>{chat.unread_count}</Tag> : null}
                        </div>
                      </div>
                    </div>
                  ))}
            </div>
          </div>

          {/* Thread Panel */}
          <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#fafbfc' }}>
            <div style={{ padding: '12px 16px', borderBottom: '1px solid #e5e7eb', background: '#fff' }}>
              {editingName && activeChat ? (
                <Input size="small" value={editNameVal} onChange={(e) => setEditNameVal(e.target.value)}
                  onBlur={async () => { setEditingName(false); if (editNameVal.trim() && editNameVal.trim() !== activeChat.display_name) { await updateChatDisplayName(activeChat.chat_id, editNameVal.trim()); loadChats(1); } }}
                  onPressEnter={async () => { setEditingName(false); if (editNameVal.trim() && editNameVal.trim() !== activeChat.display_name) { await updateChatDisplayName(activeChat.chat_id, editNameVal.trim()); loadChats(1); } }}
                  autoFocus />
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <p style={{ margin: 0, color: '#3b82f6', fontSize: 11, fontWeight: 700, textTransform: 'uppercase' }}>Current Chat</p>
                  <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600, flex: 1 }}>
                    {activeChat ? chatName(activeChat) : '未选择会话'}
                  </h2>
                  {activeChat && <Button size="small" type="text" icon={<EditOutlined />} onClick={() => { setEditNameVal(activeChat.display_name || ''); setEditingName(true); }} />}
                </div>
              )}
            </div>

            {/* Context Meter */}
            {activeChat && (
              <div style={{ padding: '8px 16px', background: '#fff', borderBottom: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: 12, whiteSpace: 'nowrap' }}>上下文 {activeChat.context?.used_chars || 0} / {activeChat.context?.limit_chars || 0}</span>
                <Progress percent={Math.min(100, Math.round(((activeChat.context?.used_chars || 0) / Math.max(1, activeChat.context?.limit_chars || 1)) * 1000) / 10)}
                  size="small" style={{ flex: 1, margin: 0 }} showInfo={false} />
                <Tooltip title={activeChat.conversation_status === 'archived' ? '已归档会话不能压缩' : ''}>
                  <Button size="small" icon={<CompressOutlined />} loading={compressing}
                    disabled={activeChat.conversation_status === 'archived' || compressing}
                    onClick={handleCompress}>手动压缩</Button>
                </Tooltip>
              </div>
            )}

            {/* Messages */}
            <div ref={msgListRef} style={{ flex: 1, overflow: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
              {loadingDetail ? <Empty description="加载中..." /> :
                !activeChat ? <Empty description="选择左侧会话后查看消息。" /> :
                  !activeChat.messages?.length ? <Empty description="该会话暂无消息。" /> :
                    activeChat.messages.map((msg) => (
                      <div key={msg.id} style={{ display: 'flex', gap: 10, maxWidth: '80%', alignSelf: msg.direction === 'user' ? 'flex-end' : 'flex-start', flexDirection: msg.direction === 'user' ? 'row-reverse' : 'row' }}>
                        <Avatar src={msg.direction === 'user' ? '/avatars/user.svg' : '/avatars/me.svg'} size={32} />
                        <div>
                          <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 2, textAlign: msg.direction === 'user' ? 'right' : 'left' }}>
                            {msg.sender_display_name || displayUserName(msg.sender_name, msg.sender_id)}
                            <span style={{ marginLeft: 6 }}>{formatTime(msg.created_at)}</span>
                            {msg.reply_source && <Tag style={{ marginLeft: 4, fontSize: 10 }} color={msg.reply_source === 'manual' ? 'blue' : 'green'}>{msg.reply_source === 'manual' ? '手动' : 'AI'}</Tag>}
                            {msg.feedback && <Tag style={{ fontSize: 10 }} color={msg.feedback.result === 'useful' ? 'green' : msg.feedback.result === 'useless' ? 'red' : 'orange'}>{msg.feedback.result === 'useful' ? '有效' : msg.feedback.result === 'useless' ? '无效' : '有争议'}</Tag>}
                          </div>
                          <div style={{
                            padding: '10px 14px', borderRadius: 12, fontSize: 14, lineHeight: 1.6, wordBreak: 'break-word',
                            background: msg.direction === 'user' ? '#eff6ff' : '#f3f4f6',
                            border: msg.direction === 'user' ? '1px solid #dbeafe' : '1px solid #e5e7eb',
                          }}>
                            {/* Render message parts */}
                            {(msg.metadata?.parts || []).length > 0 ? msg.metadata!.parts!.map((part, i) => {
                              if (part.type === 'text') return <div key={i}>{part.text}</div>;
                              if (part.type === 'image' && part.url) return <img key={i} src={part.url} alt="" style={{ maxWidth: 200, borderRadius: 8 }} />;
                              if (part.type === 'file') return <div key={i} style={{ padding: '8px 12px', background: '#fff', borderRadius: 8, marginTop: 4, border: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', gap: 8 }}>
                                <Tag>{part.mime_type?.split('/')[0]?.toUpperCase() || 'FILE'}</Tag>
                                <span style={{ fontSize: 12 }}>{part.filename}</span>
                              </div>;
                              return null;
                            }) : <div>{msg.content}</div>}
                          </div>
                        </div>
                      </div>
                    ))}
            </div>

            {/* Reply Composer */}
            {activeChat && activeChat.conversation_status !== 'archived' && (
              <div style={{ padding: '12px 16px', borderTop: '1px solid #e5e7eb', background: '#fff' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <span style={{ fontSize: 12 }}>回复模式:</span>
                  <Switch checked={replyMode === 'ai'} onChange={(v) => setReplyMode(v ? 'ai' : 'manual')}
                    checkedChildren="AI" unCheckedChildren="手动" />
                  {replyMode === 'ai' && (
                    <Space size={4}>
                      <Button size="small" type="primary" icon={<RobotOutlined />} loading={generatingAi} onClick={handleGenerateAi}
                        disabled={!canUseAi}>生成 AI 回复</Button>
                      {generatingAi && <Button size="small" danger onClick={handleCancelAi}>取消</Button>}
                    </Space>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Input.TextArea value={manualReply} onChange={(e) => setManualReply(e.target.value)}
                    placeholder={replyMode === 'ai' ? '先生成 AI 回复，或直接手动输入...' : '输入回复内容...'}
                    rows={3} disabled={!canManualReply}
                    onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); handleSendReply(); } }} />
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <Upload showUploadList={false} multiple beforeUpload={(file) => { setAttachments((p) => [...p, file]); return false; }}>
                      <Button icon={<PaperClipOutlined />} title="添加附件" />
                    </Upload>
                    <Button type="primary" icon={<SendOutlined />} loading={sending} onClick={handleSendReply} disabled={!manualReply.trim() && !attachments.length}>
                      发送
                    </Button>
                  </div>
                </div>
                {attachments.length > 0 && (
                  <div style={{ marginTop: 6, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {attachments.map((f, i) => (
                      <Tag key={i} closable onClose={() => setAttachments((p) => p.filter((_, j) => j !== i))}>{f.name}</Tag>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </Card>
    </section>
  );
}
