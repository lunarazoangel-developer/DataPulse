'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import axios from 'axios'
import {
  Upload,
  FileSpreadsheet,
  AlertTriangle,
  Shield,
  Box,
  Database,
  FolderOpen,
  Trash2,
  Plus,
  Calendar,
  Layers,
  Rows,
  X,
} from 'lucide-react'
import { API_URL, api, DatabaseInfo } from '@/lib/api'
import PulseLogo from '@/components/PulseLogo'

export default function Home() {
  const router = useRouter()
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [files, setFiles] = useState<File[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [databases, setDatabases] = useState<DatabaseInfo[]>([])
  const [databasesLoading, setDatabasesLoading] = useState(false)
  const [busyDb, setBusyDb] = useState<string | null>(null)

  useEffect(() => {
    loadDatabases()
  }, [])

  const loadDatabases = async () => {
    setDatabasesLoading(true)
    try {
      const res = await api.listDatabases()
      setDatabases(res.data.databases || [])
    } catch (err) {
      console.error('Error loading databases:', err)
    } finally {
      setDatabasesLoading(false)
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const incoming = Array.from(e.target.files)
      setFiles(prev => [...(prev || []), ...incoming])
    }
    e.target.value = ''
  }

  const removeFile = (index: number) => {
    setFiles(prev => (prev ? prev.filter((_, i) => i !== index) : prev))
  }

  const formatBytes = (bytes: number): string => {
    if (!bytes && bytes !== 0) return ''
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const handleUpload = async () => {
    if (!files || files.length === 0) return

    setLoading(true)
    setError('')
    setMessage('')

    const formData = new FormData()
    files.forEach(file => {
      formData.append('files', file)
    })

    try {
      const response = await api.uploadFiles(formData)
      setMessage(response.data.message)
      setFiles(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      await loadDatabases()
      router.push('/dashboard')
    } catch (err: any) {
      if (err.code === 'ERR_NETWORK') {
        setError('Cannot connect to backend. Is the server running at ' + API_URL + '?')
      } else {
        setError(err.response?.data?.detail || err.message || 'Error uploading files')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleOpenDatabase = async (name: string) => {
    setBusyDb(name)
    setError('')
    setMessage('')
    try {
      await api.openDatabase(name)
      router.push('/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Error opening database')
    } finally {
      setBusyDb(null)
    }
  }

  const handleDeleteDatabase = async (name: string) => {
    const ok = window.confirm(
      `Delete database "${name}"? This will permanently remove all its files.`
    )
    if (!ok) return
    setBusyDb(name)
    setError('')
    setMessage('')
    try {
      await api.deleteDatabase(name)
      setMessage(`Database "${name}" deleted.`)
      await loadDatabases()
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Error deleting database')
    } finally {
      setBusyDb(null)
    }
  }

  const formatDate = (iso: string) => {
    if (!iso) return '—'
    try {
      const d = new Date(iso)
      return d.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      })
    } catch {
      return iso
    }
  }

  return (
    <main className="min-h-screen bg-bg-primary p-8">
      <div className="max-w-5xl mx-auto">
        <div className="mb-8 flex flex-col items-start gap-3">
          <PulseLogo size="lg" withHalo />
          <p className="text-text-secondary text-sm tracking-wide">
            Intelligent Data Cleaning Assistant
          </p>
        </div>

        <div className="card mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Database className="w-5 h-5" />
              Saved Databases
            </h2>
            <button
              onClick={loadDatabases}
              disabled={databasesLoading}
              className="btn-secondary text-sm"
            >
              {databasesLoading ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>

          {databasesLoading && databases.length === 0 ? (
            <p className="text-sm text-text-secondary">Loading saved databases…</p>
          ) : databases.length === 0 ? (
            <p className="text-sm text-text-secondary">
              No saved databases yet. Upload files below to create your first one.
            </p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {databases.map(db => (
                <div
                  key={db.name}
                  className="p-4 bg-bg-tertiary rounded border border-border flex flex-col gap-3"
                >
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <FolderOpen className="w-4 h-4 text-accent" />
                      <span className="font-mono font-semibold">{db.name}</span>
                    </div>
                    <div className="flex items-center gap-1 text-xs text-text-muted">
                      <Calendar className="w-3 h-3" />
                      {formatDate(db.created_at)}
                    </div>
                  </div>

                  <div className="flex items-center gap-4 text-xs text-text-secondary">
                    <span className="flex items-center gap-1">
                      <Layers className="w-3 h-3" />
                      {db.table_count} table{db.table_count === 1 ? '' : 's'}
                    </span>
                    <span className="flex items-center gap-1">
                      <Rows className="w-3 h-3" />
                      {db.total_rows.toLocaleString('en-US')} rows
                    </span>
                    <span className="flex items-center gap-1">
                      <FileSpreadsheet className="w-3 h-3" />
                      {db.file_count} file{db.file_count === 1 ? '' : 's'}
                    </span>
                  </div>

                  {db.tables.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {db.tables.slice(0, 4).map(t => (
                        <span
                          key={t.name}
                          className="text-[10px] bg-bg-secondary px-2 py-0.5 rounded font-mono"
                        >
                          {t.name}
                        </span>
                      ))}
                      {db.tables.length > 4 && (
                        <span className="text-[10px] text-text-muted px-1">
                          +{db.tables.length - 4} more
                        </span>
                      )}
                    </div>
                  )}

                  <div className="flex gap-2 mt-1">
                    <button
                      onClick={() => handleOpenDatabase(db.name)}
                      disabled={busyDb === db.name}
                      className="btn-primary text-sm flex items-center gap-1 flex-1"
                    >
                      <FolderOpen className="w-3 h-3" />
                      {busyDb === db.name ? 'Opening…' : 'Open'}
                    </button>
                    <button
                      onClick={() => handleDeleteDatabase(db.name)}
                      disabled={busyDb === db.name}
                      className="btn-secondary text-sm flex items-center gap-1"
                      title="Delete database"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card mb-8">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Plus className="w-5 h-5" />
            Create New Database
          </h2>

          <p className="text-sm text-text-secondary mb-4">
            Upload one or more CSV/Excel files. They will be grouped into a new database
            folder with a timestamp name, and stored under{' '}
            <code className="font-mono text-xs">backend/data/</code> for reuse.
          </p>

          <div className="mb-4">
            <input
              ref={fileInputRef}
              id="file-input"
              type="file"
              multiple
              accept=".csv,.xlsx,.xls"
              onChange={handleFileChange}
              className="hidden"
            />
            <label htmlFor="file-input" className="btn-pulse cursor-pointer">
              <Upload className="w-4 h-4" />
              Browse files
            </label>
            <span className="ml-3 text-xs text-text-muted">
              .csv, .xlsx, .xls — multiple files supported
            </span>
          </div>

          {files && files.length > 0 ? (
            <div className="mb-4 flex flex-wrap gap-2">
              {files.map((f, idx) => (
                <span
                  key={`${f.name}-${idx}`}
                  className="inline-flex items-center gap-2 bg-bg-tertiary border border-border rounded-full pl-3 pr-1 py-1 text-xs"
                >
                  <FileSpreadsheet className="w-3 h-3 text-pulse" />
                  <span className="font-medium">{f.name}</span>
                  <span className="text-text-muted">{formatBytes(f.size)}</span>
                  <button
                    type="button"
                    onClick={() => removeFile(idx)}
                    className="ml-1 w-5 h-5 rounded-full bg-bg-secondary hover:bg-status-red/30 text-text-secondary hover:text-status-red flex items-center justify-center transition-colors"
                    aria-label={`Remove ${f.name}`}
                    title="Remove"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          ) : (
            <p className="text-xs text-text-muted mb-4">No files selected</p>
          )}

          <div className="flex gap-4">
            <button
              onClick={handleUpload}
              disabled={loading || !files || files.length === 0}
              className="btn-pulse"
            >
              <Upload className="w-4 h-4" />
              {loading ? 'Uploading…' : 'Upload & Create Database'}
            </button>
          </div>

          {message && <p className="mt-4 text-status-green">{message}</p>}
          {error && <p className="mt-4 text-status-red">{error}</p>}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="card">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-5 h-5 text-status-yellow" />
              <h3 className="font-semibold">Anomaly Detection</h3>
            </div>
            <p className="text-sm text-text-secondary">
              Traffic light system (RED/YELLOW/GREEN) for text and numeric data quality
              issues
            </p>
          </div>

          <div className="card">
            <div className="flex items-center gap-2 mb-2">
              <Shield className="w-5 h-5 text-status-red" />
              <h3 className="font-semibold">Column Security</h3>
            </div>
            <p className="text-sm text-text-secondary">
              Auto-detect and mark sensitive columns (PII, passwords, etc.)
            </p>
          </div>

          <div className="card">
            <div className="flex items-center gap-2 mb-2">
              <Box className="w-5 h-5 text-accent" />
              <h3 className="font-semibold">AI Payload Generation</h3>
            </div>
            <p className="text-sm text-text-secondary">
              Export sanitized JSON payloads for AI processing
            </p>
          </div>

          <div className="card">
            <div className="flex items-center gap-2 mb-2">
              <Database className="w-5 h-5 text-accent" />
              <h3 className="font-semibold">Persistent Storage</h3>
            </div>
            <p className="text-sm text-text-secondary">
              Each upload becomes a timestamped database folder you can reopen later
            </p>
          </div>
        </div>
      </div>
    </main>
  )
}
