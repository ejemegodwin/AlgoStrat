import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../auth";

// Wraps pages that need a session. While a stored token is being
// exchanged for the user we wait; logged-out visitors go to /login
// and come back here afterwards via location.state.from.
export default function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <main>
        <p>Loading…</p>
      </main>
    );
  }
  if (!user) {
    return (
      <Navigate to="/login" replace state={{ from: location.pathname }} />
    );
  }
  return children;
}
