import { useState } from 'react'
import { Button, Card, Typography, Table, Tag, Spin, Empty, Statistic, Row, Col } from 'antd'
import {
  CheckCircleOutlined,
  WarningOutlined,
  DisconnectOutlined,
  ClockCircleOutlined,
  UserAddOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'

const { Title } = Typography

interface LintReport {
  orphan_pages: { page_id: string; issue: string }[]
  dangling_links: { page_id: string; target: string; issue: string }[]
  stale_pages: { page_id: string; last_modified: string; sensitive_words: string[]; issue: string }[]
  missing_entities: { name: string; mention_count: number; issue: string }[]
  summary: {
    orphan_count: number
    dangling_count: number
    stale_count: number
    missing_count: number
    total_issues: number
  }
}

export default function LintPage() {
  const [report, setReport] = useState<LintReport | null>(null)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const runLint = async () => {
    setLoading(true)
    try {
      const resp = await fetch('/api/lint/run', { method: 'POST' })
      if (!resp.ok) throw new Error(`Server error: ${resp.status}`)
      const data = await resp.json()
      setReport(data)
    } catch {
      setReport(null)
    } finally {
      setLoading(false)
    }
  }

  const pageLink = (pageId: string) => (
    <a
      href={`/wiki/${pageId}`}
      onClick={(e) => {
        e.preventDefault()
        navigate(`/wiki/${pageId}`)
      }}
    >
      {pageId}
    </a>
  )

  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0 }}>Wiki 健康检查</Title>
        <Button type="primary" onClick={runLint} loading={loading} icon={<CheckCircleOutlined />}>
          运行检查
        </Button>
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: 60 }}>
          <Spin size="large" tip="正在检查..." />
        </div>
      )}

      {report && !loading && (
        <>
          <Row gutter={16} style={{ marginBottom: 24 }}>
            <Col span={6}>
              <Card>
                <Statistic
                  title="孤立页面"
                  value={report.summary.orphan_count}
                  prefix={<DisconnectOutlined />}
                  valueStyle={{ color: report.summary.orphan_count > 0 ? '#faad14' : '#52c41a' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="悬空链接"
                  value={report.summary.dangling_count}
                  prefix={<WarningOutlined />}
                  valueStyle={{ color: report.summary.dangling_count > 0 ? '#ff4d4f' : '#52c41a' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="过期页面"
                  value={report.summary.stale_count}
                  prefix={<ClockCircleOutlined />}
                  valueStyle={{ color: report.summary.stale_count > 0 ? '#faad14' : '#52c41a' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="缺失实体"
                  value={report.summary.missing_count}
                  prefix={<UserAddOutlined />}
                  valueStyle={{ color: report.summary.missing_count > 0 ? '#1677ff' : '#52c41a' }}
                />
              </Card>
            </Col>
          </Row>

          {report.orphan_pages.length > 0 && (
            <Card title="孤立页面 — 没有其他页面引用" style={{ marginBottom: 16 }}>
              <Table
                size="small"
                dataSource={report.orphan_pages}
                rowKey="page_id"
                pagination={false}
                columns={[
                  { title: '页面', dataIndex: 'page_id', render: (v: string) => pageLink(v) },
                  { title: '问题', dataIndex: 'issue' },
                ]}
              />
            </Card>
          )}

          {report.dangling_links.length > 0 && (
            <Card title="悬空链接 — 目标页面不存在" style={{ marginBottom: 16 }}>
              <Table
                size="small"
                dataSource={report.dangling_links}
                rowKey={(r) => `${r.page_id}-${r.target}`}
                pagination={false}
                columns={[
                  { title: '所在页面', dataIndex: 'page_id', render: (v: string) => pageLink(v) },
                  { title: '目标', dataIndex: 'target', render: (v: string) => <Tag color="red">[[{v}]]</Tag> },
                  { title: '问题', dataIndex: 'issue' },
                ]}
              />
            </Card>
          )}

          {report.stale_pages.length > 0 && (
            <Card title="过期页面 — 含时间敏感词且长期未更新" style={{ marginBottom: 16 }}>
              <Table
                size="small"
                dataSource={report.stale_pages}
                rowKey="page_id"
                pagination={false}
                columns={[
                  { title: '页面', dataIndex: 'page_id', render: (v: string) => pageLink(v) },
                  { title: '最后修改', dataIndex: 'last_modified' },
                  {
                    title: '敏感词',
                    dataIndex: 'sensitive_words',
                    render: (words: string[]) => words.map((w) => <Tag key={w}>{w}</Tag>),
                  },
                ]}
              />
            </Card>
          )}

          {report.missing_entities.length > 0 && (
            <Card title="缺失实体 — 频繁提及但无对应页面" style={{ marginBottom: 16 }}>
              <Table
                size="small"
                dataSource={report.missing_entities}
                rowKey="name"
                pagination={false}
                columns={[
                  { title: '名称', dataIndex: 'name' },
                  { title: '被提及次数', dataIndex: 'mention_count', render: (v: number) => <Tag color="blue">{v} 次</Tag> },
                  { title: '建议', dataIndex: 'issue' },
                ]}
              />
            </Card>
          )}

          {report.summary.total_issues === 0 && (
            <Card>
              <Empty
                image={<CheckCircleOutlined style={{ fontSize: 48, color: '#52c41a' }} />}
                description="Wiki 健康状况良好，未发现问题"
              />
            </Card>
          )}
        </>
      )}

      {!report && !loading && (
        <Empty description="点击「运行检查」开始 Wiki 健康检查" style={{ marginTop: 60 }} />
      )}
    </div>
  )
}
