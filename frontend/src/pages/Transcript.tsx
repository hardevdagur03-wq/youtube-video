import { motion } from 'framer-motion';
import { useState } from 'react';
import { Youtube, Loader2, MessageSquareText } from 'lucide-react';
import { Container, Badge, Card } from '../components/ui';
import VideoUrlInput from '../components/blog/VideoUrlInput';
import VideoDetails from '../components/blog/VideoDetails';
import TranscriptPipeline from '../components/transcript/TranscriptPipeline';
import TranscriptViewer from '../components/transcript/TranscriptViewer';
import TranscriptSkeleton from '../components/transcript/TranscriptSkeleton';
import TranscriptError from '../components/transcript/TranscriptError';
import type {
  VideoMetadataResponse,
  TranscriptResult,
  PipelineStep,
} from '../types';
import { transcriptService } from '../services/TranscriptService';

export default function Transcript() {
  const [validatedVideoId, setValidatedVideoId] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<VideoMetadataResponse | null>(null);
  const [loadingMetadata, setLoadingMetadata] = useState(false);
  const [metadataError, setMetadataError] = useState<string | null>(null);

  // Transcript state — stored SEPARATELY
  const [loadingTranscript, setLoadingTranscript] = useState(false);
  const [transcriptError, setTranscriptError] = useState<string | null>(null);

  const [manualTranscript, setManualTranscript] =
    useState<TranscriptResult | null>(null);
  const [autoTranscript, setAutoTranscript] =
    useState<TranscriptResult | null>(null);
  const [translatedTranscripts, setTranslatedTranscripts] = useState<
    Record<string, TranscriptResult>
  >({});
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStep[]>([]);
  const [availableLanguages, setAvailableLanguages] = useState<
    { language: string; language_code: string; is_generated: boolean; is_translatable: boolean }[]
  >([]);

  const [selectedLanguage, setSelectedLanguage] = useState<string>('en');
  const [isTranslating, setIsTranslating] = useState(false);

  // Compute active transcript from separate stores
  const getActiveTranscript = (): TranscriptResult | null => {
    const lang = selectedLanguage;

    // If selected language matches auto transcript, return auto
    if (autoTranscript && lang === autoTranscript.language) {
      console.log(`[Transcript] active=auto (lang=${lang})`);
      return autoTranscript;
    }

    // If selected language matches manual transcript, return manual
    if (manualTranscript && lang === manualTranscript.language) {
      console.log(`[Transcript] active=manual (lang=${lang})`);
      return manualTranscript;
    }

    // If translated version exists, return it
    if (translatedTranscripts[lang]) {
      console.log(`[Transcript] active=translated (lang=${lang})`);
      return translatedTranscripts[lang];
    }

    // Fallback: auto first, then manual
    const fallback = autoTranscript || manualTranscript;
    if (fallback) {
      console.log(`[Transcript] active=fallback (${fallback.source}, lang=${fallback.language})`);
    }
    return fallback;
  };

  const handleValidUrl = async (videoId: string, _normalizedUrl: string) => {
    setValidatedVideoId(videoId);
    setLoadingMetadata(true);
    setMetadataError(null);
    setMetadata(null);
    resetTranscriptState();

    try {
      const resp = await fetch(`/api/video-metadata/${videoId}`);
      if (!resp.ok) {
        const body = await resp.json().catch(() => null);
        setMetadataError(
          body?.error || `Server returned ${resp.status} ${resp.statusText}.`,
        );
        return;
      }
      const data: VideoMetadataResponse = await resp.json();
      if (data.success && data.video) {
        setMetadata(data);
        await fetchAllTranscripts(videoId);
      } else {
        setMetadataError(data.error || 'Failed to load video metadata.');
      }
    } catch (err) {
      setMetadataError(
        err instanceof TypeError
          ? 'Could not reach the server. Check your connection.'
          : `Metadata request failed: ${
              err instanceof Error ? err.message : 'Unknown error'
            }.`,
      );
    } finally {
      setLoadingMetadata(false);
    }
  };

  const resetTranscriptState = () => {
    setManualTranscript(null);
    setAutoTranscript(null);
    setTranslatedTranscripts({});
    setPipelineSteps([]);
    setAvailableLanguages([]);
    setSelectedLanguage('en');
    setTranscriptError(null);
  };

  const fetchAllTranscripts = async (videoId: string) => {
    setLoadingTranscript(true);
    setTranscriptError(null);
    resetTranscriptState();

    try {
      const data = await transcriptService.fetchAllTranscripts(videoId);
      console.log(`[Transcript] All transcripts response:`, data);

      if (!data.success) {
        setTranscriptError('Failed to load any transcript.');
        setPipelineSteps(data.pipeline_steps || []);
        return;
      }

      // Store manual and auto SEPARATELY
      setManualTranscript(data.manual || null);
      setAutoTranscript(data.auto || null);
      setPipelineSteps(data.pipeline_steps || []);
      setAvailableLanguages(data.available_languages || []);

      // Set default language from whichever is available
      const firstAvailable = data.auto || data.manual;
      if (firstAvailable) {
        setSelectedLanguage(firstAvailable.language);
        console.log(`[Transcript] Default language set to: ${firstAvailable.language}`);
      }
    } catch (err) {
      setTranscriptError(
        err instanceof TypeError
          ? 'Could not reach the server. Check your connection.'
          : `Transcript request failed: ${
              err instanceof Error ? err.message : 'Unknown error'
            }.`,
      );
    } finally {
      setLoadingTranscript(false);
    }
  };

  const translateTranscript = async (
    videoId: string,
    targetLang: string,
  ) => {
    const source = autoTranscript || manualTranscript;
    if (!source) return;

    console.log(`[Transcript] translateTranscript called: targetLang=${targetLang}, source.lang=${source.language}`);

    // If already in this language, just select it
    if (targetLang === source.language) {
      console.log(`[Transcript] Same as source language, selecting directly`);
      setSelectedLanguage(targetLang);
      return;
    }

    // If already translated
    if (translatedTranscripts[targetLang]) {
      console.log(`[Transcript] Using cached translation: ${targetLang}`);
      setSelectedLanguage(targetLang);
      return;
    }

    // Check service cache
    const cached = transcriptService.getCachedTranslation(videoId, targetLang);
    if (cached) {
      console.log(`[Transcript] Using service-cached translation: ${targetLang}`);
      setTranslatedTranscripts((prev) => ({
        ...prev,
        [targetLang]: cached,
      }));
      setSelectedLanguage(targetLang);
      return;
    }

    setIsTranslating(true);
    console.log(`[Transcript] Fetching translation: ${targetLang}`);
    try {
      const data = await transcriptService.translateTranscript(
        videoId,
        targetLang,
      );
      console.log(`[Transcript] Translation API response:`, data);

      if (data.success) {
        // Only store as translated if language actually changed
        if (data.language !== source.language) {
          setTranslatedTranscripts((prev) => ({
            ...prev,
            [targetLang]: data,
          }));
          console.log(`[Transcript] Translation stored for: ${targetLang}`);
        } else {
          console.log(`[Transcript] Translation returned same language (${data.language}), not storing`);
        }
      }
      setSelectedLanguage(targetLang);
    } catch (err) {
      console.error(`[Transcript] Translation failed:`, err);
    } finally {
      setIsTranslating(false);
    }
  };

  const handleLanguageChange = async (lang: string) => {
    console.log(`[Transcript] Language change requested: ${lang}`);
    if (!validatedVideoId) return;
    setSelectedLanguage(lang);
    console.log(`[Transcript] selectedLanguage set to: ${lang}`);

    // If it's NOT the source language, fetch translation
    const source = autoTranscript || manualTranscript;
    if (source && lang !== source.language && !translatedTranscripts[lang]) {
      await translateTranscript(validatedVideoId, lang);
    }
  };

  const handleRetry = () => {
    if (validatedVideoId) {
      transcriptService.clearCache();
      fetchAllTranscripts(validatedVideoId);
    }
  };

  // Build transcript object for TranscriptViewer from separate stores
  const buildViewerTranscript = (): TranscriptResult | null => {
    const active = getActiveTranscript();
    if (!active) return null;

    // Merge pipeline steps and available languages into the active transcript
    return {
      ...active,
      pipeline_steps: pipelineSteps,
      available_languages: availableLanguages,
    };
  };

  const viewerTranscript = buildViewerTranscript();

  console.log(`[Transcript] RENDER: selectedLanguage=${selectedLanguage}, manual=${manualTranscript ? 'YES' : 'NULL'}, auto=${autoTranscript ? 'YES' : 'NULL'}, translated=${Object.keys(translatedTranscripts).join(',') || 'none'}`);

  return (
    <>
      <section className="relative overflow-hidden bg-gradient-to-br from-emerald-600 via-emerald-500 to-teal-600 dark:from-emerald-800 dark:via-emerald-700 dark:to-teal-900">
        <div className="absolute inset-0">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,rgba(255,255,255,0.12),transparent_60%)]" />
          <div className="absolute bottom-0 right-1/4 w-[400px] h-[400px] bg-white/5 rounded-full blur-3xl" />
        </div>

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-28 lg:pt-32 pb-12 lg:pb-16">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            className="max-w-2xl"
          >
            <Badge variant="info">Transcript Engine</Badge>
            <h1 className="text-[36px] sm:text-[44px] lg:text-[52px] font-extrabold leading-[1.08] tracking-[-0.03em] text-white mt-4 mb-3">
              URL → Transcript
            </h1>
            <p className="text-[17px] leading-relaxed text-white/75 max-w-lg">
              Extract the highest-quality transcript from any YouTube video.
              Automatic fallback from manual captions to Whisper AI.
            </p>
          </motion.div>
        </div>
      </section>

      <section className="relative z-10 -mt-6 pb-20">
        <Container>
          <div className="max-w-4xl mx-auto">
            {!metadata && !loadingMetadata && (
              <Card padding="lg" className="mb-6">
                <div className="flex items-center gap-3 mb-6">
                  <div className="w-10 h-10 rounded-xl bg-emerald-50 dark:bg-emerald-900/30 flex items-center justify-center flex-shrink-0">
                    <Youtube
                      size={18}
                      className="text-emerald-600 dark:text-emerald-400"
                    />
                  </div>
                  <div>
                    <h3 className="text-base font-semibold text-gray-900 dark:text-white">
                      YouTube Video URL
                    </h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      Enter a YouTube video URL to extract its transcript
                    </p>
                  </div>
                </div>
                <VideoUrlInput onValidUrl={handleValidUrl} />
              </Card>
            )}

            {loadingMetadata && !metadata && (
              <div className="mb-6">
                <Card padding="lg">
                  <div className="flex items-center gap-2.5 text-sm text-gray-500 dark:text-gray-400">
                    <Loader2
                      size={14}
                      className="animate-spin text-emerald-500"
                    />
                    Fetching video metadata...
                  </div>
                </Card>
              </div>
            )}

            {metadataError && !loadingMetadata && (
              <div className="mb-6">
                <Card padding="lg">
                  <Badge variant="error">{metadataError}</Badge>
                </Card>
              </div>
            )}

            {metadata?.video && !loadingTranscript && (
              <div className="mb-6">
                <VideoDetails metadata={metadata.video} />
              </div>
            )}

            {loadingTranscript && <TranscriptSkeleton />}

            {transcriptError && !loadingTranscript && (
              <TranscriptError
                message={transcriptError}
                onRetry={handleRetry}
              />
            )}

            {pipelineSteps.length > 0 && (
              <div className="mb-6">
                <TranscriptPipeline steps={pipelineSteps} />
              </div>
            )}

            {(manualTranscript || autoTranscript) && viewerTranscript && (
              <TranscriptViewer
                transcript={viewerTranscript}
                manualTranscript={manualTranscript}
                autoTranscript={autoTranscript}
                translatedTranscripts={translatedTranscripts}
                selectedLanguage={selectedLanguage}
                onLanguageChange={handleLanguageChange}
                isTranslating={isTranslating}
              />
            )}
          </div>
        </Container>
      </section>
    </>
  );
}
