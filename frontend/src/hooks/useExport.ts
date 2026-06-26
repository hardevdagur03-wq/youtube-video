import { useState, useCallback, useRef } from 'react';
import type { ProgressData, ResultData, RunResponse } from '../types';

export function useExport() {
  const [runId, setRunId] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressData | null>(null);
  const [result, setResult] = useState<ResultData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollingRef = useRef<number | null>(null);

  const startExport = useCallback(async (channel: string, limit: number) => {
    setLoading(true);
    setError(null);
    setProgress(null);
    setResult(null);

    const formData = new FormData();
    formData.append('channel', channel);
    formData.append('limit', String(limit));

    try {
      const resp = await fetch('/run', {
        method: 'POST',
        headers: { 'X-SPA-Request': '1' },
        body: formData,
      });
      if (!resp.ok) throw new Error(`Server error: ${resp.status}`);
      const data: RunResponse = await resp.json();
      setRunId(data.run_id);
      pollProgress(data.run_id);
    } catch (err: any) {
      setError(err.message || 'Network error. Please try again.');
      setLoading(false);
    }
  }, []);

  const pollProgress = useCallback((id: string) => {
    const poll = async () => {
      try {
        const resp = await fetch(`/api/progress/${id}`);
        const data: ProgressData = await resp.json();
        setProgress(data);
        setLoading(false);

        if (data.complete) {
          const resultResp = await fetch(`/api/result/${id}`);
          const resultData: ResultData = await resultResp.json();
          setResult(resultData);
          return;
        }
        pollingRef.current = window.setTimeout(poll, 1200);
      } catch {
        pollingRef.current = window.setTimeout(poll, 1200);
      }
    };
    poll();
  }, []);

  const reset = useCallback(() => {
    if (pollingRef.current) clearTimeout(pollingRef.current);
    setRunId(null);
    setProgress(null);
    setResult(null);
    setLoading(false);
    setError(null);
  }, []);

  return { runId, progress, result, loading, error, startExport, reset };
}
