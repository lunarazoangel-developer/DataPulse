'use client'

import { useState, useEffect } from 'react'
import axios from 'axios'
import Link from 'next/link'
import { ArrowLeft, Database, AlertTriangle, Settings, Download, Table2, BarChart3 } from 'lucide-react'
import { API_URL } from '@/lib/api'
import MermaidDiagram from '@/components/MermaidDiagram'

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
  const [activeTab, setActiveTab] = useState('relationships')
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

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      const tablesRes = await axios.get(`${API_URL}/api/files/tables`)
      setTables(tablesRes.data.tables || [])

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

  return (
    <main className="min-h-screen bg-bg-primary p-8">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center gap-4 mb-8">
          <Link href="/" className="btn-secondary flex items-center gap-2">
            <ArrowLeft className="w-4 h-4" />
            Back
          </Link>
          <h1 className="text-3xl font-bold text-accent">Dashboard</h1>
        </div>

        <div className="flex gap-2 mb-6">
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
                  <div className="p-4 bg-status-red/10 border border-status-red/30 rounded text-center">
                    <div className="text-2xl font-bold text-status-red">{summary.red}</div>
                    <div className="text-sm text-text-secondary">RED</div>
                  </div>
                  <div className="p-4 bg-status-yellow/10 border border-status-yellow/30 rounded text-center">
                    <div className="text-2xl font-bold text-status-yellow">{summary.yellow}</div>
                    <div className="text-sm text-text-secondary">YELLOW</div>
                  </div>
                  <div className="p-4 bg-status-green/10 border border-status-green/30 rounded text-center">
                    <div className="text-2xl font-bold text-status-green">{summary.green}</div>
                    <div className="text-sm text-text-secondary">GREEN</div>
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

                <div className="mt-6 pt-4 border-t border-border flex items-center justify-between gap-3">
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
      </div>
    </main>
  )
}
