.PHONY: help install seed run test eval clean

help:           ## Show this help
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/ -/'

install:        ## Install dependencies
	pip install -r requirements.txt

seed:           ## Build/rebuild the database (data/raw or sample)
	python -m scripts.seed

run:            ## Start the API + UI at http://127.0.0.1:8000
	uvicorn app.main:app --reload

test:           ## Run the test suite
	pytest -q

eval:           ## Measure /ask accuracy (needs GROQ_API_KEY)
	python -m scripts.eval

clean:          ## Remove the database and caches
	rm -f data/*.db
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
