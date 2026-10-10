# DIAGNÓSTICO DE ACESSO (coleta em 2026-10-05)

| Fonte | URL testada | Resultado |
|---|---|---|
| B3 | b3.com.br (página Ibovespa) | abriu, sem login |
| B3 sistemas listados | sistemaswebb3-listados.b3.com.br | bloqueado (HTTP 403) |
| CVM | gov.br/cvm e rad.cvm.gov.br | abriu |
| Banco Central | bcb.gov.br (página Selic) | HTML abre mas conteúdo carrega por JavaScript; API SGS api.bcb.gov.br abriu com dados |
| InfoMoney | infomoney.com.br/mercados | abriu, sem paywall |
| Reuters | reuters.com/markets | bloqueado (HTTP 401 e recusa da ferramenta de leitura) |
| Valor Econômico | valor.globo.com | HTTP 200 por curl, mas ferramenta de leitura recusou; matérias com paywall |
| RI de empresa | investidorpetrobras.com.br | abriu (ri.petrobras.com.br não resolve DNS) |
| Cotações | Yahoo Finance chart API (dados da B3) | abriu, série diária disponível |
| Cotações | brapi.dev | abriu |
| Cotações | stooq.com | bloqueado (verificação JavaScript) |

Observação: as cotações vêm de agregadores (Yahoo Finance, brapi) que replicam o preço de fechamento da B3. A fonte primária (B3) não oferece série diária por acesso direto.
