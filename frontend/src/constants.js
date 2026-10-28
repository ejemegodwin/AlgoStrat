// Mirrors SUPPORTED_CURRENCIES on the backend (ADR in schemas.py).
// The API remains the validator of record — this list only shapes the
// <select>; if the backend extends its allowlist the API still
// accepts values this list predates.
export const SUPPORTED_CURRENCIES = [
  "USD", "EUR", "GBP", "CAD", "AUD", "NZD", "CHF",
  "JPY", "CNY", "HKD", "SGD", "INR",
  "AED", "SAR",
  "NGN", "GHS", "KES", "ZAR", "EGP",
  "BRL", "MXN",
  "SEK", "NOK", "DKK",
  "PHP", "IDR",
];
