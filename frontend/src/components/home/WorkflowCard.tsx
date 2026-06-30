import { Link } from 'react-router-dom';
import { ArrowRight, type LucideIcon } from 'lucide-react';

interface WorkflowCardProps {
  icon: LucideIcon;
  title: string;
  description: string;
  features: string[];
  cta: string;
  to: string;
  gradient: string;
}

export default function WorkflowCard({
  icon: Icon,
  title,
  description,
  features,
  cta,
  to,
  gradient,
}: WorkflowCardProps) {
  return (
    <Link
      to={to}
      className="group relative block no-underline"
    >
      <div className="relative bg-white dark:bg-gray-900 rounded-3xl border border-gray-100 dark:border-gray-800 shadow-card hover:shadow-elevated transition-all-300 overflow-hidden h-full">
        <div className="p-8 sm:p-10">
          <div
            className={`w-14 h-14 rounded-2xl ${gradient} flex items-center justify-center mb-6 group-hover:scale-110 transition-transform-200`}
          >
            <Icon size={28} className="text-white" />
          </div>

          <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">
            {title}
          </h3>

          <p className="text-[15px] text-gray-500 dark:text-gray-400 leading-relaxed mb-6">
            {description}
          </p>

          <ul className="space-y-2.5 mb-8">
            {features.map((feature) => (
              <li key={feature} className="flex items-center gap-2.5 text-sm text-gray-600 dark:text-gray-300">
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 16 16"
                  fill="none"
                  className="flex-shrink-0 text-emerald-500"
                >
                  <path
                    d="M13.3 4.3L6 11.6L2.7 8.3"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                {feature}
              </li>
            ))}
          </ul>

          <div className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-600 text-white font-semibold text-sm group-hover:bg-emerald-500 transition-colors-200 shadow-lg shadow-emerald-200 dark:shadow-emerald-900/30">
            {cta}
            <ArrowRight size={15} className="group-hover:translate-x-0.5 transition-transform-200" />
          </div>
        </div>
      </div>
    </Link>
  );
}
