import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import AppLayout from './components/Layout'
import IngestPage from './pages/IngestPage'
import WikiPage from './pages/WikiPage'
import SearchPage from './pages/SearchPage'
import LintPage from './pages/LintPage'

function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: { colorPrimary: '#1677ff' },
      }}
    >
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<Navigate to="/wiki" replace />} />
            <Route path="/ingest" element={<IngestPage />} />
            <Route path="/wiki" element={<WikiPage />} />
            <Route path="/wiki/:category/:pageName" element={<WikiPage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/lint" element={<LintPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}

export default App
