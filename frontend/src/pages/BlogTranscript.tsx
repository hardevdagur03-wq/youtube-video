import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useWorkflow } from '../context/WorkflowContext';
import { WorkflowHeader, WorkflowFooter, WorkflowCompletionCard, WorkflowSkeleton } from '../components/workflow';
import TranscriptPipeline from '../components/transcript/TranscriptPipeline';
import TranscriptViewer from '../components/transcript/TranscriptViewer';
import TranscriptError from '../components/transcript/TranscriptError';
import type { TranscriptResult } from '../types';

export default function BlogTranscript() {
  const navigate = useNavigate();
  const { state, dispatch, goToStep } = useWorkflow();
  const { videoId, stepStatus, transcript, metadata } = state;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isOk = stepStatus.transcript === 'ok';

  useEffect(() => {
    if (!videoId) {
      navigate('/blog', { replace: true });
      return;
    }
    if (stepStatus.transcript === 'pending') {
      fetchTranscript();
    }
  }, [videoId]);

  const fetchTranscript = async () => {
    dispatch({ type: 'SET_STEP_STATUS', payload: { step: 'transcript', status: 'running' } });
    setLoading(true);
    setError(null);

    try {
      const resp = await fetch(`/api/transcript/${videoId}`);
      const data: TranscriptResult = await resp.json();
      dispatch({ type: 'SET_TRANSCRIPT', payload: data });
      if (!data.success) {
        setError(data.error || 'Failed to load transcript.');
      }
    } catch {
      setError('Network error loading transcript.');
      dispatch({ type: 'SET_STEP_STATUS', payload: { step: 'transcript', status: 'error' } });
    } finally {
      setLoading(false);
    }
  };

  const handleContinue = () => {
    goToStep('analysis');
    navigate('/blog/analysis');
  };

  const handleBack = () => {
    goToStep('metadata');
    navigate('/blog/metadata');
  };

  const handleRetry = () => {
    if (videoId) fetchTranscript();
  };

  if (!videoId) return null;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
    >
      <WorkflowHeader currentStep={state.currentStep} />

      {/* Video context */}
      {metadata && (
        <div className="mb-6 p-4 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-800">
          <div className="flex items-center gap-3">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                {metadata.title || 'Untitled'}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {metadata.channel.name} · {metadata.duration.readable || metadata.duration.compact}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Loading state */}
      {loading && !transcript && <WorkflowSkeleton />}

      {/* Pipeline progress */}
      {transcript?.pipeline_steps && transcript.pipeline_steps.length > 0 && (
        <div className="mb-6">
          <TranscriptPipeline steps={transcript.pipeline_steps} />
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <TranscriptError message={error} onRetry={handleRetry} />
      )}

      {/* Transcript viewer */}
      {isOk && transcript && (
        <>
          <TranscriptViewer transcript={transcript} />

          <div className="mt-8">
            <WorkflowCompletionCard
              title="Transcript Retrieved Successfully"
              subtitle={`${transcript.word_count.toLocaleString()} words · ${transcript.estimated_read_time} read time · Source: ${transcript.source}`}
              nextStepLabel="Continue to AI Analysis"
              nextStepDescription="Analyze the transcript content with AI to extract key topics, sentiment, and insights for blog generation."
              estimatedTime="15-30 seconds"
              status="ok"
              onContinue={handleContinue}
            />
          </div>
        </>
      )}

      <WorkflowFooter
        currentStep={state.currentStep}
        onBack={handleBack}
        onContinue={isOk ? handleContinue : undefined}
        disableContinue={!isOk}
        continueLabel="Continue to Analysis →"
      />
    </motion.div>
  );
}
