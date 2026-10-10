# advogado-do-diabo

**Uma análise independente e aprofundada, ação por ação, da carteira "Top Ações" da XP, para quem
quer outra opinião antes de decidir.** Todo mês a XP publica uma carteira recomendada para o
longo prazo. Este projeto parte dela, mas não a toma como verdade: refaz a análise toda semana
com dados primários, tenta se desmentir e entrega um relatório que diz o que sabe, o que não
sabe e onde discorda.

> **Não somos filiados à XP.** Projeto independente e de código aberto, sem vínculo,
> patrocínio ou endosso da XP Investimentos. "XP" é marca de seu titular e aparece apenas para
> identificar o relatório analisado.
>
> **Não é recomendação de investimento.** As saídas são de um modelo, podem conter erros e não
> consideram o seu perfil. Leia o [aviso legal](docs/AVISO_LEGAL.md) antes de usar.

## Sobre os rótulos "comprar", "aguardar" e "evitar"

São a **classificação do modelo** para o horizonte de semanas, resultado de uma nota calculada
com regras públicas e pesos documentados. **Não são uma ordem, uma oferta nem uma recomendação
de investimento pessoal.** Eles ignoram seu perfil de risco, seu patrimônio, seus objetivos e seus
impostos, e podem estar errados. "Comprar" significa apenas "o modelo vê relação favorável entre
nota e upside nesta semana"; "evitar", o contrário. Use como mais uma opinião, confira os dados
nas fontes e, se for investir, converse com um profissional habilitado.

## O que sai para cada ação

- **Dossiê com dados da CVM:** receita, lucro e EBITDA de 12 meses, margens, ROE, dívida líquida,
  múltiplos e histórico de 4 anos, calculados dos dados abertos (DFP e ITR), com método e fonte.
- **Valuation em cenários** (bear, base e bull) e grade de sensibilidade, mais o que o preço
  embute: retorno esperado (ke implícito), crescimento implícito e ROE exigido.
- **Checklist do setor** (banco, saneamento, petróleo, mineração, software etc.), cada item com
  fonte e data, ou "pendente".
- **Nota, ação sugerida e certeza**, com prós, contras, riscos, gatilho de revisão e as objeções de
  um agente advogado, reconferidas por um auditor independente.
- **Comparação com a XP, as casas de análise e o Ibovespa**, e a medição do próprio desempenho
  das recomendações passadas (com aviso quando a amostra é pequena).

## O que você precisa

| Quero | Preciso de |
|---|---|
| Ver o dossiê numérico (CVM, valuation, ke implícito) de uma lista de ações | Python 3.10+ e internet. **Sem Claude Code.** `python src/modo_minimo.py semana_AAAAMMDD WEGE3 ITUB4` |
| Rodar a análise completa com ranking, notícias, casas, auditoria e PDF | [Claude Code](https://claude.com/claude-code) e o PDF mensal da XP. No Claude Code: `/semana` |

Passo a passo e problemas comuns em [docs/COMO_RODAR.md](docs/COMO_RODAR.md).

## Como funciona

Cada etapa de coleta e julgamento é um agente em [.claude/agents/](.claude/agents/) (Claude Code).
Eles trocam apenas arquivos JSON dentro de uma pasta `semana_AAAAMMDD/`
(contrato em [docs/regras_comuns.md](docs/regras_comuns.md)). O que é conta é feito por scripts
em [src/](src/), não por modelo de linguagem.

| Etapa | Quem | Saída |
|---|---|---|
| Leitura do PDF (mensal) | `leitor` | `xp_mensal/AAAAMM/xp.json` |
| Coleta (semanal) | `precos`, `casas`, `noticias`, `fundamentos`, `fluxo`, `macro` | `*.json` |
| Fundamentos e dossiê | `src/coletar_cvm.py`, `src/gerar_dossie.py` | `fundamentos_cvm.json`, `dossie.json` |
| Síntese | `analista`, `risco`, `src/calcular_derivados.py` | `sintese.json`, `risco.json` |
| Crítica | `advogado`, `auditor`, `src/conferir.py` | `contra.json`, `auditoria.json`, `conferencia.json` |
| Entrega | `grafico`, `relator`, `src/montar_relatorio.py` | `graficos/`, `relatorio.pdf` |
| Diário | `monitor` | `alertas.json` |

Princípios: nenhum dado inventado (o que falta vira "não verificado"), toda informação com fonte
e data, só fontes de lista fechada, número calculável é calculado em código, e a opinião da XP
não é tratada como verdade.

## Cadência: PDF mensal, fontes semanais

- **Uma vez por mês**, quando a XP publica o PDF novo, o agente `leitor` grava
  `xp_mensal/AAAAMM/xp.json`.
- **Toda semana**, os agentes de coleta (`precos`, `casas`, `noticias`, `fundamentos`, `fluxo`,
  `macro`) buscam fontes novas dos últimos 7 dias e gravam em `semana_AAAAMMDD/`. Cada semana
  usa o `xp.json` mensal mais recente publicado até a data dela.
- `src/atualizar_historico.py` registra o ranking em `historico_carteira.json`, e a Figura 9
  compara com a semana anterior.

```
xp_mensal/202610/xp.json          # mensal
semana_20261005/*.json            # semanal: dados, análise, textos.json
semana_20261005/graficos/         # figuras e dados de cada uma
semana_20261005/relatorio.pdf
historico_carteira.json
```

## Qualidade dos dados

Número que pode ser calculado de fonte estruturada é calculado em código, não "lido" por modelo:

| Script | O que faz |
|---|---|
| `src/coletar_cvm.py` | Baixa DFP, ITR e FCA dos dados abertos da CVM e calcula receita, lucro e EBITDA de 12 meses, dívida líquida, P/L, P/VP, EV/EBITDA, ROE, payout e histórico anual de cada ticker (`fundamentos_cvm.json`). |
| `src/gerar_dossie.py` e `src/valuation.py` | Dossiê por ação: valuation de lucros descontados em cenários (premissas em `dados/premissas_valuation.json`, perfis em `dados/perfis_setoriais.json`), retorno esperado e crescimento implícitos no preço, checklist setorial preenchido pelos agentes com fonte e data. É modelo de referência, não previsão. |
| `src/regras.py` e `src/calcular_derivados.py` | Regra única de contagem de casas, mediana de preço alvo, upsides, upside ajustado e nota. O script grava os campos derivados em `casas.json` e `sintese.json` e lista o que mudou. |
| `src/atualizar_historico.py` e `src/avaliar.py` | Registram cada recomendação (nota, ação, certeza, preço, Ibovespa, versão das regras e pesos) e, quando o horizonte vence, medem o retorno contra o Ibovespa em 4 e 12 semanas por ação sugerida, certeza e posição, com correlação de postos entre nota e resultado. Sem amostra mínima (30 observações em 8 semanas) o resultado é marcado como insuficiente. |
| `src/conferir.py` | Valida cada JSON contra [schemas/](schemas/) e recalcula nota, upsides, medianas, retorno de 5 dias, beta e volatilidade de 90 pregões. Erros bloqueiam a geração do PDF. |

Limites conhecidos do cálculo da CVM (sempre sinalizados em `avisos`): EBITDA aproximado por
EBIT + depreciação da DVA; dívida sem arrendamentos; valor de mercado com preço único para ON e PN;
BDRs (como ROXO34) não têm demonstrações na CVM. Correções manuais de ticker em
[dados/mapa_tickers_manual.json](dados/mapa_tickers_manual.json).

## Código orientado a dados

Os scripts não contêm texto de análise nem tickers: leem os JSON da semana e o
`textos.json` (camada editorial escrita pelos agentes `analista`, `grafico` e `relator`).
Datas, contagens, limites de eixo, corte de compra, calendário e comparação com a semana
anterior são calculados dos dados.

## Dados e relatórios

Este repositório **não distribui** os dados nem o PDF de nenhuma semana: cada pessoa gera os
seus, a partir das fontes públicas. Há modelos dos arquivos editoriais em
[docs/modelos/](docs/modelos/) e os formatos de cada JSON estão em [schemas/](schemas/).

## Uso

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

1. **Mensal:** coloque o PDF da XP na raiz; o comando `/semana` roda o agente `leitor` e grava
   `xp_mensal/AAAAMM/xp.json`.
2. **Semanal:** no Claude Code, rode `/semana` (ou `/semana AAAAMMDD`). Ele executa os agentes de
   coleta e análise, que gravam os JSON em `semana_AAAAMMDD/` (contrato em
   [docs/regras_comuns.md](docs/regras_comuns.md)).
3. **Parte determinística**, em ordem (coleta da CVM, derivados, dossiê, conferência, avaliação,
   figuras, PDF e histórico):

```bash
python src/executar.py semana_AAAAMMDD
```

Ou passo a passo:

```bash
python src/coletar_cvm.py semana_AAAAMMDD         # fundamentos da CVM
python src/calcular_derivados.py semana_AAAAMMDD  # medianas, upsides e nota
python src/gerar_dossie.py semana_AAAAMMDD        # valuation e checklist
python src/conferir.py semana_AAAAMMDD            # conferência numérica
python src/avaliar.py semana_AAAAMMDD             # recomendações vencidas x Ibovespa
python src/gerar_graficos.py semana_AAAAMMDD      # figuras
python src/montar_relatorio.py semana_AAAAMMDD    # PDF
python src/atualizar_historico.py semana_AAAAMMDD # registra o ranking da semana
python -m unittest discover tests                 # testes offline
```

As pastas `semana_*/`, `xp_mensal/` e o `historico_carteira.json` ficam locais e são ignorados
pelo git.

## Limitações conhecidas

- A qualidade do relatório depende dos agentes: o código só renderiza o que está nos JSON.
  Se um campo faltar, a figura ou a seção mostra "não verificado" ou é omitida.
- Cotações vêm de agregadores (Yahoo Finance, brapi), não da B3 diretamente
  (ver [docs/diagnostico_acesso.md](docs/diagnostico_acesso.md)).
- O estilo visual do relatório é inspirado no PDF da XP; veja [docs/estilo_visual.md](docs/estilo_visual.md). Não somos afiliados à XP.
- O valuation é simplificado e conservador para empresas com ROE em expansão; o `ke` implícito é mais informativo que o valor justo isolado.
- Para contribuir, veja [CONTRIBUTING.md](CONTRIBUTING.md); para segurança, [SECURITY.md](SECURITY.md).

## Licença

[MIT](LICENSE) para o código. Nenhum relatório, texto editorial ou dado de terceiros é
distribuído aqui. Veja o [aviso legal](docs/AVISO_LEGAL.md).
