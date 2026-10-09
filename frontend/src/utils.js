// Small shared helpers and constants for the UI.

const CROP_NAMES = {
  kidneybeans: "Kidney beans",
  pigeonpeas: "Pigeon peas",
  mothbeans: "Moth beans",
  mungbean: "Mung bean",
  blackgram: "Black gram",
};

export function cropName(key) {
  if (!key) return "";
  const k = String(key).toLowerCase();
  return CROP_NAMES[k] || k.charAt(0).toUpperCase() + k.slice(1);
}

export const FEATURE_LABELS = {
  N: "Nitrogen (N)",
  P: "Phosphorus (P)",
  K: "Potassium (K)",
  ph: "Soil pH",
  temperature: "Temperature",
  humidity: "Humidity",
  rainfall: "Rainfall",
  season: "Season",
};

// Mirrors the backend's validation limits so mistakes are caught before sending.
export const LIMITS = {
  N: { min: 0, max: 300, unit: "" },
  P: { min: 0, max: 300, unit: "" },
  K: { min: 0, max: 300, unit: "" },
  ph: { min: 0, max: 14, unit: "" },
  temperature: { min: -10, max: 55, unit: "°C" },
  humidity: { min: 0, max: 100, unit: "%" },
  rainfall: { min: 0, max: 1000, unit: "mm" },
};

export function formatValue(value, unit) {
  if (value === null || value === undefined || value === "") return "—";
  return unit ? `${value} ${unit}` : String(value);
}

export function formatDay(isoDate) {
  const date = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return date.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

export function percent(score) {
  return `${Math.round(score * 100)}%`;
}
