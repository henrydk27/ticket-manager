"""Modo demonstração: sobe o sistema num SQLite local com dados de exemplo (sem PostgreSQL).

    python -m tests.demo            (use --limpo para começar sem nenhuma conta)

Contas: admin/admin123 (administrador, T.I), carlos/carlos123 (T.I), marta/marta123 (Manutenção),
rita/rita1234 (RH) — estes atendem o próprio setor —, ana/ana12345 e bruno/bruno123 (usuários).
"""

import os
import sys

from app import create_app
from app.config import PASTA_WEB, Config
from app.modelos import Base
from tests.dados_exemplo import popular

PASTA_DEMO = os.path.join(PASTA_WEB, "demo")


def _equipamentos(s, contas) -> None:
    from app import inventario
    exemplos = [
        ("004512", "Desktop", "Dell", "OptiPlex 3080", "ana", "", "Em uso", "i5-10500", "16 GB", "SSD 512 GB", "Windows 11 Pro", "FISCAL-01", "192.168.0.31"),
        ("004513", "Monitor", "LG", "24MK430H", "ana", "", "Em uso", "", "", "", "", "", ""),
        ("004520", "Notebook", "Lenovo", "ThinkPad E14", "bruno", "", "Em uso", "Ryzen 5 5500U", "8 GB", "SSD 256 GB", "Windows 11 Pro", "VENDAS-NB02", "192.168.0.52"),
        ("004533", "Impressora", "HP", "LaserJet M428", "", "Fiscal", "Em uso", "", "", "", "", "IMP-FISCAL", "192.168.0.200"),
        ("004540", "Desktop", "Positivo", "Master D580", "", "", "Em estoque", "i3-8100", "8 GB", "HD 500 GB", "Windows 10 Pro", "", ""),
        ("004541", "Nobreak", "SMS", "Station II 1400VA", "", "T.I", "Em manutenção", "", "", "", "", "", ""),
    ]
    for pat, tipo, marca, modelo, dono, setor, sit, cpu, mem, disco, so, host, ip in exemplos:
        inventario.salvar(s, None, {
            "patrimonio": pat, "tipo": tipo, "marca": marca, "modelo": modelo, "situacao": sit,
            "usuario_id": contas[dono].id if dono else "", "setor": setor, "processador": cpu,
            "memoria": mem, "armazenamento": disco, "sistema_operacional": so, "hostname": host, "ip": ip,
        }, contas["carlos"])


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
            contas = popular(s)
            _equipamentos(s, contas)
    app.run(host="127.0.0.1", port=5057, debug=False)


if __name__ == "__main__":
    main()
