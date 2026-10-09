import { FEATURE_LABELS } from "../utils.js";

// details: optional { field: "message" } map from the backend's validation errors.
export default function ErrorMessage({ title = "Something went wrong", message, details, onRetry, retryLabel = "Try again" }) {
  const entries = details && typeof details === "object" ? Object.entries(details) : [];
  return (
    <div className="alert alert-error" role="alert">
      <strong>{title}</strong>
      {message && <p>{message}</p>}
      {entries.length > 0 && (
        <ul>
          {entries.map(([field, text]) => (
            <li key={field}>
              <span className="mono">{FEATURE_LABELS[field] || field}</span>: {String(text)}
            </li>
          ))}
        </ul>
      )}
      {onRetry && (
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          {retryLabel}
        </button>
      )}
    </div>
  );
}
