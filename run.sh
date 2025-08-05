#!/bin/bash

set -eux

python manage.py makemigrations db
python manage.py migrate
python analyze.py list.txt
python analyze.py

