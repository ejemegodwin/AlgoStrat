import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";

export default function JobDetailPage() {
  const { jobId } = useParams();
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api(`/jobs/${jobId}`)
      .then((data) => {
        if (!cancelled) setJob(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  if (error) {
    return (
      <main>
        <p className="error">{error}</p>
        <Link to="/jobs">Back to jobs</Link>
      </main>
    );
  }
  if (job === null) {
    return (
      <main>
        <p>Loading…</p>
      </main>
    );
  }

  return (
    <main>
      <p>
        <Link to="/jobs">← All jobs</Link>
      </p>
      <h1>{job.title}</h1>
      <p className="meta">
        {job.budget !== null
          ? `${job.budget} ${job.currency}`
          : "No budget stated"}
        {job.category && <> · {job.category}</>}
        {job.location && <> · {job.location}</>}
        {" · "}Status: {job.status}
      </p>
      <p className="description">{job.description}</p>
    </main>
  );
}
