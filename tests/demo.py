"""Modo demonstração: sobe o sistema num SQLite local com dados de exemplo (sem PostgreSQL).

    python -m tests.demo            (use --limpo para começar sem nenhuma conta)

Contas: admin/admin123 (administrador), carlos/carlos123 (técnico), ana/ana12345 e bruno/bruno123.
"""

import os
import sys

from app import create_app
from app.config import PASTA_WEB, Config
from app.modelos import Base
from tests.dados_exemplo import popular

PASTA_DEMO = os.path.join(PASTA_WEB, "demo")


def main() -> None:
    os.makedirs(PASTA_DEMO, exist_ok=True)
    arquivo = os.path.join(PASTA_DEMO, "demo.db")
    if os.path.exists(arquivo):
        os.remove(arquivo)  # sempre começa do mesmo estado
    cfg = Config(banco_url=f"sqlite:///{arquivo}", secret_key="demo-" + "x" * 40,
                 anexos_pasta=os.path.join(PASTA_DEMO, "anexos"))
    app = create_app(cfg)
    Base.metadata.create_all(app.extensions["engine"])
    if "--limpo" not in sys.argv:
        with app.extensions["sessoes"]() as s:
            popular(s)
    app.run(host="127.0.0.1", port=5057, debug=False)


if __name__ == "__main__":
    main()
