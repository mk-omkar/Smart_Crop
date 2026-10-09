import { useState } from "react";
import { FEATURE_LABELS, LIMITS } from "../utils.js";

const SEASONS = [
  ["any", "Not sure / any season"],
  ["kharif", "Kharif (monsoon, about Jun–Oct)"],
  ["rabi", "Rabi (winter, about Nov–Mar)"],
  ["zaid", "Zaid (summer, about Mar–Jun)"],
];

const asText = (v) => (v === undefined || v === null ? "" : String(v));

// Defined at module level so inputs keep focus while typing.
function Field({ id, label, unit, hint, error, value, onChange, required }) {
  const hintId = `${id}-hint`;
  const errId = `${id}-err`;
  return (
    <div className={`field ${error ? "has-error" : ""}`}>
      <label htmlFor={id}>
        {label}
        {unit ? <span className="unit"> ({unit})</span> : null}
        {required ? <span aria-hidden="true" className="req"> *</span> : null}
      </label>
      <input
        id={id}
        type="number"
        step="any"
        inputMode="decimal"
        value={value}
        onChange={onChange}
        required={required}
        aria-invalid={error ? "true" : "false"}
        aria-describedby={[hint ? hintId : null, error ? errId : null].filter(Boolean).join(" ") || undefined}
      />
      {hint && <small id={hintId} className="muted">{hint}</small>}
      {error && <small id={errId} className="field-error" role="alert">{error}</small>}
    </div>
  );
}

// defaults: { temperature, humidity, rainfall, sources: {temperature, humidity, rainfall} }
export default function SoilForm({ defaults, onSubmitSoil, onSubmitWeather, busy }) {
  const [hasReport, setHasReport] = useState(null); // null | "yes" | "no"
  const [values, setValues] = useState({
    N: "", P: "", K: "", ph: "",
    temperature: asText(defaults.temperature),
    humidity: asText(defaults.humidity),
    rainfall: asText(defaults.rainfall),
    season: "any",
  });
  const [errors, setErrors] = useState({});

  const change = (name) => (event) => setValues((v) => ({ ...v, [name]: event.target.value }));

  // Returns true when valid; otherwise stores per-field messages for display.
  function validate(required) {
    const found = {};
    Object.keys(LIMITS).forEach((name) => {
      const raw = String(values[name]).trim();
      const label = FEATURE_LABELS[name];
      if (raw === "") {
        if (required.includes(name)) found[name] = `${label} is required.`;
        return;
      }
      const number = Number(raw);
      const { min, max, unit } = LIMITS[name];
      if (!Number.isFinite(number)) found[name] = `${label} must be a number.`;
      else if (number < min || number > max) {
        found[name] = `${label} must be between ${min} and ${max}${unit ? ` ${unit}` : ""}.`;
      }
    });
    setErrors(found);
    return Object.keys(found).length === 0;
  }

  function submitSoil(event) {
    event.preventDefault();
    const names = ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"];
    if (!validate(names)) return;
    const payload = {};
    names.forEach((n) => { payload[n] = Number(values[n]); });
    onSubmitSoil(payload);
  }

  function submitWeather(event) {
    event.preventDefault();
    if (!validate(["temperature"])) return;
    const payload = { season: values.season };
    ["temperature", "humidity", "rainfall"].forEach((n) => {
      if (String(values[n]).trim() !== "") payload[n] = Number(values[n]);
    });
    onSubmitWeather(payload);
  }

  const sources = defaults.sources || {};

  const weatherFields = (
    <fieldset className="fieldset">
      <legend>Weather inputs</legend>
      <p className="muted small">
        Pre-filled from your location where available. Edit them if you know your growing-season
        conditions better.
      </p>
      <div className="form-row three">
        <Field id="temperature" label={FEATURE_LABELS.temperature} unit="°C" value={values.temperature}
          onChange={change("temperature")} error={errors.temperature} hint={sources.temperature} required />
        <Field id="humidity" label={FEATURE_LABELS.humidity} unit="%" value={values.humidity}
          onChange={change("humidity")} error={errors.humidity} hint={sources.humidity}
          required={hasReport === "yes"} />
        <Field id="rainfall" label="Average monthly rainfall" unit="mm" value={values.rainfall}
          onChange={change("rainfall")} error={errors.rainfall} hint={sources.rainfall}
          required={hasReport === "yes"} />
      </div>
    </fieldset>
  );

  return (
    <section id="soil" className="card" aria-labelledby="soil-heading">
      <h2 id="soil-heading">Soil details</h2>

      <fieldset className="fieldset choice">
        <legend>Do you have a soil test report?</legend>
        <label className={`choice-card ${hasReport === "yes" ? "selected" : ""}`}>
          <input type="radio" name="report" value="yes" checked={hasReport === "yes"}
            onChange={() => { setHasReport("yes"); setErrors({}); }} />
          <span><strong>Yes, I have one</strong><br /><span className="muted small">Uses the machine-learning model with N, P, K and pH.</span></span>
        </label>
        <label className={`choice-card ${hasReport === "no" ? "selected" : ""}`}>
          <input type="radio" name="report" value="no" checked={hasReport === "no"}
            onChange={() => { setHasReport("no"); setErrors({}); }} />
          <span><strong>No, skip soil details</strong><br /><span className="muted small">Gives preliminary, rule-based suggestions from weather only.</span></span>
        </label>
      </fieldset>

      {hasReport === null && <p className="empty">Choose an option above to continue.</p>}

      {hasReport === "yes" && (
        <form onSubmit={submitSoil} noValidate aria-label="Soil-informed recommendation">
          <div className="alert alert-info">
            <strong>Where to find these values</strong>
            <p>
              Look for the table of nutrient results on your soil test report or Soil Health Card:
              “Available Nitrogen (N)”, “Phosphorus (P)”, “Potassium (K)” and “pH”. Do not guess
              values. Units differ between labs (for example kg/ha, ppm or mg/kg) and the model was
              trained on its own dataset scale, so you will be warned when a value falls outside
              what the model has seen.
            </p>
          </div>
          <fieldset className="fieldset">
            <legend>Soil test values</legend>
            <div className="form-row four">
              <Field id="N" label={FEATURE_LABELS.N} value={values.N} onChange={change("N")} error={errors.N} required />
              <Field id="P" label={FEATURE_LABELS.P} value={values.P} onChange={change("P")} error={errors.P} required />
              <Field id="K" label={FEATURE_LABELS.K} value={values.K} onChange={change("K")} error={errors.K} required />
              <Field id="ph" label={FEATURE_LABELS.ph} hint="0 to 14" value={values.ph} onChange={change("ph")} error={errors.ph} required />
            </div>
          </fieldset>
          {weatherFields}
          <button type="submit" className="btn btn-primary" disabled={busy}>
            Get soil-informed recommendation
          </button>
        </form>
      )}

      {hasReport === "no" && (
        <form onSubmit={submitWeather} noValidate aria-label="Weather-based preliminary recommendation">
          <div className="alert alert-warn">
            <strong>Preliminary suggestions only</strong>
            <p>
              Without soil values we do not guess them. This mode uses a transparent rule table of
              crop climate requirements, not the trained model, so results are less reliable. A soil
              test is recommended.
            </p>
          </div>
          {weatherFields}
          <div className="field">
            <label htmlFor="season">Sowing season (optional)</label>
            <select id="season" value={values.season} onChange={change("season")}>
              {SEASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <small className="muted">Seasons follow the Indian kharif / rabi / zaid convention.</small>
          </div>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            Get preliminary suggestions
          </button>
        </form>
      )}
    </section>
  );
}
