// Payouts (ADR-012): the worker's view of the double-entry books.
// Balances are derived server-side; the UI shows worker_receivable
// as "available to withdraw" and, for transparency, any
// client_payable still owed (a worker_favored dispute resolution
// posts an accrual without a charge, leaving the client owing).
//
// The payout itself is a real money movement even with the simulated
// provider, so it is confirm-gated and reports the provider
// reference on success — the reference is the receipt.

import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";

function PayoutForm({ receivables, onDone }) {
  const { token } = useAuth();
  const [currency, setCurrency] = useState(receivables[0].currency);
  const [amount, setAmount] = useState("");
  const [destination, setDestination] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [receipt, setReceipt] = useState(null);

  const selected = receivables.find((r) => r.currency === currency);
  // Balances arrive as JSON strings ("120.00"); Number() before math.
  const available = selected ? Number(selected.balance) : 0;

  async function handleSubmit(event) {
    event.preventDefault();
    const paying = amount === "" ? available : Number(amount);
    if (
      !window.confirm(
        `Pay out ${paying} ${currency} to "${destination}"?`,
      )
    ) {
      return;
    }
    setError(null);
    setReceipt(null);
    setSubmitting(true);
    try {
      const payout = await api("/payouts", {
        method: "POST",
        token,
        // Blank amount means "the full settled balance" (ADR-012).
        body: {
          currency,
          amount: amount === "" ? null : Number(amount),
          destination,
        },
      });
      setReceipt(payout);
      setAmount("");
      setDestination("");
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="field-row">
        <label>
          Currency
          <select
            value={currency}
            onChange={(event) => setCurrency(event.target.value)}
          >
            {receivables.map((r) => (
              <option key={r.currency} value={r.currency}>
                {r.currency}
              </option>
            ))}
          </select>
        </label>
        <label>
          Amount (blank = full balance)
          <input
            type="number"
            min="0.01"
            step="0.01"
            max={available}
            placeholder={String(available)}
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </label>
      </div>
      <label>
        Destination
        <input
          required
          minLength={3}
          maxLength={255}
          placeholder="Bank account or wallet reference"
          value={destination}
          onChange={(event) => setDestination(event.target.value)}
        />
      </label>
      {error && <p className="error">{error}</p>}
      {receipt && (
        <p>
          Payout sent: {receipt.amount} {receipt.currency} — reference{" "}
          {receipt.provider_reference}.
        </p>
      )}
      <button type="submit" disabled={submitting}>
        {submitting ? "Sending…" : `Pay out ${currency}`}
      </button>
    </form>
  );
}

export default function PayoutsPage() {
  const { token } = useAuth();
  const [balances, setBalances] = useState(null);
  const [payouts, setPayouts] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    const [balanceData, payoutData] = await Promise.all([
      api("/ledger/balance", { token }),
      api("/payouts", { token }),
    ]);
    setBalances(balanceData);
    setPayouts(payoutData);
  }, [token]);

  useEffect(() => {
    let cancelled = false;
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

  if (error) {
    return (
      <main>
        <p className="error">{error}</p>
      </main>
    );
  }
  if (balances === null) {
    return (
      <main>
        <p>Loading…</p>
      </main>
    );
  }

  const receivables = balances.filter(
    (b) => b.account_type === "worker_receivable" && Number(b.balance) > 0,
  );
  const owed = balances.filter(
    (b) => b.account_type === "client_payable" && Number(b.balance) > 0,
  );

  return (
    <main>
      <h1>Earnings & payouts</h1>

      <section>
        <h2>Available to withdraw</h2>
        {receivables.length === 0 ? (
          <p>
            No earnings yet. Earnings appear here when a client approves
            one of your milestones.
          </p>
        ) : (
          <ul className="card-list">
            {receivables.map((b) => (
              <li key={b.currency} className="card">
                <h2>
                  {b.balance} {b.currency}
                </h2>
              </li>
            ))}
          </ul>
        )}
        {owed.length > 0 && (
          <>
            <h3>Outstanding payments you owe</h3>
            <ul className="card-list">
              {owed.map((b) => (
                <li key={b.currency} className="card">
                  <p className="meta">
                    {b.balance} {b.currency} — charged to your payment
                    method when a milestone is approved
                  </p>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      {receivables.length > 0 && (
        <section>
          <h2>Request a payout</h2>
          <PayoutForm receivables={receivables} onDone={reload} />
        </section>
      )}

      {payouts !== null && payouts.length > 0 && (
        <section>
          <h2>Payout history</h2>
          <ul className="card-list">
            {payouts.map((payout) => (
              <li key={payout.id} className="card">
                <h3>
                  {payout.amount} {payout.currency}{" "}
                  <span className="meta">— {payout.status}</span>
                </h3>
                <p className="meta">
                  To: {payout.destination}
                  {" · "}
                  {new Date(payout.created_at).toLocaleString()}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
