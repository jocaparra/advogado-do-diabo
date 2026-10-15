# Como rodar

Há dois modos. Escolha pelo que você tem e pelo que quer ver.

| | Modo mínimo | Cadeia completa |
|---|---|---|
| O que gera | Dossiê numérico por ação: indicadores da CVM, valuation em cenários, ke implícito, gráficos | Tudo isso mais ranking, notícias, casas de análise, macro, objeções, auditoria e PDF |
| Precisa de Claude Code | **Não** | **Sim** (os agentes usam busca na web) |
| Precisa do PDF da XP | Não | Sim, uma vez por mês |
| Rede | CVM e Yahoo Finance | CVM, Yahoo Finance e web |
| Tempo | Cerca de 1 minuto (o primeiro uso baixa ~90 MB da CVM) | Dezenas de minutos |

## Instalação (os dois modos)

```bash
git clone <URL do repositório> && cd <pasta>
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover tests        # deve terminar em OK
```

## Modo mínimo: uma lista de tickers

```bash
python src/modo_minimo.py semana_$(date +%Y%m%d) WEGE3 ITUB4 PRIO3
```

Saídas na pasta: `resumo_dossie.md` (tabela), `dossie.json` e `graficos/dossie_TICKER.png`.
Funciona para ações da B3 com demonstrações na CVM; BDRs (final 34 e 35) não têm. Não é
recomendação de investimento: leia [AVISO_LEGAL.md](AVISO_LEGAL.md).

## Cadeia completa (Claude Code)

1. Instale o [Claude Code](https://claude.com/claude-code) e abra a pasta do projeto.
2. Coloque o PDF mais recente da carteira Top Ações da XP na raiz (só no mês em que sair).
3. No Claude Code, rode o comando:

   ```
   /semana
   ```

   Ou com uma data: `/semana 20261012`. O comando executa os agentes de `.claude/agents/` e os
   scripts de `src/` na ordem certa, e termina com um resumo e o caminho do PDF.
4. Para refazer só a parte numérica (sem agentes): `python src/executar.py semana_AAAAMMDD`. Ele não recoleta o
   Yahoo (os agentes e o PDF precisam ver o mesmo `precos_yahoo.json`); roda a medição quant e a checagem das
   posições no fim, ambas informativas.
5. Proventos conferidos em segunda fonte (brapi) exigem `BRAPI_TOKEN` para cobrir todos os tickers; sem ele a
   avaliação fica marcada como incompleta nas observações sem cobertura (`avaliacao.json`).

### O que o comando faz, em ordem
`leitor` (mensal) → coleta (`precos`, `macro`, `noticias`, `casas`, `fluxo`, `fundamentos`; mais
`coletar_yahoo.py` e `coletar_proventos.py`, **uma vez, antes dos agentes**) →
`coletar_cvm` e `calcular_derivados` → `analista` e `risco` → `advogado` e `auditor` →
`conferir` → `gerar_dossie` → `grafico` e `relator` → `avaliar`, `montar_relatorio` e
`atualizar_historico`.

## Problemas comuns

| Sintoma | Causa provável |
|---|---|
| `xp.json não encontrado` | Falta `xp_mensal/AAAAMM/xp.json` (rode o `leitor`) ou use o modo mínimo |
| `conferencia.json aponta N erro(s)` | Os dados não fecham; veja `python src/conferir.py` e corrija. `CARTEIRA_FORCAR=1` ignora, por sua conta |
| Ticker "sem dado na CVM" | BDR, empresa nova ou exercício social fora do ano civil |
| Preço ou data estranhos | Rodou durante o pregão: o último ponto pode ser intradiário |
| `download falhou, usado arquivo em cache` | Sem rede para a CVM; o cache pode estar desatualizado |

## Rodar com o computador desligado
O Claude Code roda na sua máquina e para se ela desligar ou dormir. Para execuções sem a máquina
ligada, use o Claude Code na web (sessões em nuvem que clonam o repositório do GitHub) ou rotinas
agendadas; elas precisam de acesso de rede a `dados.cvm.gov.br` e `query1.finance.yahoo.com`.
