import { useState, useEffect, useCallback, createContext, useContext } from "react";
import axios from "axios";
import { API } from "../config";

/* Who is signed in, shared across the app.
 *
 * The session is an httpOnly cookie, so this deliberately CANNOT read the token —
 * that is the point of httpOnly, and it is why the token does not live in
 * localStorage where any injected script could read it. The only way to know
 * whether we are signed in is to ask the server, which is what /auth/me is for.
 *
 * `configured` distinguishes "signed out" from "this server has no admin set up".
 * Without it the login form would be shown on a deployment where logging in
 * cannot possibly succeed. */
const AuthContext = createContext(null);

// withCredentials so the session cookie rides along. It is off by default in
// axios, and without it every admin request would arrive anonymous — the failure
// looks exactly like "the login did not work".
axios.defaults.withCredentials = true;

export function AuthProvider({ children }) {
  const [state, setState] = useState({ admin: false, username: null, configured: true, loading: true });

  const refresh = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/auth/me`);
      setState({ ...r.data, loading: false });
      return r.data;
    } catch {
      // A backend that is down is not the same as being signed out, but from the
      // UI's point of view both mean "no admin actions available".
      setState({ admin: false, username: null, configured: false, loading: false });
      return null;
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const login = useCallback(async (username, password) => {
    await axios.post(`${API}/auth/login`, { username, password });
    return refresh();
  }, [refresh]);

  const logout = useCallback(async () => {
    try { await axios.post(`${API}/auth/logout`); } finally { await refresh(); }
  }, [refresh]);

  return (
    <AuthContext.Provider value={{ ...state, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export default function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
