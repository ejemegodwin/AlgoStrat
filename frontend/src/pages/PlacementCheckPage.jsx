import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";

export default function PlacementCheckPage() {
  const { skill } = useParams();
  const { token, user } = useAuth();
  const navigate = useNavigate();
  const [check, setCheck] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setCheck(null);
    api(`/placement-checks/${encodeURIComponent(skill)}`)
      .then((data) => {
        if (!cancelled) setCheck(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [skill]);

  if (error) {
    return (
      <main>
        <p className="error">{error}</p>
        <p>
          <Link to="/placement-checks">Back to all checks</Link>
        </p>
      </main>
    );
  }
  if (!check) {
    return <main><p>Loading…</p></main>;
  }

  return (
    <main>
      <h1>{check.title}</h1>
      <p className="meta">Skill: {check.skill}</p>
      <p>{check.description}</p>
      {check.learning_resources && (
        <p className="meta">
          <a
            href={check.learning_resources}
            target="_blank"
            rel="noopener noreferrer"
          >
            Learning resources
          </a>
        </p>
      )}

      <h2>Variants</h2>
      <p className="meta">
        Each attempt serves a different variant. You get up to 5 attempts per
        check, then a 7-day cooldown.
      </p>
      <ul>
        {check.variants.map((variant) => (
          <li key={variant.id} className="card">
            <h3>Variant {variant.position + 1}</h3>
            <pre>{variant.prompt}</pre>
            <p className="meta">Criteria:</p>
            <ul>
              {variant.criteria.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </li>
        ))}
      </ul>

      {user ? (
        <button
          type="button"
          onClick={async () => {
            try {
              await api(`/placement-checks/${check.skill}/attempts`, {
                method: "POST",
                token,
              });
              navigate("/placement-attempts");
            } catch (err) {
              if (err.status === 429) {
                alert(err.message);
              } else {
                alert(err.message);
              }
            }
          }}
        >
          Start attempt
        </button>
      ) : (
        <p>
          <Link to="/login">Log in</Link> to start an attempt.
        </p>
      )}
    </main>
  );
}
