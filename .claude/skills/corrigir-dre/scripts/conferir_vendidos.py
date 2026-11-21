#!/usr/bin/env python3
"""
Conferência automática: custos de carros vendidos depois da última conferência.

A DRE do AutoConf não reconhece custo de carro em estoque. Quando o carro é
vendido, os custos dele (IPVA, taxas, despachante, laudo, preparação, garantia...)
entram na DRE do mês de COMPETÊNCIA de cada lançamento. Por isso a DRE de um mês
já conferido muda depois, e o dashboard (com valores gravados) fica para trás.

Este script lista, para cada mês já fechado, os lançamentos de custo de carros
vendidos a partir de --desde, ou seja, o quanto a DRE daquele mês deve ter subido.
Só lê a API; não altera nada.

Uso:
  python3 .claude/skills/corrigir-dre/scripts/conferir_vendidos.py --desde 16/11/2026
  python3 .claude/skills/corrigir-dre/scripts/conferir_vendidos.py --desde 16/11/2026 --meses 7,8,9

Custo de API: 1 chamada de lucro-venda por mês desde --desde até hoje
+ 1 extrato por mês conferido.

Custo de Preparação e Frete aparecem só como informação (fora do total): a DRE
não move essas contas para o mês de competência. "Quitação de financiamento"
é ignorada (não entra na DRE mesmo lançada em IPVA).
"""
import argparse, csv, io, os, sys
from collections import defaultdict
from datetime import date, datetime

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
sys.path.insert(0, REPO)
import warnings; warnings.filterwarnings('ignore')
import update_dashboard as U  # noqa: E402

LOJA = {U.REV_MM: 'MM', U.REV_BK: 'BK'}
# Contas que a DRE NÃO move para o mês de competência quando o carro é vendido
# (preparação não entrou em jun/jul/set; frete do RVM1B91 foi para o mês da venda).
# Aparecem no relatório só como informação, fora do total esperado.
INFO_CAMPOS = {'custo_prep_entrega', 'frete'}


def _ignorar(ident):
    # "Quitação de financiamento" lançada em IPVA (Renegade SYU0F26, #799824) não
    # entrou na DRE de set/2026 mesmo com o carro vendido.
    i = ident.upper()
    return 'QUITAÇÃO DE FINANCIAMENTO' in i or 'QUITACAO DE FINANCIAMENTO' in i
MESES = ['', 'jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']


def brl(v):
    return f"{v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def vendas_desde(desde, hoje):
    """{placa_norm: (data_saida, negociação, modelo, loja)} das vendas com saída >= desde."""
    out = {}
    y, m = desde.year, desde.month
    while (y, m) <= (hoje.year, hoje.month):
        t = U.api_get('relatorio/financeiro/lucro-venda', m, y)
        if t is None:
            sys.exit(f'erro ao buscar lucro-venda {m:02d}/{y}')
        for r in csv.DictReader(io.StringIO(t)):
            if (r.get('Saida', '') or '').strip().lower() == 'total':
                continue
            d = (r.get('Saida', '') or '').strip()
            try:
                ds = datetime.strptime(d, '%d/%m/%Y').date()
            except ValueError:
                continue
            if ds < desde:
                continue
            pl = U._placa_norm(r.get('Placa'))
            if pl:
                out[pl] = (d, (r.get('Negociação Saida ID', '') or '').strip(),
                           (r.get('Modelo', '') or '').strip(),
                           LOJA.get((r.get('Revenda Saída ID', '') or '').strip(), '?'))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--desde', required=True, help='data da última conferência (DD/MM/AAAA)')
    ap.add_argument('--ano', type=int, default=None, help='ano dos meses conferidos (padrão: ano atual)')
    ap.add_argument('--meses', default=None, help='meses a conferir, ex. 7,8,9 (padrão: todos os fechados)')
    a = ap.parse_args()

    hoje = date.today()
    desde = datetime.strptime(a.desde, '%d/%m/%Y').date()
    ano = a.ano or hoje.year
    meses = ([int(x) for x in a.meses.split(',')] if a.meses
             else list(range(1, (hoje.month if ano == hoje.year else 13))))

    print(f'Vendas a partir de {a.desde}...')
    vendidos = vendas_desde(desde, hoje)
    print(f'  {len(vendidos)} carros vendidos\n')
    if not vendidos:
        return

    total_geral = 0.0
    for m in meses:
        t = U.api_get('relatorio/financeiro/extrato-titulos', m, ano)
        if t is None:
            print(f'{MESES[m]}/{ano}: erro ao buscar extrato')
            continue
        alvo = f'{m:02d}/{ano}'
        por_conta = defaultdict(float)
        linhas = []
        for r in csv.DictReader(io.StringIO(t)):
            if (r.get('Data Competência', '') or '')[3:10] != alvo:
                continue
            conta = (r.get('Conta Contábil', '') or '').strip()
            op = (r.get('Operação', '') or '').strip()
            campo = U._DRE_LOOKUP.get((conta, op))
            if campo not in U._ESTOQUE_CONTAS or U._is_veic_uso(r, conta):
                continue
            ident = (r.get('Identificação', '') or '')
            if _ignorar(ident):
                continue
            placas = [U._placa_norm(x + y) for x, y in U._PLACA_RE.findall(ident.upper())]
            hit = next((p for p in placas if p in vendidos), None)
            if not hit:
                continue
            v = U.parse_num(r.get('Valor', ''))
            loja = LOJA.get((r.get('Revenda Origem Id', '') or '').strip(), '?')
            info = campo in INFO_CAMPOS
            por_conta[(info, conta, loja)] += v
            linhas.append((info, conta, loja, v, hit, vendidos[hit]))
        if not linhas:
            print(f'{MESES[m]}/{ano}: nada mudou')
            continue
        tot = sum(v for (info, _, _), v in por_conta.items() if not info)
        total_geral += tot
        print(f'{MESES[m]}/{ano}: DRE deve ter subido R$ {brl(tot)}')
        for (info, conta, loja), v in sorted(por_conta.items()):
            tag = '  (só informativo: a DRE não costuma mover)' if info else ''
            print(f'    {conta:<34} {loja}  +{brl(v):>10}{tag}')
        for info, conta, loja, v, pl, (d, neg, modelo, lj) in sorted(linhas):
            print(f'      · {conta[:22]:<22} {brl(v):>9}  {modelo} {pl} vendido {d} (#{neg}, {lj})')
        print()
    print(f'Total nos meses conferidos: R$ {brl(total_geral)}')


if __name__ == '__main__':
    main()
