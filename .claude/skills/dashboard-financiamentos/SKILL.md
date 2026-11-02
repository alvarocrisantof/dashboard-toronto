---
name: dashboard-financiamentos
description: Atualiza, gera ou recria o dashboard de retorno de financiamentos do Grupo Toronto (valor financiado, quantidade e retorno por banco e por mês, Competência vs Fluxo de Caixa, lojas Consolidado/Multimarcas/Black). Use sempre que o usuário pedir para atualizar, gerar ou recriar o dashboard de retorno de financiamentos, ou pedir os números de financiamento por banco/mês, mesmo sem dizer "dashboard".
---

# Dashboard de Retorno de Financiamentos

Mostra quanto cada banco financiou nas vendas do Grupo Toronto, mês a mês, em duas visões:

- **Competência** (`comp`): financiamento das vendas feitas no mês. Fonte AutoConf: relatório **Lucro de Vendas**, por **Data Saída**.
- **Fluxo de Caixa** (`fluxo`): financiamento que o banco pagou no mês. Fonte AutoConf: **Financeiro liquidado**, por **Data Liquidação** (Vendas de Mercadorias + Intermediação).

Os totais das duas visões não batem, e isso é esperado: venda antiga é paga em mês seguinte, venda recente pode ainda não ter sido paga.

**Valor financiado é a métrica principal. Retorno é secundário** (vem em cinza no layout).

Lojas: `cons` (Grupo Toronto consolidado), `mm` (Toronto Multimarcas), `bk` (Toronto Black). `cons` = `mm` + `bk`.

Bancos (nomes canônicos, use exatamente assim): Votorantim, Bradesco, C6, Santander, Safra, Carbank, Itaú, Pan, Sicredi, Banco do Brasil. A normalização fica em `norm_bank()` no `update_dashboard.py`.

## Primeiro: qual dos 3 pedidos é?

| Pedido | O que fazer |
|---|---|
| **Atualizar** o dashboard (números novos) | Seção A. Site ao vivo, via script. |
| **Corrigir** um banco/mês que veio errado ou faltando | Seção B. Dicionários manuais. |
| **Gerar/recriar** um HTML avulso (snapshot, envio, mês específico) | Seção C. Template. |

Se não der para saber qual é, pergunte. Se for DRE (IPVA, salários, feirão...), use a skill `corrigir-dre`, não esta.

## A. Atualizar o site ao vivo

O dashboard ao vivo é o `index.html` deste repo (GitHub Pages: https://alvarocrisantof.github.io/dashboard-toronto/). Os dados ficam em `var FINAL={...}`, separados por ano (`'2024'`, `'2025'`, `'2026'`). Cada ano tem `generated, comp, fluxo, seguro, dre, gvop, acordo`, e também `posv` em 2026.

1. `git pull` antes (o cron do GitHub Actions faz commit 2x/dia).
2. Rode `python3 update_dashboard.py`. Precisa das credenciais da API AutoConf no ambiente; se faltarem, **não invente**: avise o usuário ou dispare o workflow `update.yml` (`gh workflow run update.yml`).
3. Confira o resumo que o script imprime (COMP cons fin/ret/q e FLUXO mm mês a mês) contra o que o usuário espera.
4. **Não edite `FINAL` à mão para mudar comp/fluxo.** O próximo cron sobrescreve. Só `gvop` e `acordo` de 2026 são preservados.
5. 2025 e 2024 estão **congelados** (`main()` reaproveita o bloco já salvo). Não reabra sem o usuário pedir.
6. Commit e push só com confirmação do usuário.

## B. Corrigir banco/mês errado ou faltando

Quando a API não traz um financiamento (comum: Itaú BBA, consórcio Bradesco, pagamento no último dia do mês), corrija em `update_dashboard.py`:

- Competência: `_COMP_MANUAL[ano][loja][mes][banco] = {'fin': ..., 'ret': ..., 'q': ...}`
- Fluxo: `_FLUXO_MANUAL[ano][loja][mes][banco] = {...}`

Regras:
- Confirme **loja, mês, ano e visão** (comp ou fluxo) antes de gravar. Não deduza a loja pelo valor.
- Coloque um comentário na linha com o nº do lançamento/placa e o motivo (siga o padrão que já existe).
- Grave em `mm` ou `bk`, nunca em `cons`: o consolidado é calculado.
- Depois rode o script (seção A) para o `index.html` refletir.

## C. Gerar/recriar HTML avulso

Template original (snapshot de 18/06/2026, só 2026, sem seletor de ano): `assets/template_original.html`. É um arquivo único com HTML+CSS+JS, sem build e sem libs externas.

Estrutura do layout (mantenha, a menos que o usuário peça mudança):
- Cabeçalho "GRUPO TORONTO" + subtítulo + "Atualizado em DD/MM/AAAA".
- Abas de loja: Consolidado / Multimarcas / Black.
- Toggle: 📊 Competência (azul `#4a9be8`) / 💰 Fluxo de Caixa (verde-água `#3fb6a8`).
- 4 KPIs: Valor Financiado, Financiamentos (qtd), Retorno (secundário), % Retorno/Financiado.
- Barras verticais: valor financiado por mês.
- Barras horizontais: valor financiado por banco, ordem decrescente.
- Tabela por banco: Qtd, Valor Financiado, Retorno, com linha TOTAL.
- Nota explicando Competência vs Fluxo + rodapé com as fontes.
- Tema escuro (`#0b1626` fundo, `#16243a` cards), responsivo até 720px.

Formato de dados que o **template** espera (`FINAL[view][store]`):

```js
{
  bm:        { "<Banco>": { "<mes>": {fin, ret, q} } },
  monthly:   { "<mes>": <fin total do mês> },          // número
  finByBank: [ {bank, fin}, ... ],                      // lista, ordem desc
  months:    [1,2,...],
  kpi:       {fin, ret, q}
}
```

**Cuidado com o formato:** o `update_dashboard.py` atual gera o `fluxo` diferente: `monthly[mes] = {fin, ret, q}` (objeto), `finByBank = {banco: {fin, q}}` (dicionário) e `kpi` sem `ret`. Além disso, o FINAL atual é separado por ano (`FINAL['2026'].comp.mm`). Para usar dados do `index.html` atual no template, converta antes: pegue `FINAL[ano][view][store]`, transforme `monthly` em número (`.fin`), `finByBank` em lista ordenada e preencha `kpi.ret` com 0 se faltar. Ou adapte o JS do template para aceitar os dois formatos.

Passos:
1. Pergunte ano e período, se o usuário não disser (padrão: ano corrente, todos os meses com dados).
2. Extraia os dados do `index.html` atual:
   ```bash
   python3 -c "
   import json;s=open('index.html',encoding='utf-8').read();i=s.index('var FINAL=')+10
   F,_=json.JSONDecoder().raw_decode(s[i:]);print(json.dumps(F['2026']['comp']['cons']['kpi']))"
   ```
3. Copie o template, troque o `var FINAL=...;` e a data "Atualizado em".
4. Recalcule `monthly`, `finByBank` e `kpi` a partir de `bm`. Não confie em totais copiados.
5. Valide: soma de `bm` por mês = `monthly`; soma de `mm` + `bk` = `cons` em cada mês/banco; `kpi.fin` = soma de `monthly`.
6. Salve na pasta que o usuário pedir. Na falta de indicação, salve em `~/Downloads/Dashboard_Financiamentos_<ANO>_Toronto.html`, sem sobrescrever arquivo existente sem perguntar.
7. Abra com `open <arquivo>` e mostre os KPIs de Consolidado (comp e fluxo).

## Formatação

- Moeda: `R$ 1.234.567,89` (`toLocaleString('pt-BR')`). KPIs sem centavos, tabela com centavos.
- Barras mensais: rótulo em milhares (`1.272k`).
- Meses: Jan, Fev, Mar, Abr, Mai, Jun, Jul, Ago, Set, Out, Nov, Dez.
- Retorno zerado na tabela aparece como `—`.
