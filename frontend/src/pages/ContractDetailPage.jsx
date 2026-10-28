// Contract detail: the ADR-008 milestone loop as a UI. The API
// enforces every rule (party-only access, client/worker actions,
// active-contract-only mutations, budget cap); the UI's job is only
// to not offer what doesn't apply — same philosophy as the apply
// form on the job page.
//
// Money note (ADR-012): approving a PRICED milestone charges the
// client, so the review form asks for a payment token. That is a
// provider token, never card data; with the simulated provider any
// value charges and "tok_fail" exercises the 402 decline path.

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { fetchJobTitles } from "../jobs";

// Mirrors OPEN_MILESTONE_STATUSES in the contracts router: these
// block completion and are cancelled with the contract. The API is
// the enforcement; this copy only drives button states.
const OPEN_STATUSES = ["pending", "submitted", "changes_requested"];

function formatDateTime(value) {
  return new Date(value).toLocaleString();
}

function formatDate(value) {
  return new Date(value).toLocaleDateString();
}

// One form serves add and edit: the fields are identical, only the
// request differs (POST vs PATCH, empty vs prefilled).
function MilestoneForm({ contractId, milestone, onDone, onCancel }) {
  const { token } = useAuth();
  const editing = milestone !== null;
  const [title, setTitle] = useState(milestone?.title ?? "");
  const [description, setDescription] = useState(milestone?.description ?? "");
  const [amount, setAmount] = useState(milestone?.amount ?? "");
  const [dueDate, setDueDate] = useState(
    milestone?.due_date ? milestone.due_date.slice(0, 10) : "",
  );
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    const body = {
      title,
      description: description || null,
      amount: amount === "" || amount === null ? null : Number(amount),
      due_date: dueDate ? new Date(`${dueDate}T00:00:00`).toISOString() : null,
    };
    try {
      if (editing) {
        await api(`/milestones/${milestone.id}`, {
          method: "PATCH",
          token,
          body,
        });
      } else {
        await api(`/contracts/${contractId}/milestones`, {
          method: "POST",
          token,
          body,
        });
      }
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <label>
        Title
        <input
          required
          minLength={3}
          maxLength={150}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>
      <label>
        Description (optional)
        <textarea
          rows={3}
          maxLength={5000}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>
      <div className="field-row">
        <label>
          Amount (optional)
          <input
            type="number"
            min="0.01"
            step="0.01"
            value={amount ?? ""}
            onChange={(event) => setAmount(event.target.value)}
          />
        </label>
        <label>
          Due date (optional)
          <input
            type="date"
            value={dueDate}
            onChange={(event) => setDueDate(event.target.value)}
          />
        </label>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button type="submit" disabled={submitting}>
          {submitting ? "Saving…" : editing ? "Save changes" : "Add milestone"}
        </button>
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

// The worker's half of the loop: a note describing what was delivered
// (the API requires at least 10 characters — "done" is not a
// submission).
function SubmitForm({ milestone, onDone, onCancel }) {
  const { token } = useAuth();
  const [note, setNote] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api(`/milestones/${milestone.id}/submit`, {
        method: "POST",
        token,
        body: { note },
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
      <label>
        What was delivered?
        <textarea
          required
          minLength={10}
          maxLength={5000}
          rows={4}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button type="submit" disabled={submitting}>
          {submitting ? "Submitting…" : "Submit work"}
        </button>
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

// The client's half: approve (moves money when the milestone is
// priced — the accrual posts in the same transaction, ADR-009/012) or
// request changes (note required, so the worker is never left with a
// dead end).
function ReviewForm({ milestone, onDone, onCancel }) {
  const { token } = useAuth();
  const priced = milestone.amount !== null;
  const [decision, setDecision] = useState("approve");
  const [note, setNote] = useState("");
  const [paymentToken, setPaymentToken] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api(`/milestones/${milestone.id}/review`, {
        method: "POST",
        token,
        body: {
          decision,
          note: note || null,
          payment_token: paymentToken || null,
        },
      });
      onDone();
    } catch (err) {
      // 402 means the charge was declined: nothing posted, the
      // milestone is still submitted, and trying another token is safe.
      setError(
        err instanceof ApiError && err.status === 402
          ? "The payment was declined. Try another payment token."
          : err.message,
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="actions">
        <button
          type="button"
          className={decision === "approve" ? "" : "secondary"}
          onClick={() => setDecision("approve")}
        >
          Approve
        </button>
        <button
          type="button"
          className={decision === "request_changes" ? "" : "secondary"}
          onClick={() => setDecision("request_changes")}
        >
          Request changes
        </button>
      </div>
      <label>
        Note {decision === "request_changes" ? "(required)" : "(optional)"}
        <textarea
          required={decision === "request_changes"}
          minLength={10}
          maxLength={5000}
          rows={3}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      {decision === "approve" && priced && (
        <label>
          Payment token
          <input
            required
            minLength={3}
            maxLength={100}
            value={paymentToken}
            onChange={(event) => setPaymentToken(event.target.value)}
          />
          <span className="meta">
            Approving charges {milestone.amount} now. Simulated provider:
            any token succeeds; tok_fail simulates a decline.
          </span>
        </label>
      )}
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button type="submit" disabled={submitting}>
          {submitting
            ? "Sending…"
            : decision === "approve"
              ? priced
                ? "Approve & pay"
                : "Approve"
              : "Request changes"}
        </button>
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function MilestoneCard({ milestone, isClient, contractActive, onChanged }) {
  const { token } = useAuth();
  // Which inline form (if any) is open under this milestone.
  const [form, setForm] = useState(null); // "edit" | "submit" | "review"
  const [error, setError] = useState(null);
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!window.confirm(`Delete milestone "${milestone.title}"?`)) return;
    setError(null);
    setDeleting(true);
    try {
      await api(`/milestones/${milestone.id}`, { method: "DELETE", token });
      setForm(null);
      onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setDeleting(false);
    }
  }

  function closeAndReload() {
    setForm(null);
    onChanged();
  }

  return (
    <li className="card">
      <h3>
        {milestone.title}{" "}
        <span className="meta">— {milestone.status.replaceAll("_", " ")}</span>
      </h3>
      <p className="meta">
        {milestone.amount !== null && <>Amount: {milestone.amount} </>}
        {milestone.due_date && <>Due: {formatDate(milestone.due_date)} </>}
        {milestone.submitted_at &&
          `Submitted: ${formatDateTime(milestone.submitted_at)}`}
      </p>
      {milestone.description && (
        <p className="description">{milestone.description}</p>
      )}
      {milestone.submission_note && (
        <p className="description">
          <strong>Submission:</strong> {milestone.submission_note}
        </p>
      )}
      {error && <p className="error">{error}</p>}

      {form === "edit" && (
        <MilestoneForm
          contractId={milestone.contract_id}
          milestone={milestone}
          onDone={closeAndReload}
          onCancel={() => setForm(null)}
        />
      )}
      {form === "submit" && (
        <SubmitForm
          milestone={milestone}
          onDone={closeAndReload}
          onCancel={() => setForm(null)}
        />
      )}
      {form === "review" && (
        <ReviewForm
          milestone={milestone}
          onDone={closeAndReload}
          onCancel={() => setForm(null)}
        />
      )}

      {form === null && contractActive && (
        <div className="actions">
          {isClient && milestone.status === "pending" && (
            <>
              <button
                type="button"
                className="secondary"
                disabled={deleting}
                onClick={() => setForm("edit")}
              >
                Edit
              </button>
              <button
                type="button"
                className="secondary"
                disabled={deleting}
                onClick={handleDelete}
              >
                {deleting ? "Deleting…" : "Delete"}
              </button>
            </>
          )}
          {!isClient &&
            (milestone.status === "pending" ||
              milestone.status === "changes_requested") && (
              <button type="button" onClick={() => setForm("submit")}>
                {milestone.status === "changes_requested"
                  ? "Resubmit work"
                  : "Submit work"}
              </button>
            )}
          {isClient && milestone.status === "submitted" && (
            <button type="button" onClick={() => setForm("review")}>
              Review
            </button>
          )}
        </div>
      )}
    </li>
  );
}

// Human-readable labels for the audit log; unknown types fall back to
// their raw name with spaces so a new event type never renders blank.
const EVENT_LABELS = {
  contract_created: "Contract created",
  dispute_raised: "Dispute raised",
  dispute_resolved: "Dispute resolved",
  milestone_added: "Milestone added",
  milestone_updated: "Milestone updated",
  milestone_removed: "Milestone removed",
  milestone_submitted: "Milestone submitted",
  review_approved: "Milestone approved",
  changes_requested: "Changes requested",
  contract_completed: "Contract completed",
  contract_cancelled: "Contract cancelled",
  dispute_raised: "Dispute raised",
};

function EventsList({ events, userId }) {
  if (events.length === 0) return null;
  return (
    <section>
      <h2>History</h2>
      <ul className="card-list">
        {events.map((event) => (
          <li key={event.id} className="card">
            <p className="meta">
              {formatDateTime(event.created_at)}
              {" · "}
              {event.actor_id === userId ? "You" : "The other party"}
            </p>
            <p className="description">
              <strong>
                {EVENT_LABELS[event.event_type] ??
                  event.event_type.replaceAll("_", " ")}
              </strong>
              {event.note && <> — {event.note}</>}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

// Either party can raise a dispute on an active contract (ADR-011).
// Raising freezes everything immediately — the confirm says so in
// plain terms, because every other action on this page silently
// disappears while the contract is disputed.
function DisputeSection({ contract, milestones, disputes, onChanged }) {
  const { user, token } = useAuth();
  const [raising, setRaising] = useState(false);
  const [reason, setReason] = useState("");
  const [milestoneId, setMilestoneId] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleRaise(event) {
    event.preventDefault();
    if (
      !window.confirm(
        "Raise a dispute? The contract freezes immediately: no " +
          "milestones can be added, submitted, reviewed, or completed " +
          "until an admin resolves it.",
      )
    ) {
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await api(`/contracts/${contract.id}/disputes`, {
        method: "POST",
        token,
        body: {
          reason,
          milestone_id: milestoneId === "" ? null : Number(milestoneId),
        },
      });
      setRaising(false);
      setReason("");
      setMilestoneId("");
      onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section>
      <h2>Disputes</h2>
      {contract.status === "disputed" && (
        <p className="meta">
          This contract is frozen while an admin reviews the dispute —
          all other actions are paused.
        </p>
      )}
      {disputes.length > 0 && (
        <ul className="card-list">
          {disputes.map((dispute) => (
            <li key={dispute.id} className="card">
              <p className="meta">
                {dispute.raised_by === user.id ? "You" : "The other party"}
                {" · "}
                {new Date(dispute.created_at).toLocaleString()}
                {" · "}
                {dispute.status}
              </p>
              <p className="description">{dispute.reason}</p>
              {dispute.status === "resolved" && (
                <p className="meta">
                  Resolved: {dispute.resolution?.replaceAll("_", " ")}
                  {dispute.resolution_note && <> — {dispute.resolution_note}</>}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
      {contract.status === "active" && !raising && (
        <div className="actions">
          <button
            type="button"
            className="secondary"
            onClick={() => setRaising(true)}
          >
            Raise a dispute
          </button>
        </div>
      )}
      {raising && (
        <form onSubmit={handleRaise}>
          <label>
            What went wrong? (at least 20 characters)
            <textarea
              required
              minLength={20}
              maxLength={5000}
              rows={4}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          <label>
            About a specific milestone? (optional)
            <select
              value={milestoneId}
              onChange={(event) => setMilestoneId(event.target.value)}
            >
              <option value="">The contract as a whole</option>
              {milestones.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.title} — {m.status.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
          {error && <p className="error">{error}</p>}
          <div className="actions">
            <button type="submit" disabled={submitting}>
              {submitting ? "Raising…" : "Raise dispute"}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => setRaising(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

export default function ContractDetailPage() {
  const { contractId } = useParams();
  const { user, token } = useAuth();
  const [contract, setContract] = useState(null);
  const [events, setEvents] = useState(null);
  const [disputes, setDisputes] = useState(null);
  const [jobTitle, setJobTitle] = useState(null);
  const [error, setError] = useState(null);
  const [adding, setAdding] = useState(false);
  const [actionError, setActionError] = useState(null);

  // One loader for mount and for refresh after every mutation: each
  // action changes the contract, the milestones, and the audit log.
  const load = useCallback(async () => {
    const [detail, eventList, disputeList] = await Promise.all([
      api(`/contracts/${contractId}`, { token }),
      api(`/contracts/${contractId}/events`, { token }),
      api(`/contracts/${contractId}/disputes`, { token }),
    ]);
    setContract(detail);
    setEvents(eventList);
    setDisputes(disputeList);
    const titles = await fetchJobTitles(token, [detail.job_id]);
    setJobTitle(titles[detail.job_id]);
  }, [contractId, token]);

  useEffect(() => {
    let cancelled = false;
    load().catch((err) => {
      if (!cancelled) setError(err.message);
    });
    return () => {
      cancelled = true;
    };
  }, [load]);

  // Post-mutation reloads surface failures in the page error block
  // instead of becoming unhandled promise rejections.
  const reload = useCallback(
    () => load().catch((err) => setError(err.message)),
    [load],
  );

  async function contractAction(action, confirmText) {
    if (!window.confirm(confirmText)) return;
    setActionError(null);
    try {
      await api(`/contracts/${contractId}/${action}`, {
        method: "POST",
        token,
      });
      await reload();
    } catch (err) {
      setActionError(err.message);
    }
  }

  if (error) {
    return (
      <main>
        <p className="error">{error}</p>
        <Link to="/contracts">Back to contracts</Link>
      </main>
    );
  }
  if (contract === null) {
    return (
      <main>
        <p>Loading…</p>
      </main>
    );
  }

  const isClient = contract.client_id === user.id;
  const active = contract.status === "active";
  const milestones = [...contract.milestones].sort(
    (a, b) => a.position - b.position || a.id - b.id,
  );
  const openCount = milestones.filter((m) =>
    OPEN_STATUSES.includes(m.status),
  ).length;
  const allocated = milestones
    .filter((m) => m.status !== "cancelled" && m.amount !== null)
    .reduce((sum, m) => sum + Number(m.amount), 0);
  // Float sums of 2-decimal amounts can print long tails (0.1 + 0.2);
  // the budget check itself happens server-side in Decimal.
  const allocatedDisplay = Number(allocated.toFixed(2));

  return (
    <main>
      <p>
        <Link to="/contracts">← My contracts</Link>
      </p>
      <h1>
        <Link to={`/jobs/${contract.job_id}`}>
          {jobTitle ?? `Job #${contract.job_id}`}
        </Link>
      </h1>
      <p className="meta">
        {isClient ? "You are the client" : "You are the worker"}
        {" · "}Status: {contract.status}
        {contract.agreed_amount !== null && (
          <>
            {" · "}Agreed: {contract.agreed_amount} {contract.currency}
          </>
        )}
      </p>

      <section>
        <h2>Milestones</h2>
        {milestones.length === 0 && (
          <p>
            {isClient
              ? "No milestones yet — add the first one below."
              : "No milestones yet. The client defines them."}
          </p>
        )}
        <ul className="card-list">
          {milestones.map((milestone) => (
            <MilestoneCard
              key={milestone.id}
              milestone={milestone}
              isClient={isClient}
              contractActive={active}
              onChanged={reload}
            />
          ))}
        </ul>
        {isClient && active && !adding && (
          <div className="actions">
            <button type="button" onClick={() => setAdding(true)}>
              Add milestone
            </button>
          </div>
        )}
        {isClient && active && adding && (
          <>
            {contract.agreed_amount !== null && (
              <p className="meta">
                Allocated so far: {allocatedDisplay} of{" "}
                {contract.agreed_amount} {contract.currency}
              </p>
            )}
            <MilestoneForm
              contractId={contract.id}
              milestone={null}
              onDone={() => {
                setAdding(false);
                reload();
              }}
              onCancel={() => setAdding(false)}
            />
          </>
        )}
      </section>

      {isClient && active && (
        <section>
          <h2>Contract actions</h2>
          {actionError && <p className="error">{actionError}</p>}
          <div className="actions">
            <button
              type="button"
              disabled={openCount > 0}
              onClick={() =>
                contractAction(
                  "complete",
                  "Complete this contract? This is final.",
                )
              }
            >
              Complete contract
            </button>
            <button
              type="button"
              className="danger"
              onClick={() =>
                contractAction(
                  "cancel",
                  "Cancel this contract? All open milestones will be " +
                    "cancelled with it. This cannot be undone.",
                )
              }
            >
              Cancel contract
            </button>
          </div>
          {openCount > 0 && (
            <p className="meta">
              {openCount} open milestone{openCount === 1 ? "" : "s"} must be
              approved or cancelled before the contract can be completed.
            </p>
          )}
        </section>
      )}

      {disputes !== null && (
        <DisputeSection
          contract={contract}
          milestones={milestones}
          disputes={disputes}
          onChanged={reload}
        />
      )}

      {events !== null && <EventsList events={events} userId={user.id} />}
    </main>
  );
}
