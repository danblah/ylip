#!/bin/bash
exec gunicorn -w 1 --threads 100 --bind 0.0.0.0:8088 -k gevent --keep-alive 5 wsgi:app