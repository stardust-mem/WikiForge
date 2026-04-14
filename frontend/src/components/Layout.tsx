import { Layout, Menu } from 'antd'
import {
  UploadOutlined,
  BookOutlined,
  SearchOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'

const { Header, Content } = Layout

const menuItems = [
  { key: '/wiki', icon: <BookOutlined />, label: 'Wiki' },
  { key: '/ingest', icon: <UploadOutlined />, label: '导入文档' },
  { key: '/search', icon: <SearchOutlined />, label: '搜索问答' },
  { key: '/lint', icon: <SafetyCertificateOutlined />, label: '健康检查' },
]

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()

  const currentKey = '/' + location.pathname.split('/')[1]

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          background: '#fff',
          borderBottom: '1px solid #f0f0f0',
          padding: '0 24px',
        }}
      >
        <div
          style={{
            fontSize: 18,
            fontWeight: 600,
            marginRight: 40,
            cursor: 'pointer',
          }}
          onClick={() => navigate('/wiki')}
        >
          WikiForge
        </div>
        <Menu
          mode="horizontal"
          selectedKeys={[currentKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ flex: 1, border: 'none' }}
        />
      </Header>
      <Content style={{ padding: '24px', background: '#f5f5f5' }}>
        <Outlet />
      </Content>
    </Layout>
  )
}
