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
import AdminLogin from "./pages/admin/Login";
import AdminHome from "./pages/admin/AdminHome";
import RequireAdmin from "./components/RequireAdmin";
import { AuthProvider } from "./hooks/useAuth";
import { C, SIDEBAR_W } from "./theme";
import { useIsNarrow } from "./hooks/useBreakpoint";

export default function App() {
  return (
    <Router>
      {/* Inside the Router so the guard can redirect, and outside Shell so the
          sidebar and the pages read one shared session rather than each asking
          the server independently. */}
      <AuthProvider>
        <Shell />
      </AuthProvider>
    </Router>
  );
}

/* Split from App because the responsive hook has to live inside the Router —
 * Sidebar uses useLocation to close its drawer on navigation. */
function Shell() {
  const narrow = useIsNarrow();
  return (
      <div style={{ fontFamily: "'Inter', sans-serif", background: C.slate50, minHeight: "100vh" }}>
        <Sidebar />
        <main style={{
          // The 220px gutter belongs to the fixed rail; when the rail becomes a
          // drawer the gutter has to go with it, or the content stays indented
          // behind nothing on a narrow screen.
          marginLeft: narrow ? 0 : SIDEBAR_W,
          minHeight: "100vh",
          padding: narrow ? "68px 16px 24px" : "32px 28px",
        }}>
          <Routes>
            <Route path="/"          element={<Dashboard />} />
            <Route path="/predict"   element={<Predict />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/teams"     element={<Teams />} />
            <Route path="/history"   element={<History />} />
            <Route path="/model"     element={<ModelPage />} />

            {/* Admin. The guard is convenience — every one of these endpoints is
                enforced server-side, so a hand-typed URL gains nothing. */}
            <Route path="/admin/login" element={<AdminLogin />} />
            <Route path="/admin"       element={<RequireAdmin><AdminHome /></RequireAdmin>} />
          </Routes>
        </main>
      </div>
  );
}
