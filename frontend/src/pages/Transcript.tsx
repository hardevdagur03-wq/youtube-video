import { motion } from 'framer-motion';
import { useState } from 'react';
import { FileText, Youtube, Loader2, MessageSquareText } from 'lucide-react';
import { Container, Badge, Card } from '../components/ui';
import VideoUrlInput from '../components/blog/VideoUrlInput';
import VideoDetails from '../components/blog/VideoDetails';
import TranscriptPipeline from '../components/transcript/TranscriptPipeline';
import TranscriptViewer from '../components/transcript/TranscriptViewer';
import TranscriptSkeleton from '../components/transcript/TranscriptSkeleton';
import TranscriptError from '../components/transcript/TranscriptError';
import type { VideoMetadataResponse, TranscriptResult } from '../types';

export default function Transcript() {
  const [validatedVideoId, setValidatedVideoId] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<VideoMetadataResponse | null>(null);
  const [transcript, setTranscript] = useState<TranscriptResult | null>(null);
  const [loadingMetadata, setLoadingMetadata] = useState(false);
  const [loadingTranscript, setLoadingTranscript] = useState(false);
  const [metadataError, setMetadataError] = useState<string | null>(null);
  const [transcriptError, setTranscriptError] = useState<string | null>(null);

  const handleValidUrl = async (videoId: string, _normalizedUrl: string) => {
    setValidatedVideoId(videoId);
    setLoadingMetadata(true);
    setMetadataError(null);
    setMetadata(null);
    setTranscript(null);
    setTranscriptError(null);

    try {
      const resp = await fetch(`/api/video-metadata/${videoId}`);
      const data: VideoMetadataResponse = await resp.json();
      if (data.success && data.video) {
        setMetadata(data);
        await fetchTranscript(videoId);
      } else {
        setMetadataError(data.error || 'Failed to load video metadata.');
      }
    } catch {
      setMetadataError('Network error. Please try again.');
    } finally {
      setLoadingMetadata(false);
    }
  };

  const fetchTranscript = async (videoId: string) => {
    setLoadingTranscript(true);
    setTranscriptError(null);
    setTranscript(null);

    try {
      const resp = await fetch(`/api/transcript/${videoId}`);
      const data: TranscriptResult = await resp.json();
      if (data.success) {
        setTranscript(data);
      } else {
        setTranscriptError(data.error || 'Failed to load transcript.');
      }
    } catch {
      setTranscriptError('Network error loading transcript.');
    } finally {
      setLoadingTranscript(false);
    }
  };

  const handleRetry = () => {
    if (validatedVideoId) {
      fetchTranscript(validatedVideoId);
    }
  };

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
              Extract the highest-quality transcript from any YouTube video. Automatic fallback from manual captions to Whisper AI.
            </p>
          </motion.div>
        </div>
      </section>

      <section className="relative z-10 -mt-6 pb-20">
        <Container>
          <div className="max-w-4xl mx-auto">
            {/* URL Input */}
            {!metadata && !loadingMetadata && (
              <Card padding="lg" className="mb-6">
                <div className="flex items-center gap-3 mb-6">
                  <div className="w-10 h-10 rounded-xl bg-emerald-50 dark:bg-emerald-900/30 flex items-center justify-center flex-shrink-0">
                    <Youtube size={18} className="text-emerald-600 dark:text-emerald-400" />
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

            {/* Loading metadata */}
            {loadingMetadata && !metadata && (
              <div className="mb-6">
                <Card padding="lg">
                  <div className="flex items-center gap-2.5 text-sm text-gray-500 dark:text-gray-400">
                    <Loader2 size={14} className="animate-spin text-emerald-500" />
                    Fetching video metadata...
                  </div>
                </Card>
              </div>
            )}

            {/* Metadata error */}
            {metadataError && !loadingMetadata && (
              <div className="mb-6">
                <Card padding="lg">
                  <Badge variant="error">{metadataError}</Badge>
                </Card>
              </div>
            )}

            {/* Video Details */}
            {metadata?.video && !loadingTranscript && (
              <div className="mb-6">
                <VideoDetails metadata={metadata.video} />
              </div>
            )}

            {/* Loading transcript */}
            {loadingTranscript && <TranscriptSkeleton />}

            {/* Transcript error */}
            {transcriptError && !loadingTranscript && (
              <TranscriptError message={transcriptError} onRetry={handleRetry} />
            )}

            {/* Transcript Pipeline */}
            {transcript?.pipeline_steps && transcript.pipeline_steps.length > 0 && (
              <div className="mb-6">
                <TranscriptPipeline steps={transcript.pipeline_steps} />
              </div>
            )}

            {/* Transcript Viewer */}
            {transcript?.success && <TranscriptViewer transcript={transcript} />}
          </div>
        </Container>
      </section>
    </>
  );
}
