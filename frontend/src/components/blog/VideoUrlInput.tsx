import { useState, useCallback, useRef, useEffect } from 'react';
import { Youtube, CheckCircle2, XCircle, Loader2, ArrowRight, X, Clipboard } from 'lucide-react';

interface ValidationResult {
  valid: boolean;
  video_id: string | null;
  normalized_url: string | null;
  url_type: string | null;
  original_url: string | null;
  error: string | null;
}

interface VideoUrlInputProps {
  onValidUrl: (videoId: string, normalizedUrl: string) => void;
}

export default function VideoUrlInput({ onValidUrl }: VideoUrlInputProps) {
  const [url, setUrl] = useState('');
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [touched, setTouched] = useState(false);
  const debounceRef = useRef<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const validateUrl = useCallback(async (input: string) => {
    if (!input.trim()) {
      setValidation(null);
      return;
    }

    setLoading(true);
    try {
      const resp = await fetch(`/api/validate-url?url=${encodeURIComponent(input)}`);
      const data: ValidationResult = await resp.json();
      setValidation(data);
      if (data.valid && data.video_id && data.normalized_url) {
        onValidUrl(data.video_id, data.normalized_url);
      }
    } catch {
      setValidation({
        valid: false,
        video_id: null,
        normalized_url: null,
        url_type: null,
        original_url: input,
        error: 'Network error. Please try again.',
      });
    } finally {
      setLoading(false);
    }
  }, [onValidUrl]);

  const handleChange = (value: string) => {
    setUrl(value);
    setTouched(true);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => validateUrl(value), 400);
  };

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      handleChange(text);
    } catch {
      // Clipboard API not available
    }
  };

  const handleClear = () => {
    setUrl('');
    setValidation(null);
    setTouched(false);
    inputRef.current?.focus();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (url.trim()) validateUrl(url);
  };

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const statusIcon = () => {
    if (loading) return <Loader2 size={16} className="text-gray-400 animate-spin" />;
    if (!touched || !url) return null;
    if (validation?.valid) return <CheckCircle2 size={16} className="text-emerald-500" />;
    if (validation && !validation.valid) return <XCircle size={16} className="text-red-500" />;
    return null;
  };

  const borderColor = () => {
    if (!touched || !url) return 'border-gray-200 dark:border-gray-700 focus:border-violet-400 dark:focus:border-violet-500';
    if (loading) return 'border-gray-200 dark:border-gray-700';
    if (validation?.valid) return 'border-emerald-400 dark:border-emerald-500';
    if (validation && !validation.valid) return 'border-red-300 dark:border-red-700';
    return 'border-gray-200 dark:border-gray-700';
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
          YouTube Video URL
        </label>
        <div className="relative">
          <Youtube size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            ref={inputRef}
            type="url"
            value={url}
            onChange={(e) => handleChange(e.target.value)}
            onBlur={() => setTouched(true)}
            placeholder="https://youtube.com/watch?v=..."
            className={`w-full pl-10 pr-20 py-3 rounded-xl border-2 text-sm transition-all-200 outline-none bg-white dark:bg-gray-800 focus:ring-4 focus:ring-violet-100 dark:focus:ring-violet-900/30 ${borderColor()}`}
            autoFocus
            autoComplete="off"
            spellCheck={false}
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1">
            {url && (
              <button
                type="button"
                onClick={handleClear}
                className="p-1 rounded-md text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-all-200"
                aria-label="Clear input"
              >
                <X size={14} />
              </button>
            )}
            <button
              type="button"
              onClick={handlePaste}
              className="p-1 rounded-md text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-all-200"
              aria-label="Paste from clipboard"
            >
              <Clipboard size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* Validation feedback */}
      {touched && url && !loading && validation && (
        <div
          className={`mb-5 px-4 py-3 rounded-xl border text-sm ${
            validation.valid
              ? 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300'
              : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-600 dark:text-red-400'
          }`}
        >
          <div className="flex items-start gap-2.5">
            {validation.valid ? (
              <CheckCircle2 size={16} className="mt-0.5 flex-shrink-0 text-emerald-500" />
            ) : (
              <XCircle size={16} className="mt-0.5 flex-shrink-0 text-red-500" />
            )}
            <div>
              {validation.valid ? (
                <>
                  <span className="font-medium">Valid URL</span>
                  <div className="mt-0.5 font-mono text-xs opacity-75">
                    Video ID: {validation.video_id}
                  </div>
                </>
              ) : (
                <span>{validation.error || 'Invalid YouTube video URL.'}</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Status indicator row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
          {loading && <Loader2 size={12} className="animate-spin" />}
          {statusIcon()}
          {validation?.valid && !loading && (
            <span className="text-emerald-600 dark:text-emerald-400 font-medium">
              Ready to process
            </span>
          )}
          {validation && !validation.valid && !loading && (
            <span className="text-red-500 font-medium">Unsupported URL</span>
          )}
        </div>

        <button
          type="submit"
          disabled={!validation?.valid}
          className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm transition-all-200 ${
            validation?.valid
              ? 'bg-violet-600 text-white hover:bg-violet-500 active:bg-violet-700 shadow-lg shadow-violet-200 dark:shadow-violet-900/30 hover:shadow-xl'
              : 'bg-gray-200 dark:bg-gray-800 text-gray-400 dark:text-gray-600 cursor-not-allowed'
          }`}
        >
          Continue
          <ArrowRight size={15} />
        </button>
      </div>
    </form>
  );
}
