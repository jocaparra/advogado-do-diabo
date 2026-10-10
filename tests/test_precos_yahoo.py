"""Parser de cotações do Yahoo (offline, com payload sintético)."""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import precos_yahoo as P  # noqa: E402


def payload(closes, d0=dt.date(2026, 9, 1), offset=-10800):
    ts = []
    d = d0
    while len(ts) < len(closes):
        if d.weekday() < 5:  # 13:00 UTC, dentro do pregão de São Paulo
            ts.append(int(dt.datetime(d.year, d.month, d.day, 13, tzinfo=dt.timezone.utc).timestamp()))
        d += dt.timedelta(days=1)
    return {'chart': {'result': [{'timestamp': ts, 'meta': {'gmtoffset': offset}, 'indicators': {'quote': [{'close': closes}]}}]}}


class TesteYahoo(unittest.TestCase):
    def test_descarta_pontos_sem_preco_e_mantem_ordem(self):
        s = P.interpretar(payload([10, None, 11, 12, None, 13]))
        self.assertEqual([p[1] for p in s], [10, 11, 12, 13])
        self.assertEqual(s, sorted(s))

    def test_retorno_5_pregoes(self):
        closes = [100.0] * 10 + [110.0]
        r = P.retornos(P.interpretar(payload(closes)))
        self.assertEqual(r['ret_5d'], '10.00%')

    def test_serie_curta_nao_inventa_retorno(self):
        self.assertEqual(P.retornos(P.interpretar(payload([1, 2, 3]))), {})


if __name__ == '__main__':
    unittest.main()
