web: gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.core.server:app --bind 0.0.0.0:$PORT --timeout 120
