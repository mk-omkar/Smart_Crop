import ErrorMessage from "./ErrorMessage.jsx";
import LoadingState from "./LoadingState.jsx";
import { formatDay, formatValue } from "../utils.js";

// state: { status: "idle" | "loading" | "success" | "error", data, error }
export default function WeatherCard({ state, onRetry }) {
  return (
    <section id="weather" className="card" aria-labelledby="weather-heading">
      <h2 id="weather-heading">Weather for your location</h2>

      {state.status === "idle" && <p className="empty">Set your location above to see the weather.</p>}
      {state.status === "loading" && <LoadingState message="Fetching weather from Open-Meteo…" />}
      {state.status === "error" && (
        <ErrorMessage
          title="Weather unavailable"
          message={state.error && state.error.message}
          onRetry={onRetry}
          retryLabel="Retry weather request"
        />
      )}
      {state.status === "success" && state.data && <WeatherDetails data={state.data} />}
    </section>
  );
}

function Tile({ icon, label, value, note }) {
  return (
    <div className="tile">
      <span className="tile-icon" aria-hidden="true">{icon}</span>
      <span className="tile-label">{label}</span>
      <span className="tile-value">{value}</span>
      {note && <span className="tile-note">{note}</span>}
    </div>
  );
}

function WeatherDetails({ data }) {
  const { current, forecast, climate, climate_error: climateError } = data;
  const days = (forecast && forecast.days) || [];

  return (
    <>
      <div className="subsection">
        <h3>Current conditions</h3>
        <p className="muted small">{current.label}{data.timezone ? ` · timezone ${data.timezone}` : ""}</p>
        <div className="tiles">
          <Tile icon="🌡️" label="Temperature" value={formatValue(current.temperature_c, "°C")} />
          <Tile icon="💧" label="Relative humidity" value={formatValue(current.relative_humidity_pct, "%")} />
          <Tile icon="🌧️" label="Precipitation (last hour)" value={formatValue(current.precipitation_mm, "mm")} note="Not seasonal rainfall" />
        </div>
      </div>

      <div className="subsection">
        <h3>Upcoming forecast</h3>
        <p className="muted small">{forecast.label}</p>
        {days.length === 0 ? (
          <p className="empty">No forecast data was returned.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Day</th>
                  <th scope="col">Min / max</th>
                  <th scope="col">Mean</th>
                  <th scope="col">Rain</th>
                </tr>
              </thead>
              <tbody>
                {days.map((d) => (
                  <tr key={d.date}>
                    <th scope="row">{formatDay(d.date)}</th>
                    <td>{formatValue(d.temperature_min_c)} / {formatValue(d.temperature_max_c, "°C")}</td>
                    <td>{formatValue(d.temperature_mean_c, "°C")}</td>
                    <td>{formatValue(d.precipitation_sum_mm, "mm")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="subsection">
        <h3>Historical average</h3>
        {climate ? (
          <>
            <p className="muted small">
              {climate.label} · {climate.period_start} to {climate.period_end}
            </p>
            <div className="tiles">
              <Tile icon="🌡️" label="Mean temperature" value={formatValue(climate.mean_temperature_c, "°C")} />
              <Tile icon="💧" label="Mean humidity" value={formatValue(climate.mean_relative_humidity_pct, "%")} />
              <Tile icon="🌧️" label="Average monthly rainfall" value={formatValue(climate.average_monthly_rainfall_mm, "mm")} note={`≈ ${formatValue(climate.total_rainfall_mm, "mm")} over the period`} />
            </div>
            <p className="muted small">{climate.note}</p>
          </>
        ) : (
          <div className="alert alert-warn" role="status">
            Historical climate data is unavailable{climateError ? `: ${climateError}` : "."} You can still
            enter temperature, humidity and rainfall yourself in the next step.
          </div>
        )}
      </div>
    </>
  );
}
