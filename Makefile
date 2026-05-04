.PHONY: run run-https stop

run:
	docker compose up postgres -d --wait
	docker compose up --build auth-service

run-https:
	docker compose up postgres -d --wait
	docker compose up --build auth-service

stop:
	docker compose down
