import { NavLink } from "react-router-dom";
import { C, SIDEBAR_W } from "../theme";

const NAV = [
  { to: "/",          icon: "📊", label: "Dashboard"  },
  { to: "/predict",   icon: "🔮", label: "Predict"    },
  { to: "/analytics", icon: "📈", label: "Analytics"  },
  { to: "/teams",     icon: "👥", label: "Teams"      },
  { to: "/history",   icon: "📋", label: "History"    },
  { to: "/model",     icon: "⚙️",  label: "Model"      },
];

export default function Sidebar() {
  return (
    <aside style={{
      width: SIDEBAR_W, minHeight: "100vh", background: C.navy,
      display: "flex", flexDirection: "column", position: "fixed", top: 0, left: 0, zIndex: 100,
    }}>
      <div style={{ padding: "24px 20px 20px", borderBottom: `1px solid ${C.navyLight}` }}>
        <div style={{ fontSize: 20, fontWeight: 700, color: C.white }}>⚽ EPL Predictor</div>
        <div style={{ fontSize: 11, color: C.slate400, marginTop: 3 }}>ML-Powered Analytics</div>
      </div>
      <nav style={{ padding: "12px 10px", flex: 1 }}>
        {NAV.map(({ to, icon, label }) => (
          <NavLink key={to} to={to} end={to === "/"} style={({ isActive }) => ({
            display: "flex", alignItems: "center", gap: 10,
            padding: "10px 12px", borderRadius: 8, marginBottom: 2,
            textDecoration: "none", fontSize: 14, fontWeight: 500,
            color: isActive ? C.white : C.slate400,
            background: isActive ? C.navyLight : "transparent",
            transition: "all 0.15s",
          })}>
            <span style={{ fontSize: 16 }}>{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>
      <div style={{ padding: "16px 20px", borderTop: `1px solid ${C.navyLight}`, fontSize: 11, color: C.slate500 }}>
        Data: Premier League API
      </div>
    </aside>
  );
}
