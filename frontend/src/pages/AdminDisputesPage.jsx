// The admin dispute queue (ADR-011/017). Admins are ordinary users
// with is_admin set (seeded manually via SQL); the listing embeds the
// job, contract, milestone, and party names because the admin decides
// without being a party — the party endpoints would 403 for them.
//
// Each resolution's consequences are spelled out next to the choice:
// resolving moves money (force-approve accrues, client-favored
// refunds a charged milestone), so the confirm restates the outcome
// before the request leaves.

import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";

const OUTCOMES = {
  worker_favored:
    "force-approves the referenced milestone if work was submitted " +
    "(the worker's earnings accrue), and the contract resumes.",
  client_favored:
    "cancels the contract and its open milestones; if the referenced " +
    "milestone was approved and charged, the charge is refunded and " +
    "the accrual reversed.",
  dismissed: "changes nothing — the contract simply resumes.",
};

function ResolveForm({ dispute, onDone, onCancel }) {
  const { token } = useAuth();
  const [resolution, setResolution] = useState("dismissed");
  const [note, setNote] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (
      !window.confirm(
        `Resolve dispute #${dispute.id} as ` +
          `${resolution.replaceAll("_", " ")}? This ${OUTCOMES[resolution]}`,
      )
    ) {
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await api(`/admin/disputes/${dispute.id}/resolve`, {
        method: "POST",
        token,
        body: { resolution, note },
      });
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="actions">
        {Object.keys(OUTCOMES).map((outcome) => (
          <button
            key={outcome}
            type="button"
            className={resolution === outcome ? "" : "secondary"}
            onClick={() => setResolution(outcome)}
          >
            {outcome.replaceAll("_", " ")}
          </button>
        ))}
      </div>
      <p className="meta">
        {resolution.replaceAll("_", " ")}: this {OUTCOMES[resolution]}
      </p>
      <label>
        Resolution note (required, at least 10 characters)
        <textarea
          required
          minLength={10}
          maxLength={5000}
          rows={3}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button type="submit" disabled={submitting}>
          {submitting ? "Resolving…" : "Resolve dispute"}
        </button>
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

export default function AdminDisputesPage() {
  const { user, token } = useAuth();
  const [tab, setTab] = useState("open");
  const [disputes, setDisputes] = useState(null);
  const [error, setError] = useState(null);
  const [resolvingId, setResolvingId] = useState(null);

  const load = useCallback(async () => {
    const data = await api(`/admin/disputes?dispute_status=${tab}`, { token });
    setDisputes(data);
  }, [tab, token]);

  useEffect(() => {
    let cancelled = false;
    setDisputes(null);
    load().catch((err) => {
      if (!cancelled) setError(err.message);
    });
    return () => {
      cancelled = true;
    };
  }, [load]);

  const reload = useCallback(
    () => load().catch((err) => setError(err.message)),
    [load],
  );

  if (!user?.is_admin) {
    return (
      <main>
        <p className="error">Admin access required.</p>
      </main>
    );
  }

  return (
    <main>
      <h1>Dispute queue</h1>
      <div className="actions">
        <button
          type="button"
          className={tab === "open" ? "" : "secondary"}
          onClick={() => setTab("open")}
        >
          Open
        </button>
        <button
          type="button"
          className={tab === "resolved" ? "" : "secondary"}
          onClick={() => setTab("resolved")}
        >
          Resolved
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {disputes === null && !error && <p>Loading…</p>}
      {disputes !== null && disputes.length === 0 && (
        <p>No {tab} disputes.</p>
      )}
      <ul className="card-list">
        {disputes?.map((dispute) => (
          <li key={dispute.id} className="card">
            <h3>
              Dispute #{dispute.id}: {dispute.job_title}
            </h3>
            <p className="meta">
              Raised by {dispute.raised_by_name}
              {" · "}
              {new Date(dispute.created_at).toLocaleString()}
              {" · "}Contract {dispute.contract_status}
              {dispute.agreed_amount !== null && (
                <>
                  {" · "}Agreed: {dispute.agreed_amount} {dispute.currency}
                </>
              )}
            </p>
            <p className="meta">
              {dispute.client_name} (client) vs {dispute.worker_name} (worker)
            </p>
            {dispute.milestone_id !== null && (
              <p className="meta">
                Milestone: {dispute.milestone_title} —{" "}
                {dispute.milestone_status?.replaceAll("_", " ")}
                {dispute.milestone_amount !== null && (
                  <>, {dispute.milestone_amount} {dispute.currency}</>
                )}
              </p>
            )}
            <p className="description">{dispute.reason}</p>
            {dispute.status === "resolved" ? (
              <p className="meta">
                Resolved as {dispute.resolution?.replaceAll("_", " ")}
                {dispute.resolution_note && <> — {dispute.resolution_note}</>}
              </p>
            ) : resolvingId === dispute.id ? (
              <ResolveForm
                dispute={dispute}
                onDone={() => {
                  setResolvingId(null);
                  reload();
                }}
                onCancel={() => setResolvingId(null)}
              />
            ) : (
              <div className="actions">
                <button
                  type="button"
                  disabled={resolvingId !== null}
                  onClick={() => setResolvingId(dispute.id)}
                >
                  Resolve
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
