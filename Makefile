.PHONY: run stop

run:
	docker compose up postgres -d --wait
	uvicorn main:app --host 0.0.0.0 --reload

stop:
	docker compose down
