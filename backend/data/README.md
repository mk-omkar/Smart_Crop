# Data folder

## Required (you must supply): `Crop_recommendation.csv`

The soil-informed model is trained on the **Crop Recommendation Dataset**:
https://www.kaggle.com/datasets/atharvaingle/crop-recommendation-dataset

This repository does **not** include the CSV (its licence/redistribution terms are set by
the dataset author on Kaggle, so please download it yourself and check them).

1. Sign in to Kaggle (free) and open the link above.
2. Click **Download** and unzip the archive.
3. Copy `Crop_recommendation.csv` into **this folder** (`backend/data/`).

Expected columns: `N, P, K, temperature, humidity, ph, rainfall, label`

The widely used version has about 2,200 rows and 22 crops, but `train_model.py` reads the
real file and prints the actual row count and crop labels, so nothing is assumed.

Notes about the dataset:
- N, P, K are on the dataset's own scale (not specified lab units like ppm or kg/ha).
- `rainfall` is in mm; the dataset does not state the averaging period.
- Its reported accuracy is often very high; this reflects the dataset's well-separated
  classes, not guaranteed real-farm performance.

## Included: `crop_rules.json`

Illustrative crop requirement ranges used by the **weather-only rule-based** mode. This is
not derived from the Kaggle dataset. Edit it to match local agricultural guidance.
Each crop has `min / optimal_min / optimal_max / max` ranges for temperature (°C),
humidity (%) and rainfall (mm/month), plus sowing seasons.
