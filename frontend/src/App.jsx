import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Predict from "./pages/Predict";
import Analytics from "./pages/Analytics";
import Teams from "./pages/Teams";
import History from "./pages/History";
import ModelPage from "./pages/ModelPage";
import { C, SIDEBAR_W } from "./theme";

export default function App() {
  return (
    <Router>
      <div style={{ fontFamily: "'Inter', sans-serif", background: C.slate50, minHeight: "100vh" }}>
        <Sidebar />
        <main style={{ marginLeft: SIDEBAR_W, minHeight: "100vh", padding: "32px 28px" }}>
          <Routes>
            <Route path="/"          element={<Dashboard />} />
            <Route path="/predict"   element={<Predict />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/teams"     element={<Teams />} />
            <Route path="/history"   element={<History />} />
            <Route path="/model"     element={<ModelPage />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}
