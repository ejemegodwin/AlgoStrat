// Session state, provided to the whole tree via context (ADR-013).
// The JWT lives in localStorage and is attached as a Bearer token; on
// load we exchange it for the current user via GET /auth/me, dropping
// it silently if the API rejects it (expired or revoked).

import { createContext, useContext, useEffect, useState } from "react";

import { api } from "./api";

const TOKEN_KEY = "algostrat_token";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() =>
    localStorage.getItem(TOKEN_KEY),
  );
  const [user, setUser] = useState(null);
  // True while a stored token is being exchanged for the user, so
  // pages don't flash "logged out" on reload.
  const [loading, setLoading] = useState(() =>
    Boolean(localStorage.getItem(TOKEN_KEY)),
  );

  useEffect(() => {
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    api("/auth/me", { token })
      .then((me) => {
        if (!cancelled) setUser(me);
      })
      .catch(() => {
        if (cancelled) return;
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
        setUser(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function login(email, password) {
    const data = await api("/auth/login", {
      method: "POST",
      body: { email, password },
    });
    localStorage.setItem(TOKEN_KEY, data.access_token);
    setToken(data.access_token);
  }

  async function register(fullName, email, password) {
    await api("/auth/register", {
      method: "POST",
      body: { full_name: fullName, email, password },
    });
    // Registration does not return a token, so log in right after —
    // one flow from the user's point of view.
    await login(email, password);
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider
      value={{ user, token, loading, login, register, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
