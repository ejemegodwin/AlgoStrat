import { Link, Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth";
import RequireAuth from "./components/RequireAuth";
import JobDetailPage from "./pages/JobDetailPage";
import JobsPage from "./pages/JobsPage";
import LoginPage from "./pages/LoginPage";
import MyApplicationsPage from "./pages/MyApplicationsPage";
import PostJobPage from "./pages/PostJobPage";
import RegisterPage from "./pages/RegisterPage";

function Header() {
  const { user, loading, logout } = useAuth();

  return (
    <header className="site-header">
      <Link to="/jobs" className="brand">
        AlgoStrat
      </Link>
      <nav>
        <Link to="/jobs/new">Post a job</Link>
        {loading ? null : user ? (
          <>
            <Link to="/applications">My applications</Link>
            <span className="who">{user.full_name}</span>
            <button type="button" className="link" onClick={logout}>
              Log out
            </button>
          </>
        ) : (
          <>
            <Link to="/login">Log in</Link>
            <Link to="/register">Register</Link>
          </>
        )}
      </nav>
    </header>
  );
}

export default function App() {
  return (
    <>
      <Header />
      <Routes>
        <Route path="/" element={<Navigate to="/jobs" replace />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route
          path="/jobs/new"
          element={
            <RequireAuth>
              <PostJobPage />
            </RequireAuth>
          }
        />
        <Route path="/jobs/:jobId" element={<JobDetailPage />} />
        <Route
          path="/applications"
          element={
            <RequireAuth>
              <MyApplicationsPage />
            </RequireAuth>
          }
        />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="*" element={<Navigate to="/jobs" replace />} />
      </Routes>
    </>
  );
}
