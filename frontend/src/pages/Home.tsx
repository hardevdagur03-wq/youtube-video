import { motion } from 'framer-motion';
import { Download, FileText, MessageSquareText } from 'lucide-react';
import WorkflowCard from '../components/home/WorkflowCard';

const workflows = [
  {
    icon: Download,
    title: 'Download Metadata',
    description:
      'Export complete metadata from any YouTube channel. Resolve channel IDs, discover all uploaded videos, fetch detailed stats, and download as CSV.',
    features: [
      'Channel handle & URL resolution',
      'Fetch all public videos',
      'Full metadata (views, likes, duration)',
      'CSV export with progress tracking',
    ],
    cta: 'Open Metadata Downloader',
    to: '/metadata',
    gradient: 'bg-gradient-to-br from-emerald-500 to-emerald-700',
  },
  {
    icon: MessageSquareText,
    title: 'URL → Transcript',
    description:
      'Extract the highest-quality transcript from any YouTube video. Automatic fallback from manual captions to Whisper AI speech-to-text.',
    features: [
      'Official manual & auto transcripts',
      'Whisper AI speech-to-text fallback',
      'Timestamped segments & plain text',
      'Multi-language support',
    ],
    cta: 'Extract Transcript',
    to: '/transcript',
    gradient: 'bg-gradient-to-br from-emerald-500 to-teal-600',
  },
  {
    icon: FileText,
    title: 'URL → AI Blog',
    description:
      'Convert any YouTube video into a professional AI-generated SEO blog article. Automatically extracts transcripts and generates optimized content.',
    features: [
      'Paste any YouTube URL',
      'Auto transcript extraction',
      'SEO-optimized blog generation',
      'Multiple export formats',
    ],
    cta: 'Generate Blog',
    to: '/blog',
    gradient: 'bg-gradient-to-br from-violet-500 to-violet-700',
  },
];

export default function Home() {
  return (
    <>
      <section className="relative overflow-hidden bg-gradient-to-br from-emerald-600 via-emerald-500 to-emerald-700 dark:from-emerald-800 dark:via-emerald-700 dark:to-emerald-900 min-h-[420px] lg:min-h-[400px]">
        <div className="absolute inset-0">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(255,255,255,0.15),transparent_60%)]" />
          <div className="absolute bottom-0 left-1/3 w-[500px] h-[500px] bg-white/5 rounded-full blur-3xl" />
        </div>

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-28 lg:pt-32 pb-16 lg:pb-20">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            className="text-center max-w-3xl mx-auto"
          >
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/10 border border-white/20 text-white/90 text-xs font-medium mb-5">
              YouTube Export Tool v2
            </div>

            <h1 className="text-[40px] sm:text-[48px] lg:text-[56px] font-extrabold leading-[1.08] tracking-[-0.03em] text-white mb-4">
              Export YouTube Data or Generate AI Blogs
            </h1>

            <p className="text-[17px] leading-relaxed text-white/75 max-w-xl mx-auto">
              Choose your workflow to start.
            </p>
          </motion.div>
        </div>
      </section>

      <section className="relative z-10 -mt-10 pb-20 sm:pb-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid md:grid-cols-2 gap-6 sm:gap-8 max-w-4xl mx-auto">
            {workflows.map((wf, i) => (
              <motion.div
                key={wf.title}
                initial={{ opacity: 0, y: 24 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: i * 0.15, ease: [0.16, 1, 0.3, 1] }}
              >
                <WorkflowCard {...wf} />
              </motion.div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
