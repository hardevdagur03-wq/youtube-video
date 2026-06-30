import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Github, Moon, Sun, Menu, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTheme } from '../../theme/ThemeContext';
import { Button } from '../ui';

const navLinks = [
  { label: 'Transcript', path: '/transcript' },
  { label: 'AI Blog', path: '/blog' },
  { label: 'Docs', path: '/docs', disabled: true },
];

const isBlogPath = (path: string) => path === '/blog' || path.startsWith('/blog/');

export default function Navbar() {
  const { dark, toggle } = useTheme();
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const isHome = location.pathname === '/';

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    setMenuOpen(false);
  }, [location]);

  const showBg = scrolled || !isHome;

  return (
    <header
      className={`fixed top-0 left-0 right-0 z-50 transition-all-300 ${
        showBg
          ? 'bg-white/90 dark:bg-gray-950/90 backdrop-blur-xl border-b border-gray-100 dark:border-gray-800 shadow-sm'
          : 'bg-transparent'
      }`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16 lg:h-[72px]">
          <Link to="/" className="flex items-center gap-2.5 no-underline">
            <img src="/static/logo.png" alt="Logo" className="h-8 w-auto rounded-lg" />
            <span className={`font-bold text-lg ${showBg ? 'text-gray-900 dark:text-white' : 'text-white'}`}>
              YouTube Export
            </span>
          </Link>

          <nav className="hidden md:flex items-center gap-1">
            {navLinks.map((link) =>
              link.disabled ? (
                <span
                  key={link.label}
                  className={`px-3 py-2 rounded-lg text-sm font-medium cursor-not-allowed opacity-40 ${
                    showBg
                      ? 'text-gray-500 dark:text-gray-400'
                      : 'text-white/60'
                  }`}
                >
                  {link.label}
                </span>
              ) : (
                  <Link
                  key={link.label}
                  to={link.path}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-all-200 no-underline ${
                    (link.path === '/blog' ? isBlogPath(location.pathname) : location.pathname === link.path)
                      ? showBg
                        ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/30'
                        : 'text-emerald-300 bg-white/10'
                      : showBg
                        ? 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800'
                        : 'text-white/80 hover:text-white hover:bg-white/10'
                  }`}
                >
                  {link.label}
                </Link>
              )
            )}
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className={`p-2 rounded-lg transition-all-200 ${
                showBg
                  ? 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800'
                  : 'text-white/70 hover:text-white hover:bg-white/10'
              }`}
              aria-label="GitHub"
            >
              <Github size={18} />
            </a>
            <button
              onClick={toggle}
              className={`p-2 rounded-lg transition-all-200 ${
                showBg
                  ? 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800'
                  : 'text-white/70 hover:text-white hover:bg-white/10'
              }`}
              aria-label="Toggle dark mode"
            >
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </nav>

          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className={`md:hidden p-2 rounded-lg transition-all-200 ${
              showBg ? 'text-gray-600 dark:text-gray-300' : 'text-white'
            }`}
            aria-label="Toggle menu"
          >
            {menuOpen ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>
      </div>

      <AnimatePresence>
        {menuOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden border-t border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-950 shadow-lg overflow-hidden"
          >
            <div className="px-4 py-4 space-y-1">
              {navLinks.map((link) =>
                link.disabled ? (
                  <span
                    key={link.label}
                    className="block px-3 py-2.5 rounded-lg text-sm font-medium text-gray-400 dark:text-gray-600 cursor-not-allowed"
                  >
                    {link.label}
                  </span>
                ) : (
                  <Link
                    key={link.label}
                    to={link.path}
                    className={`block px-3 py-2.5 rounded-lg text-sm font-medium no-underline ${
                      (link.path === '/blog' ? isBlogPath(location.pathname) : location.pathname === link.path)
                        ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/30'
                        : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                    }`}
                  >
                    {link.label}
                  </Link>
                )
              )}
              <a
                href="https://github.com"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 no-underline"
              >
                <Github size={16} /> GitHub
              </a>
              <button
                onClick={toggle}
                className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 w-full"
              >
                {dark ? <Sun size={16} /> : <Moon size={16} />} {dark ? 'Light Mode' : 'Dark Mode'}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
