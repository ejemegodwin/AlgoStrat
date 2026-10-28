import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";
import { fetchJobTitles } from "../jobs";

export default function ContractsPage() {
  const { user, token } = useAuth();
  const [contracts, setContracts] = useState(null);
  const [jobTitles, setJobTitles] = useState({});
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api("/contracts", { token })
      .then(async (data) => {
        if (cancelled) return;
        setContracts(data);
        const titles = await fetchJobTitles(
          token,
          data.map((c) => c.job_id),
        );
        if (!cancelled) setJobTitles(titles);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <main>
      <h1>My contracts</h1>
      {error && <p className="error">{error}</p>}
      {contracts === null && !error && <p>Loading…</p>}
      {contracts !== null && contracts.length === 0 && (
        <p>
          No contracts yet. A contract is created when a client accepts
          an application.
        </p>
      )}
      <ul className="card-list">
        {contracts?.map((contract) => (
          <li key={contract.id} className="card">
            <h2>
              <Link to={`/jobs/${contract.job_id}`}>
                {jobTitles[contract.job_id] ?? `Job #${contract.job_id}`}
              </Link>
            </h2>
            <p className="meta">
              {contract.client_id === user.id ? "You are the client" : "You are the worker"}
              {" · "}Status: {contract.status}
              {contract.agreed_amount !== null && (
                <>
                  {" · "}
                  {contract.agreed_amount} {contract.currency}
                </>
              )}
            </p>
          </li>
        ))}
      </ul>
    </main>
  );
}
