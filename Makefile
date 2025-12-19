.PHONY: help init backtest paper train clean

help:
	@echo "Trading News AI - Quick Commands"
	@echo "  make init        - Initialize database"
	@echo "  make backtest    - Run backtest"
	@echo "  make paper       - Run paper trading"
	@echo "  make train       - Train models"
	@echo "  make clean       - Remove cache files"

init:
	python3 run.py scripts/utils/init_db.py

backtest:
	python3 run.py scripts/trading/run_backtest.py --start 2020-01-01

paper:
	python3 run.py scripts/trading/paper_trader.py

train:
	python3 run.py scripts/training/train_news_model.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete

# Docker commands
docker-build:
	docker-compose build

docker-backtest:
	docker-compose run --rm backtest

docker-up:
	docker-compose up -d paper-trader news-ingest monitor

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

docker-clean:
	docker-compose down -v
	docker system prune -f

docker-build:
	docker-compose build

docker-backtest:
	docker-compose run --rm backtest

docker-up:
	docker-compose up -d paper-trader news-ingest redis

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f paper-trader

docker-status:
	docker-compose ps
