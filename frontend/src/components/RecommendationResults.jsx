import ErrorMessage from "./ErrorMessage.jsx";
import LoadingState from "./LoadingState.jsx";
import { FEATURE_LABELS, cropName, formatValue, percent } from "../utils.js";

// state: { status: "idle" | "loading" | "success" | "error", mode, data, error }
export default function RecommendationResults({ state, onReset }) {
  if (state.status === "idle") return null;

  return (
    <section id="results" className="card results" aria-labelledby="results-heading" aria-live="polite">
      <h2 id="results-heading">Recommendation</h2>

      {state.status === "loading" && <LoadingState message="Working out suitable crops…" />}

      {state.status === "error" && (
        <>
          <ErrorMessage
            title="Could not get a recommendation"
            message={state.error && state.error.message}
            details={state.error && state.error.details}
          />
          <button type="button" className="btn btn-secondary" onClick={onReset}>
            Change inputs and try again
          </button>
        </>
      )}

      {state.status === "success" && state.data && (
        <>
          {state.data.mode === "soil" ? <SoilResult data={state.data} /> : <WeatherResult data={state.data} />}
          <div className="alert alert-info disclaimer" role="note">
            <strong>Disclaimer</strong>
            <p>{state.data.disclaimer}</p>
          </div>
          <button type="button" className="btn btn-secondary" onClick={onReset}>
            Try again with different inputs
          </button>
        </>
      )}
    </section>
  );
}

function MethodBadge({ type, text }) {
  const isML = type === "machine_learning";
  return (
    <div className={`method ${isML ? "method-ml" : "method-rules"}`}>
      <span className="badge">{isML ? "Machine-learning model" : "Rule-based · preliminary"}</span>
      <p className="small">{text}</p>
    </div>
  );
}

function SoilResult({ data }) {
  const { top_predictions: top = [], inputs = {}, typical_conditions: typical, warnings = [], model_info: info = {} } = data;
  return (
    <>
      <MethodBadge type={data.method_type} text={data.method} />

      <div className="top-crop">
        <span className="muted small">Best match from the model</span>
        <p className="crop-name">{cropName(data.predicted_crop)}</p>
      </div>

      {warnings.length > 0 && (
        <div className="alert alert-warn" role="status">
          <strong>Check your inputs</strong>
          <ul>{warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </div>
      )}

      <h3>Top model matches</h3>
      <ul className="bars">
        {top.map((item) => (
          <li key={item.crop}>
            <span className="bar-label">{cropName(item.crop)}</span>
            <span className="bar-track" aria-hidden="true">
              <span className="bar-fill" style={{ width: percent(item.score) }} />
            </span>
            <span className="bar-value">{percent(item.score)}</span>
          </li>
        ))}
      </ul>
      <p className="muted small">{data.confidence_note}</p>

      <h3>Inputs used</h3>
      <dl className="kv">
        {Object.entries(inputs).map(([name, item]) => (
          <div key={name}>
            <dt>{FEATURE_LABELS[name] || name}</dt>
            <dd>{formatValue(item.value, item.unit === "dataset scale" || item.unit === "pH" ? "" : item.unit)}</dd>
          </div>
        ))}
      </dl>

      {typical && (
        <>
          <h3>Typical conditions for {cropName(data.predicted_crop)} in the training data</h3>
          <dl className="kv">
            {Object.entries(typical).map(([name, range]) => (
              <div key={name}>
                <dt>{FEATURE_LABELS[name] || name}</dt>
                <dd>{range[0]} – {range[1]}</dd>
              </div>
            ))}
          </dl>
          <p className="muted small">{data.typical_conditions_note}</p>
        </>
      )}

      {info.held_out_test_accuracy !== null && info.held_out_test_accuracy !== undefined && (
        <p className="muted small">
          Model trained on {info.training_rows} rows; measured accuracy on its held-out test split:{" "}
          {percent(info.held_out_test_accuracy)}. {info.evaluation_note}
        </p>
      )}
    </>
  );
}

function WeatherResult({ data }) {
  const recs = data.recommendations || [];
  const warnings = data.missing_data_warnings || [];
  return (
    <>
      <MethodBadge type={data.method_type} text={data.method} />

      {recs.length === 0 ? (
        <p className="empty">No crop in the rule table fits these conditions well.</p>
      ) : (
        <ol className="rec-list">
          {recs.map((rec) => (
            <li key={rec.crop} className="rec-item">
              <div className="rec-head">
                <h3>{rec.display_name}</h3>
                <span className={`badge ${rec.match_level === "good" ? "badge-good" : "badge-fair"}`}>
                  {rec.match_level === "good" ? "Good fit" : "Fair fit"} · {percent(rec.score)}
                </span>
              </div>
              <ul className="chips">
                {rec.factors.map((f) => (
                  <li key={f.factor} className={`chip chip-${f.status}`}>
                    {FEATURE_LABELS[f.factor]}: {f.value} {f.unit} — {f.status} (ideal {f.optimal_range[0]}–{f.optimal_range[1]})
                  </li>
                ))}
              </ul>
              <p className="small">
                <strong>Sowing seasons:</strong> {rec.seasons.join(", ")}.
                {rec.notes ? ` ${rec.notes}` : ""}
              </p>
            </li>
          ))}
        </ol>
      )}

      <div className="alert alert-warn" role="status">
        <strong>Missing information</strong>
        <ul>{warnings.map((w) => <li key={w}>{w}</li>)}</ul>
      </div>

      <div className="alert alert-info">
        <strong>Get a soil test</strong>
        <p>{data.soil_test_recommendation}</p>
      </div>

      <details>
        <summary>Limitations of this method</summary>
        <ul>{(data.limitations || []).map((l) => <li key={l}>{l}</li>)}</ul>
        {data.rules_info && data.rules_info.disclaimer && <p className="muted small">{data.rules_info.disclaimer}</p>}
      </details>
    </>
  );
}
