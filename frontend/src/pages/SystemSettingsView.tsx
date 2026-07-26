import { useEffect, useState, useCallback } from 'react';
import { Card, Button, InputNumber, Switch, Select, message, Space, Divider, Table, Upload, Row, Col } from 'antd';
import { SaveOutlined, DeleteOutlined, UploadOutlined, ReloadOutlined } from '@ant-design/icons';
import { getPlatformSettings, savePlatformSettings as saveSettings, getDocuments, getDocumentsConfig, uploadDocuments, deleteDocument, downloadDocumentBlob } from '@/api/system';
import { getBots, restoreDeletedBots } from '@/api/bots';
import { formatBytes } from '@/utils/format';
import type { ColumnsType } from 'antd/es/table';

interface DocItem { id: string; filename: string; size: number; created_at: string; status: string; }

function SettingField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="settings-section" style={{ marginBottom: 16 }}>
      <div className="settings-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong>{label}</strong>
        <div>{children}</div>
      </div>
    </div>
  );
}

function SettingSwitch({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="settings-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
      <span><strong>{label}</strong></span>
      <Switch checked={checked} onChange={onChange} />
    </div>
  );
}

export default function SystemSettingsView() {
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);
  const [deletedBots, setDeletedBots] = useState<Array<{ bot_key: string; name: string; deleted_at: string }>>([]);
  const [restoring, setRestoring] = useState(false);
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [docConfig, setDocConfig] = useState({ allowed_extensions: ['.doc', '.docx', '.txt', '.md', '.json', '.csv'], max_file_size: 10 * 1024 * 1024, max_characters: 5000 });

  const loadSettings = useCallback(async () => {
    try { const s: unknown = await getPlatformSettings(); setSettings(s as Record<string, unknown> || {}); } catch (e) { message.error(String(e)); }
  }, []);
  const loadDeletedBots = useCallback(async () => {
    try { const r: unknown = await getBots({ include_deleted: true }); setDeletedBots((r as { bots?: Array<{ bot_key: string; name: string; deleted_at: string; is_deleted: boolean }> })?.bots?.filter((b) => b.is_deleted) || []); } catch { /* ignore */ }
  }, []);
  const loadDocs = useCallback(async () => {
    try { const r: unknown = await getDocuments(); setDocs((r as { documents?: DocItem[] })?.documents || []); } catch { /* ignore */ }
  }, []);
  const loadDocConfig = useCallback(async () => {
    try { const c: unknown = await getDocumentsConfig(); if (c) setDocConfig(c as typeof docConfig); } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadSettings(); loadDeletedBots(); loadDocs(); loadDocConfig(); }, []); // eslint-disable-line

  const setField = (key: string, value: unknown) => setSettings((s) => ({ ...s, [key]: value }));

  const handleSave = async () => { setSaving(true); try { await saveSettings(settings); message.success('设置已保存'); } catch (e) { message.error(String(e)); } finally { setSaving(false); } };
  const handleRestore = async () => { setRestoring(true); try { await restoreDeletedBots(deletedBots.map((b) => b.bot_key)); message.success('Bot 已恢复'); loadDeletedBots(); } catch (e) { message.error(String(e)); } finally { setRestoring(false); } };
  const handleUpload = async (file: File) => { setUploading(true); try { await uploadDocuments([file]); message.success('文档已上传'); loadDocs(); } catch (e) { message.error(String(e)); } finally { setUploading(false); } return false; };
  const handleDeleteDoc = async (id: string) => { await deleteDocument(id); message.success('已删除'); loadDocs(); };
  const handleDownload = async (doc: DocItem) => { try { const blob = await downloadDocumentBlob(doc.id); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = doc.filename; a.click(); URL.revokeObjectURL(url); } catch (e) { message.error(String(e)); } };

  const docColumns: ColumnsType<DocItem> = [
    { title: '文件名', dataIndex: 'filename', ellipsis: true },
    { title: '大小', dataIndex: 'size', width: 100, render: (v: number) => formatBytes(v) },
    { title: '状态', dataIndex: 'status', width: 80 },
    { title: '上传时间', dataIndex: 'created_at', width: 160, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
    { title: '操作', width: 160, render: (_, r) => (
      <Space><Button size="small" type="link" onClick={() => handleDownload(r)}>下载</Button>
        <Button size="small" type="link" danger icon={<DeleteOutlined />} onClick={() => handleDeleteDoc(r.id)}>删除</Button></Space>
    )},
  ];

  return (
    <section>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ margin: 0 }}>系统设置</h2>
        <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>保存设置</Button>
      </div>

      <Row gutter={[24, 24]}>
        <Col xs={24} lg={12}>
          <Card className="panel" title="通用设置" size="small">
            <SettingField label="日志级别">
              <Select value={String(settings.logging_level || 'INFO')} style={{ width: 280 }} onChange={(v) => setField('logging_level', v)}
                options={['DEBUG', 'INFO', 'WARNING', 'ERROR'].map((val) => ({ value: val, label: val }))} />
            </SettingField>
            <SettingField label="上下文长度限制">
              <InputNumber value={Number(settings.context_length_limit) || undefined} style={{ width: 280 }} onChange={(v) => setField('context_length_limit', v)} />
            </SettingField>
            <SettingField label="平台 Agent 超时(秒)">
              <InputNumber value={Number(settings.platform_agent_timeout_seconds) || undefined} style={{ width: 280 }} onChange={(v) => setField('platform_agent_timeout_seconds', v)} />
            </SettingField>
            <SettingField label="平台 Agent 最大迭代">
              <InputNumber value={Number(settings.platform_agent_max_iterations) || undefined} style={{ width: 280 }} onChange={(v) => setField('platform_agent_max_iterations', v)} />
            </SettingField>
            <SettingField label="文档最大字符数">
              <InputNumber value={Number(settings.document_max_characters) || 5000} style={{ width: 280 }} onChange={(v) => setField('document_max_characters', v)} />
            </SettingField>
            <SettingField label="记忆更新最大条目">
              <InputNumber value={Number(settings.memory_update_max_pairs) || 100} style={{ width: 280 }} onChange={(v) => setField('memory_update_max_pairs', v)} />
            </SettingField>
            <SettingField label="线程池最大工作数">
              <InputNumber value={Number(settings.thread_pool_max_workers) || undefined} style={{ width: 280 }} onChange={(v) => setField('thread_pool_max_workers', v)} />
            </SettingField>
            <Divider />
            <SettingSwitch label="附件回复" checked={Boolean(settings.attachment_reply)} onChange={(v) => setField('attachment_reply', v)} />
            <SettingSwitch label="游客账号" checked={Boolean(settings.guest_account_enabled)} onChange={(v) => setField('guest_account_enabled', v)} />
            <SettingSwitch label="反馈告警" checked={Boolean(settings.feedback_alert_enabled)} onChange={(v) => setField('feedback_alert_enabled', v)} />
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card className="panel" title="文档管理" size="small"
            extra={<Upload showUploadList={false} beforeUpload={(f) => { handleUpload(f); return false; }}><Button icon={<UploadOutlined />} loading={uploading}>上传文档</Button></Upload>}>
            <Table<DocItem> columns={docColumns} dataSource={docs} rowKey="id" size="small" pagination={{ pageSize: 10 }} />
            {docConfig.allowed_extensions && <p style={{ fontSize: 12, color: '#9ca3af', marginTop: 8 }}>允许格式: {docConfig.allowed_extensions.join(', ')} · 最大: {formatBytes(docConfig.max_file_size)}</p>}
          </Card>

          <Card className="panel" title={`已删除 Bot (${deletedBots.length})`} size="small" style={{ marginTop: 24 }}>
            {deletedBots.length === 0 ? <p style={{ color: '#9ca3af' }}>无已删除 Bot</p> : (
              <>
                {deletedBots.map((bot) => (
                  <div key={bot.bot_key} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                    <span><strong>{bot.name}</strong> <span style={{ color: '#9ca3af', fontSize: 12 }}>{bot.deleted_at ? new Date(bot.deleted_at).toLocaleString('zh-CN') : ''}</span></span>
                  </div>
                ))}
                <Button type="primary" icon={<ReloadOutlined />} loading={restoring} onClick={handleRestore} style={{ marginTop: 12 }}>恢复所有已删除 Bot</Button>
              </>
            )}
          </Card>
        </Col>
      </Row>
    </section>
  );
}
