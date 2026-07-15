#!/usr/bin/env python3
"""
update_dashboard.py — Atualiza FINAL no index.html via API AutoConf
Competência : lucro-venda  (filtro: mês de saída)
Fluxo de caixa: extrato-titulos (filtro: Data Liquidação no mês, Status=Liquidado)

Uso: python3 update_dashboard.py
"""

import csv, io, json, re, sys
from collections import defaultdict
from datetime import datetime, date

try:
    import requests
except ImportError:
    print("Instalando requests..."); import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

# ── CREDENCIAIS ────────────────────────────────────────────────────────────
TOKEN = "ZU1DsPDbRbva9ccEDF8eRjv7BrkkSwqj96lfrt1z"
AUTH  = "vyOhX5a2LbXG9B2LHDK0I5JUQe51m63rkRlP7crsQHAKIbi4Sugl4z2hSozDl4iakm79HMtIlwRIw3RdZ0ZZ4ZdXTQ0iJnE3qc1HMRbLLZDHKS43TdcrPbwYeqn932PLKCdKOJTw3PJQE8NmUjGSpuT74FxQsJ59R6IaprxVLxX6YG8OmOJOD5dpEY0Y9TqsvwLGZvAnN7Fl2sjQ5v2AnAiAjn0FEdlE3hVp69oENti8hStYmkCstXIuvtz0PpNM"
BASE  = "https://api.autoconf.com.br/api/v1"
YEAR  = 2026
INDEX = "/Users/alvarocrisanto/projetos/dashboard-toronto/index.html"

# Revenda IDs
REV_MM = "185"   # Toronto Corretora E Locadora (Multimarcas)
REV_BK = "726"   # Toronto Black

# ── NORMALIZAÇÃO DE BANCOS ─────────────────────────────────────────────────
BANK_MAP = {
    'BANCO VOTORANTIM S.A.':         'Votorantim',
    'BCO VOTORANTIM S.A.':           'Votorantim',
    'BCO C6 S.A.':                   'C6',
    'BCO SANTANDER (BRASIL) S.A.':   'Santander',
    'BCO BRADESCO S.A.':             'Bradesco',
    'BCO BRADESCO FINANC. S.A.':     'Bradesco',
    'BCO SAFRA S.A.':                'Safra',
    'CARBANK AUTOMOVEIS':            'Carbank',
    'ITAÚ UNIBANCO S.A.':            'Itaú',
    'BCO ITAÚ BBA S.A.':             'Itaú',
    'BANCO PAN':                     'Pan',
    'BCO COOPERATIVO SICREDI S.A.':  'Sicredi',
    'BCO DO BRASIL S.A.':            'Banco do Brasil',
    'IDEALY CORRETORA DE SEGURO':    'Idealy Corretora',
}
BANK_KEYS = ['VOTORANTIM','SANTANDER','SAFRA','BRADESCO','C6 S.A','CARBANK','ITAÚ','ITAU','BANCO PAN','SICREDI','DO BRASIL S.A']

def norm_bank(b):
    b = b.strip()
    return BANK_MAP.get(b, b)

def is_bank(s):
    return any(k in s.upper() for k in BANK_KEYS)

def parse_num(s):
    s = (s or '').strip()
    if not s: return 0.0
    if ',' in s:
        # Brazilian format: "1.141,58" or "32.900,00"
        s = s.replace('.', '').replace(',', '.')
    # else: US/plain format already uses '.' as decimal
    try: return float(s)
    except: return 0.0

def parse_date(s):
    s = (s or '').strip()
    if len(s) == 10:
        try: return datetime.strptime(s, '%d/%m/%Y').date()
        except: pass
    return None

# ── API CALLS ──────────────────────────────────────────────────────────────
def api_get(endpoint, mes, ano):
    r = requests.get(
        f"{BASE}/{endpoint}",
        params={"mes": f"{mes:02d}", "ano": str(ano), "token": TOKEN},
        headers={"authorization": AUTH},
        timeout=30
    )
    t = r.text
    if t.startswith('{'):
        return None  # JSON error
    return t

# ── COMPETÊNCIA: lucro-venda ───────────────────────────────────────────────
def parse_comp(csv_text, store_filter=None):
    """
    Retorna dict: bank -> {fin, ret, q}
    store_filter: None=todos, 'mm'=185, 'bk'=726
    """
    if not csv_text: return {}
    reader = csv.DictReader(io.StringIO(csv_text))
    result = defaultdict(lambda: {'fin':0,'ret':0,'q':0})
    rev_id_col = 'Revenda Saída ID'
    for row in reader:
        if (row.get('Saida','') or '').strip().lower() == 'total':
            continue
        # store filter
        if store_filter:
            rev = (row.get(rev_id_col,'') or '').strip()
            target = REV_MM if store_filter == 'mm' else REV_BK
            if rev != target:
                continue
        banco_raw = (row.get('Banco') or '').strip()
        if not banco_raw: continue
        try: float(banco_raw); continue
        except: pass
        banco = norm_bank(banco_raw)
        fin = parse_num(row.get('Valor Financiado'))
        ret = parse_num(row.get('Retorno'))
        if fin == 0: continue
        result[banco]['fin'] += fin
        result[banco]['ret'] += ret
        result[banco]['q']   += 1
    return dict(result)

# ── FLUXO DE CAIXA: extrato-titulos ───────────────────────────────────────
# Acumula entradas de TODOS os meses; filtra por data de liquidação
_extrato_cache = {}  # (mes,ano) -> csv_text

def fetch_all_extratos(ano, months):
    for m in months:
        key = (m, ano)
        if key not in _extrato_cache:
            print(f"  Extrato {m:02d}/{ano}...", end=" ", flush=True)
            t = api_get("relatorio/financeiro/extrato-titulos", m, ano)
            _extrato_cache[key] = t
            print("ok" if t else "sem dados")

def parse_fluxo_month(target_mes, target_ano, store_filter=None):
    """
    Varre TODOS os extratos em cache.
    Filtra: Data Liquidação == target_mes/target_ano AND Status == Liquidado.
    Conta Contábil financing = 'Vendas de Mercadorias' (ident contém 'Financiamento')
                              + 'Intermediação de financiamento'
    """
    by_fin = defaultdict(float)
    by_ret = defaultdict(float)
    by_q   = defaultdict(int)
    seen_idents_fin = set()  # dedup por ident (evita dupla contagem)

    target_month_str = f"{target_mes:02d}/{target_ano}"

    for (m, ano), csv_text in _extrato_cache.items():
        if not csv_text: continue
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            status   = (row.get('Status','') or '').strip()
            if status != 'Liquidado': continue

            data_liq = (row.get('Data Liquidação','') or '').strip()
            if not data_liq or len(data_liq) < 10: continue
            # formato DD/MM/YYYY → verificar MM/YYYY
            if data_liq[3:10] != target_month_str: continue

            conta    = (row.get('Conta Contábil','') or '').strip()
            op       = (row.get('Operação','') or '').strip()
            ident    = (row.get('Identificação','') or '').strip()
            cliente  = (row.get('Cliente Fornecedor','') or '').strip()
            valor    = parse_num(row.get('Valor',''))
            rev_orig = (row.get('Revenda Origem Id','') or '').strip()
            part_id  = (row.get('Parcela Id','') or '').strip()

            if op != 'A receber': continue
            if not is_bank(cliente): continue

            banco = norm_bank(cliente)

            # store filter
            if store_filter:
                target_rev = REV_MM if store_filter == 'mm' else REV_BK
                if rev_orig != target_rev: continue

            # Valor Financiado
            is_fin = (
                (conta == 'Vendas de Mercadorias' and 'Financiamento' in ident and 'Retorno' not in ident) or
                (conta == 'Intermediação de financiamento')
            )
            # Retorno de Financiamento
            is_ret = (conta == 'Retorno de Financiamento')

            if is_fin:
                key_dedup = f"{banco}|{part_id}|{valor}"
                if key_dedup in seen_idents_fin: continue
                seen_idents_fin.add(key_dedup)
                by_fin[banco] += valor
                by_q[banco]   += 1
            elif is_ret:
                by_ret[banco] += valor

    result = {}
    for b in set(list(by_fin.keys()) + list(by_ret.keys())):
        if by_fin.get(b,0) > 0 or by_ret.get(b,0) > 0:
            result[b] = {
                'fin': round(by_fin.get(b,0), 2),
                'ret': round(by_ret.get(b,0), 2),
                'q':   by_q.get(b,0)
            }
    return result

# ── SEGURO: Comissão de Seguro (extrato-titulos) ──────────────────────────
def parse_seguro_month(target_mes, target_ano, store_filter=None):
    """
    Varre extratos em cache para Conta Contábil='Comissão de Seguro',
    Status=Liquidado, Operação=A receber, filtrado por Data Liquidação.
    Retorna dict: bank -> total
    """
    by_bank = defaultdict(float)
    target_month_str = f"{target_mes:02d}/{target_ano}"

    for (m, ano), csv_text in _extrato_cache.items():
        if not csv_text: continue
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            if (row.get('Conta Contábil','') or '').strip() != 'Comissão de Seguro': continue
            if (row.get('Status','') or '').strip() != 'Liquidado': continue
            if (row.get('Operação','') or '').strip() != 'A receber': continue
            data_liq = (row.get('Data Liquidação','') or '').strip()
            if not data_liq or len(data_liq) < 10: continue
            if data_liq[3:10] != target_month_str: continue
            valor = parse_num(row.get('Valor',''))
            if valor <= 0: continue
            if store_filter:
                rev_orig = (row.get('Revenda Origem Id','') or '').strip()
                target_rev = REV_MM if store_filter == 'mm' else REV_BK
                if rev_orig != target_rev: continue
            banco = norm_bank((row.get('Cliente Fornecedor','') or '').strip())
            by_bank[banco] += valor

    return {b: round(v, 2) for b, v in by_bank.items()}

# ── BUILDER ────────────────────────────────────────────────────────────────
def build_store_comp(months_data):
    """months_data: {mes: {bank: {fin,ret,q}}}"""
    bm = {}
    for mes, banks in months_data.items():
        for bank, v in banks.items():
            if bank not in bm: bm[bank] = {}
            bm[bank][str(mes)] = v

    monthly = {}
    for mes, banks in months_data.items():
        f = sum(v['fin'] for v in banks.values())
        r = sum(v['ret'] for v in banks.values())
        q = sum(v['q']   for v in banks.values())
        if f > 0 or q > 0:
            monthly[str(mes)] = f

    kpi_fin = sum(v['fin'] for banks in months_data.values() for v in banks.values())
    kpi_ret = sum(v['ret'] for banks in months_data.values() for v in banks.values())
    kpi_q   = sum(v['q']   for banks in months_data.values() for v in banks.values())

    fin_by_bank = {}
    for banks in months_data.values():
        for bank, v in banks.items():
            fin_by_bank[bank] = fin_by_bank.get(bank,0) + v['fin']
    fin_by_bank_list = sorted(
        [{'bank': b, 'fin': f} for b,f in fin_by_bank.items()],
        key=lambda x: -x['fin']
    )

    active_months = sorted(m for m,banks in months_data.items() if any(v['fin']>0 for v in banks.values()))

    return {
        'bm': bm,
        'monthly': monthly,
        'finByBank': fin_by_bank_list,
        'months': active_months,
        'kpi': {'fin': round(kpi_fin,2), 'ret': round(kpi_ret,2), 'q': kpi_q}
    }

def build_store_fluxo(months_data):
    """months_data: {mes: {bank: {fin,ret,q}}}"""
    bm = {}
    for mes, banks in months_data.items():
        for bank, v in banks.items():
            if bank not in bm: bm[bank] = {}
            bm[bank][str(mes)] = v

    monthly = {}
    for mes, banks in months_data.items():
        f = sum(v['fin'] for v in banks.values())
        r = sum(v['ret'] for v in banks.values())
        q = sum(v['q']   for v in banks.values())
        if f != 0 or r != 0 or q != 0:
            monthly[str(mes)] = {'fin': round(f,2), 'ret': round(r,2), 'q': q}

    # finByBank as dict (fluxo format)
    fin_by_bank = {}
    for banks in months_data.values():
        for bank, v in banks.items():
            if bank not in fin_by_bank: fin_by_bank[bank] = {'fin':0,'q':0}
            fin_by_bank[bank]['fin'] += v['fin']
            fin_by_bank[bank]['q']   += v['q']

    kpi_fin = sum(v['fin'] for banks in months_data.values() for v in banks.values())
    kpi_q   = sum(v['q']   for banks in months_data.values() for v in banks.values())

    active_months = sorted(m for m,banks in months_data.items() if any(v['fin']!=0 or v['ret']!=0 for v in banks.values()))

    return {
        'bm': bm,
        'monthly': monthly,
        'finByBank': fin_by_bank,
        'months': active_months,
        'kpi': {'fin': round(kpi_fin,2), 'q': kpi_q}
    }

# ── DRE: lucro-venda + extrato por Data Competência ───────────────────────
_DRE_EXT = {
    'retorno_fin':      ('Retorno de Financiamento',        'A receber'),
    'intermediacao_fin':('Intermediação de financiamento', 'A receber'),
    'laudo_venda':      ('Laudo cautelar/venda',           'A receber'),
    'transf_venda':     ('Transferência - venda',          'A receber'),
    'fotos':            ('Fotos Veiculares',                'A receber'),
    'prep_veiculo':     ('Preparação Veícular',             'A receber'),
    'gasolina':         ('Gasolina de Agenciados',          'A receber'),
    'garantia_venda':   ('Garantia',                        'A receber'),
    'aluguel':          ('Receitas com Aluguéis',           'A receber'),
    'rec_diversas':     ('Ajuste de saldo - Entrada',       'A receber'),
    'retorno_acordos':  ('Retorno (Acordos e Plus)',         'A receber'),
    'rendimento':       ('Rendimento de aplicação',          'A receber'),
    'seguro_rec':       ('Comissão de Seguro',               'A receber'),
    'devolucao':        ('Devolução',                        'A pagar'),
    'dev_fin':          ('Devolução - intermediação de financiamento', 'A pagar'),
    'esocial':          ('Darf E-social (INSS e IR)',        'A pagar'),
    'fgts':             ('FGTS',                             'A pagar'),
    'fgts_rescis':      ('FGTS Rescisório',                  'A pagar'),
    'csll_irpj':        ('DARF CSLL E IRPJ',                 'A pagar'),
    'pis_cofins':       ('DARF PIS E COFINS',                'A pagar'),
    'icms':             ('ICMS',                             'A pagar'),
    'iss':              ('ISS',                              'A pagar'),
    'alvara':           ('Taxa de Alvará',                   'A pagar'),
    'fisc_func':        ('Taxa de Fiscalização e Funcionamento', 'A pagar'),
    'iptu':             ('IPTU',                             'A pagar'),
    'retencoes':        ('Darf Retenções Federais',          'A pagar'),
    'custas':           ('Custas e taxas processuais',       'A pagar'),
    'das':              ('Documento de Arrecadação do Simples Nacional (DAS)', 'A pagar'),
    'custo_prep_entrega':('Custo Preparação e Entrega',      'A pagar'),
    'frete':            ('Frete',                            'A pagar'),
    'multa_veiculo':    ('Multa veícular',                   'A pagar'),
    'despachante_ent':  ('Despachante (ENTRADA)',             'A pagar'),
    'despachante_sai':  ('DESPACHANTE (SAIDA)',               'A pagar'),
    'ipva':             ('IPVA',                             'A pagar'),
    'taxas_transf_ent': ('TAXAS DE TRANSFERÊNCIA (ENTRADA)', 'A pagar'),
    'taxas_transf_sai': ('TAXAS DE TRANSFERÊNCIA (SAÍDA)',   'A pagar'),
    'baixa_gravame':    ('Baixa de gravame',                 'A pagar'),
    'comunicado_venda': ('Comunicado de venda',              'A pagar'),
    'multas_nao_abat':  ('Multas não abatidas na compra',    'A pagar'),
    'garantia_custo':   ('Garantia',                         'A pagar'),
    'laudo_custo':      ('Laudo cautelar/custo',             'A pagar'),
    'comissao_venda':   ('Comissão S/ Venda',                'A pagar'),
    'pos_vendas':       ('PÓS-VENDAS',                       'A pagar'),
    'salarios':         ('Salários',                         'A pagar'),
    'refeitorio':       ('Refeitório e Lanches',             'A pagar'),
    'ferias':           ('Férias',                           'A pagar'),
    'rescisao':         ('Rescisão',                         'A pagar'),
    'plano_saude':      ('Plano de Saúde',                   'A pagar'),
    'datas_com':        ('Datas Comemorativas',              'A pagar'),
    'aluguel_cond':     ('Aluguéis e Condomínios',           'A pagar'),
    'copa':             ('Copa e Bar',                       'A pagar'),
    'cartorio':         ('Despesas com Cartório',            'A pagar'),
    'mat_aux':          ('Materiais Auxiliares e Consumo',   'A pagar'),
    'mat_escrit':       ('Material de Escritório',           'A pagar'),
    'seguros':          ('Seguros e Proteções',              'A pagar'),
    'contabil':         ('Serviços Contábeis',               'A pagar'),
    'informatica':      ('Manutenção de sistema / informática', 'A pagar'),
    'manutencao_loja':  ('Manutenção da Loja',               'A pagar'),
    'agua':             ('Água e Esgoto',                    'A pagar'),
    'energia':          ('Energia Elétrica',                 'A pagar'),
    'telefonia':        ('Telefonia e Internet',             'A pagar'),
    'limpeza':          ('Materiais de Higiene e Limpeza',   'A pagar'),
    'emprestimos':      ('Pagamento de Empréstimos - Bancários e de Investidores', 'A pagar'),
    'maq_equip':        ('Bens de Natureza Permanente',      'A pagar'),
    'brindes':          ('Brindes e Presentes',              'A pagar'),
    'publicidade':      ('Propaganda e Publicidade',         'A pagar'),
    'portais':          ('Portais de anúncio',               'A pagar'),
    'feirao':           ('Feirão e eventos de marketing',    'A pagar'),
    'pro_labore':       ('Pró labore',                       'A pagar'),
    'dividendos':       ('Distribuição de dividendos',       'A pagar'),
    'aj_saida':         ('Ajuste de saldo - Saida',          'A pagar'),
    'tarifa_bancaria':  ('Tarifa Bancária',                  'A pagar'),
    'juros_pagar':      ('Juros a pagar (despesa)',          'A pagar'),
    'juros_pagar2':     ('Juros a pagar',                    'A pagar'),
    'associacoes':      ('Associações e Sindicatos',         'A pagar'),
    'transporte':       ('Transporte',                       'A pagar'),
    'uniforme':         ('Uniforme',                         'A pagar'),
    # Receitas adicionais
    'venda_comiss':     ('Venda Comissionada',               'A receber'),
    # Resultado financeiro adicional
    'remuner_bank':     ('Remuneração Bancária - TIME',      'A receber'),
    'retorno_comiss':   ('Retorno / Comissões / Acordos',    'A receber'),
    'juros_rec':        ('Juros a receber (receita)',         'A receber'),
    # Despesas operacionais adicionais
    'viagens':          ('Viagens e Representações',         'A pagar'),
    'comissao_c':       ('Comissão c/ venda',                'A pagar'),
    'aluguel_cond2':    ('Aluguéis e Condominios',           'A pagar'),
    'consultoria':      ('Serviços Consultoria',             'A pagar'),
    'juridico':         ('Serviços Advocatícios',            'A pagar'),
    'churrasco':        ('Churrasco por Meta',               'A pagar'),
    'almoco_meta':      ('Almoço Meta Diamante',             'A pagar'),
    'compras_func':     ('Compras - Funcionários',           'A pagar'),
    'cursos':           ('Cursos e treinamentos',            'A pagar'),
    'medicina':         ('Medicina do Trabalho - ASO',       'A pagar'),
    'estacionamento':   ('Estacionamento',                   'A pagar'),
    'iof':              ('IOF',                              'A pagar'),
    'pecld_rec':        ('PECLD Recuperação de perda reconhecida por inadimplência', 'A receber'),
}
_DRE_LOOKUP = {(conta, op): field for field, (conta, op) in _DRE_EXT.items()}

# ── CORREÇÕES MANUAIS (sobrescrevem dados da API por mês) ──────────────────
# 'mm'/'bk': aplicado antes do merge → afeta cons automaticamente
# 'cons': aplicado após merge (quando não faz sentido dividir entre lojas)
_DRE_CORR = {
    'mm': {},
    'bk': {},
    'cons': {
        '1': {'rec_doc_sai': 12518.20, 'rec_svc': 9521.40, 'prep_veiculo': 1000.0, 'custo_prep_entrega': 93152.51, 'frete': 130.0, 'multa_veiculo': 0.0, 'despachante_ent': 3770.0, 'taxas_transf_ent': 6395.18, 'comunicado_venda': 293.13, 'laudo_custo': 4072.10, 'despachante_sai': 0.0, 'salarios': 101675.32},
        '2': {'rec_doc_sai': 16323.66, 'rec_svc': 5720.0, 'desc_sw': 72545.50, 'custo_prep_entrega': 63811.0, 'frete': 600.0, 'despachante_ent': 1460.0, 'ipva': 18414.83, 'taxas_transf_ent': 11702.84, 'baixa_gravame': 40.0, 'laudo_custo': 3025.0, 'despachante_sai': 0.0},
        '3': {'rec_doc_sai': 25043.25, 'rec_svc': 10030.0, 'rec_diversas': 15554.90, 'desc_sw': 118306.96, 'desc_at': 42900.0, 'custo_prep_entrega': 80624.66, 'frete': 0.0, 'despachante_ent': 2300.0, 'ipva': 30297.31, 'taxas_transf_ent': 5793.22, 'comunicado_venda': 149.90, 'laudo_custo': 2620.20, 'despachante_sai': 0.0},
        '4': {'rec_svc': 7300.0, 'laudo_venda': 9775.90, 'custo_prep_entrega': 40676.10, 'frete': 0.0, 'despachante_ent': 2150.0, 'ipva': 27580.05, 'taxas_transf_ent': 6938.16, 'multas_nao_abat': 104.13, 'laudo_custo': 5156.70, 'taxas_transf_sai': 14389.08, 'despachante_sai': 0.0, 'compras_func': 0.0},
        '5': {'rec_svc': 6314.0, 'desc_sw': 125020.01, 'desc_at': 20782.0, 'custo_prep_entrega': 57438.43, 'frete': 80.0, 'despachante_ent': 700.0, 'ipva': 40485.04, 'taxas_transf_ent': 3711.0, 'laudo_custo': 2470.50, 'despachante_sai': 0.0, 'compras_func': 0.0},
        '6': {'rec_doc_sai': 5310.40, 'rec_svc': 7000.0, 'fotos': 4250.0, 'custo_prep_entrega': 50890.65, 'frete': 0.0, 'despachante_ent': 1200.0, 'ipva': 16883.52, 'taxas_transf_ent': 2306.0, 'laudo_custo': 1977.10, 'despachante_sai': 0.0, 'compras_func': 0.0},
        '7': {'rec_svc': 4550.0, 'aluguel': 9000.0, 'garantia_venda': 1650.0, 'rec_diversas': 15554.90, 'custo_prep_entrega': 46554.22, 'frete': 0.0, 'despachante_ent': 500.0, 'ipva': 4655.73, 'taxas_transf_ent': 1814.0, 'laudo_custo': 903.30, 'despachante_sai': 0.0, 'compras_func': 0.0, 'medicina': 20.0, 'almoco_meta': 457.44, 'taxas_transf_sai': 11004.06},
    },
}

def apply_dre_corrections(raw, store):
    corr = _DRE_CORR.get(store, {})
    for mes_str, fixes in corr.items():
        if mes_str in raw:
            raw[mes_str].update(fixes)

def parse_lv_dre(csv_text, rev):
    d = defaultdict(float)
    d['q'] = 0
    if not csv_text: return d
    for row in csv.DictReader(io.StringIO(csv_text)):
        if (row.get('Saida','') or '').strip().lower() == 'total': continue
        if (row.get('Revenda Saída ID','') or '').strip() != rev: continue
        tipo = (row.get('Tipo Venda','') or '').strip()
        sw = tipo != 'Atacado'
        vb    = parse_num(row.get('Venda Bruta','') or '') if '.' in (row.get('Venda Bruta','') or '') else 0
        # lucro-venda uses US decimal
        def pus(s): s=(s or '').strip(); return float(s) if s else 0.0
        vb    = pus(row.get('Venda Bruta'))
        desc  = pus(row.get('Valor Desconto'))
        compra= pus(row.get('Compra'))
        ret   = pus(row.get('Retorno'))
        custos= pus(row.get('Custos'))
        rec_ds= pus(row.get('Receita com Documentos Saída'))
        rec_de= pus(row.get('Receita com Documentos Entrada'))
        rec_se= pus(row.get('Receita com Serviços Agregados Entrada'))
        rec_ss= pus(row.get('Receita com Serviços Agregados Saída'))
        rec_sa= pus(row.get('Receita com Serviços Agregados'))
        if vb <= 0 and compra <= 0: continue
        d['q'] += 1
        if sw:
            d['merch_bruta_sw'] += vb;  d['desc_sw']  += desc;  d['custo_compra_sw'] += compra
        else:
            d['merch_bruta_at'] += vb;  d['desc_at']  += desc;  d['custo_compra_at'] += compra
        d['rec_doc_sai']   += rec_ds + rec_de
        d['rec_svc']       += rec_se + rec_ss + rec_sa
    return d

def parse_ext_dre(rev, target_mes, target_ano):
    d = defaultdict(float)
    seen = set()
    target_str = f"{target_mes:02d}/{target_ano}"
    for (m, ano), csv_text in _extrato_cache.items():
        if not csv_text: continue
        for row in csv.DictReader(io.StringIO(csv_text)):
            if (row.get('Revenda Origem Id','') or '').strip() != rev: continue
            dc = (row.get('Data Competência','') or '').strip()
            if not dc or len(dc) < 7 or dc[3:10] != target_str: continue
            conta = (row.get('Conta Contábil','') or '').strip()
            op    = (row.get('Operação','') or '').strip()
            valor = parse_num(row.get('Valor',''))
            if valor == 0: continue
            field = _DRE_LOOKUP.get((conta, op))
            if not field and conta == 'Venda Comissionada':
                field = 'venda_comiss'
            if not field: continue
            pid = (row.get('Parcela Id','') or '').strip()
            key = (pid, conta, op, valor) if pid else None
            if key and key in seen: continue
            if key: seen.add(key)
            d[field] += valor
    return d

def parse_ext_dre_group(target_mes, target_ano):
    """Captures extrato entries with blank Revenda Origem Id (group-level entries).
    These are not attributed to a specific store but belong to the consolidated view."""
    d = defaultdict(float)
    seen = set()
    target_str = f"{target_mes:02d}/{target_ano}"
    for (m, ano), csv_text in _extrato_cache.items():
        if not csv_text: continue
        for row in csv.DictReader(io.StringIO(csv_text)):
            if (row.get('Revenda Origem Id','') or '').strip() != '': continue
            dc = (row.get('Data Competência','') or '').strip()
            if not dc or len(dc) < 7 or dc[3:10] != target_str: continue
            conta = (row.get('Conta Contábil','') or '').strip()
            op    = (row.get('Operação','') or '').strip()
            valor = parse_num(row.get('Valor',''))
            if valor == 0: continue
            field = _DRE_LOOKUP.get((conta, op))
            if not field and conta == 'Venda Comissionada':
                field = 'venda_comiss'
            if not field: continue
            pid = (row.get('Parcela Id','') or '').strip()
            key = (pid, conta, op, valor) if pid else None
            if key and key in seen: continue
            if key: seen.add(key)
            d[field] += valor
    return d

# ── MAIN ───────────────────────────────────────────────────────────────────
def main():
    today = date.today()
    # months to fetch: all months up to current
    active_months = [m for m in range(1, 13) if date(YEAR, m, 1) <= today]
    if not active_months:
        print("Sem meses ativos."); return

    print(f"=== Atualizando dashboard {YEAR} — {len(active_months)} meses ===")
    print(f"Data atual: {today.strftime('%d/%m/%Y')}")

    # ── 1. COMPETÊNCIA (lucro-venda) ──────────────────────────────────────
    print("\n[1/3] Buscando lucro-venda (competência)...")
    comp_mm_raw = {}; comp_bk_raw = {}
    _lv_cache = {}  # m -> csv_text (reused for DRE)
    for m in active_months:
        print(f"  lucro-venda {m:02d}/{YEAR}...", end=" ", flush=True)
        txt = api_get("relatorio/financeiro/lucro-venda", m, YEAR)
        if txt:
            _lv_cache[m] = txt
            mm = parse_comp(txt, store_filter='mm')
            bk = parse_comp(txt, store_filter='bk')
            if mm: comp_mm_raw[m] = mm
            if bk: comp_bk_raw[m] = bk
            print(f"MM:{sum(v['q'] for v in mm.values())}veic BK:{sum(v['q'] for v in bk.values())}veic")
        else:
            print("sem dados")

    comp_mm   = build_store_comp(comp_mm_raw)
    comp_bk   = build_store_comp(comp_bk_raw)
    # cons = mm + bk merged
    cons_comp_raw = {}
    for m in active_months:
        mm = comp_mm_raw.get(m, {}); bk = comp_bk_raw.get(m, {})
        merged = defaultdict(lambda: {'fin':0,'ret':0,'q':0})
        for bank, v in mm.items():
            merged[bank]['fin'] += v['fin']
            merged[bank]['ret'] += v['ret']
            merged[bank]['q']   += v['q']
        for bank, v in bk.items():
            merged[bank]['fin'] += v['fin']
            merged[bank]['ret'] += v['ret']
            merged[bank]['q']   += v['q']
        if merged: cons_comp_raw[m] = dict(merged)
    comp_cons = build_store_comp(cons_comp_raw)

    # ── 2. FLUXO DE CAIXA (extrato-titulos) ──────────────────────────────
    print("\n[2/3] Buscando extrato-titulos (fluxo de caixa)...")
    # Fetch all months into cache
    fetch_all_extratos(YEAR, active_months)
    # Also fetch previous month (entries de mês anterior liquidadas no mês atual)
    if active_months[0] > 1:
        fetch_all_extratos(YEAR, [active_months[0] - 1])
    if YEAR > 2024:
        fetch_all_extratos(YEAR - 1, [12])

    fluxo_mm_raw = {}; fluxo_bk_raw = {}
    for m in active_months:
        print(f"  Agregando fluxo {m:02d}/{YEAR} (MM)...", end=" ", flush=True)
        mm = parse_fluxo_month(m, YEAR, store_filter='mm')
        bk = parse_fluxo_month(m, YEAR, store_filter='bk')
        if mm: fluxo_mm_raw[m] = mm
        if bk: fluxo_bk_raw[m] = bk
        tf = sum(v['fin'] for v in mm.values())
        print(f"fin=R${tf:,.0f} q={sum(v['q'] for v in mm.values())}")

    fluxo_mm   = build_store_fluxo(fluxo_mm_raw)
    fluxo_bk   = build_store_fluxo(fluxo_bk_raw)

    # Seguro: parse Comissão de Seguro (extrato já em cache)
    seguro_mm_raw = {}; seguro_bk_raw = {}
    for m in active_months:
        mm_s = parse_seguro_month(m, YEAR, store_filter='mm')
        bk_s = parse_seguro_month(m, YEAR, store_filter='bk')
        if mm_s: seguro_mm_raw[str(m)] = mm_s
        if bk_s: seguro_bk_raw[str(m)] = bk_s

    seguro_cons_raw = {}
    all_seg_months = set(seguro_mm_raw) | set(seguro_bk_raw)
    for mes in all_seg_months:
        merged = defaultdict(float)
        for b, v in seguro_mm_raw.get(mes, {}).items():
            merged[b] += v
        for b, v in seguro_bk_raw.get(mes, {}).items():
            merged[b] += v
        seguro_cons_raw[mes] = {b: round(v, 2) for b, v in merged.items()}

    seguro_final = {
        'mm':   seguro_mm_raw,
        'bk':   seguro_bk_raw,
        'cons': seguro_cons_raw,
    }

    cons_fluxo_raw = {}
    for m in active_months:
        mm = fluxo_mm_raw.get(m, {}); bk = fluxo_bk_raw.get(m, {})
        merged = defaultdict(lambda: {'fin':0,'ret':0,'q':0})
        for bank, v in mm.items():
            merged[bank]['fin'] += v['fin']
            merged[bank]['ret'] += v['ret']
            merged[bank]['q']   += v['q']
        for bank, v in bk.items():
            merged[bank]['fin'] += v['fin']
            merged[bank]['ret'] += v['ret']
            merged[bank]['q']   += v['q']
        if merged: cons_fluxo_raw[m] = dict(merged)
    fluxo_cons = build_store_fluxo(cons_fluxo_raw)

    # ── 2b. DRE (lucro-venda por competência + extrato por Data Competência) ─
    print("\n[2b] Computando DRE...")
    dre_mm_raw = {}; dre_bk_raw = {}
    for m in active_months:
        txt = _lv_cache.get(m, '')
        lv_mm = parse_lv_dre(txt, REV_MM)
        lv_bk = parse_lv_dre(txt, REV_BK)
        ex_mm = parse_ext_dre(REV_MM, m, YEAR)
        ex_bk = parse_ext_dre(REV_BK, m, YEAR)
        def merge_dre(a, b):
            d = dict(a)
            for k, v2 in b.items(): d[k] = round(d.get(k, 0) + v2, 2)
            return d
        dre_mm_raw[str(m)] = merge_dre(lv_mm, ex_mm)
        dre_bk_raw[str(m)] = merge_dre(lv_bk, ex_bk)
        print(f"  {m:02d}/{YEAR} MM:{dre_mm_raw[str(m)].get('q',0):.0f}v BK:{dre_bk_raw[str(m)].get('q',0):.0f}v")
    apply_dre_corrections(dre_mm_raw, 'mm')
    apply_dre_corrections(dre_bk_raw, 'bk')
    dre_cons_raw = {}
    for m in [str(x) for x in active_months]:
        all_keys = set(dre_mm_raw.get(m,{}).keys()) | set(dre_bk_raw.get(m,{}).keys())
        dre_cons_raw[m] = {k: round(dre_mm_raw.get(m,{}).get(k,0)+dre_bk_raw.get(m,{}).get(k,0),2) for k in all_keys}
        # Add group-level extrato entries (blank Revenda Origem Id) to consolidated only
        grp = parse_ext_dre_group(int(m), YEAR)
        for k, v in grp.items():
            dre_cons_raw[m][k] = round(dre_cons_raw[m].get(k, 0) + v, 2)
        # Consolidated netting: if CONS inter == CONS devf (within 1.0), both are
        # intercompany pass-throughs that cancel at group level → zero all three stores
        cons = dre_cons_raw[m]
        ci = cons.get('intermediacao_fin', 0)
        cd = cons.get('dev_fin', 0)
        if ci > 0 and cd > 0 and abs(ci - cd) < 1.0:
            for store in (cons, dre_mm_raw[m], dre_bk_raw[m]):
                store['intermediacao_fin'] = 0
                store['dev_fin'] = 0
    apply_dre_corrections(dre_cons_raw, 'cons')

    # ── 3. MONTAR FINAL E ATUALIZAR INDEX.HTML ────────────────────────────
    print("\n[3/3] Atualizando index.html...")

    with open(INDEX, 'r', encoding='utf-8') as f:
        html = f.read()

    m = re.search(r'var FINAL=(\{.*?\});', html, re.DOTALL)
    if not m:
        print("ERRO: var FINAL não encontrado em index.html"); return

    old_final = json.loads(m.group(1))

    # Preserve gvop / acordo / seguro (não vêm do lucro-venda nem extrato)
    new_final = {
        'generated': today.strftime('%d/%m/%Y'),
        'comp': {
            'mm':   comp_mm,
            'bk':   comp_bk,
            'cons': comp_cons,
        },
        'fluxo': {
            'mm':   fluxo_mm,
            'bk':   fluxo_bk,
            'cons': fluxo_cons,
        },
        'gvop':   old_final.get('gvop', {}),
        'acordo': old_final.get('acordo', {}),
        'seguro': seguro_final,
        'dre':    {'mm': dre_mm_raw, 'bk': dre_bk_raw, 'cons': dre_cons_raw},
    }

    new_json = json.dumps(new_final, ensure_ascii=False, separators=(',', ':'))
    new_html = html[:m.start(1)] + new_json + html[m.end(1):]

    with open(INDEX, 'w', encoding='utf-8') as f:
        f.write(new_html)

    print(f"✓ index.html atualizado — gerado em {today.strftime('%d/%m/%Y')}")
    print(f"\nResumo COMP (cons):")
    print(f"  Total financiado: R${comp_cons['kpi']['fin']:,.2f}")
    print(f"  Total retorno:    R${comp_cons['kpi']['ret']:,.2f}")
    print(f"  Total veículos:   {comp_cons['kpi']['q']}")
    print(f"\nResumo FLUXO (mm):")
    for m_num in active_months:
        fd = fluxo_mm['monthly'].get(str(m_num), {})
        if fd:
            print(f"  Mês {m_num:02d}: fin=R${fd.get('fin',0):,.0f} ret=R${fd.get('ret',0):,.0f} q={fd.get('q',0)}")

if __name__ == '__main__':
    main()
