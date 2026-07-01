import type { TranscriptResult, AllTranscriptsResponse } from '../types';

const API_BASE = '/api';

class TranscriptService {
  private transcriptCache = new Map<string, AllTranscriptsResponse>();
  private translationCache = new Map<string, TranscriptResult>();

  async fetchAllTranscripts(videoId: string): Promise<AllTranscriptsResponse> {
    const cached = this.transcriptCache.get(videoId);
    if (cached) {
      console.log(`[TranscriptService] Cache HIT for ${videoId}`);
      return cached;
    }

    console.log(`[TranscriptService] Fetching ALL transcripts for ${videoId}`);
    const resp = await fetch(`${API_BASE}/transcript/${videoId}/all`);
    if (!resp.ok) {
      const body = await resp.json().catch(() => null);
      throw new Error(body?.error || `Server returned ${resp.status}`);
    }

    const data: AllTranscriptsResponse = await resp.json();
    console.log(`[TranscriptService] Response: success=${data.success}, manual=${data.manual ? 'YES' : 'NULL'}, auto=${data.auto ? 'YES' : 'NULL'}`);

    if (data.success) {
      this.transcriptCache.set(videoId, data);
    }
    return data;
  }

  async fetchTranscript(videoId: string): Promise<TranscriptResult> {
    const cached = this.transcriptCache.get(videoId);
    if (cached) {
      const best = cached.manual || cached.auto;
      if (best) return best;
    }

    console.log(`[TranscriptService] Fetching single transcript for ${videoId}`);
    const resp = await fetch(`${API_BASE}/transcript/${videoId}`);
    if (!resp.ok) {
      const body = await resp.json().catch(() => null);
      throw new Error(body?.error || `Server returned ${resp.status}`);
    }

    const data: TranscriptResult = await resp.json();
    return data;
  }

  async translateTranscript(
    videoId: string,
    targetLang: string,
  ): Promise<TranscriptResult> {
    const cacheKey = `${videoId}:${targetLang}`;
    const cached = this.translationCache.get(cacheKey);
    if (cached) {
      console.log(`[TranscriptService] Translation cache HIT for ${targetLang}`);
      return cached;
    }

    console.log(`[TranscriptService] Fetching translation for ${targetLang}`);
    const resp = await fetch(
      `${API_BASE}/transcript/${videoId}/translate/${targetLang}`,
    );
    const data: TranscriptResult = await resp.json();
    console.log(`[TranscriptService] Translation response: success=${data.success}, lang=${data.language}`);
    if (data.success) {
      this.translationCache.set(cacheKey, data);
    }
    return data;
  }

  getCachedAll(videoId: string): AllTranscriptsResponse | undefined {
    return this.transcriptCache.get(videoId);
  }

  getCachedTranslation(
    videoId: string,
    targetLang: string,
  ): TranscriptResult | undefined {
    return this.translationCache.get(`${videoId}:${targetLang}`);
  }

  clearCache(): void {
    this.transcriptCache.clear();
    this.translationCache.clear();
  }
}

export const transcriptService = new TranscriptService();
