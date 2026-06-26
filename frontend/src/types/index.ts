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
