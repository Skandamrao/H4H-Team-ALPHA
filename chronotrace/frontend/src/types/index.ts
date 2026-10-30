// ── Shared TypeScript Types for ChronoTrace AI ──────────────────────────────

export type EventType =
  | 'PROPOSED' | 'APPROVED' | 'REJECTED' | 'IMPLEMENTED'
  | 'MODIFIED' | 'RENAMED' | 'REMOVED' | 'DEPENDENCY_ADDED' | 'OTHER';

export type DatePrecision = 'exact' | 'approximate' | 'month' | 'quarter' | 'year' | 'unknown';
export type DateBasis = 'explicit' | 'inferred_context' | 'inferred_sequence' | 'unknown';
export type AnswerStatus = 'SUPPORTED' | 'PARTIALLY_SUPPORTED' | 'CONFLICTED' | 'INSUFFICIENT_EVIDENCE';

export interface TemporalEvent {
  id: string;
  project_id: string;
  feature_id: string | null;
  unresolved_feature_mention: string | null;
  event_type: EventType;
  description: string;
  previous_name: string | null;
  new_name: string | null;
  event_date: string | null;         // ISO date string
  event_date_raw: string | null;
  event_date_precision: DatePrecision;
  event_date_basis: DateBasis;
  source_id: string;
  evidence_excerpt: string;
  actor: string | null;
  related_event_ids: string[];
  supersedes_event_id: string | null;
  is_superseded: boolean;
  extraction_confidence: number | null;
  needs_review: boolean;
  ingestion_timestamp: string;
}

export interface FeatureAlias {
  id: string;
  alias: string;
  source_id: string;
  evidence_excerpt: string;
  added_at: string;
}

export interface Feature {
  id: string;
  project_id: string;
  canonical_name: string;
  created_at: string;
  is_removed: boolean;
  is_implemented: boolean;
  is_approved: boolean;
  aliases: FeatureAlias[];
}

export interface TimelineEvent {
  event: TemporalEvent;
  milestone_label: string | null;
}

export interface FeatureTimeline {
  feature: Feature;
  events: TimelineEvent[];
  conflicts: string[];
  gaps: string[];
  as_of_event_date: string | null;
}

export interface ConflictRecord {
  id: string;
  project_id: string;
  event_id_a: string;
  event_id_b: string;
  conflict_type: string;
  description: string;
  detected_at: string;
  resolved: boolean;
}

export interface SupportingEvidence {
  event: TemporalEvent;
  relevance_note: string;
}

export interface QuestionAnswer {
  question: string;
  answer: string;
  status: AnswerStatus;
  supporting_evidence: SupportingEvidence[];
  conflicting_events: TemporalEvent[];
  missing_information: string[];
  cited_source_ids: string[];
  confidence: number;
}

export interface IngestRecordResult {
  source_id: string;
  events_extracted: number;
  features_identified: number;
  conflicts_detected: number;
  warnings: string[];
}

export interface IngestBatchResponse {
  batch_id: string;
  records_processed: number;
  total_events_extracted: number;
  total_features_identified: number;
  total_conflicts_detected: number;
  results: IngestRecordResult[];
  warnings: string[];
}

