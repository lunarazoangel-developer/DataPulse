'use client'

import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import Link from 'next/link'
import {
  ArrowLeft,
  Database,
  AlertTriangle,
  Settings,
  Download,
  Table2,
  BarChart3,
  FolderOpen,
  Sparkles,
  Send,
  AlertCircle,
  User as UserIcon,
  Trash2,
} from 'lucide-react'
import {
  API_URL,
  api,
  aiApi,
  AIPayload,
  AIStatus,
  ChatMessage,
} from '@/lib/api'
import MermaidDiagram from '@/components/MermaidDiagram'
import PulseLogo from '@/components/PulseLogo'
import PulseBar from '@/components/PulseBar'

interface Relationship {
  source: string
  target: string
  column: string
  relationship_type: string
}

interface TableInfo {
  name: string
  rows: number
  columns: number
  column_names: string[]
}

interface NullStats {
  table_name: string
  null_percentage: number
  health_status: string
  row_count: number
  column_count: number
}

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<'relationships' | 'anomalies' | 'ai'>('relationships')
  const SECTION_TITLES: Record<'relationships' | 'anomalies' | 'ai', string> = {
    relationships: 'Database Relationships',
    anomalies: 'Anomaly Report',
    ai: 'AI Analysis',
  }
  const [tables, setTables] = useState<TableInfo[]>([])
  const [relationships, setRelationships] = useState<Relationship[]>([])
  const [mermaidDiagram, setMermaidDiagram] = useState('')
  const [nullStatistics, setNullStatistics] = useState<NullStats[]>([])
  const [sensitiveColumns, setSensitiveColumns] = useState<Record<string, string[]>>({})
  const [anomalies, setAnomalies] = useState<any>(null)
  const [settings, setSettings] = useState({
    text_threshold: 80,
    iqr_multiplier: 1.5,
    zscore_threshold: 3.0
  })
  const [loading, setLoading] = useState(false)
  const [detectionProgress, setDetectionProgress] = useState(0)
  const [payloadSize, setPayloadSize] = useState<{ bytes: number; human: string } | null>(null)
  const [currentDatabase, setCurrentDatabase] = useState<string>('')

  const [aiStatus, setAiStatus] = useState<AIStatus | null>(null)
  const [aiPayload, setAiPayload] = useState<AIPayload | null>(null)
  const [aiPayloadLoading, setAiPayloadLoading] = useState(false)
  const [aiPayloadError, setAiPayloadError] = useState<string>('')
  const [aiMessages, setAiMessages] = useState<ChatMessage[]>([])
  const [aiInput, setAiInput] = useState('')
  const [aiSending, setAiSending] = useState(false)
  const [aiError, setAiError] = useState<string>('')
  const [aiSeedFired, setAiSeedFired] = useState(false)
  const aiScrollRef = useRef<HTMLDivElement | null>(null)
  const aiTextareaRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    loadData()
    aiApi
      .getStatus()
      .then(res => setAiStatus(res.data))
      .catch(err => {
        console.error('Failed to fetch AI status:', err)
        setAiStatus({ available: false, model: 'unknown' })
      })
  }, [])

  const loadData = async () => {
    try {
      const tablesRes = await axios.get(`${API_URL}/api/files/tables`)
      setTables(tablesRes.data.tables || [])
      setCurrentDatabase(tablesRes.data.database || '')

      const relRes = await axios.get(`${API_URL}/api/analyze/relationships`)
      setRelationships(relRes.data.relationships || [])
      setMermaidDiagram(relRes.data.mermaid_diagram || '')

      const schemaRes = await axios.get(`${API_URL}/api/analyze/schema`)
      setNullStatistics(schemaRes.data.null_statistics || [])

      const sensitiveRes = await axios.get(`${API_URL}/api/payload/sensitive-columns`)
      setSensitiveColumns(sensitiveRes.data.sensitive_columns || {})
    } catch (err) {
      console.error('Error loading data:', err)
    }
  }

  const runAnomalyDetection = async () => {
    setLoading(true)
    setDetectionProgress(0)
    setPayloadSize(null)

    const progressInterval = setInterval(() => {
      setDetectionProgress(prev => {
        if (prev >= 90) {
          clearInterval(progressInterval)
          return prev
        }
        return prev + 10
      })
    }, 200)

    try {
      const response = await axios.post(`${API_URL}/api/analyze/anomalies`, settings)
      setAnomalies(response.data)
      setDetectionProgress(100)

      try {
        const sizeRes = await axios.get(`${API_URL}/api/payload/size`)
        setPayloadSize({ bytes: sizeRes.data.size_bytes, human: sizeRes.data.size_human })
      } catch (sizeErr) {
        setPayloadSize(null)
      }
    } catch (err) {
      console.error('Error running anomaly detection:', err)
    } finally {
      setTimeout(() => {
        clearInterval(progressInterval)
        setLoading(false)
        setDetectionProgress(0)
      }, 500)
    }
  }

  const updateSensitiveColumns = async (table: string, columns: string[]) => {
    const updated = { ...sensitiveColumns, [table]: columns }
    setSensitiveColumns(updated)
    try {
      await axios.post(`${API_URL}/api/payload/sensitive-columns`, { sensitive_columns: updated })
    } catch (err) {
      console.error('Error updating sensitive columns:', err)
    }
  }

  const downloadPayload = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/payload/download`)
      const blob = new Blob([response.data.json], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'ai_payload.json'
      a.click()
    } catch (err) {
      console.error('Error downloading payload:', err)
    }
  }

  const getAnomalySummary = () => {
    if (!anomalies?.categorized) return { red: 0, yellow: 0, green: 0 }

    const red = anomalies.categorized.red?.reduce((acc: number, item: any) => acc + (item.data?.length || 0), 0) || 0
    const yellow = anomalies.categorized.yellow?.reduce((acc: number, item: any) => acc + (item.data?.length || 0), 0) || 0
    const green = anomalies.categorized.green?.reduce((acc: number, item: any) => acc + (item.data?.length || 0), 0) || 0

    return { red, yellow, green }
  }

  const summary = getAnomalySummary()
  const isAiUnlocked = !!anomalies && (summary.red + summary.yellow + summary.green) > 0

  const SEED_QUESTION =
    'Analiza este reporte de calidad de datos y dime qué discrepancias debo corregir, ordenadas por prioridad.'

  const loadAiPayload = async () => {
    setAiPayloadLoading(true)
    setAiPayloadError('')
    try {
      const res = await api.getPayloadPreview()
      setAiPayload(res.data.payload)
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        'No se pudo cargar el reporte. Corre la detección de anomalías primero.'
      setAiPayloadError(detail)
      setAiPayload(null)
    } finally {
      setAiPayloadLoading(false)
    }
  }

  useEffect(() => {
    if (activeTab === 'ai' && isAiUnlocked && !aiPayload && !aiPayloadLoading) {
      void loadAiPayload()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, isAiUnlocked])

  useEffect(() => {
    if (aiScrollRef.current) {
      aiScrollRef.current.scrollTop = aiScrollRef.current.scrollHeight
    }
  }, [aiMessages, aiSending])

  const sendAiMessage = async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || !aiPayload || aiSending) return

    const userMsg: ChatMessage = { role: 'user', content: trimmed }
    const nextHistory = [...aiMessages, userMsg]
    setAiMessages(nextHistory)
    setAiInput('')
    setAiError('')
    setAiSending(true)

    try {
      const res = await aiApi.chat({
        payload: aiPayload,
        history: nextHistory.slice(0, -1),
        message: trimmed,
      })
      const reply = res.data.message
      setAiMessages(prev => [...prev, { role: 'assistant', content: reply }])
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        'Error contacting the AI service.'
      setAiError(detail)
      setAiMessages(prev => [
        ...prev,
        { role: 'assistant', content: `⚠️ ${detail}` },
      ])
    } finally {
      setAiSending(false)
      aiTextareaRef.current?.focus()
    }
  }

  useEffect(() => {
    if (activeTab !== 'ai') return
    if (!aiPayload || !aiStatus || aiSeedFired) return
    if (!aiStatus.available) {
      setAiMessages([
        {
          role: 'assistant',
          content:
            'AI service is not configured yet. Add a DeepSeek API key in `backend/.env` (variable `DEEPSEEK_API_KEY`) and restart the backend to enable analysis.',
        },
      ])
      setAiSeedFired(true)
      return
    }
    setAiSeedFired(true)
    void sendAiMessage(SEED_QUESTION)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, aiPayload, aiStatus, aiSeedFired])

  const handleAiKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void sendAiMessage(aiInput)
    }
  }

  const handleClearAiChat = () => {
    setAiMessages([])
    setAiError('')
    setAiSeedFired(false)
  }

  const aiEnabled = aiStatus?.available ?? false

  return (
    <main className="min-h-screen bg-bg-primary p-8">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center gap-4 mb-8">
          <Link href="/" className="btn-secondary flex items-center gap-2">
            <ArrowLeft className="w-4 h-4" />
            Back
          </Link>
          <PulseLogo size="sm" showWordmark={false} />
          <h1 className="text-3xl font-bold text-accent">
            {SECTION_TITLES[activeTab] ?? 'Dashboard'}
          </h1>
          {currentDatabase && (
            <div className="flex items-center gap-2 text-sm text-text-secondary bg-bg-secondary border border-border px-3 py-1.5 rounded font-mono">
              <FolderOpen className="w-4 h-4 text-accent" />
              {currentDatabase}
            </div>
          )}
        </div>

        <div className="flex gap-2 mb-6 flex-wrap">
          <button
            onClick={() => setActiveTab('relationships')}
            className={`px-4 py-2 rounded flex items-center gap-2 ${activeTab === 'relationships' ? 'bg-white text-black font-medium' : 'btn-secondary'}`}
          >
            <Database className="w-4 h-4" />
            Database Relationships
          </button>
          <button
            onClick={() => setActiveTab('anomalies')}
            className={`px-4 py-2 rounded flex items-center gap-2 ${activeTab === 'anomalies' ? 'bg-white text-black font-medium' : 'btn-secondary'}`}
          >
            <AlertTriangle className="w-4 h-4" />
            Anomaly Report
          </button>
          {isAiUnlocked && (
            <button
              onClick={() => setActiveTab('ai')}
              className={`px-4 py-2 rounded flex items-center gap-2 ${
                activeTab === 'ai' ? 'bg-white text-black font-medium' : 'btn-secondary'
              }`}
            >
              <Sparkles className={`w-4 h-4 ${activeTab === 'ai' ? '' : 'animate-pulse text-pulse'}`} />
              AI Analysis
              <span
                className={`text-[9px] uppercase tracking-widest font-semibold px-1.5 py-0.5 rounded border ${
                  aiEnabled
                    ? 'text-status-green border-status-green/40 bg-status-green/10'
                    : 'text-status-yellow border-status-yellow/40 bg-status-yellow/10'
                }`}
              >
                {aiEnabled ? 'Ready' : 'Beta'}
              </span>
            </button>
          )}
        </div>

        {activeTab === 'relationships' && (
          <div className="space-y-6">
            {relationships.length > 0 && (
              <div className="card">
                <h3 className="font-semibold mb-4 flex items-center gap-2">
                  <Database className="w-4 h-4" />
                  Entity-Relationship Diagram
                </h3>
                <p className="text-sm text-text-secondary mb-4">
                  {relationships.length} relationship(s) detected
                </p>
                <MermaidDiagram chart={mermaidDiagram} />
              </div>
            )}

            <div className="grid grid-cols-1 gap-4">
              {tables.map((table, idx) => {
                const tableStats = nullStatistics.find(s => s.table_name === table.name)
                return (
                  <div key={idx} className="card">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-semibold flex items-center gap-2">
                        <Table2 className="w-4 h-4" />
                        {table.name}
                      </h3>
                      <span className="text-sm text-text-secondary">
                        {table.rows} rows × {table.columns} cols
                      </span>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="bg-bg-tertiary p-3 rounded">
                        <p className="text-xs text-text-muted mb-1">Null Values</p>
                        <p className={`text-lg font-semibold ${
                          tableStats?.health_status === 'Good' ? 'text-status-green' :
                          tableStats?.health_status === 'Needs Attention' ? 'text-status-yellow' : 'text-status-red'
                        }`}>
                          {tableStats?.null_percentage?.toFixed(1) || 0}%
                        </p>
                      </div>
                      <div className="bg-bg-tertiary p-3 rounded">
                        <p className="text-xs text-text-muted mb-1">Health Status</p>
                        <p className={`text-lg font-semibold ${
                          tableStats?.health_status === 'Good' ? 'text-status-green' :
                          tableStats?.health_status === 'Needs Attention' ? 'text-status-yellow' : 'text-status-red'
                        }`}>
                          {tableStats?.health_status || 'Unknown'}
                        </p>
                      </div>
                      <div className="bg-bg-tertiary p-3 rounded">
                        <p className="text-xs text-text-muted mb-1">Columns</p>
                        <p className="text-lg font-semibold">{table.columns}</p>
                      </div>
                    </div>

                    <div className="mt-4">
                      <p className="text-xs text-text-muted mb-2">Column Names</p>
                      <div className="flex flex-wrap gap-1">
                        {table.column_names.map((col: string, cidx: number) => (
                          <span key={cidx} className="text-xs bg-bg-tertiary px-2 py-1 rounded">
                            {col}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>

            {tables.length === 0 && (
              <div className="card text-center py-8">
                <p className="text-text-secondary">No data loaded. Upload files from the home page.</p>
                <Link href="/" className="btn-primary inline-block mt-4">
                  Go to Home
                </Link>
              </div>
            )}
          </div>
        )}

        {activeTab === 'anomalies' && (
          <div className="space-y-6">
            <div className="card">
              <h3 className="font-semibold mb-4">Sensitive Columns</h3>
              <div className="space-y-3">
                {tables.map((table, idx) => (
                  <div key={idx} className="p-3 bg-bg-tertiary rounded">
                    <h4 className="font-medium mb-2 text-sm">{table.name}</h4>
                    <div className="flex flex-wrap gap-2">
                      {table.column_names.map((col: string) => (
                        <label key={col} className="flex items-center gap-1 text-xs cursor-pointer">
                          <input
                            type="checkbox"
                            checked={(sensitiveColumns[table.name] || []).includes(col)}
                            onChange={(e) => {
                              const current = sensitiveColumns[table.name] || []
                              const updated = e.target.checked
                                ? [...current, col]
                                : current.filter((c: string) => c !== col)
                              updateSensitiveColumns(table.name, updated)
                            }}
                            className="accent-white"
                          />
                          {col}
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="card">
              <h3 className="font-semibold mb-4 flex items-center gap-2">
                <Settings className="w-4 h-4" />
                Configuration
              </h3>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <div>
                  <label className="block text-sm text-text-secondary mb-1">Text Similarity (%)</label>
                  <input
                    type="number"
                    value={settings.text_threshold}
                    onChange={(e) => setSettings({ ...settings, text_threshold: Number(e.target.value) })}
                    className="input"
                    min={50}
                    max={100}
                  />
                </div>
                <div>
                  <label className="block text-sm text-text-secondary mb-1">IQR Multiplier</label>
                  <input
                    type="number"
                    value={settings.iqr_multiplier}
                    onChange={(e) => setSettings({ ...settings, iqr_multiplier: Number(e.target.value) })}
                    className="input"
                    step={0.1}
                    min={0.5}
                    max={3.0}
                  />
                </div>
                <div>
                  <label className="block text-sm text-text-secondary mb-1">Z-Score</label>
                  <input
                    type="number"
                    value={settings.zscore_threshold}
                    onChange={(e) => setSettings({ ...settings, zscore_threshold: Number(e.target.value) })}
                    className="input"
                    step={0.1}
                    min={1.0}
                    max={5.0}
                  />
                </div>
              </div>

              <div className="flex items-center gap-4">
                <button 
                  onClick={runAnomalyDetection} 
                  disabled={loading || tables.length === 0}
                  className="btn-primary disabled:opacity-50"
                >
                  {loading ? 'Detecting...' : 'Run Detection'}
                </button>
                {loading && (
                  <div className="flex-1">
                    <div className="progress-bar">
                      <div className="progress-bar-fill" style={{ width: `${detectionProgress}%` }} />
                    </div>
                  </div>
                )}
              </div>
            </div>

            {anomalies && (
              <div className="card">
                <h3 className="font-semibold mb-4">Detection Summary</h3>
                <div className="grid grid-cols-3 gap-4 mb-6">
                  <div className="p-4 bg-status-red/10 border border-status-red/30 rounded">
                    <div className="flex items-center justify-center gap-2">
                      <PulseBar color="red" compact />
                      <div className="text-2xl font-bold text-status-red">
                        {summary.red}
                      </div>
                    </div>
                    <div className="text-sm text-text-secondary text-center mt-1">
                      RED
                    </div>
                  </div>
                  <div className="p-4 bg-status-yellow/10 border border-status-yellow/30 rounded">
                    <div className="flex items-center justify-center gap-2">
                      <PulseBar color="yellow" compact />
                      <div className="text-2xl font-bold text-status-yellow">
                        {summary.yellow}
                      </div>
                    </div>
                    <div className="text-sm text-text-secondary text-center mt-1">
                      YELLOW
                    </div>
                  </div>
                  <div className="p-4 bg-status-green/10 border border-status-green/30 rounded">
                    <div className="flex items-center justify-center gap-2">
                      <PulseBar color="green" compact />
                      <div className="text-2xl font-bold text-status-green">
                        {summary.green}
                      </div>
                    </div>
                    <div className="text-sm text-text-secondary text-center mt-1">
                      GREEN
                    </div>
                  </div>
                </div>

                {summary.red > 0 && (
                  <div className="mb-4">
                    <h4 className="font-medium mb-2 text-status-red flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4" />
                      Red Alerts ({summary.red})
                    </h4>
                    <div className="space-y-1">
                      {anomalies.categorized.red?.map((item: any, idx: number) => (
                        <div key={idx} className="text-sm bg-bg-tertiary p-2 rounded flex justify-between">
                          <span>{item.table} - {item.column}</span>
                          <span className="text-text-muted">{item.detection_type}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {summary.yellow > 0 && (
                  <div className="mb-4">
                    <h4 className="font-medium mb-2 text-status-yellow flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4" />
                      Yellow Alerts ({summary.yellow})
                    </h4>
                    <div className="space-y-1">
                      {anomalies.categorized.yellow?.map((item: any, idx: number) => (
                        <div key={idx} className="text-sm bg-bg-tertiary p-2 rounded flex justify-between">
                          <span>{item.table} - {item.column}</span>
                          <span className="text-text-muted">{item.detection_type}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {summary.green > 0 && (
                  <div className="mb-4">
                    <h4 className="font-medium mb-2 text-status-green flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4" />
                      Green Alerts ({summary.green})
                    </h4>
                    <div className="space-y-1">
                      {anomalies.categorized.green?.map((item: any, idx: number) => (
                        <div key={idx} className="text-sm bg-bg-tertiary p-2 rounded flex justify-between">
                          <span>{item.table} - {item.column}</span>
                          <span className="text-text-muted">{item.detection_type}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {summary.red === 0 && summary.yellow === 0 && summary.green === 0 && (
                  <p className="text-text-secondary text-center py-4">No anomalies detected</p>
                )}

                <div className="mt-6 pt-4 border-t border-border flex flex-wrap items-center justify-between gap-3">
                  <button onClick={downloadPayload} className="btn-primary flex items-center gap-2">
                    <Download className="w-4 h-4" />
                    Download AI Payload
                  </button>
                  {payloadSize && (
                    <span
                      className={
                        payloadSize.bytes < 100_000
                          ? "text-xs text-status-green"
                          : payloadSize.bytes < 1_000_000
                          ? "text-xs text-status-yellow"
                          : "text-xs text-status-red"
                      }
                      title="Tamaño estimado del payload JSON"
                    >
                      Peso: {payloadSize.human}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'ai' && isAiUnlocked && (
          <div className="space-y-4">
            {!aiEnabled && (
              <div className="card border-status-yellow/40 bg-status-yellow/10 flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-status-yellow flex-shrink-0 mt-0.5" />
                <div className="text-sm">
                  <p className="font-semibold text-status-yellow mb-1">
                    AI is not configured
                  </p>
                  <p className="text-text-secondary">
                    Set <code className="font-mono text-xs">DEEPSEEK_API_KEY</code> in{' '}
                    <code className="font-mono text-xs">backend/.env</code> and restart the
                    backend to enable the AI chat. You can still see the report loaded below.
                  </p>
                </div>
              </div>
            )}

            {aiPayloadError && !aiPayload && (
              <div className="card border-status-red/40 bg-status-red/10 text-status-red text-sm">
                {aiPayloadError}
              </div>
            )}

            {aiPayloadLoading && !aiPayload && (
              <div className="card text-text-secondary text-sm text-center py-10">
                <span className="inline-block w-2 h-2 bg-pulse rounded-full animate-pulse mr-2" />
                Loading report payload…
              </div>
            )}

            {aiPayload && (
              <>
                <div
                  ref={aiScrollRef}
                  className="card overflow-y-auto space-y-4 min-h-[400px] max-h-[60vh]"
                >
                  {aiMessages.length === 0 && !aiSending && (
                    <p className="text-text-muted text-sm text-center py-8">
                      Starting analysis…
                    </p>
                  )}

                  {aiMessages.map((m, idx) => (
                    <div
                      key={idx}
                      className={`flex gap-3 ${
                        m.role === 'user' ? 'justify-end' : 'justify-start'
                      }`}
                    >
                      {m.role !== 'user' && (
                        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-pulse/10 border border-pulse/40 flex items-center justify-center">
                          <PulseBar color="blue" compact />
                        </div>
                      )}

                      <div
                        className={`max-w-[80%] rounded-lg px-4 py-2.5 text-sm whitespace-pre-wrap break-words ${
                          m.role === 'user'
                            ? 'bg-pulse text-white'
                            : 'bg-bg-tertiary border border-border text-text-primary'
                        }`}
                      >
                        {m.content}
                      </div>

                      {m.role === 'user' && (
                        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-bg-tertiary border border-border flex items-center justify-center">
                          <UserIcon className="w-4 h-4 text-text-secondary" />
                        </div>
                      )}
                    </div>
                  ))}

                  {aiSending && (
                    <div className="flex gap-3 justify-start">
                      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-pulse/10 border border-pulse/40 flex items-center justify-center">
                        <PulseBar color="blue" compact />
                      </div>
                      <div className="bg-bg-tertiary border border-border rounded-lg px-4 py-3 text-sm text-text-secondary flex items-center gap-2">
                        <span className="inline-block w-2 h-2 bg-pulse rounded-full animate-pulse" />
                        <span
                          className="inline-block w-2 h-2 bg-pulse rounded-full animate-pulse"
                          style={{ animationDelay: '120ms' }}
                        />
                        <span
                          className="inline-block w-2 h-2 bg-pulse rounded-full animate-pulse"
                          style={{ animationDelay: '240ms' }}
                        />
                      </div>
                    </div>
                  )}

                  {aiError && aiMessages[aiMessages.length - 1]?.role !== 'assistant' && (
                    <div className="bg-status-red/10 border border-status-red/30 text-status-red text-sm rounded-lg px-3 py-2">
                      {aiError}
                    </div>
                  )}
                </div>

                <div className="flex items-end gap-3">
                  <button
                    onClick={handleClearAiChat}
                    disabled={aiMessages.length === 0 || aiSending}
                    className="btn-secondary flex items-center gap-2 self-end"
                    title="Clear conversation"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                  <textarea
                    ref={aiTextareaRef}
                    value={aiInput}
                    onChange={e => setAiInput(e.target.value)}
                    onKeyDown={handleAiKeyDown}
                    placeholder={
                      aiEnabled
                        ? 'Ask a follow-up about the discrepancies… (Enter to send, Shift+Enter for newline)'
                        : 'AI not configured — input disabled'
                    }
                    disabled={!aiEnabled || aiSending}
                    rows={2}
                    className="input resize-none flex-1"
                  />
                  <button
                    onClick={() => void sendAiMessage(aiInput)}
                    disabled={!aiEnabled || aiSending || aiInput.trim().length === 0}
                    className="btn-pulse self-end"
                  >
                    <Send className="w-4 h-4" />
                    Send
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {activeTab === 'ai' && !isAiUnlocked && (
          <div className="card text-center py-10">
            <Sparkles className="w-10 h-10 text-pulse mx-auto mb-4" />
            <h2 className="text-xl font-semibold mb-2">AI Analysis locked</h2>
            <p className="text-text-secondary text-sm">
              Run anomaly detection first. Once at least one discrepancy is found, the
              AI Analysis tab unlocks here.
            </p>
          </div>
        )}
      </div>
    </main>
  )
}
