import { useState } from "react";
import { searchPlaces } from "../api.js";
import ErrorMessage from "./ErrorMessage.jsx";
import LoadingState from "./LoadingState.jsx";

const GEO_MESSAGES = {
  1: "Location permission was denied. You can allow it in your browser's site settings (location also needs localhost or HTTPS), or enter your location manually below.",
  2: "Your device could not determine its location. Try again, or enter your location manually below.",
  3: "Finding your location took too long. Try again, or enter your location manually below.",
};

const SOURCE_LABELS = {
  gps: "Detected with your browser's location (GPS/network)",
  manual: "Entered manually as coordinates",
  place: "Chosen from a place search",
};

function placeLabel(p) {
  return [p.name, p.admin3, p.admin2, p.admin1, p.country].filter(Boolean).join(", ");
}

// `location` is { latitude, longitude, source, label? } or null. Nothing is stored or sent
// anywhere except to our backend for the weather lookup.
export default function LocationPicker({ location, onLocationChange }) {
  const [geo, setGeo] = useState({ status: "idle", message: "" });
  const [showManual, setShowManual] = useState(false);
  const [coords, setCoords] = useState({ latitude: "", longitude: "" });
  const [coordErrors, setCoordErrors] = useState({});
  const [place, setPlace] = useState({ name: "", district: "", state: "" });
  const [search, setSearch] = useState({ status: "idle", results: [], error: null });

  function detect() {
    if (!("geolocation" in navigator)) {
      setGeo({
        status: "error",
        message: "This browser does not support location detection. Please enter your location manually.",
      });
      setShowManual(true);
      return;
    }
    setGeo({ status: "locating", message: "" });
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setGeo({ status: "idle", message: "" });
        onLocationChange({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          source: "gps",
        });
      },
      (error) => {
        setGeo({ status: "error", message: GEO_MESSAGES[error.code] || "Could not get your location." });
        setShowManual(true);
      },
      { enableHighAccuracy: false, timeout: 15000, maximumAge: 0 }
    );
  }

  function submitCoords(event) {
    event.preventDefault();
    const found = {};
    const lat = Number(coords.latitude);
    const lon = Number(coords.longitude);
    if (coords.latitude.trim() === "" || !Number.isFinite(lat) || lat < -90 || lat > 90) {
      found.latitude = "Latitude must be a number between -90 and 90.";
    }
    if (coords.longitude.trim() === "" || !Number.isFinite(lon) || lon < -180 || lon > 180) {
      found.longitude = "Longitude must be a number between -180 and 180.";
    }
    setCoordErrors(found);
    if (Object.keys(found).length === 0) {
      onLocationChange({ latitude: lat, longitude: lon, source: "manual" });
    }
  }

  async function submitPlace(event) {
    event.preventDefault();
    if (place.name.trim().length < 2) {
      setSearch({ status: "error", results: [], error: { message: "Enter at least 2 characters of the village, town or city name." } });
      return;
    }
    const region = [place.district, place.state].map((s) => s.trim()).filter(Boolean).join(",");
    setSearch({ status: "loading", results: [], error: null });
    try {
      const data = await searchPlaces(place.name.trim(), region);
      setSearch({ status: "success", results: data.results || [], error: null });
    } catch (error) {
      setSearch({ status: "error", results: [], error });
    }
  }

  function choosePlace(p) {
    onLocationChange({ latitude: p.latitude, longitude: p.longitude, source: "place", label: placeLabel(p) });
  }

  return (
    <section className="card location-card" aria-labelledby="location-heading">
      <h2 id="location-heading">Your location</h2>
      <p className="muted">
        We use your coordinates only to look up weather. They are not saved, and nothing is requested
        until you press the button.
      </p>

      <button type="button" className="btn btn-primary btn-large" onClick={detect} disabled={geo.status === "locating"}>
        <span aria-hidden="true">📍</span> Detect My Location
      </button>

      {geo.status === "locating" && <LoadingState message="Waiting for your browser's location…" />}
      {geo.status === "error" && <ErrorMessage title="Location not available" message={geo.message} />}

      {location && (
        <div className="location-summary" role="status">
          <strong>Location set</strong>
          <dl>
            <div><dt>Latitude</dt><dd>{location.latitude.toFixed(4)}°</dd></div>
            <div><dt>Longitude</dt><dd>{location.longitude.toFixed(4)}°</dd></div>
          </dl>
          <p className="muted small">
            {SOURCE_LABELS[location.source]}
            {location.label ? ` — ${location.label}` : ""}
          </p>
        </div>
      )}
      {!location && geo.status === "idle" && (
        <p className="empty">No location yet. Detect it above or enter it manually.</p>
      )}

      <button
        type="button"
        className="btn btn-link"
        aria-expanded={showManual}
        aria-controls="manual-location"
        onClick={() => setShowManual((v) => !v)}
      >
        {showManual ? "Hide manual location" : "Enter location manually instead"}
      </button>

      {showManual && (
        <div id="manual-location" className="manual">
          <form onSubmit={submitCoords} noValidate aria-label="Enter coordinates">
            <h3>Enter coordinates</h3>
            <div className="form-row">
              <div className={`field ${coordErrors.latitude ? "has-error" : ""}`}>
                <label htmlFor="lat">Latitude</label>
                <input
                  id="lat" type="number" step="any" inputMode="decimal" placeholder="e.g. 13.0827"
                  value={coords.latitude}
                  onChange={(e) => setCoords((c) => ({ ...c, latitude: e.target.value }))}
                  aria-invalid={coordErrors.latitude ? "true" : "false"}
                />
                {coordErrors.latitude && <small className="field-error" role="alert">{coordErrors.latitude}</small>}
              </div>
              <div className={`field ${coordErrors.longitude ? "has-error" : ""}`}>
                <label htmlFor="lon">Longitude</label>
                <input
                  id="lon" type="number" step="any" inputMode="decimal" placeholder="e.g. 80.2707"
                  value={coords.longitude}
                  onChange={(e) => setCoords((c) => ({ ...c, longitude: e.target.value }))}
                  aria-invalid={coordErrors.longitude ? "true" : "false"}
                />
                {coordErrors.longitude && <small className="field-error" role="alert">{coordErrors.longitude}</small>}
              </div>
            </div>
            <button type="submit" className="btn btn-secondary">Use these coordinates</button>
          </form>

          <form onSubmit={submitPlace} noValidate aria-label="Search for a place">
            <h3>Or search by place name</h3>
            <div className="form-row three">
              <div className="field">
                <label htmlFor="place-name">Village / town / city</label>
                <input id="place-name" type="text" value={place.name} placeholder="e.g. Hosur"
                  onChange={(e) => setPlace((p) => ({ ...p, name: e.target.value }))} />
              </div>
              <div className="field">
                <label htmlFor="place-district">District (optional)</label>
                <input id="place-district" type="text" value={place.district}
                  onChange={(e) => setPlace((p) => ({ ...p, district: e.target.value }))} />
              </div>
              <div className="field">
                <label htmlFor="place-state">State (optional)</label>
                <input id="place-state" type="text" value={place.state}
                  onChange={(e) => setPlace((p) => ({ ...p, state: e.target.value }))} />
              </div>
            </div>
            <button type="submit" className="btn btn-secondary" disabled={search.status === "loading"}>
              Search places
            </button>

            {search.status === "loading" && <LoadingState message="Searching places…" />}
            {search.status === "error" && (
              <ErrorMessage title="Place search failed" message={search.error && search.error.message} />
            )}
            {search.status === "success" && search.results.length === 0 && (
              <p className="empty">No places found. Try a different spelling, or remove the district/state.</p>
            )}
            {search.status === "success" && search.results.length > 0 && (
              <ul className="place-results" aria-label="Matching places">
                {search.results.map((p, i) => (
                  <li key={`${p.latitude}-${p.longitude}-${i}`}>
                    <button type="button" className="place-option" onClick={() => choosePlace(p)}>
                      <span>{placeLabel(p)}</span>
                      <span className="muted small">{p.latitude.toFixed(2)}, {p.longitude.toFixed(2)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </form>
        </div>
      )}
    </section>
  );
}
