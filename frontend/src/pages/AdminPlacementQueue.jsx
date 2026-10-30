import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";

export default function AdminPlacementQueue() {
  const { token, user } = useAuth();
  const [status, setStatus] = useState("submitted");
  const [attempts, setAttempts] = useState(null);
  const [error, setError] = useState(null);
  const [reviewingId, setReviewingId] = useState(null);
  const [reviewDecision, setReviewDecision] = useState("passed");
  const [reviewFeedback, setReviewFeedback] = useState("");

  const load = useCallback(async () => {
    setAttempts(null);
    setError(null);
    try {
      const data = await api(`/admin/placement-attempts?status=${status}`, { token });
      setAttempts(data);
    } catch (err) {
      setError(err.message);
    }
  }, [status, token]);

  useEffect(() => {
    let cancelled = false;
    load().then(() => {
      if (!cancelled) return;
    });
    return () => {
      cancelled = true;
    };
  }, [load]);

  const reload = useCallback(() => {
    load().catch((err) => setError(err.message));
  }, [load]);

  async function handleReview(attempt) {
    if (!reviewFeedback.trim()) {
      alert("Feedback is required.");
      return;
    }
    const url =
      reviewDecision === "passed"
        ? `/admin/placement-attempts/${attempt.id}/review/pass`
        : `/admin/placement-attempts/${attempt.id}/review/not-yet`;
    try {
      await api(url, {
        method: "POST",
        token,
        body: { feedback: reviewFeedback },
      });
      setReviewingId(null);
      setReviewFeedback("");
      reload();
    } catch (err) {
      alert(err.message);
    }
  }

  if (!user?.is_admin) {
    return (
      <main>
        <p className="error">Admin access required.</p>
      </main>
    );
  }

  return (
    <main>
      <h1>Placement check queue</h1>
      <div className="actions">
        <button
          type="button"
          className={status === "submitted" ? "" : "secondary"}
          onClick={() => setStatus("submitted")}
        >
          To review
        </button>
        <button
          type="button"
          className={status === "passed" ? "" : "secondary"}
          onClick={() => setStatus("passed")}
        >
          Passed
        </button>
        <button
          type="button"
          className={status === "not_yet" ? "" : "secondary"}
          onClick={() => setStatus("not_yet")}
        >
          Not yet
        </button>
      </div>

      {error && <p className="error">{error}</p>}
      {attempts === null && !error && <p>Loading…</p>}
      {attempts !== null && attempts.length === 0 && (
        <p>No placement attempts with status "{status}".</p>
      )}

      {reviewingId !== null && (
        <div className="card" style={{ marginTop: "1rem" }}>
          <h2>Reviewing attempt #{reviewingId}</h2>
          <div className="actions">
            <button
              type="button"
              className={reviewDecision === "passed" ? "" : "secondary"}
              onClick={() => setReviewDecision("passed")}
            >
              Pass
            </button>
            <button
              type="button"
              className={reviewDecision === "not_yet" ? "" : "secondary"}
              onClick={() => setReviewDecision("not_yet")}
            >
              Not yet
            </button>
          </div>
          <label>
            Feedback (required, at least 10 characters)
            <textarea
              required
              minLength={10}
              maxLength={5000}
              rows={4}
              value={reviewFeedback}
              onChange={(event) => setReviewFeedback(event.target.value)}
            />
          </label>
          <div className="actions">
            <button
              type="button"
              onClick={() => {
                const attempt = attempts.find(
                  (a) => a.id === reviewingId,
                );
                handleReview(attempt);
              }}
            >
              Submit review
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setReviewingId(null);
                setReviewFeedback("");
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <ul className="card-list">
        {attempts?.map((attempt) => (
          <li key={attempt.id} className="card">
            <h2>
              {attempt.check.title} — {attempt.check.skill}
            </h2>
            <p className="meta">
              Variant {attempt.variant_id} · Status:{" "}
              {attempt.status.replaceAll("_", " ")}
              {attempt.submitted_at && (
                <>
                  {" · "}
                  Submitted {new Date(attempt.submitted_at).toLocaleString()}
                </>
              )}
            </p>
            <p>
              <span className="meta">Submission:</span>{" "}
              {attempt.submission}
            </p>
            {attempt.feedback && (
              <p>
                <span className="meta">Feedback:</span> {attempt.feedback}
              </p>
            )}
            {attempt.status === "submitted" && reviewingId !== attempt.id && (
              <div className="actions">
                <button
                  type="button"
                  onClick={() => {
                    setReviewingId(attempt.id);
                    setReviewDecision("passed");
                    setReviewFeedback("");
                  }}
                >
                  Review
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
