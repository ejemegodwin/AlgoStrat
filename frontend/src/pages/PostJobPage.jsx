import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";
import { SUPPORTED_CURRENCIES } from "../constants";

export default function PostJobPage() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [budget, setBudget] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [category, setCategory] = useState("");
  const [location, setLocation] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
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
        },
      });
      navigate(`/jobs/${job.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
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
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Posting…" : "Post job"}
        </button>
      </form>
    </main>
  );
}
