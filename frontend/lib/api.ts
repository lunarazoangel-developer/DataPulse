import axios from 'axios'

export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface DatabaseTable {
  name: string
  rows: number
  columns: number
}

export interface DatabaseInfo {
  name: string
  created_at: string
  tables: DatabaseTable[]
  table_count: number
  file_count: number
  total_rows: number
}

export interface UploadResponse {
  message: string
  database: string
  tables: string[]
  table_count: number
  relationships_count: number
}

export interface OpenDatabaseResponse {
  message: string
  database: string
  tables: string[]
  table_count: number
  relationships_count: number
}

export interface AIPayload {
  metadata?: Record<string, unknown>
  schemas?: Record<string, unknown>
  relationships?: unknown[]
  anomalies?: Record<string, unknown>
  summary?: Record<string, unknown>
  [key: string]: unknown
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface AIStatus {
  available: boolean
  model: string
}

export type ProposalRisk = 'low' | 'medium' | 'high'

export interface Proposal {
  id: string
  risk: ProposalRisk
  title: string
  description: string
  table: string
  column: string
  action: string
  params: Record<string, unknown>
}

export interface ChatRequestBody {
  payload: AIPayload
  history: ChatMessage[]
  message?: string | null
}

export interface ChatResponseBody {
  message: string
  available: boolean
  model: string
  summary: string
  proposals: Proposal[]
}

export interface ApplyRequestBody {
  database?: string | null
  proposals: Proposal[]
}

export interface ApplyResultItem {
  id: string
  table: string
  column: string
  action: string
  risk: ProposalRisk
  rows_changed: number
  rows_after: number
}

export interface ApplyResponseBody {
  database: string
  applied: ApplyResultItem[]
  skipped: { id?: string; reason: string }[]
  errors: { id?: string; table?: string; column?: string; action?: string; reason: string }[]
  table_summaries: { table: string; rows: number; columns: number }[]
}

export const api = {
  listDatabases: () =>
    axios.get<{ databases: DatabaseInfo[]; count: number }>(`${API_URL}/api/databases`),
  openDatabase: (name: string) =>
    axios.get<OpenDatabaseResponse>(`${API_URL}/api/databases/${encodeURIComponent(name)}`),
  deleteDatabase: (name: string) =>
    axios.delete<{ message: string }>(`${API_URL}/api/databases/${encodeURIComponent(name)}`),
  getCurrentDatabase: () =>
    axios.get<{ database: string | null }>(`${API_URL}/api/databases/current`),
  uploadFiles: (formData: FormData) =>
    axios.post<UploadResponse>(`${API_URL}/api/files/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  clearSession: () => axios.delete(`${API_URL}/api/files/clear`),
  getPayloadPreview: () =>
    axios.get<{ payload: AIPayload; summary: Record<string, unknown> }>(
      `${API_URL}/api/payload/preview`
    ),
}

export const aiApi = {
  getStatus: () => axios.get<AIStatus>(`${API_URL}/api/ai/status`),
  chat: (body: ChatRequestBody) =>
    axios.post<ChatResponseBody>(`${API_URL}/api/ai/chat`, body),
  apply: (body: ApplyRequestBody) =>
    axios.post<ApplyResponseBody>(`${API_URL}/api/ai/apply`, body),
}
