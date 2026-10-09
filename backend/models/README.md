# Models folder

`crop_model.joblib` and `crop_model_metadata.json` are **generated** by:

```
python train_model.py
```

They are created from `data/Crop_recommendation.csv`, are git-ignored, and are not shipped
with the source. Until you train, `GET /api/health` reports `"model_loaded": false` and
`POST /api/recommend` returns HTTP 503 with a message explaining what to do.

The joblib file is a dict holding the fitted `RandomForestClassifier`, the feature names and
order (`N, P, K, temperature, humidity, ph, rainfall`), per-feature training ranges, per-crop
typical conditions, the measured test metrics and the scikit-learn version used. The JSON
file is a readable copy of everything except the model, plus the classification report.

Re-train if you upgrade scikit-learn and see a "could not be loaded" message.
