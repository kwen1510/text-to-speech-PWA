import multiprocessing
import os


bind = f"0.0.0.0:{os.getenv('PORT', '10000')}"
workers = int(os.getenv("WEB_CONCURRENCY", "1"))
threads = int(os.getenv("GUNICORN_THREADS", "2"))
worker_class = "gthread"
timeout = int(os.getenv("GUNICORN_TIMEOUT", "180"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "50"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "10"))

if workers < 1:
    workers = 1

# Keep memory usage predictable on small Render instances.
workers = min(workers, max(1, multiprocessing.cpu_count()))
