"""Ponto de entrada para o Gunicorn:  gunicorn wsgi:app"""

from app import create_app

app = create_app()
