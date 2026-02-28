import multiprocessing

bind = "0.0.0.0:5000"
worker_class = "gevent"
workers = multiprocessing.cpu_count() * 2 + 1
timeout = 300
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
