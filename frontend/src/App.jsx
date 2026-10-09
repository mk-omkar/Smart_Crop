import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Navbar from "./components/Navbar.jsx";
import LocationPicker from "./components/LocationPicker.jsx";
import WeatherCard from "./components/WeatherCard.jsx";
import SoilForm from "./components/SoilForm.jsx";
import RecommendationResults from "./components/RecommendationResults.jsx";
import { getWeather, recommendSoil, recommendWeather } from "./api.js";

const IDLE = { status: "idle", data: null, error: null };

// Pre-fill the form from weather data without inventing anything: empty if unavailable.
function deriveDefaults(weather) {
  const climate = weather && weather.climate;
  const current = weather && weather.current;
  const defaults = { temperature: "", humidity: "", rainfall: "", sources: {} };

  if (climate && climate.mean_temperature_c != null) {
    defaults.temperature = climate.mean_temperature_c;
    defaults.sources.temperature = "Average over the past ~12 months";
  } else if (current && current.temperature_c != null) {
    defaults.temperature = current.temperature_c;
    defaults.sources.temperature = "Current reading (a snapshot, not a seasonal average)";
  }
  if (climate && climate.mean_relative_humidity_pct != null) {
    defaults.humidity = climate.mean_relative_humidity_pct;
    defaults.sources.humidity = "Average over the past ~12 months";
  } else if (current && current.relative_humidity_pct != null) {
    defaults.humidity = current.relative_humidity_pct;
    defaults.sources.humidity = "Current reading (a snapshot, not a seasonal average)";
  }
  if (climate && climate.average_monthly_rainfall_mm != null) {
    defaults.rainfall = climate.average_monthly_rainfall_mm;
    defaults.sources.rainfall = "Average monthly rainfall over the past ~12 months";
  } else {
    defaults.sources.rainfall = "Not available automatically; enter it if you know it";
  }
  return defaults;
}

export default function App() {
  const [location, setLocation] = useState(null);
  const [weather, setWeather] = useState(IDLE);
  const [retryToken, setRetryToken] = useState(0);
  const [result, setResult] = useState({ ...IDLE, mode: null });
  const resultsRef = useRef(null);

  // Fetch weather once per location (or per manual retry). No polling, no loops.
  useEffect(() => {
    if (!location) return undefined;
    const controller = new AbortController();
    setWeather({ status: "loading", data: null, error: null });
    getWeather(location.latitude, location.longitude, controller.signal)
      .then((data) => setWeather({ status: "success", data, error: null }))
      .catch((error) => {
        if (controller.signal.aborted) return; // superseded by a newer request
        setWeather({ status: "error", data: null, error });
      });
    return () => controller.abort();
  }, [location, retryToken]);

  const handleLocation = useCallback((next) => {
    setLocation(next);
    setResult({ ...IDLE, mode: null });
  }, []);

  const retryWeather = useCallback(() => setRetryToken((n) => n + 1), []);

  const run = useCallback(async (mode, call, values) => {
    setResult({ status: "loading", data: null, error: null, mode });
    try {
      const data = await call(values);
      setResult({ status: "success", data, error: null, mode });
    } catch (error) {
      setResult({ status: "error", data: null, error, mode });
    }
  }, []);

  const submitSoil = useCallback((values) => run("soil", recommendSoil, values), [run]);
  const submitWeather = useCallback((values) => run("weather", recommendWeather, values), [run]);

  const resetResult = useCallback(() => {
    setResult({ ...IDLE, mode: null });
    const soil = document.getElementById("soil");
    if (soil) soil.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  // Bring the answer into view once it appears.
  useEffect(() => {
    if (result.status !== "idle" && resultsRef.current) {
      resultsRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [result.status]);

  const defaults = useMemo(() => deriveDefaults(weather.data), [weather.data]);

  return (
    <>
      <Navbar />
      <main>
        <section id="home" className="hero">
          <div className="container hero-grid">
            <div className="hero-text">
              <span className="badge badge-sdg">SDG 2 · Zero Hunger</span>
              <h1>Smart Crop Advisor</h1>
              <p className="lead">
                Find crops that may suit your land. Share your location to get local weather, add your
                soil test values if you have them, and get preliminary crop suggestions. Everything
                is explained, nothing is guessed.
              </p>
            </div>
            <LocationPicker location={location} onLocationChange={handleLocation} />
          </div>
        </section>

        <div className="container stack">
          {location && <WeatherCard state={weather} onRetry={retryWeather} />}

          {location && weather.status === "success" && (
            <SoilForm
              defaults={defaults}
              onSubmitSoil={submitSoil}
              onSubmitWeather={submitWeather}
              busy={result.status === "loading"}
            />
          )}

          {location && weather.status === "error" && (
            <div className="alert alert-info" role="note">
              Recommendations need weather values. Retry the weather request above, or choose a
              different location.
            </div>
          )}

          <div ref={resultsRef}>
            <RecommendationResults state={result} onReset={resetResult} />
          </div>

          <section id="about" className="card about" aria-labelledby="about-heading">
            <h2 id="about-heading">About this project</h2>
            <h3>Objective</h3>
            <p>
              Smart Crop Advisor helps farmers explore which crops may suit their local conditions,
              using free weather data and, where available, soil test results.
            </p>
            <h3>AI / ML methodology</h3>
            <ul>
              <li>
                <strong>With a soil report:</strong> a Random Forest classifier, trained on the public
                Crop Recommendation Dataset (N, P, K, temperature, humidity, pH, rainfall), suggests
                crops. Its scores are model vote shares, not guarantees.
              </li>
              <li>
                <strong>Without a soil report:</strong> a separate, transparent rule-based method
                ranks crops by how well the weather fits each crop's requirement ranges. It is not a
                trained ML model, and soil values are never invented to fit the classifier.
              </li>
              <li>
                <strong>Weather</strong> comes from Open-Meteo: current conditions, a short forecast,
                and a historical average, each labelled separately.
              </li>
            </ul>
            <h3>SDG 2 — Zero Hunger</h3>
            <p>
              Better-informed crop choices can support productivity and food security for smallholder
              farmers. This tool is a learning project and a starting point for a conversation with
              local agricultural experts. It does not replace them.
            </p>
          </section>
        </div>
      </main>
      <footer className="footer">
        <div className="container">
          <p>Weather data by Open-Meteo.com. Recommendations are preliminary; verify with local agricultural guidance.</p>
        </div>
      </footer>
    </>
  );
}
