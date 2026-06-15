'use client'

import { useEffect, useRef, useState } from 'react'
import { Download, FileSpreadsheet, FileText, ChevronDown } from 'lucide-react'
import { API_URL } from '@/lib/api'

interface TableInfo {
  table: string
  rows: number
  columns: number
}

interface TableDownloadMenuProps {
  database: string
  tables: TableInfo[]
  disabled?: boolean
}

export default function TableDownloadMenu({ database, tables, disabled }: TableDownloadMenuProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const download = (table: string, format: 'csv' | 'xlsx') => {
    const url = `${API_URL}/api/databases/${encodeURIComponent(database)}/tables/${encodeURIComponent(table)}/download?format=${format}`
    const a = document.createElement('a')
    a.href = url
    a.download = ''
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setOpen(false)
  }

  if (!tables || tables.length === 0) return null

  return (
    <div className="relative" ref={ref} data-testid="table-download-menu">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        disabled={disabled}
        className="btn-secondary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
        data-testid="table-download-trigger"
      >
        <Download className="w-4 h-4" />
        Descargar tabla
        <ChevronDown className="w-3 h-3" />
      </button>
      {open && (
        <div
          className="absolute right-0 mt-1 w-72 max-h-80 overflow-y-auto bg-bg-tertiary border border-border rounded shadow-lg z-20"
          data-testid="table-download-dropdown"
        >
          <p className="text-[10px] uppercase tracking-widest text-text-muted px-3 py-2 border-b border-border">
            {tables.length} tabla{tables.length === 1 ? '' : 's'} en {database}
          </p>
          {tables.map(t => (
            <div
              key={t.table}
              className="p-2 border-b border-border last:border-0 flex items-center gap-2"
              data-testid={`table-download-row-${t.table}`}
            >
              <div className="flex-1 min-w-0">
                <p className="text-xs font-mono text-text-primary truncate" title={t.table}>
                  {t.table}
                </p>
                <p className="text-[10px] text-text-muted">
                  {t.rows.toLocaleString()} filas · {t.columns} columnas
                </p>
              </div>
              <button
                type="button"
                onClick={() => download(t.table, 'csv')}
                title="Descargar como CSV"
                className="text-text-muted hover:text-status-green p-1.5 rounded hover:bg-bg-secondary"
                data-testid={`download-csv-${t.table}`}
              >
                <FileText className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => download(t.table, 'xlsx')}
                title="Descargar como XLSX"
                className="text-text-muted hover:text-accent p-1.5 rounded hover:bg-bg-secondary"
                data-testid={`download-xlsx-${t.table}`}
              >
                <FileSpreadsheet className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
