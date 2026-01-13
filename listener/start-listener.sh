#!/bin/bash
set -eu
exec gunicorn -w 4 -b 0.0.0.0:9000 --access-logfile - --error-logfile - listener9000:app
