import Header from './components/Header';
import Hero from './components/Hero';
import ExportForm from './components/ExportForm';
import Features from './components/Features';
import Footer from './components/Footer';
import { useExport } from './hooks/useExport';

export default function App() {
  const { result, loading, progress, error, startExport, reset } = useExport();

  return (
    <div className="min-h-screen bg-white">
      <Header />
      <Hero />
      <ExportForm
        onExport={startExport}
        loading={loading}
        progress={progress}
        result={result}
        error={error}
        reset={reset}
      />
      <Features />
      <Footer />
    </div>
  );
}
