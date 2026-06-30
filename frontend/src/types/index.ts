export interface Step {
  name: string;
  status: 'pending' | 'running' | 'ok' | 'error';
  detail: string;
}

export interface ProgressData {
  steps: Step[];
  complete: boolean;
}

export interface ResultData {
  success: boolean;
  run_id?: string;
  channel_title?: string;
  channel_id?: string;
  total_videos?: number;
  total_discovered?: number;
  total_api_calls?: number;
  file_size_bytes?: number;
  elapsed_seconds?: number;
  error?: string;
  steps?: Step[];
}

export interface RunResponse {
  run_id: string;
}

export type ExportFormat = 'csv' | 'excel' | 'json';

export interface DurationInfo {
  iso: string | null;
  readable: string | null;
  compact: string | null;
  seconds: number | null;
}

export interface VideoStatistics {
  views: number;
  likes: number;
  comments: number;
  views_formatted: string;
  likes_formatted: string;
  comments_formatted: string;
}

export interface Thumbnails {
  default: string | null;
  medium: string | null;
  high: string | null;
  standard: string | null;
  maxres: string | null;
}

export interface DateInfo {
  iso: string | null;
  localized: string | null;
  relative: string | null;
}

export interface ChannelInfo {
  name: string | null;
  id: string | null;
  url: string | null;
  verified: boolean | null;
}

export interface DescriptionInfo {
  full: string | null;
  urls: string[];
  hashtags: string[];
  mentions: string[];
}

export interface VideoMetadata {
  video_id: string;
  title: string | null;
  description: DescriptionInfo;
  channel: ChannelInfo;
  published_at: DateInfo;
  duration: DurationInfo;
  statistics: VideoStatistics;
  thumbnails: Thumbnails;
  tags: string[];
  category_id: string | null;
  language: string | null;
  license: string | null;
  embeddable: boolean | null;
  caption: boolean | null;
  privacy: string | null;
  live_status: string | null;
  default_audio_language: string | null;
}

export interface VideoMetadataResponse {
  success: boolean;
  video: VideoMetadata | null;
  error: string | null;
}

// Transcript types
export type TranscriptSource = 'manual' | 'auto' | 'whisper';
export type TranscriptProvider = 'youtube_manual' | 'youtube_auto' | 'faster_whisper';
export type PipelineStepStatus = 'pending' | 'running' | 'ok' | 'error' | 'skipped';

export interface TranscriptSegment {
  start: number;
  end: number;
  duration: number;
  text: string;
}

export interface WhisperProcessingInfo {
  model_name: string;
  transcription_duration_seconds: number | null;
  audio_duration_seconds: number | null;
  processing_time_seconds: number | null;
  language_detected: string | null;
  language_confidence: number | null;
  word_timestamps: boolean;
  audio_download_time_seconds: number | null;
}

export interface PipelineStep {
  name: string;
  status: PipelineStepStatus;
  detail: string;
  duration_seconds: number | null;
}

export interface TranscriptResult {
  success: boolean;
  video_id: string;
  source: TranscriptSource;
  provider: TranscriptProvider;
  language: string;
  language_confidence: number | null;
  segments: TranscriptSegment[];
  plain_text: string;
  paragraph_text: string;
  word_count: number;
  character_count: number;
  estimated_read_time: string;
  generated_at: string;
  duration_seconds: number | null;
  whisper_info: WhisperProcessingInfo | null;
  pipeline_steps: PipelineStep[];
  error: string | null;
}

// Workflow types
export type WorkflowStep = 'url' | 'metadata' | 'transcript' | 'analysis' | 'generate' | 'editor' | 'export';

export const WORKFLOW_STEPS: { key: WorkflowStep; label: string; number: number }[] = [
  { key: 'url', label: 'Video URL', number: 1 },
  { key: 'metadata', label: 'Metadata', number: 2 },
  { key: 'transcript', label: 'Transcript', number: 3 },
  { key: 'analysis', label: 'AI Analysis', number: 4 },
  { key: 'generate', label: 'Blog Generation', number: 5 },
  { key: 'editor', label: 'Editor', number: 6 },
  { key: 'export', label: 'Export', number: 7 },
];

export interface WorkflowState {
  currentStep: WorkflowStep;
  videoId: string | null;
  normalizedUrl: string | null;
  metadata: VideoMetadata | null;
  metadataResponse: VideoMetadataResponse | null;
  transcript: TranscriptResult | null;
  stepStatus: Record<WorkflowStep, 'pending' | 'running' | 'ok' | 'error' | 'skipped'>;
  error: string | null;
}
