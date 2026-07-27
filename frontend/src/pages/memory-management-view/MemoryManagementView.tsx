import { useEffect, useState, useCallback, useRef } from 'react';
import { Table, Tag, Button, Modal, Input, Select, Tabs, Space, message, Empty, Popconfirm, Row, Col } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, EyeOutlined, ReloadOutlined } from '@ant-design/icons';
import { getMemoryFiles, getMemoryItems, addMemoryItem, updateMemoryItem, deleteMemoryItem, searchMemory, getMemoryReviews, getMemoryReviewContent, deleteMemoryReview } from '@/api/system';
import { formatTime } from '@/utils/format';
import type { ColumnsType } from 'antd/es/table';

interface MemoryItem {
  id: string;
  content: string;
  content_type?: string;
  priority?: number;
  source?: string;
  source_id?: string;
  speed_lookup?: string;
  created_at?: string;
  _file_key?: string;
  _score?: number;
  _isSearchResult?: boolean;
}

interface MemoryFile {
  file_key: string;
  label: string;
  item_count?: number;
}

interface Review {
  filename: string;
  created_at?: string;
  status?: string;
}

function ctColor(ct?: string) {
  const m: Record<string, string> = { problem_solution: 'red', qa: 'green', term_definition: 'blue', operation_guide: 'orange', configuration: 'default', process: 'red', rule: 'orange', fact: 'blue', preference: 'green' };
  return m[ct || ''] || 'default';
}

function priorityLabel(p?: number) {
  if (p == null) return '-';
  if (p >= 10) return '紧急';
  if (p >= 6) return '高';
  if (p >= 3) return '中';
  return '低';
}

function priorityColor(p?: number) {
  if (p == null) return 'default';
  if (p >= 10) return 'red';
  if (p >= 6) return 'orange';
  if (p >= 3) return 'default';
  return 'default';
}

export default function MemoryManagementView() {
  const [files, setFiles] = useState<MemoryFile[]>([]);
  const [selectedFile, setSelectedFile] = useState('');
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [loadingItems, setLoadingItems] = useState(false);
  const [searchQ, setSearchQ] = useState('');
  const [searchResults, setSearchResults] = useState<MemoryItem[]>([]);
  const [isSearchMode, setIsSearchMode] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogMode, setDialogMode] = useState<'add' | 'edit' | 'view'>('view');
  const [dialogForm, setDialogForm] = useState<MemoryItem>({ id: '', content: '', content_type: 'fact', priority: 4, source: '', speed_lookup: '' });
  const [dialogSaving, setDialogSaving] = useState(false);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [reviewContent, setReviewContent] = useState('');
  const [reviewOpen, setReviewOpen] = useState(false);

  const fileGroups = (() => {
    const core: MemoryFile[] = [], timeline: MemoryFile[] = [], documents: MemoryFile[] = [];
    files.forEach((f) => {
      if (f.file_key.startsWith('documents/')) documents.push(f);
      else if (f.file_key.startsWith('timeline/')) timeline.push(f);
      else core.push(f);
    });
    return [
      ...(core.length ? [{ key: 'core', label: '核心记忆', files: core }] : []),
      ...(timeline.length ? [{ key: 'timeline', label: '时间线', files: timeline }] : []),
      ...(documents.length ? [{ key: 'documents', label: '文档记忆', files: documents }] : []),
    ];
  })();

  const loadFiles = useCallback(async () => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result: any = await getMemoryFiles();
      const fls = result.files || [];
      setFiles(fls);
      if ((!selectedFile || !fls.some((f: MemoryFile) => f.file_key === selectedFile)) && fls.length) {
        setSelectedFile(fls[0].file_key);
      }
    } catch (e) { message.error(String(e)); }
  }, [selectedFile]);

  const loadItems = useCallback(async () => {
    if (!selectedFile) { setItems([]); return; }
    setLoadingItems(true);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result: any = await getMemoryItems(selectedFile);
      setItems(result.items || []);
    } catch (e) { message.error(String(e)); }
    finally { setLoadingItems(false); }
  }, [selectedFile]);

  useEffect(() => { loadFiles(); }, []); // eslint-disable-line

  const itemsMounted = useRef(false);
  useEffect(() => {
    if (!isSearchMode) {
      itemsMounted.current = true;
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadItems();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFile, isSearchMode]);

  const handleSearch = async () => {
    const q = searchQ.trim();
    if (!q) { setIsSearchMode(false); setSearchResults([]); return; }
    setSearchLoading(true); setIsSearchMode(true);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result: any = await searchMemory(q, selectedFile || '');
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      setSearchResults((result.results || []).map((r: any) => ({ ...r.item, _file_key: r.file_key, _score: r.score, _isSearchResult: true })));
    } catch (e) { message.error(String(e)); }
    finally { setSearchLoading(false); }
  };

  const displayItems = isSearchMode ? searchResults : items;

  const openAdd = () => {
    setDialogMode('add');
    setDialogForm({ id: '', content: '', content_type: 'fact', priority: 4, source: '', speed_lookup: '', _file_key: selectedFile });
    setDialogOpen(true);
  };

  const openView = (item: MemoryItem) => { setDialogMode('view'); setDialogForm(item); setDialogOpen(true); };
  const openEdit = (item: MemoryItem) => { setDialogMode('edit'); setDialogForm(item); setDialogOpen(true); };

  const handleSave = async () => {
    if (!dialogForm.content?.trim()) { message.warning('记忆内容不能为空'); return; }
    setDialogSaving(true);
    try {
      if (dialogMode === 'add') {
        await addMemoryItem(selectedFile, dialogForm as unknown as Record<string, unknown>);
        message.success('记忆已添加');
      } else {
        await updateMemoryItem(dialogForm._file_key || selectedFile, dialogForm.id, dialogForm as unknown as Record<string, unknown>);
        message.success('记忆已更新');
      }
      setDialogOpen(false);
      loadItems();
    } catch (e) { message.error(String(e)); }
    finally { setDialogSaving(false); }
  };

  const handleDelete = async (item: MemoryItem) => {
    await deleteMemoryItem(item._file_key || selectedFile, item.id);
    message.success('记忆已删除');
    loadItems();
  };

  const loadReviews = async () => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result: any = await getMemoryReviews();
      setReviews(result.reviews || []);
    } catch (e) { message.error(String(e)); }
  };

  const viewReview = async (filename: string) => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result: any = await getMemoryReviewContent(filename);
      setReviewContent(result.content || String(result));
      setReviewOpen(true);
    } catch (e) { message.error(String(e)); }
  };

  const handleDeleteReview = async (filename: string) => {
    await deleteMemoryReview(filename);
    message.success('审核报告已删除');
    loadReviews();
  };

  const columns: ColumnsType<MemoryItem> = [
    { title: 'ID', dataIndex: 'id', width: 60, responsive: ['md'] },
    { title: '类型', dataIndex: 'content_type', width: 90, render: (v: string) => <Tag color={ctColor(v)}>{v || '-'}</Tag> },
    { title: '内容', dataIndex: 'content', ellipsis: true, render: (v: string) => v?.length > 120 ? v.slice(0, 120) + '...' : v },
    { title: '优先级', dataIndex: 'priority', width: 80, render: (v: number) => <Tag color={priorityColor(v)}>{priorityLabel(v)}</Tag> },
    { title: '操作', width: 160, render: (_, r) => (
      <Space>
        <Button size="small" type="link" icon={<EyeOutlined />} onClick={() => openView(r)}>查看</Button>
        <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEdit(r)}>编辑</Button>
        <Popconfirm title="确定删除此记忆？" onConfirm={() => handleDelete(r)}><Button size="small" type="link" danger icon={<DeleteOutlined />} /></Popconfirm>
      </Space>
    )},
  ];

  return (
    <section>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>记忆管理</h2>
        <Space>
          <Input.Search value={searchQ} onChange={(e) => setSearchQ(e.target.value)} onSearch={handleSearch} placeholder="搜索记忆内容" style={{ width: 240 }} loading={searchLoading} />
          {isSearchMode && <Button onClick={() => { setSearchQ(''); setIsSearchMode(false); }}>清除</Button>}
          <Button icon={<ReloadOutlined />} onClick={() => { loadFiles(); loadItems(); }}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openAdd} disabled={!selectedFile}>新增记忆</Button>
        </Space>
      </div>

      <Tabs defaultActiveKey="items" onChange={(key) => { if (key === 'reviews') loadReviews(); }} items={[
        {
          key: 'items', label: '记忆条目',
          children: (
            <Row gutter={16}>
              <Col xs={24} md={6}>
                <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13, color: '#6b7280' }}>记忆文件</div>
                {fileGroups.map((group) => (
                  <div key={group.key} style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#9ca3af', marginBottom: 4 }}>{group.label}</div>
                    {group.files.map((f) => (
                      <div key={f.file_key} onClick={() => setSelectedFile(f.file_key)}
                        style={{ padding: '6px 10px', cursor: 'pointer', borderRadius: 6, fontSize: 13, background: selectedFile === f.file_key ? '#eff6ff' : 'transparent', color: selectedFile === f.file_key ? '#3b82f6' : '#374151', fontWeight: selectedFile === f.file_key ? 600 : 400, marginBottom: 2 }}>
                        {f.label} <span style={{ color: '#9ca3af', fontSize: 11 }}>({f.item_count || 0})</span>
                      </div>
                    ))}
                  </div>
                ))}
              </Col>
              <Col xs={24} md={18}>
                <Table<MemoryItem> columns={columns} dataSource={displayItems}
                  rowKey={(r) => `${r._file_key || ''}:${r.id}`}
                  loading={loadingItems || searchLoading} size="small" scroll={{ x: 700 }}
                  locale={{ emptyText: <Empty description="暂无记忆条目" /> }}
                  pagination={{ pageSize: 20, showSizeChanger: true }} />
              </Col>
            </Row>
          ),
        },
        {
          key: 'reviews', label: '审核报告',
          children: reviews.length === 0 ? <Empty description="暂无审核报告" /> : (
            <Table<Review> dataSource={reviews} rowKey="filename" size="small"
              columns={[
                { title: '文件名', dataIndex: 'filename', ellipsis: true },
                { title: '状态', dataIndex: 'status', width: 100, render: (v: string) => <Tag>{v || '-'}</Tag> },
                { title: '创建时间', dataIndex: 'created_at', width: 180, render: (v: string) => formatTime(v) },
                { title: '操作', width: 160, render: (_, r) => (
                  <Space>
                    <Button size="small" type="link" onClick={() => viewReview(r.filename)}>查看</Button>
                    <Popconfirm title="确定删除？" onConfirm={() => handleDeleteReview(r.filename)}><Button size="small" type="link" danger>删除</Button></Popconfirm>
                  </Space>
                )},
              ]} pagination={{ pageSize: 20 }} />
          ),
        },
      ]} />

      {/* Add/Edit/View Dialog */}
      <Modal title={dialogMode === 'add' ? '新增记忆' : dialogMode === 'edit' ? '编辑记忆' : '查看记忆'}
        open={dialogOpen} onCancel={() => setDialogOpen(false)} width={640}
        footer={dialogMode === 'view' ? [<Button key="close" onClick={() => setDialogOpen(false)}>关闭</Button>] : [
          <Button key="cancel" onClick={() => setDialogOpen(false)}>取消</Button>,
          <Button key="save" type="primary" loading={dialogSaving} onClick={handleSave}>保存</Button>,
        ]}>
        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>内容</label>
          <Input.TextArea value={dialogForm.content} disabled={dialogMode === 'view'} rows={6}
            onChange={(e) => setDialogForm((f) => ({ ...f, content: e.target.value }))} />
        </div>
        <Row gutter={12}>
          <Col span={12}>
            <label style={{ fontSize: 13, fontWeight: 500 }}>类型</label>
            <Select value={dialogForm.content_type} disabled={dialogMode === 'view'} style={{ width: '100%' }}
              onChange={(v) => setDialogForm((f) => ({ ...f, content_type: v }))}
              options={['fact', 'qa', 'preference', 'problem_solution', 'operation_guide', 'configuration', 'process', 'rule', 'term_definition'].map((v) => ({ value: v, label: v }))} />
          </Col>
          <Col span={12}>
            <label style={{ fontSize: 13, fontWeight: 500 }}>优先级 (1-10)</label>
            <Input type="number" min={1} max={10} value={dialogForm.priority} disabled={dialogMode === 'view'}
              onChange={(e) => setDialogForm((f) => ({ ...f, priority: Number(e.target.value) }))} />
          </Col>
        </Row>
      </Modal>

      {/* Review Content Modal */}
      <Modal title="审核报告" open={reviewOpen} onCancel={() => setReviewOpen(false)} footer={null} width={800}>
        <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 500, overflow: 'auto', background: '#f5f5f5', padding: 16, borderRadius: 6, fontSize: 13 }}>
          {reviewContent}
        </pre>
      </Modal>
    </section>
  );
}
