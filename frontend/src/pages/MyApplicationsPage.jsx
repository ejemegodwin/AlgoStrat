import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";
import { fetchJobTitles } from "../jobs";

export default function MyApplicationsPage() {
  const { token } = useAuth();
  const [applications, setApplications] = useState(null);
  const [jobTitles, setJobTitles] = useState({});
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api("/applications/me", { token })
      .then(async (apps) => {
        if (cancelled) return;
        setApplications(apps);
        const titles = await fetchJobTitles(
          token,
          apps.map((a) => a.job_id),
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
      <h1>My applications</h1>
      {error && <p className="error">{error}</p>}
      {applications === null && !error && <p>Loading…</p>}
      {applications !== null && applications.length === 0 && (
        <p>
          You have not applied to any jobs yet.{" "}
          <Link to="/jobs">Browse open jobs</Link>
        </p>
      )}
      <ul className="card-list">
        {applications?.map((application) => (
          <li key={application.id} className="card">
            <h2>
              <Link to={`/jobs/${application.job_id}`}>
                {jobTitles[application.job_id] ??
                  `Job #${application.job_id}`}
              </Link>
            </h2>
            <p className="meta">
              Status: {application.status}
              {" · "}
              {new Date(application.created_at).toLocaleDateString()}
            </p>
            <p>{application.cover_letter}</p>
          </li>
        ))}
      </ul>
    </main>
  );
}
