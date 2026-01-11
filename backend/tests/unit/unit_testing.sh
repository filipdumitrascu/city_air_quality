pytest ../../microservices/client_message_handler/unit_test_cl_msg_hnd.py -v

pytest ../../microservices/data_provider_service/unit_test_dt_prvdr_srvc.py -v

pytest ../../microservices/database_service/unit_test_dtbs_srvc.py -v

pytest ../../microservices/ingest_service/unit_test_ingst_srvc.py -v

pytest ../../microservices/routing_service/unit_test_rtng_srvc.py -v

rm -r ../../.pytest_cache
