import { useState } from 'react'
import { Input, Card, Typography, List, Spin, Empty, Button, message } from 'antd'
import { SearchOutlined, SaveOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const { Title, Paragraph } = Typography
const { Search } = Input

interface SuggestedPage {
  title: string
  category: string
  content: string
}

interface QueryResult {
  answer: string
  citations: string[]
  suggested_page?: SuggestedPage | null
}

export default function SearchPage() {
  const [result, setResult] = useState<QueryResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [archiving, setArchiving] = useState(false)
  const [lastQuestion, setLastQuestion] = useState('')
  const navigate = useNavigate()

  const handleArchive = async (page: SuggestedPage) => {
    setArchiving(true)
    try {
      const resp = await fetch('/api/search/archive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: page.title,
          category: page.category,
          content: page.content,
          source_question: lastQuestion,
        }),
      })
      if (!resp.ok) throw new Error(`Server error: ${resp.status}`)
      const data = await resp.json()
      message.success('已归档为 Wiki 页面')
      navigate(`/wiki/${data.page_id}`)
    } catch {
      message.error('归档失败，请重试')
    } finally {
      setArchiving(false)
    }
  }

  const handleSearch = async (question: string) => {
    if (!question.trim()) return
    setLastQuestion(question)
    setLoading(true)
    try {
      const resp = await fetch('/api/search/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })
      if (!resp.ok) throw new Error(`Server error: ${resp.status}`)
      const data = await resp.json()
      setResult(data)
    } catch {
      setResult({ answer: '查询失败，请检查后端服务是否运行。', citations: [] })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <Title level={3}>搜索问答</Title>

      <Search
        placeholder="输入你的问题，例如：关于 Transformer 的核心贡献是什么？"
        enterButton="提问"
        size="large"
        prefix={<SearchOutlined />}
        onSearch={handleSearch}
        loading={loading}
        style={{ marginBottom: 24 }}
      />

      {loading && (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin size="large" tip="正在检索和思考..." />
        </div>
      )}

      {result && !loading && (
        <Card>
          <div className="wiki-content">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {result.answer}
            </ReactMarkdown>
          </div>

          {result.citations.length > 0 && (
            <div style={{ marginTop: 16, borderTop: '1px solid #f0f0f0', paddingTop: 12 }}>
              <Paragraph type="secondary" strong>
                引用来源：
              </Paragraph>
              <List
                size="small"
                dataSource={result.citations}
                renderItem={(c) => (
                  <List.Item>
                    <a
                      href={`/wiki/${c}`}
                      onClick={(e) => {
                        e.preventDefault()
                        navigate(`/wiki/${c}`)
                      }}
                    >
                      {c}
                    </a>
                  </List.Item>
                )}
              />
            </div>
          )}

          {result.suggested_page && (
            <div style={{ marginTop: 16, borderTop: '1px solid #f0f0f0', paddingTop: 12 }}>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                loading={archiving}
                onClick={() => handleArchive(result.suggested_page!)}
              >
                归档为 Wiki 页面：{result.suggested_page.title}
              </Button>
              <Paragraph type="secondary" style={{ marginTop: 4, fontSize: 12 }}>
                分类：{result.suggested_page.category}
              </Paragraph>
            </div>
          )}
        </Card>
      )}

      {!result && !loading && (
        <Empty description="输入问题开始搜索" style={{ marginTop: 60 }} />
      )}
    </div>
  )
}
