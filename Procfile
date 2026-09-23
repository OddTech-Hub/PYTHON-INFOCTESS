web: python manage.py migrate && python manage.py loaddata datadump.json && python manage.py ensure_admin && gunicorn infoctess.wsgi --bind 0.0.0.0:$PORT
