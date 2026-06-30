import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Brain, Sparkles, Lock } from 'lucide-react';
import { useWorkflow } from '../context/WorkflowContext';
import { WorkflowHeader, WorkflowFooter } from '../components/workflow';
import { Card, Badge } from '../components/ui';

export default function BlogAnalysis() {
  const navigate = useNavigate();
  const { state, goToStep } = useWorkflow();
  const { videoId } = state;

  const handleContinue = () => {
    goToStep('generate');
    navigate('/blog/generate');
  };

  const handleBack = () => {
    goToStep('transcript');
    navigate('/blog/transcript');
  };

  if (!videoId) {
    navigate('/blog', { replace: true });
    return null;
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
    >
      <WorkflowHeader currentStep={state.currentStep} />

      <Card padding="lg" className="mb-6">
        <div className="flex flex-col items-center text-center py-12">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-500 to-violet-700 flex items-center justify-center mb-6 shadow-lg shadow-violet-200 dark:shadow-violet-900/30">
            <Brain size={32} className="text-white" />
          </div>
          <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
            AI Analysis — Coming Soon
          </h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md mb-4">
            This step will analyze the transcript content with AI to extract key topics, sentiment, entities, and insights for blog generation.
          </p>
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-violet-50 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 text-sm font-medium">
            <Sparkles size={15} />
            AI-powered content analysis
          </div>
        </div>
      </Card>

      <WorkflowFooter
        currentStep={state.currentStep}
        onBack={handleBack}
        onContinue={handleContinue}
        continueLabel="Skip to Generation →"
      />
    </motion.div>
  );
}
