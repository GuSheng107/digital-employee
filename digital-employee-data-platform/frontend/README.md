# Frontend

数字员工数据中台管理页面，提供连接状态查看、脱敏配置查看、连接测试、Redis/MinIO 测试、`data_items` CRUD。

## 环境要求

- Node.js 18+
- npm

## 安装依赖

```bash
cd frontend
npm install
```

## 配置

```bash
copy .env.example .env
```

默认 API 地址：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

服务器公网访问时可改为：

```env
VITE_API_BASE_URL=http://101.37.69.110:8000
```

## 启动

```bash
npm run dev
```

访问：`http://127.0.0.1:5174`
