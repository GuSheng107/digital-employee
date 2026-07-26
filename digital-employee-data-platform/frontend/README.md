# 前端服务说明

本目录是数字员工数据中台的 Vue 3 管理页面。

页面提供：

- Dashboard：查看服务和依赖状态。
- System Config：查看脱敏配置并测试连接。
- Data Items：验证已有表 `data_items` 的 CRUD API。

前端不提供建库、建表、任意 SQL 执行页面。数据库结构管理由 CloudBeaver Community 负责。

## 安装依赖

```bash
cd frontend
npm install
```

## 配置

```bash
cp .env.example .env
```

默认 API 地址：

```env
VITE_API_BASE_URL=http://127.0.0.1:8010
```

服务器部署时按实际地址调整，例如：

```env
VITE_API_BASE_URL=http://your-server-ip:8010
```

## 启动

```bash
npm run dev
```

访问：

```text
http://127.0.0.1:5174
```

## 构建

```bash
npm run build
```
