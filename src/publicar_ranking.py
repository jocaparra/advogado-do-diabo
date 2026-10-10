"""Exporta o ranking da semana em um ranking.json enxuto, para publicar no repositório.

uso: python src/publicar_ranking.py <pasta_da_semana> [publico/ranking.json]

Leva só o que o cruzamento com a carteira usa: posição, ticker, setor, nota, classificação,
certeza, cotação e upside ajustado, mais os pesos da carteira da XP. Não leva preços-alvo da XP,
nem textos, nem notícias. É o arquivo que `npx advogado-do-diabo` baixa por padrão.
"""
import json
import os
import sys

import carteira as C
import minha_carteira as M


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit('uso: python src/publicar_ranking.py <pasta_da_semana> [publico/ranking.json]')
    pasta = C.pasta_semana(sys.argv[:2])
    saida = os.path.abspath(sys.argv[2] if len(sys.argv) == 3 else 'publico/ranking.json')
    dados = M.exportar_publico(pasta)
    os.makedirs(os.path.dirname(saida), exist_ok=True)
    with open(saida, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(f"ok: {len(dados['ranking'])} ações da semana de {dados['data']} -> {saida}")


if __name__ == '__main__':
    main()
