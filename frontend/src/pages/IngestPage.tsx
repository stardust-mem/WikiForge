import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
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
  Popconfirm,
  Button,
} from 'antd'
import {
  InboxOutlined,
  CheckCircleOutlined,
  LoadingOutlined,
  DeleteOutlined,
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

// sessionStorage 持久化任务 ID（切换页签不丢失）
const STORAGE_KEY = 'pkm_pending_tasks'
function loadPendingIds(): Set<string> {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? new Set(JSON.parse(raw)) : new Set()
  } catch { return new Set() }
}
function savePendingIds(ids: Set<string>) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...ids]))
}

export default function IngestPage() {
  const navigate = useNavigate()
  const [history, setHistory] = useState<IngestResult[]>([])
  const [pendingTaskIds, setPendingTaskIds] = useState<Set<string>>(loadPendingIds)
  const [taskMap, setTaskMap] = useState<Record<string, TaskInfo>>({})
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pendingRef = useRef<Set<string>>(loadPendingIds())
  const timeoutRefs = useRef<ReturnType<typeof setTimeout>[]>([])

  // 加载历史记录
  useEffect(() => {
    fetch('/api/ingest/history')
      .then((r) => r.json())
      .then(setHistory)
      .catch(() => {})
  }, [])

  // 轮询：只在有活跃任务时
  const startPolling = useCallback(() => {
    if (pollingRef.current) return
    pollingRef.current = setInterval(async () => {
      try {
        const resp = await fetch('/api/ingest/tasks')
        const allTasks: TaskInfo[] = await resp.json()

        // 只跟踪我们提交的任务 — read from ref to avoid stale closure
        const currentPending = pendingRef.current
        const myTasks: Record<string, TaskInfo> = {}
        for (const t of allTasks) {
          if (currentPending.has(t.task_id)) {
            myTasks[t.task_id] = t
          }
        }
        setTaskMap(myTasks)

        // 检查完成的任务 → 移入 history
        const newCompleted: string[] = []
        for (const t of Object.values(myTasks)) {
          if (t.status === 'completed' && t.result) {
            setHistory(prev => {
              if (prev.some(h => h.source_id === t.result!.source_id)) return prev
              return [t.result!, ...prev]
            })
            newCompleted.push(t.task_id)
          } else if (t.status === 'failed') {
            newCompleted.push(t.task_id)
          }
        }

        // 清除已完成的任务ID（延迟3秒让用户看到状态）
        if (newCompleted.length > 0) {
          const t1 = setTimeout(() => {
            setPendingTaskIds(prev => {
              const next = new Set(prev)
              newCompleted.forEach(id => next.delete(id))
              pendingRef.current = next
              savePendingIds(next)
              return next
            })
          }, 3000)
          timeoutRefs.current.push(t1)
        }

        // 没有活跃任务了，停止轮询
        const stillActive = Object.values(myTasks).some(
          t => !['completed', 'failed'].includes(t.status)
        )
        if (!stillActive && newCompleted.length > 0) {
          const t2 = setTimeout(() => {
            if (pollingRef.current) {
              clearInterval(pollingRef.current)
              pollingRef.current = null
            }
          }, 3500)
          timeoutRefs.current.push(t2)
        }
      } catch { /* ignore */ }
    }, 1500)
  }, [])

  // pendingTaskIds 变化时管理轮询
  useEffect(() => {
    if (pendingTaskIds.size > 0) {
      startPolling()
    }
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
        pollingRef.current = null
      }
      timeoutRefs.current.forEach(clearTimeout)
      timeoutRefs.current = []
    }
  }, [pendingTaskIds, startPolling])

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
        const newTask: TaskInfo = {
          task_id: resp.task_id,
          filename: resp.filename,
          status: 'pending',
          progress_label: '等待处理',
          error: null,
          result: null,
        }
        setPendingTaskIds(prev => {
          const next = new Set(prev).add(resp.task_id)
          pendingRef.current = next
          savePendingIds(next)
          return next
        })
        setTaskMap(prev => ({ ...prev, [resp.task_id]: newTask }))
      } else if (status === 'error') {
        const errMsg = info.file.response?.detail || '上传失败'
        message.error(`${info.file.name}: ${errMsg}`)
      }
    },
  }

  const handleDelete = async (sourceId: string, filename: string) => {
    try {
      const resp = await fetch(`/api/ingest/${sourceId}`, { method: 'DELETE' })
      if (!resp.ok) {
        const err = await resp.json()
        message.error(err.detail || '删除失败')
        return
      }
      const result = await resp.json()
      message.success(
        `已删除 ${filename}，清理 ${result.pages_deleted.length} 个页面`
      )
      setHistory((prev) => prev.filter((h) => h.source_id !== sourceId))
    } catch {
      message.error('删除请求失败')
    }
  }

  const activeTasks = Object.values(taskMap).filter(
    t => pendingTaskIds.has(t.task_id)
  )
  const runningTasks = activeTasks.filter(t => !['completed', 'failed'].includes(t.status))
  const justCompleted = activeTasks.filter(t => t.status === 'completed')
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
        <Card key={t.task_id} style={{ marginBottom: 16 }} size="small">
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

      {/* 刚完成的任务（短暂显示） */}
      {justCompleted.map((t) => (
        <Card key={t.task_id} style={{ marginBottom: 16 }} size="small">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <CheckCircleOutlined style={{ fontSize: 20, color: '#52c41a' }} />
            <Text strong>{t.filename}</Text>
            <Text type="secondary">处理完成</Text>
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
          extra={
            <Popconfirm
              title="确认删除"
              description={`将删除「${r.filename}」及其生成的 Wiki 页面，不可恢复。`}
              onConfirm={() => handleDelete(r.source_id, r.filename)}
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button type="text" danger icon={<DeleteOutlined />} size="small">
                删除
              </Button>
            </Popconfirm>
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
                    <a href={`/wiki/${p}`} onClick={(e) => { e.preventDefault(); navigate(`/wiki/${p}`) }}>{p}</a>
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
