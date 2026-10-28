// The job owner's review panel: pending applicants ranked by the
// explainable matching score (ADR-010 — the API shows the owner the
// same factors it shows workers), plus the decided history. Accepting
// is consequential (ADR-001/008): it hires, closes the job, rejects
// the other pending applications, and creates the contract — so the
// confirm says exactly that before the request leaves.

import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";

function FactorList({ factors }) {
  return (
    <ul className="factors">
      {Object.values(factors).map((factor, index) => (
        <li key={index}>{factor.reason}</li>
      ))}
    </ul>
  );
}

export default function ApplicantsSection({ job, onJobChanged }) {
  const { token } = useAuth();
  const [ranked, setRanked] = useState(null);
  const [decided, setDecided] = useState(null);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    const [rankedData, allData] = await Promise.all([
      api(`/jobs/${job.id}/applicants/ranked`, { token }),
      api(`/jobs/${job.id}/applications`, { token }),
    ]);
    setRanked(rankedData);
    setDecided(allData.filter((a) => a.status !== "pending"));
  }, [job.id, token]);

  useEffect(() => {
    let cancelled = false;
    load().catch((err) => {
      if (!cancelled) setError(err.message);
    });
    return () => {
      cancelled = true;
    };
  }, [load]);

  async function decide(application, workerName, status) {
    if (status === "accepted") {
      const confirmed = window.confirm(
        `Accept ${workerName}'s application?\n\n` +
          "This hires them: the job closes, every other pending " +
          "application is rejected, and a contract is created.",
      );
      if (!confirmed) return;
    }
    setBusyId(application.id);
    setError(null);
    try {
      await api(`/jobs/${job.id}/applications/${application.id}`, {
        method: "PATCH",
        token,
        body: { status },
      });
      await load();
      // An accept closes the job — let the page refresh it.
      onJobChanged?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section>
      <h2>Applicants</h2>
      {error && <p className="error">{error}</p>}
      {ranked === null && !error && <p>Loading…</p>}
      {ranked !== null && ranked.length === 0 && (
        <p>No pending applications.</p>
      )}
      <ul className="card-list">
        {ranked?.map(({ application, worker_name, score, factors }) => (
          <li key={application.id} className="card">
            <h3>
              {worker_name}{" "}
              <span className="meta">
                — match {Math.round(score * 100)}%
              </span>
            </h3>
            <FactorList factors={factors} />
            <p className="description">{application.cover_letter}</p>
            <div className="actions">
              <button
                type="button"
                disabled={busyId !== null}
                onClick={() => decide(application, worker_name, "accepted")}
              >
                Accept & hire
              </button>
              <button
                type="button"
                className="secondary"
                disabled={busyId !== null}
                onClick={() => decide(application, worker_name, "rejected")}
              >
                Reject
              </button>
            </div>
          </li>
        ))}
      </ul>
      {decided !== null && decided.length > 0 && (
        <>
          <h3>Decided</h3>
          <ul className="card-list">
            {decided.map((application) => (
              <li key={application.id} className="card">
                <p className="meta">
                  Application #{application.id} — {application.status}
                </p>
                <p className="description">{application.cover_letter}</p>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
