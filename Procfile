web: python manage.py migrate && python manage.py ensure_admin && gunicorn infoctess.wsgi:application --workers=3 --threads=4 --worker-class=gthread --timeout=120 --bind 0.0.0.0:$PORT
