// Single source for the API base URL.
//
// This was previously copy-pasted into nine files, so changing the backend
// address meant nine edits and any missed file failed silently at runtime.
//
// Override at build time with REACT_APP_API_BASE.
export const API = (
  process.env.REACT_APP_API_BASE || "/api"
).replace(/\/$/, "");

export default API;
