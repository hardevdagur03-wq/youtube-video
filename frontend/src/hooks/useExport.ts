import { useState, useCallback, useRef } from 'react';
import type { ProgressData, ResultData, RunResponse } from '../types';

const API_BASE = '';
const FETCH_TIMEOUT = 30000; // 30 seconds
const POLL_INTERVAL = 1500; // 1.5 seconds
const MAX_POLL_ATTEMPTS = 400; // 10 minutes at 1.5s intervals
const MAX_CONSECUTIVE_ERRORS = 5;

function fetchWithTimeout(url: string, options: RequestInit = {}, timeoutMs = FETCH_TIMEOUT): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const signal = controller.signal;
  return fetch(url, { ...options, signal }).finally(() => clearTimeout(timeoutId));
}

function describeFetchError(err: unknown, status?: number): string {
  // Network-level errors
  if (err instanceof DOMException && err.name === 'AbortError') {
    return 'Request timed out. The server may be overloaded or unreachable. Please try again.';
  }
  if (err instanceof TypeError) {
    const msg = err.message;
    if (msg === 'Failed to fetch' || msg.includes('NetworkError') || msg.includes('network')) {
      return 'Unable to connect to the server. Make sure the backend is running (start_server.bat) and try again.';
    }
    if (msg.includes('load')) {
      return 'Failed to load resource. Check that the backend server is running on port 8000.';
    }
  }
  // HTTP errors
  if (status) {
    if (status === 0) {
      return 'Unable to connect to the server. Make sure the backend is running and try again.';
    }
    if (status === 429) {
      return 'Server is receiving too many requests. Please wait a moment and try again.';
    }
    if (status >= 500) {
      return 'Server encountered an internal error. Please try again later.';
    }
    return `Server returned an error (HTTP ${status}). Please try again later.`;
  }
  // Error objects
  if (err instanceof Error) {
    const msg = err.message;
    if (msg.includes('quota') || msg.includes('403') || msg.includes('quotaExceeded')) {
      return 'YouTube API quota exceeded or API key is invalid. Please check your API key configuration.';
    }
    if (msg.includes('expired') || msg.includes('API key')) {
      return 'YouTube API key has expired or is invalid. Please update your .env file.';
    }
    if (msg.includes('not found') || msg.includes('404')) {
      return 'The requested channel or video was not found. Check the URL and try again.';
    }
    if (msg.includes('connection') || msg.includes('timeout') || msg.includes('ECONNREFUSED')) {
      return 'Unable to connect to the server. Make sure the backend is running and try again.';
    }
    if (msg.includes('not configured') || msg.includes('access not configured')) {
      return 'YouTube API access is not configured. Please enable the YouTube Data API v3 in Google Cloud Console.';
    }
    return msg;
  }
  return 'An unexpected error occurred. Please try again.';
}

async function checkHealth(): Promise<{ ok: boolean; error?: string }> {
  try {
    const resp = await fetchWithTimeout(`${API_BASE}/api/health`, {}, 5000);
    if (!resp.ok) {
      return { ok: false, error: `Health check failed (HTTP ${resp.status})` };
    }
    const data = await resp.json();
    if (data.status !== 'ok') {
      return { ok: false, error: data.youtube_api_key_error || 'Backend is in degraded state.' };
    }
    return { ok: true };
  } catch (err: any) {
    return { ok: false, error: describeFetchError(err) };
  }
}

export function useExport() {
  const [runId, setRunId] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressData | null>(null);
  const [result, setResult] = useState<ResultData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollingRef = useRef<number | null>(null);
  const [backendStatus, setBackendStatus] = useState<'unknown' | 'ok' | 'error'>('unknown');

  const startExport = useCallback(async (channel: string, limit: number) => {
    setLoading(true);
    setError(null);
    setProgress(null);
    setResult(null);

    // Check backend health first
    const health = await checkHealth();
    if (!health.ok) {
      setError(health.error || 'Backend is not reachable. Please make sure the server is running.');
      setLoading(false);
      setBackendStatus('error');
      return;
    }
    setBackendStatus('ok');

    const formData = new FormData();
    formData.append('channel', channel);
    formData.append('limit', String(limit));

    try {
      const resp = await fetchWithTimeout(`${API_BASE}/run`, {
        method: 'POST',
        headers: { 'X-SPA-Request': '1' },
        body: formData,
      });
      if (!resp.ok) {
        let detail = '';
        try {
          const body = await resp.json();
          detail = body.error || body.detail || '';
        } catch {
          // ignore parse errors
        }
        throw new Error(detail || `Server error (HTTP ${resp.status})`);
      }
      const data: RunResponse = await resp.json();
      if (!data.run_id) throw new Error('Server did not return a run ID.');
      setRunId(data.run_id);
      pollProgress(data.run_id);
    } catch (err: any) {
      setError(describeFetchError(err, (err as any)?.status));
      setLoading(false);
    }
  }, []);

  const pollProgress = useCallback((id: string) => {
    let attempts = 0;
    let consecutiveErrors = 0;

    const poll = async () => {
      try {
        const resp = await fetchWithTimeout(`${API_BASE}/api/progress/${id}`, {}, 10000);
        if (!resp.ok) {
          consecutiveErrors++;
          if (consecutiveErrors > MAX_CONSECUTIVE_ERRORS) {
            setError('Failed to check export progress. The server may have restarted. Please try again.');
            setLoading(false);
            return;
          }
          pollingRef.current = window.setTimeout(poll, POLL_INTERVAL);
          return;
        }
        consecutiveErrors = 0;
        const data: ProgressData = await resp.json();
        setProgress(data);
        setLoading(false);

        if (data.complete) {
          const resultResp = await fetchWithTimeout(`${API_BASE}/api/result/${id}`, {}, 10000);
          if (!resultResp.ok) {
            let detail = '';
            try {
              const body = await resultResp.json();
              detail = body.error || '';
            } catch {
              // ignore
            }
            setError(detail || 'Failed to retrieve export result.');
            return;
          }
          const resultData: ResultData = await resultResp.json();
          setResult(resultData);
          return;
        }
        attempts = 0;
        if (pollingRef.current !== null) {
          pollingRef.current = window.setTimeout(poll, POLL_INTERVAL);
        }
      } catch (err: any) {
        consecutiveErrors++;
        if (consecutiveErrors > MAX_CONSECUTIVE_ERRORS) {
          setError('Lost connection to the server while checking progress. Please try again.');
          setLoading(false);
          return;
        }
        if (pollingRef.current !== null) {
          pollingRef.current = window.setTimeout(poll, POLL_INTERVAL);
        }
      }
    };
    poll();
  }, []);

  const reset = useCallback(() => {
    if (pollingRef.current !== null) {
      clearTimeout(pollingRef.current);
      pollingRef.current = null;
    }
    setRunId(null);
    setProgress(null);
    setResult(null);
    setLoading(false);
    setError(null);
    setBackendStatus('unknown');
  }, []);

  return { runId, progress, result, loading, error, startExport, reset, backendStatus };
}
