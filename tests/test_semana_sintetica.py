"""Pipeline numérico ponta a ponta com uma semana SINTÉTICA (tickers e números fictícios).

Não depende de rede nem de dados reais: valida calcular_derivados, conferir e gerar_dossie.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(RAIZ, 'src')
sys.path.insert(0, SRC)

import conferir  # noqa: E402
import gerar_dossie  # noqa: E402

TICKERS = {'AAAA3': (10.0, 12.0), 'BBBB4': (20.0, 18.0), 'CCCC3': (5.0, 7.5)}  # preço, alvo da XP


def serie(n, p0, passo, fim=dt.date(2026, 10, 5)):
    """n pregões (dias úteis) terminando em `fim`, com preços sintéticos."""
    datas, d = [], fim
    while len(datas) < n:
        if d.weekday() < 5:
            datas.append(d)
        d -= dt.timedelta(days=1)
    out, p = [], p0
    for i, d in enumerate(reversed(datas)):
        out.append([d.isoformat(), round(p, 4)])
        p *= 1 + passo * (1 if i % 3 else -1.2)
    return out


def gravar(caminho, obj):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)


def montar_semana(raiz):
    pasta = os.path.join(raiz, 'semana_20261005')
    gravar(os.path.join(raiz, 'xp_mensal', '202610', 'xp.json'), {
        'data_relatorio': '2026-10-01', 'dados_ate': '2026-09-30', 'fonte': 'sintético',
        'acoes': [{'ticker': t, 'empresa': f'Empresa {t}', 'setor': 'Setor X', 'peso_atual': 10, 'peso_anterior': 10,
                   'rating': 'Compra', 'preco_alvo': v[1]} for t, v in TICKERS.items()],
        'carteira': {'retornos': {}, 'indicadores': {}}, 'setores': [{'setor': 'Setor X', 'peso_ibovespa': 10, 'peso_carteira': 30}]})
    ib = serie(130, 100000.0, 0.004)
    acoes, casas, rank = {}, {}, []
    for i, (t, (preco, alvo)) in enumerate(TICKERS.items()):
        s = serie(130, preco * 0.9, 0.006 + i * 0.001)
        s[-1][1] = preco
        r5 = round((s[-1][1] / s[-6][1] - 1) * 100, 2)
        acoes[t] = {'preco_atual': preco, 'data_cotacao': s[-1][0], 'ret_5d': f'{r5}%', 'serie': s}
        casas[t] = {'casas': [{'casa': c, 'rating': 'compra', 'preco_alvo': preco * k, 'moeda': 'R$', 'data': '2026-09-15',
                               'fonte': 'InfoMoney', 'url': 'https://exemplo.invalid/x', 'situacao': 'verificada'}
                              for c, k in (('Casa A', 1.2), ('Casa B', 1.3), ('Casa C', 1.1))], 'xp': {'rating': 'Compra'}}
        comp = {'catalisadores': 6 - i, 'noticias': 5, 'momentum': 5 + i, 'macro_eleicao': 5, 'valuation_upside': 6}
        rank.append({'posicao': i + 1, 'ticker': t, 'setor': 'Setor X', 'componentes': comp, 'nota': 0, 'acao_sugerida': 'aguardar',
                     'certeza': 'média', 'preco_atual': preco, 'data_cotacao': s[-1][0], 'rating_xp': 'Compra',
                     'tese': 'Tese sintética apenas para teste do pipeline numérico.', 'pros': ['p'], 'contras': ['c'], 'riscos': ['r'],
                     'fontes': [{'fonte': 'Fonte sintética', 'data': '2026-09-30', 'url': 'https://exemplo.invalid/f'}],
                     'retornos': {'5d_pct': r5}})
    gravar(os.path.join(pasta, 'precos.json'), {'ibovespa': {'preco_atual': ib[-1][1], 'data_cotacao': ib[-1][0], 'serie': ib}, 'acoes': acoes})
    gravar(os.path.join(pasta, 'casas.json'), {'tickers': casas})
    gravar(os.path.join(pasta, 'sintese.json'), {'metodologia': {'pesos': {'catalisadores': .25, 'noticias': .2, 'momentum': .2,
                                                                      'macro_eleicao': .2, 'valuation_upside': .15}}, 'ranking': rank})
    cv = {}
    for t, (preco, _) in TICKERS.items():
        mcap = preco * 1e9
        cv[t] = {'ticker': t, 'situacao': 'ok', 'nome': f'Empresa {t}', 'valores': {
            'lucro_liquido_12m': {'valor': mcap / 10, 'unidade': 'REAL', 'certeza': 'alta', 'metodo': 'teste'},
            'roe_12m': {'valor': 18.0, 'unidade': '%', 'certeza': 'alta', 'metodo': 'teste'},
            'valor_de_mercado': {'valor': mcap, 'unidade': 'REAL', 'certeza': 'alta', 'metodo': 'teste'},
            'p_vp': {'valor': 1.8, 'unidade': 'x', 'certeza': 'alta', 'metodo': 'teste'}},
            'historico_anual': [{'ano': 2023, 'receita': 4e9, 'lucro_liquido': 0.8e9, 'roe_pct': 15.0},
                                {'ano': 2024, 'receita': 4.6e9, 'lucro_liquido': 0.9e9, 'roe_pct': 16.0},
                                {'ano': 2025, 'receita': 5.2e9, 'lucro_liquido': 1.0e9, 'roe_pct': 17.0}], 'avisos': []}
    gravar(os.path.join(pasta, 'fundamentos_cvm.json'), {'data_coleta': '2026-10-05', 'fonte': 'sintético', 'tickers': cv})
    return pasta


def rodar(script, pasta):
    return subprocess.run([sys.executable, os.path.join(SRC, script), pasta], capture_output=True, text=True)


class TesteSemanaSintetica(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = montar_semana(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_derivados_conferencia_e_dossie(self):
        r = rodar('calcular_derivados.py', self.pasta)
        self.assertEqual(r.returncode, 0, r.stderr)
        sy = json.load(open(self.pasta + '/sintese.json', encoding='utf-8'))
        # nota recalculada, ranking ordenado e upside até o alvo da XP
        notas = [x['nota'] for x in sy['ranking']]
        self.assertEqual(notas, sorted(notas, reverse=True))
        a = next(x for x in sy['ranking'] if x['ticker'] == 'AAAA3')
        self.assertAlmostEqual(a['upside_xp_pct'], 20.0)
        self.assertEqual(a['n_alvos_mediana'], 3)
        rel = conferir.conferir(self.pasta)
        self.assertEqual([i for i in rel['itens'] if i['severidade'] == 'erro'], [], rel['itens'])
        # dossiê: valuation em ordem e ke implícito presente
        d = gerar_dossie.construir(self.pasta)
        for t, v in d['tickers'].items():
            c = v['valuation']['cenarios']
            self.assertLess(c['bear']['valor_justo_por_acao'], c['base']['valor_justo_por_acao'])
            self.assertLess(c['base']['valor_justo_por_acao'], c['bull']['valor_justo_por_acao'])
            self.assertIsNotNone(v['valuation']['ke_implicito_pct'])
            self.assertTrue(all(i['status'] == 'pendente' for i in v['checklist']))  # nada inventado

    def test_conferencia_pega_nota_adulterada(self):
        rodar('calcular_derivados.py', self.pasta)
        p = self.pasta + '/sintese.json'
        sy = json.load(open(p, encoding='utf-8'))
        sy['ranking'][0]['nota'] = round(sy['ranking'][0]['nota'] + 1.0, 2)
        json.dump(sy, open(p, 'w', encoding='utf-8'))
        regras = {i['regra'] for i in conferir.conferir(self.pasta)['itens'] if i['severidade'] == 'erro'}
        self.assertIn('nota', regras)

    def test_conferencia_pega_preco_divergente(self):
        rodar('calcular_derivados.py', self.pasta)
        p = self.pasta + '/precos.json'
        pr = json.load(open(p, encoding='utf-8'))
        pr['acoes']['BBBB4']['preco_atual'] = 25.0
        json.dump(pr, open(p, 'w', encoding='utf-8'))
        regras = {i['regra'] for i in conferir.conferir(self.pasta)['itens'] if i['severidade'] == 'erro'}
        self.assertTrue({'preco', 'serie_preco'} & regras, regras)


if __name__ == '__main__':
    unittest.main()
