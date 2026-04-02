from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline

from .config import PolPredConfig
from .features import build_snapshot_feature_row


class PolPredModel:
    def __init__(self, config: PolPredConfig | None = None) -> None:
        self.config = config or PolPredConfig()
        self.models_: dict[str, Pipeline] = {}
        self.feature_columns_: list[str] = []

    def _prepare_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        cfg = self.config
        required = {
            cfg.timestamp_col,
            cfg.station_id_col,
            cfg.latitude_col,
            cfg.longitude_col,
            *cfg.pollutant_columns,
        }
        missing = sorted(col for col in required if col not in frame.columns)
        if missing:
            raise ValueError(f"Training frame is missing required columns: {missing}")

        df = frame.copy()
        df[cfg.timestamp_col] = pd.to_datetime(df[cfg.timestamp_col], utc=True).dt.tz_localize(None)

        numeric_cols = [cfg.latitude_col, cfg.longitude_col, *cfg.value_columns]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=[cfg.timestamp_col, cfg.station_id_col, cfg.latitude_col, cfg.longitude_col])
        df = df.sort_values([cfg.timestamp_col, cfg.station_id_col]).drop_duplicates(
            subset=[cfg.timestamp_col, cfg.station_id_col],
            keep="last",
        )
        return df.reset_index(drop=True)

    def _prepare_station_state(self, station_state: pd.DataFrame | list[dict[str, object]]) -> pd.DataFrame:
        cfg = self.config
        frame = pd.DataFrame(station_state).copy() if not isinstance(station_state, pd.DataFrame) else station_state.copy()
        if cfg.latitude_col not in frame.columns or cfg.longitude_col not in frame.columns:
            raise ValueError(
                f"station_state must include '{cfg.latitude_col}' and '{cfg.longitude_col}' columns."
            )
        for col in [cfg.latitude_col, cfg.longitude_col, *cfg.value_columns]:
            if col in frame.columns:
                frame[col] = pd.to_numeric(frame[col], errors="coerce")
        return frame

    def build_training_samples(self, frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        cfg = self.config
        df = self._prepare_frame(frame)

        rows: list[dict[str, float | pd.Timestamp | str]] = []
        labels: list[dict[str, float]] = []
        sample_index: list[tuple[pd.Timestamp, str]] = []

        for timestamp, group in df.groupby(cfg.timestamp_col, sort=True):
            if len(group) < 2:
                continue
            records = group.to_dict("records")
            for target in records:
                neighbors = group[group[cfg.station_id_col] != target[cfg.station_id_col]]
                if neighbors.empty:
                    continue

                feature_row = build_snapshot_feature_row(
                    target_lat=float(target[cfg.latitude_col]),
                    target_lon=float(target[cfg.longitude_col]),
                    station_state=neighbors,
                    value_columns=cfg.value_columns,
                    latitude_col=cfg.latitude_col,
                    longitude_col=cfg.longitude_col,
                    distance_exponents=cfg.distance_exponents,
                    nearest_station_count=cfg.nearest_station_count,
                    timestamp=timestamp,
                )
                rows.append(feature_row)
                labels.append({pollutant: target.get(pollutant, np.nan) for pollutant in cfg.pollutant_columns})
                sample_index.append((pd.Timestamp(timestamp), str(target[cfg.station_id_col])))

        if not rows:
            raise ValueError("No usable training samples could be built from the provided frame.")

        index = pd.MultiIndex.from_tuples(sample_index, names=[cfg.timestamp_col, cfg.station_id_col])
        X = pd.DataFrame(rows, index=index)
        y = pd.DataFrame(labels, index=index)
        return X, y

    def _make_estimator(self) -> Pipeline:
        regressor = HistGradientBoostingRegressor(**self.config.model_params)
        return Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("regressor", regressor),
            ]
        )

    def fit(self, frame: pd.DataFrame) -> "PolPredModel":
        X, y = self.build_training_samples(frame)
        usable_cols = [col for col in X.columns if not X[col].isna().all()]
        if not usable_cols:
            raise ValueError("All engineered feature columns are empty.")

        self.feature_columns_ = usable_cols
        self.models_ = {}
        X_fit = X[self.feature_columns_]

        for pollutant in self.config.pollutant_columns:
            mask = y[pollutant].notna()
            if int(mask.sum()) == 0:
                continue
            model = self._make_estimator()
            model.fit(X_fit.loc[mask], y.loc[mask, pollutant])
            self.models_[pollutant] = model

        if not self.models_:
            raise ValueError("No pollutant model could be trained from the provided frame.")
        return self

    def predict_at(
        self,
        latitude: float,
        longitude: float,
        station_state: pd.DataFrame | list[dict[str, object]],
        timestamp: str | pd.Timestamp | None = None,
    ) -> dict[str, float]:
        if not self.models_:
            raise RuntimeError("The model is not fitted yet.")

        cfg = self.config
        prepared_state = self._prepare_station_state(station_state)
        feature_row = build_snapshot_feature_row(
            target_lat=float(latitude),
            target_lon=float(longitude),
            station_state=prepared_state,
            value_columns=cfg.value_columns,
            latitude_col=cfg.latitude_col,
            longitude_col=cfg.longitude_col,
            distance_exponents=cfg.distance_exponents,
            nearest_station_count=cfg.nearest_station_count,
            timestamp=pd.Timestamp(timestamp) if timestamp is not None else None,
        )
        X = pd.DataFrame([feature_row]).reindex(columns=self.feature_columns_)
        return {pollutant: float(model.predict(X)[0]) for pollutant, model in self.models_.items()}

    def predict_many(
        self,
        targets: pd.DataFrame | list[dict[str, object]],
        station_state: pd.DataFrame | list[dict[str, object]],
    ) -> pd.DataFrame:
        target_df = pd.DataFrame(targets).copy() if not isinstance(targets, pd.DataFrame) else targets.copy()
        cfg = self.config
        required = {cfg.latitude_col, cfg.longitude_col}
        missing = sorted(col for col in required if col not in target_df.columns)
        if missing:
            raise ValueError(f"targets is missing required columns: {missing}")

        rows: list[dict[str, object]] = []
        for row in target_df.to_dict("records"):
            pred = self.predict_at(
                latitude=float(row[cfg.latitude_col]),
                longitude=float(row[cfg.longitude_col]),
                station_state=station_state,
                timestamp=row.get(cfg.timestamp_col),
            )
            out_row = dict(row)
            out_row.update(pred)
            rows.append(out_row)
        return pd.DataFrame(rows)

    def evaluate_holdout(
        self,
        frame: pd.DataFrame,
        holdout_steps: int = 30,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        cfg = self.config
        df = self._prepare_frame(frame)
        timestamps = sorted(df[cfg.timestamp_col].unique())
        if holdout_steps <= 0 or len(timestamps) <= holdout_steps:
            raise ValueError("holdout_steps must be smaller than the number of unique timestamps.")

        cutoff = timestamps[-holdout_steps]
        train_df = df[df[cfg.timestamp_col] < cutoff].copy()
        test_df = df[df[cfg.timestamp_col] >= cutoff].copy()
        if train_df.empty or test_df.empty:
            raise ValueError("Chronological split produced an empty train or test partition.")

        probe = PolPredModel(config=self.config)
        probe.fit(train_df)

        prediction_rows: list[dict[str, object]] = []
        for timestamp, group in test_df.groupby(cfg.timestamp_col, sort=True):
            if len(group) < 2:
                continue
            for target in group.to_dict("records"):
                neighbors = group[group[cfg.station_id_col] != target[cfg.station_id_col]]
                if neighbors.empty:
                    continue
                pred = probe.predict_at(
                    latitude=float(target[cfg.latitude_col]),
                    longitude=float(target[cfg.longitude_col]),
                    station_state=neighbors,
                    timestamp=timestamp,
                )
                for pollutant, predicted_value in pred.items():
                    actual_value = target.get(pollutant)
                    if pd.isna(actual_value):
                        continue
                    prediction_rows.append(
                        {
                            "timestamp": pd.Timestamp(timestamp),
                            "station_id": str(target[cfg.station_id_col]),
                            "pollutant": pollutant,
                            "actual": float(actual_value),
                            "pred": float(predicted_value),
                        }
                    )

        predictions = pd.DataFrame(prediction_rows)
        if predictions.empty:
            raise ValueError("No hold-out predictions could be computed.")

        metrics_rows: list[dict[str, object]] = []
        for (station_id, pollutant), sub in predictions.groupby(["station_id", "pollutant"], sort=True):
            metrics_rows.append(_metric_row(station_id, pollutant, sub["actual"], sub["pred"]))
        for pollutant, sub in predictions.groupby("pollutant", sort=True):
            metrics_rows.append(_metric_row("__all__", pollutant, sub["actual"], sub["pred"]))

        metrics = pd.DataFrame(metrics_rows).sort_values(["pollutant", "station_id"]).reset_index(drop=True)
        return metrics, predictions

    def save(self, path: str | Path) -> Path:
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("wb") as handle:
            pickle.dump(self, handle)
        return out_path

    @classmethod
    def load(cls, path: str | Path) -> "PolPredModel":
        with Path(path).open("rb") as handle:
            obj = pickle.load(handle)
        if not isinstance(obj, cls):
            raise TypeError(f"Serialized object at {path} is not a {cls.__name__}.")
        return obj


def _metric_row(station_id: str, pollutant: str, actual: pd.Series, pred: pd.Series) -> dict[str, object]:
    actual_arr = actual.to_numpy(dtype=float)
    pred_arr = pred.to_numpy(dtype=float)
    try:
        r2 = float(r2_score(actual_arr, pred_arr)) if len(actual_arr) >= 2 else np.nan
    except ValueError:
        r2 = np.nan
    return {
        "station_id": station_id,
        "pollutant": pollutant,
        "count": int(len(actual_arr)),
        "mae": float(mean_absolute_error(actual_arr, pred_arr)),
        "rmse": float(np.sqrt(mean_squared_error(actual_arr, pred_arr))),
        "r2": r2,
    }
