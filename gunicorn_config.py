bind = "0.0.0.0:$PORT"
workers = 2
threads = 2
timeout = 60
worker_class = "eventlet"  # For WebSocket support
