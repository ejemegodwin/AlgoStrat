import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";

export default function PlacementChecksPage() {
  const [checks, setChecks] = useState(null);
  const [skillFilter, setSkillFilter] = useState("");
  const [error, setError] = useState(null);

  const load = (skill) => {
    setChecks(null);
    setError(null);
    const params = skill ? `?skill=${encodeURIComponent(skill)}` : "";
    api(`/placement-checks${params}`)
      .then((data) => setChecks(data))
      .catch((err) => setError(err.message));
  };

  useEffect(() => {
    let cancelled = false;
    api("/placement-checks")
      .then((data) => {
        if (!cancelled) setChecks(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleFilter = (event) => {
    event.preventDefault();
    load(skillFilter);
  };

  return (
    <main>
      <h1>Placement checks</h1>
      <p className="meta">
        Verified skill assessments. Pass one to earn a verified tag on that
        skill.
      </p>

      <form onSubmit={handleFilter} className="field-row" style={{ marginBottom: "1rem" }}>
        <label>
          Filter by skill
          <input
            type="text"
            placeholder="e.g. python"
            value={skillFilter}
            onChange={(event) => setSkillFilter(event.target.value)}
          />
        </label>
        <button type="submit" className="secondary">
          Filter
        </button>
        {skillFilter && (
          <button
            type="button"
            className="link"
            onClick={() => {
              setSkillFilter("");
              load("");
            }}
          >
            Clear
          </button>
        )}
      </form>

      {error && <p className="error">{error}</p>}
      {checks === null && !error && <p>Loading…</p>}
      {checks !== null && checks.length === 0 && (
        <p>No placement checks match that skill.</p>
      )}
      <ul className="card-list">
        {checks?.map((check) => (
          <li key={check.skill} className="card">
            <h2>
              <Link to={`/placement-checks/${check.skill}`}>{check.title}</Link>
            </h2>
            <p className="meta">Skill: {check.skill}</p>
            <p>{check.description}</p>
            {check.learning_resources && (
              <p className="meta">
                <a href={check.learning_resources} target="_blank" rel="noopener noreferrer">
                  Learning resources
                </a>
              </p>
            )}
            <p className="meta">{check.variants.length} variant(s) available</p>
          </li>
        ))}
      </ul>
    </main>
  );
}
