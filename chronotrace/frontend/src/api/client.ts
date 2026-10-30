import axios from 'axios';
import type {
  Feature, TemporalEvent, FeatureTimeline, ConflictRecord,
  QuestionAnswer, IngestBatchResponse,
} from '../types';

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

// ── Health ────────────────────────────────────────────────────────────────────
export const getHealth = () => api.get('/health').then(r => r.data);
export const getInfo   = () => api.get('/info').then(r => r.data);

// ── Ingestion ─────────────────────────────────────────────────────────────────
export const ingestBatch = (records: object[]): Promise<IngestBatchResponse> =>
  api.post('/ingest', { records }).then(r => r.data);

// ── Features ──────────────────────────────────────────────────────────────────
export const listFeatures = (
  projectId: string,
  params?: { is_implemented?: boolean; is_removed?: boolean }
): Promise<Feature[]> =>
  api.get('/features', { params: { project_id: projectId, ...params } }).then(r => r.data);

export const getFeature = (featureId: string): Promise<Feature> =>
  api.get(`/features/${featureId}`).then(r => r.data);

// ── Events ────────────────────────────────────────────────────────────────────
export const listEvents = (
  projectId: string,
  params?: {
    feature_id?: string;
    event_type?: string;
    from_date?: string;
    to_date?: string;
    needs_review?: boolean;
    limit?: number;
    offset?: number;
  }
): Promise<TemporalEvent[]> =>
  api.get('/events', { params: { project_id: projectId, ...params } }).then(r => r.data);

export const getEvent = (eventId: string): Promise<TemporalEvent> =>
  api.get(`/events/${eventId}`).then(r => r.data);

export const listConflicts = (
  projectId: string,
  resolved?: boolean
): Promise<ConflictRecord[]> =>
  api.get('/events/conflicts', { params: { project_id: projectId, resolved } }).then(r => r.data);

// ── Timeline ──────────────────────────────────────────────────────────────────
export const getFeatureTimeline = (
  featureId: string,
  asOfEventDate?: string,
): Promise<FeatureTimeline> =>
  api.get(`/timeline/feature/${featureId}`, {
    params: { as_of_event_date: asOfEventDate },
  }).then(r => r.data);

export const getProjectState = (
  projectId: string,
  asOfDate: string,
): Promise<{ as_of_date: string; features: object[] }> =>
  api.get('/timeline/state', { params: { project_id: projectId, as_of_date: asOfDate } })
    .then(r => r.data);

// ── QA ────────────────────────────────────────────────────────────────────────
export const askQuestion = (payload: {
  question: string;
  project_id: string;
  as_of_event_date?: string;
}): Promise<QuestionAnswer> =>
  api.post('/ask', payload).then(r => r.data);

