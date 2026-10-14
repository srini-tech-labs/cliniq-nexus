import { Navigate, Route, Routes } from "react-router-dom";
import TopBar from "./components/TopBar";
import AboutPage from "./pages/AboutPage";
import OperationsPage from "./pages/OperationsPage";
import WorkspacePage from "./pages/WorkspacePage";

export default function App() {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 btn-primary">Skip to content</a>
      <TopBar />
      <Routes>
        <Route path="/" element={<WorkspacePage />} />
        <Route path="/patients/:pid" element={<WorkspacePage />} />
        <Route path="/patients/:pid/:tab" element={<WorkspacePage />} />
        <Route path="/operations" element={<OperationsPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
