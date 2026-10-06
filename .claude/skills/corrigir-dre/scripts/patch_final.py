#!/usr/bin/env python3
"""Aplica correções de DRE direto no FINAL do index.html, sem chamar a API.

Uso:
  python3 patch_final.py --ano 2026 --loja mm --mes 8 ipva=15782.50 taxas_transf_ent=4288
  (dry-run por padrão; adicione --apply para gravar)

Regras:
  - loja mm/bk: grava o campo na loja e soma o delta no cons do mesmo mês
    (cons = mm + bk + lançamentos de grupo, então o delta propaga 1:1).
  - loja cons: grava só no cons (correção que não pertence a nenhuma loja).
  - Regenera o bloco `var DRE=` (Visão Geral) via build_bi_module.
"""
import argparse, json, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
INDEX = os.path.join(ROOT, 'index.html')
sys.path.insert(0, ROOT)


def load_final(html):
    i = html.index('var FINAL=') + len('var FINAL=')
    final, end = json.JSONDecoder().raw_decode(html[i:])
    return final, i, i + end


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ano', required=True)
    ap.add_argument('--loja', required=True, choices=['mm', 'bk', 'cons'])
    ap.add_argument('--mes', required=True)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('fixes', nargs='+', help='campo=valor')
    a = ap.parse_args()

    with open(INDEX, encoding='utf-8') as f:
        html = f.read()
    final, start, end = load_final(html)

    dre = final.get(a.ano, {}).get('dre', {})
    if a.mes not in dre.get(a.loja, {}):
        sys.exit(f'ERRO: FINAL[{a.ano}].dre.{a.loja} não tem mês {a.mes}')
    loja_m = dre[a.loja][a.mes]
    cons_m = dre['cons'][a.mes]

    print(f'{a.ano} {a.loja} mês {a.mes}' + ('' if a.apply else '  (DRY-RUN)'))
    for fx in a.fixes:
        campo, val = fx.split('=', 1)
        new = round(float(val.replace(',', '.')), 2)
        if campo not in loja_m:
            print(f'  AVISO: campo "{campo}" não existe nesse mês, será criado (confira o nome em references/campos.md)')
        old = loja_m.get(campo, 0)
        delta = round(new - old, 2)
        loja_m[campo] = new
        linha = f'  {campo}: {old:.2f} -> {new:.2f} (delta {delta:+.2f})'
        if a.loja != 'cons':
            c_old = cons_m.get(campo, 0)
            cons_m[campo] = round(c_old + delta, 2)
            linha += f' | cons {c_old:.2f} -> {cons_m[campo]:.2f}'
        print(linha)

    if not a.apply:
        print('Nada gravado. Rode de novo com --apply.')
        return

    from update_dashboard import build_bi_module
    new_json = json.dumps(final, ensure_ascii=False, separators=(',', ':'))
    html = html[:start] + new_json + html[end:]
    html = build_bi_module(html, final)
    with open(INDEX, 'w', encoding='utf-8') as f:
        f.write(html)
    print('index.html gravado (FINAL + var DRE).')


if __name__ == '__main__':
    main()
