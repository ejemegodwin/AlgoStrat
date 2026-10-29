import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api";
import { useAuth, CLIENT_SIDE } from "../auth";
import { SUPPORTED_CURRENCIES } from "../constants";

// Evaluable job types cannot be published without at least one
// acceptance criterion — the server enforces it; we hint early.
const EVALUABLE_TYPES = ["starter_task", "placement_check"];

function emptyCriterion() {
  return { text: "", required: true };
}

export default function PostJobPage() {
  const { user, token } = useAuth();
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [budget, setBudget] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [category, setCategory] = useState("");
  const [location, setLocation] = useState("");
  const [jobType, setJobType] = useState("standard");
  const [workMode, setWorkMode] = useState("remote");
  const [deadline, setDeadline] = useState("");
  const [minWorkerLevel, setMinWorkerLevel] = useState("0");
  const [criteria, setCriteria] = useState([]);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function updateCriterion(index, patch) {
    setCriteria((rows) =>
      rows.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);

    const cleanedCriteria = criteria
      .map((row) => ({ ...row, text: row.text.trim() }))
      .filter((row) => row.text !== "");
    if (EVALUABLE_TYPES.includes(jobType) && cleanedCriteria.length === 0) {
      setError(
        "This job type is reviewed against acceptance criteria — add at least one.",
      );
      return;
    }

    setSubmitting(true);
    try {
      const job = await api("/jobs", {
        method: "POST",
        token,
        body: {
          title,
          description,
          // Budget is optional on the API; "" would not parse as a
          // number, so send null instead.
          budget: budget === "" ? null : Number(budget),
          currency,
          category: category === "" ? null : category,
          location: location === "" ? null : location,
          job_type: jobType,
          work_mode: workMode,
          deadline: deadline === "" ? null : new Date(deadline).toISOString(),
          min_worker_level: Number(minWorkerLevel),
          criteria: cleanedCriteria,
        },
      });
      navigate(`/jobs/${job.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  // The API returns 403 for worker-only accounts; a direct visit to
  // the URL gets the explanation instead of the form.
  if (!CLIENT_SIDE.includes(user.account_type)) {
    return (
      <main className="narrow">
        <h1>Post a job</h1>
        <p className="meta">
          Only client accounts can post jobs. Your account is set up for
          working.
        </p>
      </main>
    );
  }

  return (
    <main className="narrow">
      <h1>Post a job</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Title
          <input
            type="text"
            required
            minLength={3}
            maxLength={150}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <label>
          Description
          <textarea
            required
            minLength={10}
            rows={6}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        <div className="field-row">
          <label>
            Budget (optional)
            <input
              type="number"
              min="0"
              step="0.01"
              value={budget}
              onChange={(event) => setBudget(event.target.value)}
            />
          </label>
          <label>
            Currency
            <select
              value={currency}
              onChange={(event) => setCurrency(event.target.value)}
            >
              {SUPPORTED_CURRENCIES.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="field-row">
          <label>
            Job type
            <select
              value={jobType}
              onChange={(event) => setJobType(event.target.value)}
            >
              <option value="standard">Standard</option>
              <option value="starter_task">Starter task</option>
              <option value="placement_check">Placement check</option>
            </select>
          </label>
          <label>
            Work mode
            <select
              value={workMode}
              onChange={(event) => setWorkMode(event.target.value)}
            >
              <option value="remote">Remote</option>
              <option value="in_person">In person</option>
            </select>
          </label>
        </div>
        <div className="field-row">
          <label>
            Deadline (optional)
            <input
              type="datetime-local"
              value={deadline}
              onChange={(event) => setDeadline(event.target.value)}
            />
          </label>
          <label>
            Minimum worker level
            <select
              value={minWorkerLevel}
              onChange={(event) => setMinWorkerLevel(event.target.value)}
            >
              <option value="0">Any level</option>
              <option value="1">Level 1+ (1 verified completion)</option>
              <option value="2">Level 2+ (proven across clients)</option>
              <option value="3">Level 3 (established)</option>
            </select>
          </label>
        </div>
        <label>
          Category (optional)
          <input
            type="text"
            maxLength={50}
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          />
        </label>
        <label>
          Location (optional)
          <input
            type="text"
            maxLength={120}
            value={location}
            onChange={(event) => setLocation(event.target.value)}
          />
        </label>

        <fieldset>
          <legend>Acceptance criteria (what "done" means)</legend>
          <p className="meta">
            Reviews and work receipts judge the work against these. Evaluable
            job types need at least one.
          </p>
          {criteria.map((row, index) => (
            <div className="field-row" key={index}>
              <label>
                Criterion {index + 1}
                <input
                  type="text"
                  maxLength={500}
                  value={row.text}
                  onChange={(event) =>
                    updateCriterion(index, { text: event.target.value })
                  }
                />
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={row.required}
                  onChange={(event) =>
                    updateCriterion(index, { required: event.target.checked })
                  }
                />
                Required
              </label>
              <button
                type="button"
                className="link"
                onClick={() =>
                  setCriteria((rows) => rows.filter((_, i) => i !== index))
                }
              >
                Remove
              </button>
            </div>
          ))}
          <button
            type="button"
            className="link"
            disabled={criteria.length >= 20}
            onClick={() => setCriteria((rows) => [...rows, emptyCriterion()])}
          >
            + Add criterion
          </button>
        </fieldset>

        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Posting…" : "Post job"}
        </button>
      </form>
    </main>
  );
}
