import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Download, Sparkles, Lock, RotateCcw } from 'lucide-react';
import { useWorkflow } from '../context/WorkflowContext';
import { WorkflowHeader, WorkflowFooter } from '../components/workflow';
import { Card, Badge } from '../components/ui';

export default function BlogExport() {
  const navigate = useNavigate();
  const { state, reset } = useWorkflow();
  const { videoId } = state;

  const handleReset = () => {
    reset();
    navigate('/blog');
  };

  const handleBack = () => {
    navigate('/blog/editor');
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
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center mb-6 shadow-lg shadow-blue-200 dark:shadow-blue-900/30">
            <Download size={32} className="text-white" />
          </div>
          <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
            Export — Coming Soon
          </h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md mb-4">
            Download your blog article in multiple formats including HTML, Markdown, PDF, and WordPress-ready format.
          </p>
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 text-sm font-medium">
            <Sparkles size={15} />
            Multi-format export
          </div>
        </div>
      </Card>

      <WorkflowFooter
        currentStep={state.currentStep}
        onBack={handleBack}
        onContinue={handleReset}
        continueLabel="Start Over →"
        showReset
        onReset={handleReset}
      />
    </motion.div>
  );
}
