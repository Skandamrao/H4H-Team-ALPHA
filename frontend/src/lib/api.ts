import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 60_000,
})

// ─── Types ────────────────────────────────────────────────────────────────────

export interface Document {
  id: string
  filename: string
  original_filename: string
  file_type: string
  file_size_bytes: number
  document_date: string | null
  document_date_confidence: string
  ingested_at: string
  processing_status: string
  processing_error: string | null
  page_count: number | null
  is_duplicate: boolean
  event_count: number
}

export interface Feature {
  id: string
  canonical_name: string
  current_status: string
  first_seen_date: string | null
  last_event_date: string | null
  module_name: string | null
  aliases: { id: string; alias: string; is_canonical: boolean; added_at: string }[]
  event_count: number
}

export interface Evidence {
  id: string
  document_id: string
  document_filename: string
  excerpt: string
  confidence: number
}

export interface Event {
  id: string
  title: string
  description: string | null
  event_type: string
  decision_status: string | null
  feature_name: string | null
  feature_name_in_source: string | null
  module_name: string | null
  reason: string | null
  decision_text: string | null
  supporting_text: string | null
  event_date: string | null
  event_date_confidence: string
  recorded_at: string
  confidence_score: number
  has_conflict: boolean
  source_document_id: string | null
  source_document_filename: string | null
  evidence: Evidence[]
}

export interface TimelineEvent {
  event_id: string
  title: string
  event_type: string
  decision_status: string | null
  event_date: string | null
  event_date_confidence: string
  description: string | null
  reason: string | null
  source_document_filename: string | null
  confidence_score: number
  has_conflict: boolean
  evidence: Evidence[]
}

export interface Timeline {
  feature_id: string
  feature_name: string
  aliases: string[]
  events: TimelineEvent[]
}

export interface DashboardStats {
  total_documents: number
  total_events: number
  total_features: number
  total_decisions: number
  total_conflicts: number
  recent_batches: IngestionBatch[]
  event_type_distribution: { event_type: string; count: number }[]
  feature_activity: unknown[]
}

export interface IngestionBatch {
  id: string
  label: string | null
  started_at: string
  completed_at: string | null
  status: string
  total_files: number
  processed_files: number
  failed_files: number
  duplicate_files: number
  new_events_extracted: number
}

export interface AssistantAnswer {
  question: string
  answer: string
  historical_events: { date: string; description: string }[]
  supporting_evidence: { document_filename: string; document_id: string; excerpt: string | null }[]
  confidence: string
  has_conflicts: boolean
  conflict_note: string | null
  missing_information: string | null
}

export interface ConflictRecord {
  feature_id: string
  feature_name: string
  conflict_type: string
  event_a: Event
  event_b: Event
  description: string
}

// ─── API calls ────────────────────────────────────────────────────────────────

export const getDashboardStats = () =>
  api.get<DashboardStats>('/api/documents/dashboard/stats').then(r => r.data)

export const getDocuments = (skip = 0, limit = 50) =>
  api.get<{ total: number; documents: Document[] }>('/api/documents/', { params: { skip, limit } }).then(r => r.data)

export const deleteDocument = (documentId: string) =>
  api.delete<{ status: string; message: string; deleted_events_count: number }>(`/api/documents/${documentId}`).then(r => r.data)

export const reprocessDocuments = () =>
  api.post<{ status: string; documents_reprocessed: number; events_extracted: number }>('/api/documents/reprocess-all').then(r => r.data)

export const uploadDocuments = (files: File[], projectId?: string, batchLabel?: string) => {
  const form = new FormData()
  files.forEach(f => form.append('files', f))
  if (projectId) form.append('project_id', projectId)
  if (batchLabel) form.append('batch_label', batchLabel)
  return api.post<Document[]>('/api/documents/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300_000,
  }).then(r => r.data)
}

export const getFeatures = (skip = 0, limit = 100) =>
  api.get<{ total: number; features: Feature[] }>('/api/features/', { params: { skip, limit } }).then(r => r.data)

export const getFeature = (id: string) =>
  api.get<Feature>(`/api/features/${id}`).then(r => r.data)

export const getEvents = (params?: Record<string, string | boolean>) =>
  api.get<{ total: number; events: Event[] }>('/api/events/', { params }).then(r => r.data)

export const getFeatureTimeline = (featureId: string, toDate?: string) =>
  api.get<Timeline>(`/api/timeline/${featureId}`, { params: toDate ? { to_date: toDate } : undefined }).then(r => r.data)

export const getKnowledgeGraph = () =>
  api.get('/api/graph/').then(r => r.data)

export const rebuildGraph = () =>
  api.post('/api/graph/rebuild').then(r => r.data)

export const askAssistant = (question: string) =>
  api.post<AssistantAnswer>('/api/assistant/ask', { question }).then(r => r.data)

export const getAssistantSuggestions = () =>
  api.get<{ suggestions: string[] }>('/api/assistant/suggestions').then(r => r.data)

export const getConflicts = () =>
  api.get<{ total: number; conflicts: ConflictRecord[] }>('/api/conflicts/').then(r => r.data)

export const getIngestionBatches = () =>
  api.get<IngestionBatch[]>('/api/ingestion/batches').then(r => r.data)

export const loadSampleData = () =>
  api.post<{ message: string; status: string }>('/api/documents/load-sample-data').then(r => r.data)
