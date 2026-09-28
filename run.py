"""Servidor de desenvolvimento (recarrega ao editar).  Em produção use Gunicorn: ver deploy/."""

from app import create_app

if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=True)
