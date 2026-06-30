import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { PenLine, Sparkles, Lock } from 'lucide-react';
import { useWorkflow } from '../context/WorkflowContext';
import { WorkflowHeader, WorkflowFooter } from '../components/workflow';
import { Card } from '../components/ui';

export default function BlogGenerate() {
  const navigate = useNavigate();
  const { state, goToStep } = useWorkflow();
  const { videoId } = state;

  const handleContinue = () => {
    goToStep('editor');
    navigate('/blog/editor');
  };

  const handleBack = () => {
    goToStep('analysis');
    navigate('/blog/analysis');
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
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-emerald-500 to-emerald-700 flex items-center justify-center mb-6 shadow-lg shadow-emerald-200 dark:shadow-emerald-900/30">
            <PenLine size={32} className="text-white" />
          </div>
          <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
            Blog Generation — Coming Soon
          </h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md mb-4">
            This step will generate a fully formatted, SEO-optimized blog article from the transcript and AI analysis.
          </p>
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 text-sm font-medium">
            <Sparkles size={15} />
            AI-powered blog generation
          </div>
        </div>
      </Card>

      <WorkflowFooter
        currentStep={state.currentStep}
        onBack={handleBack}
        onContinue={handleContinue}
        continueLabel="Skip to Editor →"
      />
    </motion.div>
  );
}
