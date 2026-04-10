import { useEffect, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Typography, Spin, Empty } from 'antd'
import {
  UserOutlined,
  BulbOutlined,
  TagsOutlined,
  FileTextOutlined,
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { MenuProps } from 'antd'

const { Sider, Content } = Layout
const { Title } = Typography

const categoryIcons: Record<string, React.ReactNode> = {
  entities: <UserOutlined />,
  concepts: <BulbOutlined />,
  topics: <TagsOutlined />,
  sources: <FileTextOutlined />,
}

const categoryNames: Record<string, string> = {
  entities: '实体',
  concepts: '概念',
  topics: '主题',
  sources: '文档',
}

interface WikiTreeItem {
  category: string
  pages: { page_id: string; title: string; category: string }[]
}

type TitleIndex = Map<string, string>

function buildTitleIndex(tree: WikiTreeItem[]): TitleIndex {
  const index = new Map<string, string>()
  for (const t of tree) {
    for (const p of t.pages) {
      // page_id -> page_id (identity, always precise — overwrite is fine)
      index.set(p.page_id, p.page_id)
      // title -> page_id: first entry wins to avoid ambiguous duplicates
      if (!index.has(p.title)) index.set(p.title, p.page_id)
      // stem -> page_id: first entry wins
      const stem = p.page_id.split('/').pop() || ''
      if (stem && !index.has(stem)) index.set(stem, p.page_id)
    }
  }
  return index
}

function convertWikilinks(md: string, titleIndex: TitleIndex): string {
  return md.replace(/\[\[([^\]]+)\]\]/g, (_match, inner) => {
    const pipeIdx = inner.indexOf('|')
    const target = pipeIdx >= 0 ? inner.slice(0, pipeIdx) : inner
    const label = pipeIdx >= 0 ? inner.slice(pipeIdx + 1) : null

    // Try to resolve target to a page_id
    const pageId = titleIndex.get(target) ?? titleIndex.get(target.trim())
    const displayText = label ?? target.split('/').pop() ?? target

    if (pageId) {
      return `[${displayText}](/wiki/${pageId})`
    }
    // Unresolved: render as plain text to avoid broken links
    return displayText
  })
}

export default function WikiPage() {
  const { category, pageName } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const [tree, setTree] = useState<WikiTreeItem[]>([])
  const [pageContent, setPageContent] = useState<string>('')
  const [pageTitle, setPageTitle] = useState<string>('')
  const [loading, setLoading] = useState(false)

  // Load wiki tree — refetch when navigating back to /wiki
  useEffect(() => {
    fetch('/api/wiki/tree')
      .then((r) => r.json())
      .then(setTree)
      .catch(() => {})
  }, [location.pathname])

  // Load page content
  useEffect(() => {
    if (category && pageName) {
      setLoading(true)
      fetch(`/api/wiki/page/${category}/${pageName}`)
        .then((r) => r.json())
        .then((data) => {
          setPageContent(data.content || '')
          setPageTitle(data.title || pageName)
          setLoading(false)
        })
        .catch(() => setLoading(false))
    } else {
      // Show index
      fetch('/api/wiki/index')
        .then((r) => r.json())
        .then((data) => {
          setPageContent(data.content || '')
          setPageTitle('知识目录')
        })
        .catch(() => {})
    }
  }, [category, pageName])

  // Build menu items
  const menuItems: MenuProps['items'] = tree.map((t) => ({
    key: t.category,
    icon: categoryIcons[t.category],
    label: `${categoryNames[t.category] || t.category}(${t.pages.length})`,
    children: t.pages.map((p) => ({
      key: p.page_id,
      label: p.title,
    })),
  }))

  const selectedKey = category && pageName ? `${category}/${pageName}` : ''

  const titleIndex = buildTitleIndex(tree)

  // Strip frontmatter and convert wikilinks for display
  const displayContent = convertWikilinks(pageContent.replace(/^---[\s\S]*?---\n*/, ''), titleIndex)

  return (
    <Layout style={{ background: '#fff', borderRadius: 8, minHeight: '70vh' }}>
      <Sider
        width={260}
        style={{
          background: '#fff',
          borderRight: '1px solid #f0f0f0',
          overflow: 'auto',
        }}
      >
        <div style={{ padding: '16px 16px 8px', fontWeight: 600, fontSize: 16 }}>
          Wiki 目录
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          defaultOpenKeys={tree.map((t) => t.category)}
          items={menuItems}
          onClick={({ key }) => navigate(`/wiki/${key}`)}
          style={{ border: 'none' }}
        />
      </Sider>
      <Content style={{ padding: '24px 32px' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" />
          </div>
        ) : pageContent ? (
          <div className="wiki-content">
            <Title level={2}>{pageTitle}</Title>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children }) => {
                  if (href?.startsWith('/wiki/')) {
                    return (
                      <a
                        href={href}
                        onClick={(e) => {
                          e.preventDefault()
                          navigate(href)
                        }}
                      >
                        {children}
                      </a>
                    )
                  }
                  return <a href={href}>{children}</a>
                },
              }}
            >
              {displayContent}
            </ReactMarkdown>
          </div>
        ) : (
          <Empty description="选择左侧页面查看内容" />
        )}
      </Content>
    </Layout>
  )
}
