import { Navigate, useLocation } from "react-router-dom";
import useAuth from "../hooks/useAuth";
import EmptyState from "./ui/EmptyState";

/* Route guard for the admin area.
 *
 * This is CONVENIENCE, not security. Every admin endpoint is enforced on the
 * server by `require_admin`, and it has to be: anyone can open devtools and
 * render whatever component they like. Hiding a button has never protected
 * anything — it just stops signed-out users being shown controls that would
 * return 401.
 *
 * The loading state matters. Rendering the redirect before /auth/me answers would
 * bounce a signed-in admin to the login page on every refresh. */
export default function RequireAdmin({ children }) {
  const { admin, loading } = useAuth();
  const location = useLocation();

  if (loading) return <EmptyState kind="loading" title="Checking your session…" />;
  if (!admin) return <Navigate to="/admin/login" replace state={{ from: location.pathname }} />;
  return children;
}
