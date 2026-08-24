import { useEffect } from "react";
import Login from "./Login";
import Console from "./Console";
import EmptyState from "../../components/ui/EmptyState";
import useAuth, { AuthProvider } from "../../hooks/useAuth";

/* The operator area, at one unadvertised path.
 *
 * Login and console are the same route on purpose. A separate /…/login would be a
 * second discoverable path, and a redirect between them would put the operator
 * URL in the browser history of anyone who guessed either one. Signed out you get
 * the form, signed in you get the console, and the address bar never changes.
 *
 * To be clear about what this does and does not do: an unguessable path reduces
 * how easily the operator area is *found*. It is not what keeps anyone out —
 * `require_admin` on the server is, and it holds whether or not a caller knows
 * this URL. If the path leaked tomorrow nothing would be exposed.
 *
 * This component is also the only thing in the app that asks who is signed in, so
 * a visitor who never comes here generates no authentication traffic at all. */
/* The provider lives here rather than at the app root.
 *
 * Nothing on the public site needs to know who is signed in, so wrapping the whole
 * app in it put the auth code — the login call, the session handling — into the
 * bundle every visitor downloads. Scoped to this chunk, the public tree contains
 * no authentication code at all. */
export default function SecureModel() {
  return (
    <AuthProvider>
      <SecureModelInner />
    </AuthProvider>
  );
}

function SecureModelInner() {
  const { admin, loading, probe } = useAuth();

  useEffect(() => { probe(); }, [probe]);

  if (loading) return <EmptyState kind="loading" title="Checking your session…" />;
  return admin ? <Console /> : <Login />;
}
