import { Link, Navigate, Route, Routes } from "react-router-dom";

import { useAuth, CLIENT_SIDE, WORKER_SIDE } from "./auth";
import RequireAuth from "./components/RequireAuth";
import AdminDisputesPage from "./pages/AdminDisputesPage";
import ContractDetailPage from "./pages/ContractDetailPage";
import ContractsPage from "./pages/ContractsPage";
import JobDetailPage from "./pages/JobDetailPage";
import JobsPage from "./pages/JobsPage";
import LoginPage from "./pages/LoginPage";
import MyApplicationsPage from "./pages/MyApplicationsPage";
import PayoutsPage from "./pages/PayoutsPage";
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
        {loading ? null : user ? (
          <>
            {CLIENT_SIDE.includes(user.account_type) && (
              <Link to="/jobs/new">Post a job</Link>
            )}
            {WORKER_SIDE.includes(user.account_type) && (
              <Link to="/applications">My applications</Link>
            )}
            <Link to="/contracts">Contracts</Link>
            <Link to="/payouts">Payouts</Link>
            {user.is_admin && <Link to="/admin/disputes">Disputes</Link>}
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
        <Route
          path="/contracts"
          element={
            <RequireAuth>
              <ContractsPage />
            </RequireAuth>
          }
        />
        <Route
          path="/payouts"
          element={
            <RequireAuth>
              <PayoutsPage />
            </RequireAuth>
          }
        />
        <Route
          path="/admin/disputes"
          element={
            <RequireAuth>
              <AdminDisputesPage />
            </RequireAuth>
          }
        />
        <Route
          path="/contracts/:contractId"
          element={
            <RequireAuth>
              <ContractDetailPage />
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
