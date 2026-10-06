---
name: corrigir-dre
description: Corrige valores da DRE do dashboard Toronto conferindo contra print/screenshot do AutoConf ou dado da API. Use sempre que o usuário mandar print da DRE, disser que um valor da DRE está errado/divergente, pedir para "conferir", "bater" ou "corrigir" campo da DRE (IPVA, feirão, salários, taxas, etc.) de qualquer loja (multimarcas, black, consolidado) e mês.
---

# Corrigir DRE

A DRE vem da API AutoConf e às vezes diverge do relatório real. A correção é manual, campo a campo, e precisa ficar em **dois lugares**:

1. **`update_dashboard.py`**: dicionário de correções, para o cron (2x/dia) não desfazer.
2. **`index.html`**: `FINAL[ano].dre`, para o site refletir já, sem gastar cota da API.

## Passo 1: confirmar loja, mês e ano ANTES de qualquer número

Este é o erro mais caro do histórico (c96d6e5, c26e33c, c8065c1): o print era do **consolidado** e foi aplicado como **multimarcas**, o que gerou commit de reversão.

- Pergunte, ou confirme explicitamente, de qual loja é o print: `mm` (Multimarcas, rev 185), `bk` (Black, rev 726) ou `cons` (Consolidado).
- Pista: se o cabeçalho/filtro do print não mostra a loja, **pergunte**. Não deduza pelo valor.
- Confirme também mês e ano.

## Passo 2: comparar

Leia os valores atuais:

```bash
python3 -c "
import json;s=open('index.html',encoding='utf-8').read();i=s.index('var FINAL=')+10
F,_=json.JSONDecoder().raw_decode(s[i:]);d=F['ANO']['dre']['LOJA']['MES']
for k in ['ipva','feirao']: print(k, d.get(k))"
```

- Converta cada rótulo do print para o campo com `references/campos.md`.
- **Corrija só linhas-folha.** Subtotais (Custo de Documentos, Despesas com Pessoal...) são calculados no JS.
- Mostre ao usuário uma tabela: campo | atual | print | diferença. Liste só as divergências.
- Se o print for do consolidado e a divergência existir, descubra de qual loja ela vem: compare `mm` e `bk` com os prints de cada loja ou com a API. Não jogue a diferença inteira em `mm` por padrão.
- Campo que aparece no dashboard mas **não existe** no relatório real (ex.: `despesas_postais`, `baixa_gravame`, `garantia_venda` em alguns meses): zerar.

## Passo 3: gravar no update_dashboard.py

Qual dicionário depende do ano:

| Ano | Onde | Observação |
|---|---|---|
| 2026 | `_DRE_CORR[loja]['MES']` | obrigatório, senão o cron reverte |
| 2025 | `_DRE_CORR_2025` | ano **congelado** (902e94a): o cron não reprocessa, então o dict é só registro. O que vale é o FINAL |
| 2024 | `_DRE_CORR_2024` | idem 2025 |

- A chave do mês é string: `'8'`, não `8`.
- Se o mês já tem bloco, edite o valor na linha existente. Se não tem, crie o bloco seguindo o formato dos vizinhos.
- `'cons'` só para correção que não pertence a nenhuma loja (aplicada depois do merge).
- Correção em `mm`/`bk` já propaga para o `cons` no próximo run do cron.

## Passo 4: aplicar no index.html, sem API

```bash
python3 .claude/skills/corrigir-dre/scripts/patch_final.py --ano 2026 --loja mm --mes 8 ipva=15782.50 taxas_transf_ent=4288.00
```

- Por padrão é dry-run: mostra antes → depois e o efeito no cons. Confira a saída e rode de novo com `--apply`.
- Para `mm`/`bk`, o script soma o delta no `cons` e regenera o `var DRE=` (Visão Geral).
- **Não rode `python3 update_dashboard.py` localmente só para isso.** Gasta cota diária da API AutoConf (já esgotou em 07/08/2026).

## Passo 5: commit

Formato do histórico:

```
fix(dre): corrige <campos legíveis> <LOJA> <mes>/<ano> (confere screenshot <loja do print>)

<campo> <antigo> -> <novo>
<campo> <antigo> -> <novo>
<nota: ex. "Cons bate exato: ...", "print enviado era consolidado">
```

- Mês abreviado em minúsculo (jan, fev, ...). Loja: MM / BK / CONS.
- Commit com `update_dashboard.py` e `index.html` juntos.
- **Pergunte antes de `git push`.** O push publica no GitHub Pages.

## Checklist final

- [ ] Loja do print confirmada com o usuário
- [ ] Só linhas-folha alteradas
- [ ] Dict do .py atualizado (2026 obrigatório)
- [ ] patch_final.py rodado com `--apply`, e o cons conferido se houver print do consolidado
- [ ] Commit no formato acima, push só com ok do usuário
