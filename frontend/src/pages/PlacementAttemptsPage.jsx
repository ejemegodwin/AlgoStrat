import { useEffect, useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";

export default function PlacementAttemptsPage() {
  const { token } = useAuth();
  const [attempts, setAttempts] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setAttempts(null);
    api("/placement-attempts/me", { token })
      .then((data) => {
        if (!cancelled) setAttempts(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (error) {
    return (
      <main>
        <p className="error">{error}</p>
      </main>
    );
  }
  if (attempts === null) {
    return <main><p>Loading…</p></main>;
  }
  if (attempts.length === 0) {
    return (
      <main>
        <h1>Your placement check attempts</h1>
        <p>You haven't started any placement checks yet.</p>
      </main>
    );
  }

  return (
    <main>
      <h1>Your placement check attempts</h1>
      <ul className="card-list">
        {attempts.map((attempt) => (
          <li key={attempt.id} className="card">
            <h2>{attempt.check.title}</h2>
            <p className="meta">
              Skill: {attempt.check.skill} · Variant {attempt.variant_id} ·
              Status: {attempt.status.replaceAll("_", " ")}
            </p>
            {attempt.status === "started" && (
              <>
                <p className="meta">In progress — finish and submit to get review.</p>
                <form
                  onSubmit={async (event) => {
                    event.preventDefault();
                    const submission = event.target.elements.submission.value;
                    try {
                      await api(
                        `/placement-attempts/${attempt.id}/submit`,
                        {
                          method: "POST",
                          token,
                          body: { submission },
                        },
                      );
                      setAttempts(null);
                    } catch (err) {
                      alert(err.message);
                    }
                  }}
                >
                  <label>
                    Your answer
                    <textarea
                      name="submission"
                      required
                      minLength={10}
                      maxLength={5000}
                      rows={6}
                    />
                  </label>
                  <div className="actions">
                    <button type="submit">Submit for review</button>
                  </div>
                </form>
              </>
            )}
            {attempt.submission && (
              <pre>{attempt.submission}</pre>
            )}
            {attempt.feedback && (
              <p>
                <span className="meta">Feedback:</span> {attempt.feedback}
              </p>
            )}
            {attempt.status === "not_yet" && attempt.feedback && (
              <p className="error">Not yet — try again.</p>
            )}
            {attempt.status === "passed" && (
              <p className="meta">Passed! This skill is now verified on your profile.</p>
            )}
            {attempt.submitted_at && (
              <p className="meta">
                Submitted {new Date(attempt.submitted_at).toLocaleString()}
              </p>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
