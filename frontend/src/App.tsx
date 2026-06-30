import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from './theme/ThemeContext';
import Layout from './components/layout/Layout';
import LayoutBlog from './components/layout/LayoutBlog';
import Home from './pages/Home';
import Metadata from './pages/Metadata';
import Blog from './pages/Blog';
import BlogHome from './pages/BlogHome';
import BlogMetadata from './pages/BlogMetadata';
import BlogTranscript from './pages/BlogTranscript';
import BlogAnalysis from './pages/BlogAnalysis';
import BlogGenerate from './pages/BlogGenerate';
import BlogEditor from './pages/BlogEditor';
import BlogExport from './pages/BlogExport';
import Transcript from './pages/Transcript';

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <Routes>
          <Route element={<LayoutBlog />}>
            <Route path="/blog/url" element={<BlogHome />} />
            <Route path="/blog/metadata" element={<BlogMetadata />} />
            <Route path="/blog/transcript" element={<BlogTranscript />} />
            <Route path="/blog/analysis" element={<BlogAnalysis />} />
            <Route path="/blog/generate" element={<BlogGenerate />} />
            <Route path="/blog/editor" element={<BlogEditor />} />
            <Route path="/blog/export" element={<BlogExport />} />
            <Route path="/blog" element={<BlogHome />} />
          </Route>
          <Route element={<Layout />}>
            <Route path="/" element={<Home />} />
            <Route path="/metadata" element={<Metadata />} />
            <Route path="/transcript" element={<Transcript />} />
            <Route path="/blog-legacy" element={<Blog />} />
          </Route>
        </Routes>
      </ThemeProvider>
    </BrowserRouter>
  );
}
