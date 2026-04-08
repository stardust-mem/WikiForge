import { useState, useEffect, useRef } from 'react'
import {
  Upload,
  Card,
  Typography,
  Tag,
  Alert,
  Descriptions,
  List,
  message,
  Progress,
} from 'antd'
import {
  InboxOutlined,
  CheckCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons'
import type { UploadProps } from 'antd'

const { Dragger } = Upload
const { Title, Text } = Typography

interface IngestResult {
  source_id: string
  filename: string
  document_type: string
  topic_tags: string[]
  summary: string
  wiki_pages_created: string[]
  wiki_pages_updated: string[]
}

interface TaskInfo {
  task_id: string
  filename: string
  status: string
  progress_label: string
  error: string | null
  result: IngestResult | null
}

const STEP_ORDER = [
  'pending', 'extracting', 'classifying', 'segmenting',
  'generating', 'indexing', 'saving', 'completed',
]

function getProgress(status: string): number {
  const idx = STEP_ORDER.indexOf(status)
  if (idx < 0) return 0
  return Math.round((idx / (STEP_ORDER.length - 1)) * 100)
}

export default function IngestPage() {
  const [history, setHistory] = useState<IngestResult[]>([])
  const [activeTasks, setActiveTasks] = useState<TaskInfo[]>([])
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // 加载历史记录
  useEffect(() => {
    fetch('/api/ingest/history')
      .then((r) => r.json())
      .then(setHistory)
      .catch(() => {})
  }, [])

  // 轮询活跃任务
  useEffect(() => {
    if (activeTasks.some(t => !['completed', 'failed'].includes(t.status))) {
      if (!pollingRef.current) {
        pollingRef.current = setInterval(async () => {
          const resp = await fetch('/api/ingest/tasks')
          const tasks: TaskInfo[] = await resp.json()
          setActiveTasks(tasks)

          // 检查新完成的任务
          for (const t of tasks) {
            if (t.status === 'completed' && t.result) {
              setHistory(prev => {
                if (prev.some(h => h.source_id === t.result!.source_id)) return prev
                return [t.result!, ...prev]
              })
            }
          }

          // 所有任务都结束了，停止轮询
          if (tasks.every(t => ['completed', 'failed'].includes(t.status))) {
            if (pollingRef.current) {
              clearInterval(pollingRef.current)
              pollingRef.current = null
            }
          }
        }, 1500)
      }
    }
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
        pollingRef.current = null
      }
    }
  }, [activeTasks])

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: true,
    action: '/api/ingest',
    accept: '.pdf,.docx,.doc,.pptx,.ppt,.md,.txt',
    showUploadList: false,
    onChange(info) {
      const { status } = info.file
      if (status === 'done') {
        const resp = info.file.response as { task_id: string; filename: string }
        message.info(`${info.file.name} 已提交处理`)
        setActiveTasks(prev => [
          ...prev,
          {
            task_id: resp.task_id,
            filename: resp.filename,
            status: 'pending',
            progress_label: '等待处理',
            error: null,
            result: null,
          },
        ])
      } else if (status === 'error') {
        const errMsg = info.file.response?.detail || '上传失败'
        message.error(`${info.file.name}: ${errMsg}`)
      }
    },
  }

  const runningTasks = activeTasks.filter(t => !['completed', 'failed'].includes(t.status))
  const failedTasks = activeTasks.filter(t => t.status === 'failed')

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <Title level={3}>导入文档</Title>

      <Card style={{ marginBottom: 24 }}>
        <Dragger {...uploadProps}>
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽文件到此区域</p>
          <p className="ant-upload-hint">
            支持 PDF / DOCX / PPTX / MD / TXT，系统将自动提取、分类并生成 Wiki 页面
          </p>
        </Dragger>
      </Card>

      {/* 正在处理的任务 */}
      {runningTasks.map((t) => (
        <Card
          key={t.task_id}
          style={{ marginBottom: 16 }}
          size="small"
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <LoadingOutlined spin style={{ fontSize: 20, color: '#1677ff' }} />
            <div style={{ flex: 1 }}>
              <Text strong>{t.filename}</Text>
              <div style={{ marginTop: 4 }}>
                <Text type="secondary">{t.progress_label}</Text>
              </div>
              <Progress
                percent={getProgress(t.status)}
                size="small"
                status="active"
                style={{ marginTop: 4 }}
              />
            </div>
          </div>
        </Card>
      ))}

      {/* 失败的任务 */}
      {failedTasks.map((t) => (
        <Alert
          key={t.task_id}
          message={`${t.filename} 处理失败`}
          description={t.error || '未知错误'}
          type="error"
          showIcon
          closable
          style={{ marginBottom: 16 }}
        />
      ))}

      {/* 历史记录 */}
      {history.map((r) => (
        <Card
          key={r.source_id}
          title={
            <span>
              <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 8 }} />
              {r.filename}
            </span>
          }
          style={{ marginBottom: 16 }}
          size="small"
        >
          <Descriptions column={1} size="small">
            <Descriptions.Item label="文档类型">
              <Tag color="blue">{r.document_type}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="主题标签">
              {r.topic_tags.map((t) => (
                <Tag key={t}>{t}</Tag>
              ))}
            </Descriptions.Item>
            <Descriptions.Item label="摘要">{r.summary}</Descriptions.Item>
          </Descriptions>
          {r.wiki_pages_created.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <strong>生成的 Wiki 页面：</strong>
              <List
                size="small"
                dataSource={r.wiki_pages_created}
                renderItem={(p) => (
                  <List.Item>
                    <a href={`/wiki/${p}`}>{p}</a>
                  </List.Item>
                )}
              />
            </div>
          )}
        </Card>
      ))}
    </div>
  )
}
