.PHONY: run stop

run:
	docker compose up postgres -d --wait
	uvicorn main:app --host 0.0.0.0 --reload --ssl-keyfile certificates/key.pem --ssl-certfile certificates/cert.pem

stop:
	docker compose down
