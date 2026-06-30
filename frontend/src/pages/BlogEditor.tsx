import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { FileEdit, Sparkles, Lock } from 'lucide-react';
import { useWorkflow } from '../context/WorkflowContext';
import { WorkflowHeader, WorkflowFooter } from '../components/workflow';
import { Card } from '../components/ui';

export default function BlogEditor() {
  const navigate = useNavigate();
  const { state, goToStep } = useWorkflow();
  const { videoId } = state;

  const handleContinue = () => {
    goToStep('export');
    navigate('/blog/export');
  };

  const handleBack = () => {
    goToStep('generate');
    navigate('/blog/generate');
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
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-amber-500 to-amber-700 flex items-center justify-center mb-6 shadow-lg shadow-amber-200 dark:shadow-amber-900/30">
            <FileEdit size={32} className="text-white" />
          </div>
          <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
            Blog Editor — Coming Soon
          </h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md mb-4">
            Review, edit, and refine your AI-generated blog article before export.
          </p>
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 text-sm font-medium">
            <Sparkles size={15} />
            Rich text editor
          </div>
        </div>
      </Card>

      <WorkflowFooter
        currentStep={state.currentStep}
        onBack={handleBack}
        onContinue={handleContinue}
        continueLabel="Continue to Export →"
      />
    </motion.div>
  );
}
