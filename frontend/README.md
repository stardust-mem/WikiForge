# NEWTYPE Frontend

React + TypeScript + Vite 前端。

## 开发

```bash
npm install
npm run dev        # 开发服务器（http://localhost:5173）
npm run build      # 生产构建（产物在 dist/）
npm run preview    # 预览生产构建
```

开发模式下，API 请求自动代理到 `http://localhost:8000`（后端需同时运行）。

生产模式下，前端静态文件由 FastAPI 后端直接 serve（`npm run build` 后重启后端即可）。
