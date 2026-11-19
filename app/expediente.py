"""Horário de expediente: os tempos do painel e o SLA contam só de segunda a sexta, das 7h às 18h."""

from datetime import datetime, timedelta

# O tempo até encerrar conta só o expediente: de segunda a sexta, das 7h às 18h
EXPEDIENTE_INICIO, EXPEDIENTE_FIM = 7, 18
DIAS_EXPEDIENTE = {0, 1, 2, 3, 4}          # segunda = 0 … domingo = 6


def segundos_expediente(inicio: datetime, fim: datetime) -> float:
    """Tempo entre dois momentos contando só o horário de expediente."""
    if fim <= inicio:
        return 0.0
    total = 0.0
    dia = inicio.date()
    while dia <= fim.date():
        if dia.weekday() in DIAS_EXPEDIENTE:
            abre = datetime.combine(dia, datetime.min.time()).replace(hour=EXPEDIENTE_INICIO)
            fecha = abre.replace(hour=EXPEDIENTE_FIM)
            ini, fi = max(inicio, abre), min(fim, fecha)
            if fi > ini:
                total += (fi - ini).total_seconds()
        dia += timedelta(days=1)
    return total


def somar_expediente(inicio: datetime, segundos: float) -> datetime:
    """Momento em que se completam `segundos` de expediente a partir de `inicio` (inverso de
    segundos_expediente). Fora do expediente, começa a contar na próxima abertura."""
    momento, resta = inicio, max(0.0, float(segundos))
    for _ in range(3660):                      # até ~10 anos de dias: proteção contra laço infinito
        dia = momento.date()
        abre = datetime.combine(dia, datetime.min.time()).replace(hour=EXPEDIENTE_INICIO)
        fecha = abre.replace(hour=EXPEDIENTE_FIM)
        if dia.weekday() in DIAS_EXPEDIENTE and momento < fecha:
            ini = max(momento, abre)
            disponivel = (fecha - ini).total_seconds()
            if resta <= disponivel:
                return ini + timedelta(seconds=resta)
            resta -= disponivel
        momento = datetime.combine(dia + timedelta(days=1), datetime.min.time())
    return momento
