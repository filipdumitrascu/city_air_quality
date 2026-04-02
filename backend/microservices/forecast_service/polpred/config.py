from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_MODEL_PARAMS = {
    "loss": "absolute_error",
    "learning_rate": 0.06,
    "max_depth": 10,
    "max_leaf_nodes": 95,
    "min_samples_leaf": 20,
    "l2_regularization": 1e-2,
    "max_iter": 300,
    "early_stopping": False,
    "random_state": 42,
}


@dataclass
class PolPredConfig:
    timestamp_col: str = "timestamp"
    station_id_col: str = "station_id"
    latitude_col: str = "lat"
    longitude_col: str = "lon"
    # CityAirQ pollutants (what fixed stations B-1 to B-8 measure)
    pollutant_columns: tuple[str, ...] = ("pm10", "pm2_5", "no2", "co")
    extra_feature_columns: tuple[str, ...] = ()
    distance_exponents: tuple[float, ...] = (0.5, 1.0, 1.5)
    nearest_station_count: int = 3
    model_params: dict[str, object] = field(default_factory=lambda: DEFAULT_MODEL_PARAMS.copy())

    @property
    def value_columns(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.pollutant_columns, *self.extra_feature_columns)))
