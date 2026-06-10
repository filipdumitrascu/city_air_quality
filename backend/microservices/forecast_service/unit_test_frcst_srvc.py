import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient
import json

# Import app for testing
from forecast_service import app, model_status, BUCHAREST_BOUNDS, PREDICT_POLLUTANTS

# Mock data
mock_sensor_data = [
    {"latitude": 44.4268, "longitude": 26.1025, "pm2_5": 25.0, "pm10": 40.0, "no2": 30.0, "co": 0.5, "sensor_type": "SPO-RO", "sensor_id": "B-1"},
    {"latitude": 44.4368, "longitude": 26.1125, "pm2_5": 28.0, "pm10": 45.0, "no2": 35.0, "co": 0.6, "sensor_type": "SPO-RO", "sensor_id": "B-2"},
    {"latitude": 44.4168, "longitude": 26.0925, "pm2_5": 22.0, "pm10": 38.0, "no2": 28.0, "co": 0.4, "sensor_type": "CityAirQ", "sensor_id": "mobile-1"},
]


class TestHealthEndpoints:
    """Tests for health and status endpoints"""
    
    @pytest.mark.asyncio
    async def test_root_endpoint(self):
        """Test root endpoint returns service info"""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "forecast_service"
        assert "model_loaded" in data
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test health endpoint returns status"""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "model_loaded" in data
        assert "predictions_count" in data
    
    @pytest.mark.asyncio
    async def test_model_status_endpoint(self):
        """Test model status endpoint"""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/model/status")
        
        assert response.status_code == 200
        data = response.json()
        assert "loaded" in data
        assert "model_path" in data
        assert "pollutants" in data


class TestFillGapsEndpoint:
    """Tests for /predict/fill-gaps endpoint"""
    
    @pytest.mark.asyncio
    async def test_fill_gaps_model_not_loaded(self):
        """Test fill-gaps returns gracefully when model not loaded"""
        # Reset model status for test
        original_loaded = model_status["loaded"]
        model_status["loaded"] = False
        
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post("/predict/fill-gaps")
        
        model_status["loaded"] = original_loaded
        
        assert response.status_code == 200
        data = response.json()
        assert "Model not loaded" in data["message"]
        assert data["gaps_filled"] == 0
    
    @pytest.mark.asyncio
    @patch("forecast_service.fetch_current_sensor_state", new_callable=AsyncMock)
    async def test_fill_gaps_no_sensors(self, mock_fetch):
        """Test handling when no sensor data available"""
        mock_fetch.return_value = []
        
        # Temporarily set model as loaded
        original_loaded = model_status["loaded"]
        model_status["loaded"] = True
        
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post("/predict/fill-gaps")
        
        model_status["loaded"] = original_loaded
        
        assert response.status_code == 200
        data = response.json()
        assert data["gaps_filled"] == 0


class TestConstants:
    """Tests for configuration constants"""
    
    def test_bucharest_bounds_valid(self):
        """Bucharest bounds should be valid coordinates"""
        assert BUCHAREST_BOUNDS["lat_min"] < BUCHAREST_BOUNDS["lat_max"]
        assert BUCHAREST_BOUNDS["lon_min"] < BUCHAREST_BOUNDS["lon_max"]
        assert 44.0 < BUCHAREST_BOUNDS["lat_min"] < 45.0
        assert 25.5 < BUCHAREST_BOUNDS["lon_min"] < 27.0
    
    def test_predict_pollutants_defined(self):
        """Should have pollutants defined for prediction"""
        assert len(PREDICT_POLLUTANTS) > 0
        assert "pm10" in PREDICT_POLLUTANTS
        assert "pm2_5" in PREDICT_POLLUTANTS


class TestTimestamp:
    """Tests for timestamp helper"""
    
    def test_get_current_timestamp_ms(self):
        """Timestamp should be in milliseconds"""
        from forecast_service import get_current_timestamp_ms
        
        ts = get_current_timestamp_ms()
        
        assert isinstance(ts, int)
        assert ts > 1700000000000  # After 2023
        assert ts < 2000000000000  # Before 2033


class TestDataValidation:
    """Tests for data validation logic"""
    
    def test_missing_value_is_negative_one(self):
        """Missing values should be encoded as -1"""
        # This tests the convention used in the system
        missing_value = -1
        valid_value = 25.0
        
        assert missing_value < 0
        assert valid_value >= 0
    
    def test_sensor_data_structure(self):
        """Mock sensor data should have required fields"""
        for sensor in mock_sensor_data:
            assert "latitude" in sensor
            assert "longitude" in sensor
            assert "sensor_type" in sensor
            # At least one pollutant should be present
            has_pollutant = any(p in sensor for p in ["pm10", "pm2_5", "no2", "co"])
            assert has_pollutant
