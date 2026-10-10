# Como contribuir

Obrigado por querer melhorar o projeto. Algumas regras mantêm o resultado confiável.

## Princípios
- **Nunca inventar dado.** O que falta aparece como "não verificado". Contribuições que
  preenchem lacunas com suposição serão recusadas.
- **Número calculável é calculado em código** (CVM, Banco Central, séries de preço), não lido de notícia.
- **Uma regra, um lugar.** Contagem de casas, mediana, upsides e nota vivem em `src/regras.py`;
  premissas de valuation em `dados/premissas_valuation.json`; perfis setoriais em
  `dados/perfis_setoriais.json`.
- **Texto de análise fica nos dados** (`textos.json`, `dossie_qualitativo.json`), não nos scripts.

## Fluxo
1. Faça um fork e crie um branch.
2. `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
3. Rode `python -m unittest discover tests` antes e depois da mudança.
4. Mudou uma regra numérica? Acrescente ou ajuste um teste e explique o efeito numa semana sua
   (`python src/calcular_derivados.py semana_AAAAMMDD --simular`).
5. Abra um pull request descrevendo o que mudou e por quê.

## O que mais ajuda
- Novos perfis setoriais e itens de checklist (`dados/perfis_setoriais.json`).
- Mapeamentos de ticker para CNPJ que a FCA da CVM não cobre (`dados/mapa_tickers_manual.json`).
- Testes com demonstrações reais que quebrem o cálculo da CVM (contas atípicas, reapresentações).
- Melhorias de acessibilidade e de leitura do PDF.

## O que não aceitamos
- Texto copiado de relatórios de terceiros.
- Fontes fora da lista de `docs/regras_comuns.md` sem discussão prévia.
- Segredos, chaves ou dados pessoais nos arquivos.
