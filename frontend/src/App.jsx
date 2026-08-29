import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import { lazy, Suspense } from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Predict from "./pages/Predict";
import Analytics from "./pages/Analytics";
import Teams from "./pages/Teams";
import History from "./pages/History";
import ModelPage from "./pages/ModelPage";
import Explainer from "./pages/Explainer";
/* Code-split, so the sign-in form, the operator console and the calls they make
 * are in a chunk the public site never downloads. A visitor to the dashboard
 * fetches none of it.
 *
 * Being straight about the limit: this reduces what is *visible*, it does not make
 * the path secret. The route string is still in the main bundle, because a
 * client-rendered app has to know its own routes — anyone reading the minified JS
 * can find it. That is fine, and it is why the path was never the protection:
 * `require_admin` on the server is, and it holds for a caller who knows the URL
 * exactly as well as for one who does not. */
const SecureModel = lazy(() => import("./pages/secure/SecureModel"));
import { C, SIDEBAR_W } from "./theme";
import { useIsNarrow } from "./hooks/useBreakpoint";

export default function App() {
  return (
    <Router>
      <Shell />
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
            <Route path="/explainer" element={<Explainer />} />

            {/* Operator route. Unlinked from anywhere in the app and reachable
                only by typing it. The path is not the protection — every endpoint
                behind it is enforced server-side — it just keeps the operator
                area unadvertised to people browsing the public site. */}
            <Route path="/secure-model" element={
              <Suspense fallback={null}><SecureModel /></Suspense>
            } />
          </Routes>
        </main>
      </div>
  );
}
