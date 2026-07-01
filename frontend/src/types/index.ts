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

export interface AvailableLanguage {
  language: string;
  language_code: string;
  is_generated: boolean;
  is_translatable: boolean;
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

export interface AllTranscriptsResponse {
  success: boolean;
  video_id: string;
  manual: TranscriptResult | null;
  auto: TranscriptResult | null;
  pipeline_steps: PipelineStep[];
  available_languages: AvailableLanguage[];
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
  available_languages: AvailableLanguage[];
  translation_source: string | null;
  error: string | null;
}

export const LANGUAGE_LABELS: Record<string, string> = {
  en: 'English',
  hi: 'Hindi',
  es: 'Spanish',
  fr: 'French',
  de: 'German',
  pt: 'Portuguese',
  ja: 'Japanese',
  ko: 'Korean',
  zh: 'Chinese',
  ru: 'Russian',
  ar: 'Arabic',
  it: 'Italian',
  nl: 'Dutch',
  tr: 'Turkish',
  vi: 'Vietnamese',
  th: 'Thai',
};

export function getLanguageLabel(code: string): string {
  return LANGUAGE_LABELS[code] || code.toUpperCase();
}

export type TranscriptTabSource = 'manual' | 'auto' | 'translated';

export interface TranscriptTab {
  key: string;
  label: string;
  source: TranscriptTabSource;
  available: boolean;
  language: string;
  languageCode: string;
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

// Phase 5 — Processing types
export interface ProcessingStep {
  name: string;
  status: 'pending' | 'running' | 'ok' | 'error' | 'skipped';
  detail: string;
  duration_ms: number | null;
}

export interface LanguageDistribution {
  primary: string;
  secondary: string | null;
  primary_confidence: number;
  secondary_confidence: number | null;
  mixed_ratio: number | null;
}

export interface ProcessingStatistics {
  word_count: number;
  character_count: number;
  paragraph_count: number;
  sentence_count: number;
  estimated_read_time: string;
  avg_sentence_length_words: number;
  avg_paragraph_length_words: number;
  longest_sentence_words: number;
  filler_word_count: number;
}

export interface ProcessingFlags {
  timestamps_removed: boolean;
  captions_merged: boolean;
  punctuation_restored: boolean;
  capitalization_fixed: boolean;
  duplicates_removed: boolean;
  language_detected: boolean;
  fillers_removed: boolean;
  quality_passed: boolean;
}

export interface ProcessedTimestamp {
  original_start: number;
  original_end: number;
  original_text: string;
  cleaned_text: string;
}

export interface ProcessingResult {
  success: boolean;
  video_id: string;
  language: LanguageDistribution | null;
  statistics: ProcessingStatistics;
  clean_transcript: string;
  paragraphs: string[];
  sentences: string[];
  processing_steps: ProcessingStep[];
  timestamps: ProcessedTimestamp[];
  flags: ProcessingFlags;
  processing_time_ms: number;
  error: string | null;
}

// Phase 6 — AI Content Analysis types

export type SearchIntent =
  | 'informational' | 'educational' | 'commercial' | 'transactional'
  | 'navigational' | 'comparative' | 'review' | 'tutorial'
  | 'opinion' | 'case_study' | 'research';

export type ContentCategory =
  | 'education' | 'technology' | 'finance' | 'healthcare' | 'politic' | 'career'
  | 'programming' | 'ai' | 'machine_learning' | 'business' | 'marketing'
  | 'lifestyle' | 'science' | 'entertainment' | 'sports' | 'news';

export interface AnalysisSummary {
  short: string;
  executive: string;
  detailed: string;
  bullet_points: string[];
  key_insights: string[];
}

export interface KeywordSet {
  primary: string;
  secondary: string[];
  long_tail: string[];
  semantic: string[];
  lsi: string[];
  related_topics: string[];
  brand_names: string[];
  products: string[];
  technologies: string[];
  frameworks: string[];
}

export interface EntitySet {
  people: string[];
  companies: string[];
  organizations: string[];
  universities: string[];
  countries: string[];
  cities: string[];
  technologies: string[];
  programming_languages: string[];
  frameworks: string[];
  books: string[];
  courses: string[];
  tools: string[];
  products: string[];
}

export interface ContentOutline {
  sections: string[];
  introduction: string;
  main_body: string[];
  conclusion: string;
}

export interface QualityScores {
  topic_coverage: number;
  depth_score: number;
  readability: number;
  technical_complexity: number;
  educational_value: number;
  seo_potential: number;
  evergreen_score: number;
  engagement_potential: number;
  confidence: number;
}

export interface ContentAnalysisResult {
  success: boolean;
  video_id: string;
  primary_topic: string;
  secondary_topics: string[];
  category: ContentCategory;
  subcategory: string;
  content_type: string;
  search_intent: SearchIntent;
  intent_confidence: number;
  target_audience: string;
  experience_level: string;
  industry: string;
  difficulty: string;
  content_purpose: string;
  problem_statement: string;
  main_solution: string;
  key_takeaways: string[];
  pain_points: string[];
  opportunities: string[];
  action_items: string[];
  call_to_actions: string[];
  learning_objectives: string[];
  business_value: string;
  educational_value: string;
  summary: AnalysisSummary;
  keywords: KeywordSet;
  entities: EntitySet;
  outline: ContentOutline;
  quality: QualityScores;
  analysis_time_ms: number;
  llm_provider: string;
  llm_model: string;
  prompt_version: string;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  cost_estimate: number;
  error: string | null;
}

export interface WorkflowState {
  currentStep: WorkflowStep;
  videoId: string | null;
  normalizedUrl: string | null;
  metadata: VideoMetadata | null;
  metadataResponse: VideoMetadataResponse | null;
  transcript: TranscriptResult | null;
  translatedTranscripts: Record<string, TranscriptResult>;
  selectedLanguage: string;
  processedTranscript: ProcessingResult | null;
  processingStatus: 'idle' | 'processing' | 'ok' | 'error';
  analysis: ContentAnalysisResult | null;
  analysisStatus: 'idle' | 'analyzing' | 'ok' | 'error';
  stepStatus: Record<WorkflowStep, 'pending' | 'running' | 'ok' | 'error' | 'skipped'>;
  error: string | null;
}
