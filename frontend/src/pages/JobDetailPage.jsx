import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, ApiError } from "../api";
import { useAuth, WORKER_SIDE } from "../auth";
import ApplicantsSection from "../components/ApplicantsSection";

// The apply form is a section, not a page: applying is something you
// do while reading the job. Own jobs and closed jobs don't offer it
// (the API enforces both; the UI just doesn't present the option).
function ApplySection({ job }) {
  const { user, token } = useAuth();
  const [coverLetter, setCoverLetter] = useState("");
  // null | "applied" | "already" — error strings go to `error`.
  const [outcome, setOutcome] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  if (!user) {
    return (
      <p>
        <Link to="/login" state={{ from: `/jobs/${job.id}` }}>
          Log in
        </Link>{" "}
        to apply for this job.
      </p>
    );
  }
  if (user.id === job.customer_id || job.status !== "open") {
    return null;
  }
  // The API returns 403 for client-only accounts; saying so up front
  // beats a failed form submit.
  if (!WORKER_SIDE.includes(user.account_type)) {
    return (
      <p className="meta">
        Only worker accounts can apply for jobs. Your account is set up
        for hiring.
      </p>
    );
  }
  if (outcome === "applied") {
    return (
      <p>
        Application sent. Track it under{" "}
        <Link to="/applications">My applications</Link>.
      </p>
    );
  }
  if (outcome === "already") {
    return (
      <p>
        You have already applied for this job — see{" "}
        <Link to="/applications">My applications</Link>.
      </p>
    );
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api(`/jobs/${job.id}/applications`, {
        method: "POST",
        token,
        body: { cover_letter: coverLetter },
      });
      setOutcome("applied");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setOutcome("already");
      } else {
        setError(err.message);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section>
      <h2>Apply</h2>
      <form onSubmit={handleSubmit}>
        <label>
          Cover letter (at least 20 characters)
          <textarea
            required
            minLength={20}
            maxLength={5000}
            rows={6}
            value={coverLetter}
            onChange={(event) => setCoverLetter(event.target.value)}
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Sending…" : "Send application"}
        </button>
      </form>
    </section>
  );
}

export default function JobDetailPage() {
  const { jobId } = useParams();
  const { user } = useAuth();
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);

  // One loader for mount and for refresh-after-accept: the applicant
  // review below can close the job, and the page should show that.
  const loadJob = useCallback(() => {
    return api(`/jobs/${jobId}`).then(setJob);
  }, [jobId]);

  useEffect(() => {
    let cancelled = false;
    loadJob().catch((err) => {
      if (!cancelled) setError(err.message);
    });
    return () => {
      cancelled = true;
    };
  }, [loadJob]);

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
        {" · "}
        {job.job_type === "standard"
          ? "Standard job"
          : job.job_type === "starter_task"
            ? "Starter task"
            : "Placement check"}
        {" · "}
        {job.work_mode === "remote" ? "Remote" : "In person"}
        {job.deadline && (
          <> · Deadline: {new Date(job.deadline).toLocaleDateString()}</>
        )}
        {job.min_worker_level > 0 && (
          <> · Requires worker level {job.min_worker_level}+</>
        )}
        {" · "}Status: {job.status}
      </p>
      <p className="description">{job.description}</p>
      {job.criteria && job.criteria.length > 0 && (
        <section>
          <h2>Acceptance criteria</h2>
          <p className="meta">
            The work is reviewed — and its receipt issued — against these.
          </p>
          <ol>
            {job.criteria.map((criterion) => (
              <li key={criterion.position}>
                {criterion.text}
                {!criterion.required && (
                  <span className="meta"> (optional)</span>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}
      {user && user.id === job.customer_id ? (
        <ApplicantsSection job={job} onJobChanged={loadJob} />
      ) : (
        <ApplySection job={job} />
      )}
    </main>
  );
}
