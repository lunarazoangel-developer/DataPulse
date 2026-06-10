'use client'

import { useState } from 'react'
import axios from 'axios'
import { Upload, FileSpreadsheet, AlertTriangle, Shield, Box, Trash2 } from 'lucide-react'
import { API_URL } from '@/lib/api'

export default function Home() {
  const [files, setFiles] = useState<File[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [tables, setTables] = useState<any[]>([])
  const [error, setError] = useState('')

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles(Array.from(e.target.files))
    }
  }

  const handleUpload = async () => {
    if (!files || files.length === 0) return

    setLoading(true)
    setError('')
    setMessage('')

    try {
      await axios.delete(`${API_URL}/api/files/clear`)
    } catch {
      console.log('No data to clear')
    }

    const formData = new FormData()
    files.forEach(file => {
      formData.append('files', file)
    })

    try {
      const response = await axios.post(`${API_URL}/api/files/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })

      setMessage(response.data.message)
      setTables(response.data.tables || [])
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

  const handleClear = async () => {
    try {
      await axios.delete(`${API_URL}/api/files/clear`)
      setFiles(null)
      setTables([])
      setMessage('')
      setError('')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Error clearing data')
    }
  }

  return (
    <main className="min-h-screen bg-bg-primary p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-4xl font-bold text-accent mb-2">DataPulse</h1>
        <p className="text-text-secondary mb-8">Intelligent Data Cleaning Assistant</p>

        <div className="card mb-8">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Upload className="w-5 h-5" />
            Upload Data Files
          </h2>

          <div className="mb-4">
            <input
              type="file"
              multiple
              accept=".csv,.xlsx,.xls"
              onChange={handleFileChange}
              className="input w-full"
            />
          </div>

          {files && files.length > 0 && (
            <p className="text-sm text-text-secondary mb-4">
              {files.length} file(s) selected: {files.map(f => f.name).join(', ')}
            </p>
          )}

          <div className="flex gap-4">
            <button
              onClick={handleUpload}
              disabled={loading || !files || files.length === 0}
              className="btn-primary disabled:opacity-50 flex items-center gap-2"
            >
              {loading ? 'Processing...' : 'Upload Files'}
            </button>

            <button onClick={handleClear} className="btn-secondary flex items-center gap-2">
              <Trash2 className="w-4 h-4" />
              Clear Data
            </button>
          </div>

          {message && (
            <p className="mt-4 text-status-green">{message}</p>
          )}

          {error && (
            <p className="mt-4 text-status-red">{error}</p>
          )}
        </div>

        {tables.length > 0 && (
          <div className="card mb-8">
            <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
              <FileSpreadsheet className="w-5 h-5" />
              Loaded Tables
            </h2>

            <div className="space-y-2">
              {tables.map((table, idx) => (
                <div key={idx} className="flex justify-between items-center p-3 bg-bg-tertiary rounded">
                  <span className="font-medium">{table.name}</span>
                  <span className="text-sm text-text-secondary">
                    {table.rows} rows × {table.columns} cols
                  </span>
                </div>
              ))}
            </div>

            <a href="/dashboard" className="btn-primary inline-block mt-4">
              Go to Dashboard
            </a>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="card">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-5 h-5 text-status-yellow" />
              <h3 className="font-semibold">Anomaly Detection</h3>
            </div>
            <p className="text-sm text-text-secondary">
              Traffic light system (RED/YELLOW/GREEN) for text and numeric data quality issues
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
        </div>
      </div>
    </main>
  )
}
