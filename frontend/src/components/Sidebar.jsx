import { useState, useEffect } from "react";
import useAuth from "../hooks/useAuth";
import { NavLink, useLocation } from "react-router-dom";
import { C, SIDEBAR_W, space, type } from "../theme";
import { useIsNarrow } from "../hooks/useBreakpoint";

const NAV = [
  { to: "/",          label: "Dashboard"  },
  { to: "/predict",   label: "Predict"    },
  { to: "/analytics", label: "Analytics"  },
  { to: "/teams",     label: "Teams"      },
  { to: "/history",   label: "History"    },
  { to: "/model",     label: "Model"      },
];

/* Fixed 220px rail on desktop; an off-canvas drawer below the md breakpoint.
 * It was previously `position: fixed` at 220px with no collapse, and <main>
 * carried an unconditional 220px left margin, so on a phone or a split window
 * the nav covered a third of the content and nothing reflowed. */
export default function Sidebar() {
  const narrow = useIsNarrow();
  const [open, setOpen] = useState(false);
  const location = useLocation();

  // Close the drawer on navigation, or it stays over the page just navigated to.
  useEffect(() => { setOpen(false); }, [location.pathname]);

  const visible = !narrow || open;

  return (
    <>
      {narrow && (
        <button
          onClick={() => setOpen(o => !o)}
          aria-label={open ? "Close navigation" : "Open navigation"}
          aria-expanded={open}
          style={{
            position: "fixed", top: space.md, left: space.md, zIndex: 120,
            width: 40, height: 40, borderRadius: 8, border: "none",
            background: C.navy, color: C.white, fontSize: 18, cursor: "pointer",
          }}
        >
          {open ? "×" : "≡"}
        </button>
      )}

      {narrow && open && (
        <div
          onClick={() => setOpen(false)}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.4)", zIndex: 110 }}
        />
      )}

      <aside style={{
        width: SIDEBAR_W, minHeight: "100vh", background: C.navy,
        display: "flex", flexDirection: "column",
        position: "fixed", top: 0, left: 0, zIndex: 115,
        transform: visible ? "translateX(0)" : `translateX(-${SIDEBAR_W}px)`,
        transition: "transform .2s ease",
      }}>
        <div style={{ padding: "24px 20px 20px", borderBottom: `1px solid ${C.navyLight}` }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: C.white, letterSpacing: "-0.3px" }}>EPL Predictor</div>
          <div style={{ ...type.micro, fontWeight: 400, color: C.slate400, marginTop: 3 }}>ML-Powered Analytics</div>
        </div>
        <nav style={{ padding: "12px 10px", flex: 1 }}>
          {NAV.map(({ to, label }) => (
            <NavLink key={to} to={to} end={to === "/"} style={({ isActive }) => ({
              display: "flex", alignItems: "center",
              padding: "10px 14px", borderRadius: 8, marginBottom: 2,
              textDecoration: "none", fontSize: 14, fontWeight: 500,
              color: isActive ? C.navy : C.slate300,
              background: isActive ? C.blue : "transparent",
              transition: "all 0.15s",
            })}>
              {label}
            </NavLink>
          ))}
        </nav>
        <AdminLink />
        <div style={{ padding: "16px 20px", borderTop: `1px solid ${C.navyLight}`, ...type.micro, fontWeight: 400, color: C.slate500 }}>
          <div>Data: Premier League API</div>
          {/* rel="noopener noreferrer" is not boilerplate here: target="_blank"
              otherwise hands the opened page a window.opener handle back into
              this one. */}
          <div style={{ marginTop: 8 }}>
            Developed by{" "}
            <a
              href="https://hanovatechnologies.co.ke"
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: C.blue, textDecoration: "none", fontWeight: 600 }}
              onMouseEnter={(e) => { e.currentTarget.style.textDecoration = "underline"; }}
              onMouseLeave={(e) => { e.currentTarget.style.textDecoration = "none"; }}
            >
              Hanova Technologies
            </a>
          </div>
        </div>
      </aside>
    </>
  );
}


/* Shown only to a signed-in admin.
 *
 * This is presentation, not access control — /admin is guarded by RequireAdmin
 * and, more to the point, every admin endpoint is enforced on the server. Hiding
 * the link keeps the public nav uncluttered; it is not what stops anyone getting in.
 */
function AdminLink() {
  const { admin } = useAuth();
  if (!admin) return null;
  return (
    <NavLink to="/admin" style={({ isActive }) => ({
      display: "block", margin: "0 10px 8px", padding: "9px 14px", borderRadius: 8,
      textDecoration: "none", fontSize: 13, fontWeight: 600,
      color: isActive ? C.navy : C.blue,
      background: isActive ? C.blue : "transparent",
      border: `1px solid ${C.blue}`,
    })}>
      Admin
    </NavLink>
  );
}
