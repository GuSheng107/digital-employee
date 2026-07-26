import { useEffect, useState, useCallback, useRef } from 'react';
import { Card, Button, Switch, Tag, Modal, Upload, Input, Divider, message, Space, Empty } from 'antd';
import { PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined, ThunderboltOutlined, UploadOutlined } from '@ant-design/icons';
import { getSkills, uploadSkills as uploadSkillsApi, parseSkills, setSkillEnabled, deleteSkill } from '@/api/skills';
import type { UploadFile } from 'antd';

interface Skill {
  name: string;
  display_name?: string;
  description?: string;
  enabled: boolean;
  scope?: string;
  is_bound_to_bot?: boolean;
  mounted_bot_count?: number;
  mounted_bot_names?: string[];
  relative_path?: string;
}

export default function SkillsConfigView() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [parsedSkills, setParsedSkills] = useState<Skill[]>([]);
  const [editOpen, setEditOpen] = useState(false);
  const [editingSkill, setEditingSkill] = useState<Skill | null>(null);
  const [editName, setEditName] = useState('');

  const sortedSkills = [...skills].sort((a, b) => {
    if (a.scope === 'system' && b.scope !== 'system') return -1;
    if (a.scope !== 'system' && b.scope === 'system') return 1;
    return 0;
  });

  const loadSkills = useCallback(async () => {
    setLoading(true);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result: any = await getSkills();
      setSkills(result.skills || []);
    } catch (e) { message.error(String(e)); }
    finally { setLoading(false); }
  }, []);

  const didMount = useRef(false);
  useEffect(() => {
    if (!didMount.current) { didMount.current = true; loadSkills(); }
  }, [loadSkills]);

  const handleRefresh = async () => { await loadSkills(); message.success('Skills 已刷新'); };

  const handleFileChange = async (file: UploadFile) => {
    const raw = file as unknown as { originFileObj?: File };
    if (raw.originFileObj) {
      if (!raw.originFileObj.name.toLowerCase().endsWith('.zip')) {
        message.error('只支持上传 zip 文件');
        return;
      }
      setSelectedFile(raw.originFileObj);
      setUploading(true);
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const result: any = await parseSkills(raw.originFileObj);
        setParsedSkills((result.skills || []).map((s: Skill) => ({
          ...s, display_name: s.display_name || s.name,
        })));
      } catch { setParsedSkills([]); }
      finally { setUploading(false); }
    }
  };

  const handleSave = async () => {
    if (!selectedFile || !parsedSkills.length) return;
    setSaving(true);
    try {
      const displayNames: Record<string, string> = {};
      parsedSkills.forEach((s) => { displayNames[s.name] = (s.display_name || s.name).trim() || s.name; });
      await uploadSkillsApi(selectedFile, displayNames, 'new');
      message.success('技能已上传并保存');
      setUploadOpen(false);
      setSelectedFile(null);
      setParsedSkills([]);
      await loadSkills();
    } finally { setSaving(false); }
  };

  const handleToggle = async (skill: Skill, enabled: boolean) => {
    await setSkillEnabled(skill.name, enabled);
    message.success(enabled ? '技能已启用' : '技能已禁用');
    await loadSkills();
  };

  const handleDelete = async (skill: Skill) => {
    Modal.confirm({
      title: '删除确认',
      content: `确定要删除技能「${skill.display_name || skill.name}」吗？`,
      okText: '确定', cancelText: '取消', okButtonProps: { danger: true },
      onOk: async () => {
        await deleteSkill(skill.name);
        message.success('技能已删除');
        await loadSkills();
      },
    });
  };

  const openEdit = (skill: Skill) => {
    setEditingSkill(skill);
    setEditName(skill.display_name || skill.name);
    setEditOpen(true);
  };

  const saveEdit = async () => {
    if (!editingSkill) return;
    await uploadSkillsApi(null, { [editingSkill.name]: editName.trim() || editingSkill.name }, 'edit', editingSkill.name);
    message.success('技能名称已保存');
    setEditOpen(false);
    await loadSkills();
  };

  const isSystem = (s: Skill) => s.scope === 'system';

  return (
    <section>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ margin: 0 }}>Skills 配置</h2>
        <Space>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={handleRefresh}>刷新技能</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { setUploadOpen(true); setSelectedFile(null); setParsedSkills([]); }}>
            新增技能
          </Button>
        </Space>
      </div>

      {sortedSkills.length === 0 ? (
        <Empty description="暂无技能，请点击「新增技能」上传 zip 文件" image={<ThunderboltOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />} />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
          {sortedSkills.map((skill) => (
            <Card key={skill.name} hoverable size="small"
              title={<>
                <div style={{ fontWeight: 600, fontSize: 15 }}>{skill.display_name || skill.name}</div>
                <div style={{ fontSize: 12, color: '#9ca3af', fontFamily: 'monospace' }}>{skill.name}</div>
              </>}
              extra={<Space>
                {isSystem(skill) && <Tag color="orange">系统</Tag>}
                {skill.mounted_bot_count ? <Tag color="red">Mounted {skill.mounted_bot_count}</Tag> : null}
                <Switch checked={skill.enabled} disabled={isSystem(skill) || (skill.is_bound_to_bot && skill.enabled)}
                  onChange={(v) => handleToggle(skill, v)} />
              </Space>}
              actions={[
                <Button key="edit" type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(skill)}>
                  {isSystem(skill) ? '查看' : '编辑'}
                </Button>,
                <Button key="delete" type="link" danger size="small" icon={<DeleteOutlined />}
                  disabled={isSystem(skill)} onClick={() => handleDelete(skill)}>
                  删除
                </Button>,
              ]}>
              <p style={{ color: '#6b7280', fontSize: 14 }}>{skill.description || '暂无描述'}</p>
            </Card>
          ))}
        </div>
      )}

      {/* Upload Dialog */}
      <Modal title="新增技能" open={uploadOpen} onCancel={() => setUploadOpen(false)} width={600}
        footer={[
          <Button key="cancel" onClick={() => setUploadOpen(false)} disabled={uploading || saving}>取消</Button>,
          <Button key="save" type="primary" loading={saving} disabled={!parsedSkills.length || uploading} onClick={handleSave}>确认保存</Button>,
        ]}>
        <Upload.Dragger accept=".zip" showUploadList={false} beforeUpload={(file) => { handleFileChange({ uid: '-1', name: file.name } as UploadFile); return false; }}
          disabled={uploading || saving}>
          <UploadOutlined style={{ fontSize: 36, color: '#3b82f6' }} />
          <p>将 zip 文件拖到此处，或<em>点击上传</em></p>
        </Upload.Dragger>

        {parsedSkills.length > 0 && (
          <>
            <Divider>解析结果 — 共找到 {parsedSkills.length} 个技能文件</Divider>
            {parsedSkills.map((skill) => (
              <div key={skill.relative_path || skill.name} style={{ marginBottom: 12, padding: 12, background: '#f9fafb', borderRadius: 8 }}>
                <div style={{ marginBottom: 8 }}><label style={{ fontSize: 12, color: '#6b7280' }}>技能名称</label>
                  <Input value={skill.display_name} onChange={(e) => {
                    setParsedSkills((prev) => prev.map((s) => s.name === skill.name ? { ...s, display_name: e.target.value } : s));
                  }} placeholder="请输入技能显示名称" />
                </div>
                <div style={{ marginBottom: 8 }}><label style={{ fontSize: 12, color: '#6b7280' }}>原始标识</label>
                  <Input value={skill.name} readOnly />
                </div>
                <div><label style={{ fontSize: 12, color: '#6b7280' }}>技能描述</label>
                  <Input.TextArea value={skill.description || '暂无描述'} readOnly rows={2} />
                </div>
              </div>
            ))}
          </>
        )}
      </Modal>

      {/* Edit Dialog */}
      <Modal title={isSystem(editingSkill!) ? '查看技能' : '编辑技能'} open={editOpen} onCancel={() => setEditOpen(false)} width={520}
        footer={[
          <Button key="close" onClick={() => setEditOpen(false)}>关闭</Button>,
          !isSystem(editingSkill!) && <Button key="save" type="primary" onClick={saveEdit}>保存</Button>,
        ]}>
        {editingSkill && (
          <>
            <div style={{ marginBottom: 12 }}><label style={{ fontSize: 12, color: '#6b7280' }}>技能名称</label>
              <Input value={editName} maxLength={100} showCount disabled={isSystem(editingSkill)}
                onChange={(e) => setEditName(e.target.value)} />
            </div>
            <div style={{ marginBottom: 12 }}><label style={{ fontSize: 12, color: '#6b7280' }}>原始标识</label>
              <Input value={editingSkill.name} readOnly />
            </div>
            <div><label style={{ fontSize: 12, color: '#6b7280' }}>技能描述</label>
              <Input.TextArea value={editingSkill.description || '暂无描述'} readOnly rows={4} />
            </div>
          </>
        )}
      </Modal>
    </section>
  );
}
