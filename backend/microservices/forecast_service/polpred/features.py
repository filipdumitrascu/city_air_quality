from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np
import pandas as pd


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _exp_suffix(value: float) -> str:
    return str(value).replace(".", "")


def _set_time_features(features: dict[str, float], timestamp: pd.Timestamp | None) -> None:
    if timestamp is None or pd.isna(timestamp):
        return

    ts = pd.Timestamp(timestamp)
    features["dayofyear_sin"] = float(np.sin(2.0 * np.pi * ts.dayofyear / 365.25))
    features["dayofyear_cos"] = float(np.cos(2.0 * np.pi * ts.dayofyear / 365.25))
    features["dayofweek_sin"] = float(np.sin(2.0 * np.pi * ts.dayofweek / 7.0))
    features["dayofweek_cos"] = float(np.cos(2.0 * np.pi * ts.dayofweek / 7.0))
    features["month_sin"] = float(np.sin(2.0 * np.pi * ts.month / 12.0))
    features["month_cos"] = float(np.cos(2.0 * np.pi * ts.month / 12.0))


def _empty_value_features(
    prefix: str,
    exponents: Iterable[float],
    nearest_station_count: int,
) -> dict[str, float]:
    out = {
        f"{prefix}_neighbor_mean": np.nan,
        f"{prefix}_neighbor_median": np.nan,
        f"{prefix}_neighbor_min": np.nan,
        f"{prefix}_neighbor_max": np.nan,
        f"{prefix}_neighbor_std": np.nan,
        f"{prefix}_neighbor_p90": np.nan,
    }
    for rank in range(1, nearest_station_count + 1):
        out[f"{prefix}_nearest{rank}_value"] = np.nan
        out[f"{prefix}_nearest{rank}_distance_km"] = np.nan
    for exp in exponents:
        suffix = _exp_suffix(exp)
        out[f"{prefix}_idw_mean_exp{suffix}"] = np.nan
        out[f"{prefix}_idw_sum_exp{suffix}"] = np.nan
        out[f"{prefix}_mostentita_max_exp{suffix}"] = np.nan
    return out


def build_snapshot_feature_row(
    target_lat: float,
    target_lon: float,
    station_state: pd.DataFrame,
    value_columns: Iterable[str],
    latitude_col: str = "lat",
    longitude_col: str = "lon",
    distance_exponents: Iterable[float] = (0.5, 1.0, 1.5),
    nearest_station_count: int = 3,
    timestamp: pd.Timestamp | None = None,
) -> dict[str, float]:
    if station_state.empty:
        raise ValueError("station_state must contain at least one station.")

    frame = station_state.copy()
    frame[latitude_col] = pd.to_numeric(frame[latitude_col], errors="coerce")
    frame[longitude_col] = pd.to_numeric(frame[longitude_col], errors="coerce")
    frame = frame.dropna(subset=[latitude_col, longitude_col]).reset_index(drop=True)
    if frame.empty:
        raise ValueError("station_state contains no valid coordinates.")

    distances = np.asarray(
        [haversine_km(target_lat, target_lon, lat, lon) for lat, lon in zip(frame[latitude_col], frame[longitude_col])],
        dtype=float,
    )

    features: dict[str, float] = {
        "target_lat": float(target_lat),
        "target_lon": float(target_lon),
        "station_count": float(len(frame)),
        "neighbor_distance_min_km": float(np.min(distances)),
        "neighbor_distance_max_km": float(np.max(distances)),
        "neighbor_distance_mean_km": float(np.mean(distances)),
        "neighbor_distance_std_km": float(np.std(distances)) if len(distances) > 1 else 0.0,
    }
    _set_time_features(features, timestamp)

    exponents = tuple(distance_exponents)
    for value_col in value_columns:
        if value_col not in frame.columns:
            features.update(_empty_value_features(value_col, exponents, nearest_station_count))
            continue

        values = pd.to_numeric(frame[value_col], errors="coerce")
        valid_mask = values.notna().to_numpy()
        if not valid_mask.any():
            features.update(_empty_value_features(value_col, exponents, nearest_station_count))
            continue

        valid_values = values.to_numpy(dtype=float)[valid_mask]
        valid_distances = distances[valid_mask]
        order = np.argsort(valid_distances)
        sorted_values = valid_values[order]
        sorted_distances = valid_distances[order]

        features[f"{value_col}_neighbor_mean"] = float(np.mean(sorted_values))
        features[f"{value_col}_neighbor_median"] = float(np.median(sorted_values))
        features[f"{value_col}_neighbor_min"] = float(np.min(sorted_values))
        features[f"{value_col}_neighbor_max"] = float(np.max(sorted_values))
        features[f"{value_col}_neighbor_std"] = float(np.std(sorted_values)) if len(sorted_values) > 1 else 0.0
        features[f"{value_col}_neighbor_p90"] = float(np.quantile(sorted_values, 0.9))

        for rank in range(1, nearest_station_count + 1):
            idx = rank - 1
            if idx < len(sorted_values):
                features[f"{value_col}_nearest{rank}_value"] = float(sorted_values[idx])
                features[f"{value_col}_nearest{rank}_distance_km"] = float(sorted_distances[idx])
            else:
                features[f"{value_col}_nearest{rank}_value"] = np.nan
                features[f"{value_col}_nearest{rank}_distance_km"] = np.nan

        for exp in exponents:
            suffix = _exp_suffix(exp)
            weights = 1.0 / (np.power(sorted_distances, exp) + 1e-6)
            features[f"{value_col}_idw_mean_exp{suffix}"] = float(np.average(sorted_values, weights=weights))
            features[f"{value_col}_idw_sum_exp{suffix}"] = float(np.sum(sorted_values * weights))
            features[f"{value_col}_mostentita_max_exp{suffix}"] = float(np.max(sorted_values * weights))

    return features
