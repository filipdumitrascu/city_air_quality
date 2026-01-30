# Unit testing

# Move to this directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Testing
pytest ../../backend/microservices/client_message_handler/unit_test_cl_msg_hnd.py -v
pytest ../../backend/microservices/data_provider_service/unit_test_dt_prvdr_srvc.py -v
pytest ../../backend/microservices/database_service/unit_test_dtbs_srvc.py -v
pytest ../../backend/microservices/ingest_service/unit_test_ingst_srvc.py -v
pytest ../../backend/microservices/routing_service/unit_test_rtng_srvc.py -v

# Remove pycache
rm -r ../../backend/.pytest_cache
