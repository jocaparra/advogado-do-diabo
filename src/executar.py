"""Executa a parte determinística do pipeline de uma semana, em ordem.

uso: python src/executar.py <pasta_da_semana> [--sem-rede] [--forcar] [--sem-notificar]

Pré-requisito: os agentes de coleta e análise já gravaram precos.json, casas.json, macro.json,
sintese.json etc. na pasta. Este script só roda o que é cálculo, conferência e montagem:

  1. coletar_cvm        fundamentos da CVM (pula com --sem-rede e reaproveita fundamentos_cvm.json)
     coletar_yahoo      múltiplos de mercado do Yahoo em precos_yahoo.json (informativo; pula com --sem-rede)
  2. calcular_derivados medianas, upsides, nota e posição pela regra única
  3. gerar_dossie       valuation por cenários e checklist setorial
  4. conferir           schemas e recálculo de números (erros interrompem)
  5. avaliar            recomendações vencidas contra o Ibovespa
  6. gerar_graficos     figuras
  7. montar_relatorio   PDF (recusa gerar com erros; --forcar ignora)
  8. atualizar_historico registra o ranking da semana
  9. aprender           portão de amostra e padrões (só informativo; nunca altera parâmetros)
 10. medir_quant        mede os retratos da carteira quantitativa já vencidos (informativo; precisa de rede)
 11. checagem_semanal   cotações de hoje das suas posições e sinais de venda (informativo; precisa de rede
                        e de entrada/posicoes_pluggy.csv ou entrada/posicoes.csv; --sem-notificar silencia o macOS)
"""
import glob
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)


def rodar(script, pasta=None, extras=(), tolerar=False, env=None):
    """Roda src/<script> com a pasta da semana (se houver) e os extras; `tolerar` não interrompe o pipeline."""
    cmd = [sys.executable, os.path.join(AQUI, script), *([pasta] if pasta else []), *extras]
    print(f'\n>>> {" ".join(os.path.basename(c) if i < 2 else c for i, c in enumerate(cmd))}', flush=True)
    r = subprocess.run(cmd, env={**os.environ, **(env or {})})
    if r.returncode != 0 and not tolerar:
        sys.exit(f'falhou: {script} (código {r.returncode})')
    return r.returncode


def complementos(sem_rede, sem_notificar):
    """Medição quant e checagem das posições: informativas, nunca interrompem nem alteram o ranking."""
    if sem_rede:
        print('\n--sem-rede: medição quant e checagem semanal puladas (precisam de cotações)')
        return
    if glob.glob(os.path.join(RAIZ, 'aprendizado', 'quant', 'carteira_*.json')):
        rodar('medir_quant.py', tolerar=True)
    else:
        print('\nmedição quant pulada: nenhum retrato em aprendizado/quant/ (rode src/carteira_quant.py)')
    posicoes = next((p for p in (os.path.join(RAIZ, 'entrada', n) for n in ('posicoes_pluggy.csv', 'posicoes.csv'))
                     if os.path.exists(p)), None)
    if posicoes:
        rodar('checagem_semanal.py', extras=['--csv', posicoes, *(['--sem-notificar'] if sem_notificar else [])], tolerar=True)
    else:
        print('\nchecagem semanal pulada: sem entrada/posicoes_pluggy.csv nem entrada/posicoes.csv')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 1:
        sys.exit(__doc__)
    pasta = os.path.abspath(args[0])
    sem_rede, forcar = '--sem-rede' in sys.argv, '--forcar' in sys.argv
    if not sem_rede:
        rodar('coletar_cvm.py', pasta)
        rodar('coletar_yahoo.py', pasta, tolerar=True)
    elif not os.path.exists(os.path.join(pasta, 'fundamentos_cvm.json')):
        sys.exit('--sem-rede precisa de fundamentos_cvm.json na pasta (de uma execução anterior): '
                 'rode sem --sem-rede uma vez para baixar os dados da CVM')
    rodar('calcular_derivados.py', pasta)
    rodar('gerar_dossie.py', pasta)
    cod = rodar('conferir.py', pasta, tolerar=forcar)
    if cod and forcar:
        print('aviso: conferência com erros, seguindo por --forcar')
    rodar('avaliar.py', pasta)
    rodar('gerar_graficos.py', pasta)
    rodar('montar_relatorio.py', pasta, env={'CARTEIRA_FORCAR': '1'} if forcar else None)
    rodar('atualizar_historico.py', pasta)
    rodar('aprender.py', pasta, extras=(), tolerar=True)
    complementos(sem_rede, '--sem-notificar' in sys.argv)
    print('\nconcluído:', os.path.join(pasta, 'relatorio.pdf'))


if __name__ == '__main__':
    main()
