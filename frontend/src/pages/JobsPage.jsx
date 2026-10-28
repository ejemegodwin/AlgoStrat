import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";

function formatBudget(job) {
  if (job.budget === null || job.budget === undefined) {
    return "No budget stated";
  }
  return `${job.budget} ${job.currency}`;
}

export default function JobsPage() {
  const [jobs, setJobs] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api("/jobs")
      .then((data) => {
        if (!cancelled) setJobs(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main>
      <h1>Open jobs</h1>
      {error && <p className="error">{error}</p>}
      {jobs === null && !error && <p>Loading…</p>}
      {jobs !== null && jobs.length === 0 && <p>No open jobs yet.</p>}
      <ul className="card-list">
        {jobs?.map((job) => (
          <li key={job.id} className="card">
            <h2>
              <Link to={`/jobs/${job.id}`}>{job.title}</Link>
            </h2>
            <p className="meta">
              {formatBudget(job)}
              {job.category && <> · {job.category}</>}
              {job.location && <> · {job.location}</>}
            </p>
            <p>{job.description}</p>
          </li>
        ))}
      </ul>
    </main>
  );
}
