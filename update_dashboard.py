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
INDEX = __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'index.html')

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
    'BANCO CREDICARRO S.A.':         'Credicarro',
    'BANCO CREDICARRO':              'Credicarro',
    'Banco Credicarro S.A.':         'Credicarro',
    'Banco Credicarro':              'Credicarro',
    'CREDICARRO':                    'Credicarro',
    'IDEALY CORRETORA DE SEGURO':    'Idealy Corretora',
}
BANK_KEYS = ['VOTORANTIM','SANTANDER','SAFRA','BRADESCO','C6 S.A','CARBANK','ITAÚ','ITAU','BANCO PAN','SICREDI','DO BRASIL S.A','CREDICARRO']

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
    'venda_svc':        ('Venda de serviços',                'A receber'),
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
    'desc_pagar':       ('Descontos a Pagar',                'A receber'),
    'desc_receber':     ('Descontos a Receber',              'A pagar'),
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

# ── COMP MANUAL: entradas de financiamento ausentes na API ─────────────────
# Estrutura: {year: {'mm': {mes: {banco: {fin,ret,q}}}, 'bk': {...}}}
# Aplicado ANTES de build_store_comp; valores somados ao existente.
_COMP_MANUAL = {
    2026: {
        'mm': {
            7: {
                'Itaú':      {'fin': 32900.00, 'ret': 0, 'q': 1},  # BCO ITAÚ BBA S.A. ausente na API
                'Santander': {'fin': 10000.00, 'ret': 0, 'q': 1},  # pago 31/07 ausente na API
            },
            8: {
                'Itaú': {'fin': 60000.00, 'ret': 0, 'q': 1},  # Intermediação #6505 BCO ITAÚ BBA S.A. liq 12/08 ausente no lucro-venda
            },
        },
        'bk': {},
    },
}

# Mesma estrutura que _COMP_MANUAL mas para o fluxo de caixa (liquidação)
_FLUXO_MANUAL = {
    2026: {
        'mm': {
            1: {
                'Safra':     {'fin': 34900.00, 'ret': 0, 'q': 1},  # #577912 Ford Ranger PKI9427 - Ajuste de saldo não capturado pelo script
            },
            3: {
                'Bradesco':  {'fin': 84953.00, 'ret': 0, 'q': 1},  # #622927 Consórcio BRADESCO CONS. LTDA. 26/03 — filtro exige 'Financiamento' no ident
            },
            7: {
                'Santander': {'fin': 10000.00, 'ret': 0, 'q': 1},  # pago 31/07 ausente na API (LTW9I01 já está no extrato jul)
            },
            8: {}
        },
        'bk': {},
    },
}

def _apply_manual(raw, store_key, year, manual_dict):
    manual = manual_dict.get(year, {}).get(store_key, {})
    for mes, banks in manual.items():
        if mes not in raw:
            raw[mes] = {}
        for bank, v in banks.items():
            if bank in raw[mes]:
                raw[mes][bank]['fin'] += v['fin']
                raw[mes][bank]['ret'] += v.get('ret', 0)
                raw[mes][bank]['q']   += v.get('q', 0)
            else:
                raw[mes][bank] = {k: v2 for k, v2 in v.items()}

def apply_comp_manual(comp_raw, store_key, year):
    _apply_manual(comp_raw, store_key, year, _COMP_MANUAL)

def apply_fluxo_manual(fluxo_raw, store_key, year):
    _apply_manual(fluxo_raw, store_key, year, _FLUXO_MANUAL)

# ── CORREÇÕES MANUAIS (sobrescrevem dados da API por mês) ──────────────────
# 'mm'/'bk': aplicado antes do merge → afeta cons automaticamente
# 'cons': aplicado após merge (quando não faz sentido dividir entre lojas)
_DRE_CORR = {
    'mm': {

        '1': {
            # RECEITAS
            'merch_bruta_sw': 2695797.02, 'merch_bruta_at': 644384.00,
            'intermediacao_fin': 234100.00, 'laudo_venda': 2765.00, 'transf_venda': 0.00,
            'fotos': 100.00, 'prep_veiculo': 1000.00, 'gasolina': 210.00,
            'rec_doc_sai': 9728.39, 'rec_svc': 8921.40, 'venda_comiss': 16419.22,
            'aluguel': 16000.00, 'rec_diversas': 17012.00,
            # DEDUÇÕES
            'desc_sw': 40474.42, 'desc_at': 26346.00, 'esocial': 3275.75, 'fgts': 4695.63,
            'pis_cofins': 9073.67, 'icms': 6952.00, 'iss': 8628.18, 'fisc_func': 189.00,
            'iptu': 2143.92, 'custas': 177.25, 'das': 3051.41, 'dev_fin': 228479.61,
            # CUSTOS
            'custo_compra_sw': 2263587.00, 'custo_compra_at': 559000.00,
            'custo_prep_entrega': 83987.59, 'frete': 130.00, 'multa_veiculo': 0.00,
            'despachante_ent': 3370.00, 'ipva': 13396.94, 'taxas_transf_ent': 5633.18,
            'comunicado_venda': 293.13, 'multas_nao_abat': 264.29, 'garantia_custo': 9070.00,
            'laudo_custo': 3081.60,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 600.00, 'comissao_c': 3140.65, 'pos_vendas': 7433.35,
            'taxas_transf_sai': 11184.74, 'despachante_sai': 0.00, 'salarios': 83976.32,
            'ferias': 2886.60, 'rescisao': 5435.52, 'plano_saude': 91.80, 'refeitorio': 300.00,
            'transporte': 821.98, 'uniforme': 3139.40, 'medicina': 80.00,
            'almoco_meta': 403.93, 'copa': 166.56, 'cartorio': 376.87, 'mat_aux': 99.05,
            'mat_escrit': 614.26, 'seguros': 1280.15, 'contabil': 3000.00,
            'informatica': 1499.00, 'associacoes': 250.00, 'consultoria': 1800.00,
            'juridico': 7000.00, 'viagens': 40470.68, 'estacionamento': 0.00,
            'aluguel_cond': 25550.00, 'agua': 0.00, 'telefonia': 601.18, 'limpeza': 661.45,
            'manutencao_loja': 761.28, 'publicidade': 14493.90, 'feirao': 11055.80,
            'brindes': 3182.93, 'pro_labore': 0.00, 'dividendos': 66700.00,
            'emprestimos': 28171.28, 'aj_saida': 5706.55,
            # RES. FINANCEIRO
            'retorno_fin': 27013.74, 'retorno_acordos': 9119.32, 'rendimento': 209.20,
            'seguro_rec': 5837.69, 'remuner_bank': 1635.41, 'retorno_comiss': 4493.39,
            'juros_rec': 46.88, 'desc_pagar': 26668.25, 'tarifa_bancaria': 706.32,
            'juros_pagar': 14.68, 'iof': 52.08, 'desc_receber': 0.00,
            # QTD/OUTROS
            'q': 49, 'q_sw': 34.00, 'q_at': 15.00, 'q_consig': 18.00, 'q_proprio': 31.00,
            # OUTROS
            'garantia_venda': 100.50,
        },
        '2': {
            # RECEITAS
            'merch_bruta_sw': 2233169.84, 'merch_bruta_at': 292000.00,
            'intermediacao_fin': 169072.40, 'laudo_venda': 4048.70, 'transf_venda': 450.00,
            'fotos': 650.00, 'prep_veiculo': 414.00, 'gasolina': 630.08,
            'rec_doc_sai': 14241.12, 'rec_svc': 4670.00, 'venda_comiss': 7200.11,
            'aluguel': 16000.00, 'rec_diversas': 53505.18,
            # DEDUÇÕES
            'desc_sw': 48327.50, 'desc_at': 11780.00, 'esocial': 3058.91, 'fgts': 4577.32,
            'pis_cofins': 8154.14, 'icms': 6547.50, 'iss': 7558.81, 'iptu': 2143.92,
            'das': 4155.39, 'devolucao': 50.00, 'dev_fin': 169072.40,
            # CUSTOS
            'custo_compra_sw': 1888289.84, 'custo_compra_at': 258000.00,
            'custo_prep_entrega': 59404.98, 'frete': 100.00, 'despachante_ent': 1160.00,
            'ipva': 12568.52, 'taxas_transf_ent': 4452.24, 'baixa_gravame': 0.00,
            'comunicado_venda': 106.90, 'multas_nao_abat': 159.46, 'garantia_custo': 4570.00,
            'laudo_custo': 2545.00,
            # DESPESAS OPERACIONAIS
            'comissao_c': 24364.89, 'pos_vendas': 5655.23, 'taxas_transf_sai': 11717.38,
            'despachante_sai': 0.00, 'salarios': 108334.61, 'rescisao': 910.02,
            'plano_saude': 91.80, 'datas_com': 5.00, 'refeitorio': 358.00,
            'transporte': 507.98, 'medicina': 40.00, 'copa': 378.69, 'cartorio': 199.96,
            'mat_aux': 600.00, 'mat_escrit': 630.06, 'seguros': 1280.09, 'contabil': 3203.70,
            'informatica': 1595.95, 'associacoes': 250.00, 'consultoria': 2925.00,
            'juridico': 1550.00, 'estacionamento': 18.00, 'aluguel_cond': 25550.00,
            'energia': 65.39, 'telefonia': 614.86, 'limpeza': 148.27,
            'manutencao_loja': 644.99, 'publicidade': 19993.44, 'feirao': 16448.21,
            'brindes': 800.00, 'pro_labore': 0.00, 'dividendos': 54000.00,
            'emprestimos': 27039.35, 'aj_saida': 44750.22, 'maq_equip': 265.99,
            # RES. FINANCEIRO
            'retorno_fin': 22028.78, 'retorno_acordos': 23835.79, 'rendimento': 241.21,
            'seguro_rec': 16862.87, 'juros_rec': 379.35, 'pecld_rec': 2000.00,
            'desc_pagar': 15489.14, 'tarifa_bancaria': 542.42, 'juros_pagar2': 43.49,
            'desc_receber': 291.40,
            # QTD/OUTROS
            'q': 37, 'q_sw': 30.00, 'q_at': 7.00, 'q_consig': 14.00, 'q_proprio': 23.00,
            # OUTROS
            'garantia_venda': 107.10,
        },
        '3': {
            # RECEITAS
            'merch_bruta_sw': 3000677.00, 'merch_bruta_at': 616210.00,
            'intermediacao_fin': 216876.29, 'laudo_venda': 5804.40, 'transf_venda': 480.16,
            'fotos': 850.00, 'prep_veiculo': 2000.00, 'gasolina': 330.00,
            'rec_doc_sai': 22639.05, 'rec_svc': 8380.00, 'venda_comiss': 14612.09,
            'aluguel': 20500.00, 'rec_diversas': 15500.00,
            # DEDUÇÕES
            'desc_sw': 87946.96, 'desc_at': 38900.00, 'esocial': 3087.59, 'fgts': 5277.84,
            'pis_cofins': 14767.96, 'icms': 8689.26, 'iss': 15492.55, 'alvara': 398.75,
            'iptu': 2143.92, 'das': 4099.07, 'dev_fin': 205900.00,
            # CUSTOS
            'custo_compra_sw': 2517340.00, 'custo_compra_at': 539310.32,
            'custo_prep_entrega': 74891.91, 'frete': 0.00, 'despachante_ent': 2300.00,
            'ipva': 20108.70, 'taxas_transf_ent': 5914.31, 'baixa_gravame': 11376.29,
            'comunicado_venda': 135.90, 'multas_nao_abat': 131.46, 'garantia_custo': 9690.00,
            'laudo_custo': 2375.40,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 1000.00, 'comissao_c': 3681.16, 'pos_vendas': 5448.68,
            'taxas_transf_sai': 13356.16, 'despachante_sai': 0.00, 'salarios': 90376.44,
            'plano_saude': 91.80, 'datas_com': 208.88, 'refeitorio': 704.44,
            'transporte': 423.20, 'medicina': 40.00, 'churrasco': 3024.66,
            'almoco_meta': 669.90, 'aluguel_cond2': 20550.00, 'copa': 1608.96,
            'cartorio': 366.64, 'mat_aux': 85.19, 'mat_escrit': 701.83, 'seguros': 2682.37,
            'contabil': 2000.00, 'informatica': 2445.95, 'associacoes': 250.00,
            'consultoria': 1800.00, 'estacionamento': 16.00, 'pub_adm': 1200.00,
            'aluguel_cond': 5000.00, 'agua': 0.00, 'energia': 932.21, 'telefonia': 612.20,
            'limpeza': 446.35, 'manutencao_loja': 130.00, 'publicidade': 7949.94,
            'portais': 8040.90, 'brindes': 40.00, 'pro_labore': 0.00, 'dividendos': 64000.00,
            'emprestimos': 25738.82, 'maq_equip': 3130.00,
            # RES. FINANCEIRO
            'retorno_fin': 24137.05, 'retorno_acordos': 18142.38, 'rendimento': 378.32,
            'seguro_rec': 246.34, 'remuner_bank': 1741.50, 'juros_rec': 60.34,
            'pecld_rec': 2000.00, 'desc_pagar': 11879.93, 'tarifa_bancaria': 139.24,
            'juros_pagar': 2201.80, 'juros_pagar2': 12.63, 'desc_receber': 65.01,
            # QTD/OUTROS
            'q': 51, 'q_sw': 36.00, 'q_at': 15.00, 'q_consig': 13.00, 'q_proprio': 38.00,
            # OUTROS
            'garantia_venda': 167.85,
        },
        '4': {
            # RECEITAS
            'merch_bruta_sw': 1726400.01, 'merch_bruta_at': 263500.00,
            'intermediacao_fin': 67900.00, 'laudo_venda': 7553.20, 'transf_venda': 60.00,
            'fotos': 2200.00, 'prep_veiculo': 2520.00, 'gasolina': 390.00,
            'rec_doc_sai': 16210.90, 'rec_svc': 6950.00, 'venda_comiss': 10816.10,
            'aluguel': 19083.35, 'rec_diversas': 15544.99,
            # DEDUÇÕES
            'desc_sw': 43190.17, 'desc_at': 3500.00, 'esocial': 3479.42, 'fgts': 5529.50,
            'csll_irpj': 93601.19, 'pis_cofins': 8477.19, 'icms': 10111.00, 'iss': 6358.10,
            'fisc_func': 189.00, 'iptu': 2143.92, 'das': 5294.23, 'devolucao': 0.00,
            'dev_fin': 67900.00,
            # CUSTOS
            'custo_compra_sw': 1437080.00, 'custo_compra_at': 229060.36,
            'custo_prep_entrega': 38110.65, 'frete': 0.00, 'despachante_ent': 2050.00,
            'ipva': 23060.09, 'taxas_transf_ent': 6828.16, 'baixa_gravame': 400.00,
            'comunicado_venda': 81.90, 'multas_nao_abat': 0.00, 'garantia_custo': 6260.00,
            'laudo_custo': 4319.60,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 500.00, 'comissao_c': 600.00, 'pos_vendas': 7250.00,
            'taxas_transf_sai': 11735.08, 'despachante_sai': 0.00, 'salarios': 113722.79,
            'ferias': 3651.05, 'rescisao': 993.08, 'fgts_rescis': 941.00, 'plano_saude': 91.80,
            'refeitorio': 30.00, 'transporte': 1412.32, 'cursos': 1297.00,
            'almoco_meta': 1000.00, 'copa': 94.32, 'cartorio': 688.82, 'mat_aux': 358.88,
            'mat_escrit': 3080.25, 'seguros': 0.00, 'contabil': 2000.00,
            'informatica': 2445.95, 'associacoes': 250.00, 'consultoria': 1800.00,
            'viagens': 1616.05, 'pub_adm': 1200.00, 'aluguel_cond': 25550.00, 'agua': 0.00,
            'energia': 354.20, 'telefonia': 583.53, 'limpeza': 379.92,
            'manutencao_loja': 223.10, 'publicidade': 9299.00, 'portais': 8040.90,
            'feirao': 13105.96, 'pro_labore': 0.00, 'dividendos': 55174.64,
            'emprestimos': 26110.95, 'aj_saida': 44.99, 'maq_equip': 36.00,
            # RES. FINANCEIRO
            'retorno_fin': 19759.78, 'retorno_acordos': 18445.78, 'rendimento': 2515.29,
            'seguro_rec': 8606.03, 'remuner_bank': 4833.99, 'retorno_comiss': 2873.03,
            'juros_rec': 201.14, 'pecld_rec': 2000.00, 'desc_pagar': 9679.23,
            'tarifa_bancaria': 237.59, 'juros_pagar2': 244.17, 'desc_receber': 116.44,
            # QTD/OUTROS
            'q': 33, 'q_sw': 24.00, 'q_at': 9.00, 'q_consig': 17.00, 'q_proprio': 16.00,
            # OUTROS
            'compras_func': 0.00, 'garantia_venda': 93.90,
        },
        '5': {
            # RECEITAS
            'merch_bruta_sw': 2441190.11, 'merch_bruta_at': 291250.00,
            'intermediacao_fin': 269780.00, 'laudo_venda': 5990.00, 'transf_venda': 2278.00,
            'fotos': 1750.00, 'prep_veiculo': 742.11, 'gasolina': 110.00,
            'rec_doc_sai': 16960.01, 'rec_svc': 5814.00, 'aluguel': 15000.00,
            'rec_diversas': 15500.00,
            # DEDUÇÕES
            'desc_sw': 90700.01, 'desc_at': 2300.00, 'esocial': 3475.07, 'fgts': 5350.78,
            'csll_irpj': 14107.73, 'pis_cofins': 17142.75, 'icms': 14601.57, 'iss': 15294.72,
            'alvara': 746.45, 'iptu': 2144.28, 'retencoes': 0.00, 'custas': 2835.88,
            'das': 5124.91, 'devolucao': 0.00, 'dev_fin': 264434.00,
            # CUSTOS
            'custo_compra_sw': 2041179.34, 'custo_compra_at': 259550.00,
            'custo_prep_entrega': 45061.72, 'frete': 80.00, 'despachante_ent': 700.00,
            'ipva': 18907.18, 'taxas_transf_ent': 3613.00, 'comunicado_venda': 20.00,
            'multas_nao_abat': 955.81, 'garantia_custo': 4780.00, 'laudo_custo': 2160.90,
            # DESPESAS OPERACIONAIS
            'comissao_c': 8422.77, 'pos_vendas': 2975.72, 'taxas_transf_sai': 15211.32,
            'despachante_sai': 0.00, 'salarios': 82368.37, 'ferias': 2666.67,
            'rescisao': 2712.31, 'fgts_rescis': 1103.06, 'plano_saude': 91.80,
            'refeitorio': 140.00, 'transporte': 551.90, 'uniforme': 206.98, 'copa': 0.00,
            'cartorio': 15.80, 'mat_aux': 123.50, 'mat_escrit': 512.29, 'seguros': 0.00,
            'contabil': 2000.00, 'informatica': 4710.18, 'associacoes': 250.00,
            'consultoria': 2580.00, 'viagens': 4810.74, 'aluguel_cond': 23550.00, 'agua': 0.00,
            'energia': 432.25, 'telefonia': 795.59, 'limpeza': 742.16, 'manutencao_loja': 0.00,
            'publicidade': 11019.96, 'portais': 8004.98, 'feirao': 12374.47,
            'brindes': 2790.00, 'pro_labore': 0.00, 'dividendos': 55500.00,
            'emprestimos': 24359.40, 'maq_equip': 1800.00,
            # RES. FINANCEIRO
            'retorno_fin': 25534.17, 'retorno_acordos': 3934.09, 'rendimento': 2730.25,
            'seguro_rec': 3993.36, 'retorno_comiss': 652.16, 'juros_rec': 370.02,
            'pecld_rec': 2000.00, 'desc_pagar': 10595.14, 'tarifa_bancaria': 714.91,
            'juros_pagar2': 145.38, 'iof': 4.56, 'desc_receber': 1000.00,
            # QTD/OUTROS
            'q': 36, 'q_sw': 28.00, 'q_at': 8.00, 'q_consig': 9.00, 'q_proprio': 27.00,
            # OUTROS
            'compras_func': 0.00, 'garantia_venda': 71.70,
        },
        '6': {
            # RECEITAS
            'merch_bruta_sw': 2447678.00, 'merch_bruta_at': 168300.00,
            'intermediacao_fin': 0.00, 'laudo_venda': 5050.00, 'transf_venda': 540.00,
            'fotos': 3500.00, 'prep_veiculo': 1200.00, 'gasolina': 380.00,
            'rec_doc_sai': 4534.90, 'rec_svc': 7000.00, 'venda_comiss': 2221.42,
            'aluguel': 12500.00, 'rec_diversas': 18147.16,
            # DEDUÇÕES
            'desc_sw': 45338.00, 'desc_at': 14600.00, 'esocial': 3684.21, 'fgts': 6216.40,
            'csll_irpj': 33320.22, 'pis_cofins': 10576.01, 'icms': 18751.64, 'iss': 6945.69,
            'alvara': 594.28, 'iptu': 2143.92, 'das': 5702.99, 'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 2132930.46, 'custo_compra_at': 131000.00,
            'custo_prep_entrega': 42582.32, 'frete': 0.00, 'despachante_ent': 1100.00,
            'ipva': 17533.71, 'taxas_transf_ent': 2052.00, 'baixa_gravame': 900.00,
            'comunicado_venda': 89.90, 'multas_nao_abat': 303.16, 'garantia_custo': 4650.00,
            'laudo_custo': 1552.00,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 0.00, 'comissao_c': 1431.60, 'pos_vendas': 16054.64,
            'taxas_transf_sai': 12513.22, 'despachante_sai': 0.00, 'salarios': 80133.40,
            'ferias': 2266.67, 'rescisao': 5207.95, 'plano_saude': 91.80, 'datas_com': 550.25,
            'refeitorio': 344.73, 'transporte': 416.08, 'uniforme': 228.76, 'copa': 917.97,
            'cartorio': 284.17, 'mat_aux': 230.16, 'mat_escrit': 570.08, 'seguros': 0.00,
            'contabil': 2000.00, 'informatica': 3477.38, 'associacoes': 250.00,
            'aluguel_cond': 25550.00, 'agua': 0.00, 'energia': 271.86, 'telefonia': 652.84,
            'limpeza': 1063.86, 'manutencao_loja': 1018.70, 'publicidade': 14300.82,
            'portais': 8004.98, 'feirao': 5161.11, 'brindes': 3450.00, 'pro_labore': 0.00,
            'dividendos': 53000.00, 'emprestimos': 24624.37, 'aj_saida': 3590.73,
            'maq_equip': 3176.53,
            # RES. FINANCEIRO
            'retorno_fin': 24060.29, 'retorno_acordos': 14514.65, 'rendimento': 5.78,
            'seguro_rec': 9546.18, 'juros_rec': 42.34, 'desc_pagar': 16763.83,
            'tarifa_bancaria': 1249.18, 'juros_pagar': 9531.10, 'juros_pagar2': 5.40,
            'desc_receber': 263.17,
            # QTD/OUTROS
            'q': 34, 'q_sw': 28.00, 'q_at': 6.00, 'q_consig': 8.00, 'q_proprio': 26.00,
            # OUTROS
            'compras_func': 0.00, 'garantia_venda': 35.25,
        },
        '7': {
            # RECEITAS
            'merch_bruta_sw': 2650159.00, 'merch_bruta_at': 344264.00,
            'intermediacao_fin': 0.00, 'laudo_venda': 4659.80, 'transf_venda': 280.16,
            'fotos': 1000.00, 'prep_veiculo': 8800.00, 'gasolina': 50.00,
            'rec_doc_sai': 8438.73, 'rec_svc': 10050.00, 'venda_comiss': 0.00,
            'aluguel': 15500.00, 'rec_diversas': 33552.44,
            # DEDUÇÕES
            'desc_sw': 30388.10, 'desc_at': 36080.00, 'esocial': 3433.27, 'fgts': 4213.06,
            'csll_irpj': 15099.48, 'pis_cofins': 12990.59, 'icms': 21659.17, 'iss': 7463.83,
            'alvara': 199.38, 'iptu': 2143.92, 'custas': 1211.18, 'das': 4590.75,
            'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 2229822.52, 'custo_compra_at': 284023.40,
            'custo_prep_entrega': 66330.00, 'frete': 0.00, 'despachante_ent': 830.00,
            'ipva': 9825.83, 'taxas_transf_ent': 7226.93, 'baixa_gravame': 530.16,
            'comunicado_venda': 138.17, 'multas_nao_abat': 595.77, 'garantia_custo': 20950.00,
            'laudo_custo': 3580.00,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 1000.00, 'comissao_c': 4678.38, 'pos_vendas': 2404.29,
            'taxas_transf_sai': 17269.45, 'despachante_sai': 0.00, 'salarios': 84538.84,
            'ferias': 4552.66, 'plano_saude': 91.80, 'refeitorio': 635.35,
            'transporte': 586.82, 'medicina': 60.00, 'churrasco': 1913.53,
            'almoco_meta': 252.02, 'copa': 1140.00, 'cartorio': 867.00, 'mat_aux': 244.50,
            'mat_escrit': 906.14, 'seguros': 0.00, 'contabil': 2000.00, 'informatica': 4792.16,
            'associacoes': 250.00, 'consultoria': 750.00, 'estacionamento': 0.00,
            'aluguel_cond': 25550.00, 'agua': 0.00, 'energia': 295.11, 'telefonia': 615.78,
            'limpeza': 429.87, 'manutencao_loja': 0.00, 'publicidade': 9999.00,
            'portais': 7444.28, 'feirao': 8395.54, 'brindes': 350.41, 'pro_labore': 0.00,
            'dividendos': 50000.00, 'emprestimos': 91606.25, 'aj_saida': 5894.12,
            'maq_equip': 3953.98,
            # RES. FINANCEIRO
            'retorno_fin': 23014.85, 'retorno_acordos': 22094.18, 'rendimento': 4.71,
            'seguro_rec': 10261.86, 'juros_rec': 29.10, 'desc_pagar': 8088.33,
            'tarifa_bancaria': 47.07, 'juros_pagar2': 90.75, 'desc_receber': 343.59,
            # QTD/OUTROS
            'q': 42, 'q_sw': 32.00, 'q_at': 10.00, 'q_consig': 10.00, 'q_proprio': 32.00,
            # OUTROS
            'compras_func': 4199.83, 'garantia_venda': 153.60,
        },
        '8': {
            # RECEITAS
            'merch_bruta_sw': 2187758.85, 'merch_bruta_at': 258390.00,
            'intermediacao_fin': 0.00, 'laudo_venda': 4650.00, 'transf_venda': 1311.00,
            'fotos': 750.00, 'prep_veiculo': 5271.00, 'gasolina': 50.00,
            'rec_doc_sai': 15123.44, 'rec_svc': 8460.00, 'venda_comiss': 18195.71,
            'aluguel': 9000.00, 'rec_diversas': 15850.00,
            # DEDUÇÕES
            'desc_sw': 33851.50, 'desc_at': 12516.00, 'esocial': 3250.30, 'fgts': 4294.48,
            'pis_cofins': 14105.06, 'icms': 23640.62, 'iss': 5854.29, 'iptu': 2143.92,
            'das': 4183.05, 'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 1871585.65, 'custo_compra_at': 221350.00,
            'custo_prep_entrega': 58603.33, 'frete': 0.00, 'despachante_ent': 3660.00,
            'ipva': 20027.60, 'taxas_transf_ent': 3242.00, 'comunicado_venda': 89.90,
            'multas_nao_abat': 703.51, 'garantia_custo': 2300.00, 'laudo_custo': 1132.80,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 1200.00, 'comissao_c': 5482.51, 'pos_vendas': 7228.49,
            'taxas_transf_sai': 14121.96, 'despachante_sai': 0.00, 'salarios': 83986.73,
            'ferias': 2813.33, 'plano_saude': 93.67, 'refeitorio': 484.75,
            'transporte': 270.40, 'medicina': 40.00, 'copa': 158.25, 'cartorio': 646.00,
            'mat_aux': 428.71, 'mat_escrit': 290.68, 'seguros': 4515.58, 'contabil': 2000.00,
            'informatica': 3119.31, 'associacoes': 250.00, 'consultoria': 750.00,
            'aluguel_cond': 25550.00, 'agua': 0.00, 'energia': 314.97, 'telefonia': 674.44,
            'limpeza': 629.15, 'manutencao_loja': 800.00, 'publicidade': 9999.00,
            'portais': 8076.28, 'brindes': 2492.00, 'pro_labore': 0.00, 'dividendos': 89758.94,
            'emprestimos': 21945.48, 'aj_saida': 1384.59,
            # RES. FINANCEIRO
            'retorno_fin': 30517.41, 'retorno_acordos': 29369.39, 'rendimento': 6.45,
            'seguro_rec': 1464.86, 'juros_rec': 200.10, 'desc_pagar': 5878.40,
            'tarifa_bancaria': 62.28, 'juros_pagar2': 4301.64, 'desc_receber': 0.00,
            # QTD/OUTROS
            'q': 33, 'q_sw': 25.00, 'q_at': 8.00, 'q_consig': 11.00, 'q_proprio': 22.00,
            # OUTROS
            'compras_func': 110.00, 'garantia_venda': 190.65,
        },
        '9': {'rec_doc_sai': 6497.01, 'rec_svc': 3740.00,
              'custo_prep_entrega': 9319.76, 'despachante_ent': 260.00,
              'ipva': 4581.02, 'taxas_transf_ent': 1086.16, 'laudo_custo': 54.90,
              'despachante_sai': 0.00, 'publicidade': 9999.00,
              'maq_equip': 31.89,
              'desc_pagar': 9487.67, 'juros_rec': 1.98,
              'desc_receber': 250.01, 'juros_pagar2': 22.68},
    
    },
    'bk': {

        '1': {
            # RECEITAS
            'merch_bruta_sw': 2010900.00, 'merch_bruta_at': 0.00, 'intermediacao_fin': 0.00,
            'laudo_venda': 700.00, 'transf_venda': 546.00, 'fotos': 500.00,
            'prep_veiculo': 0.00, 'gasolina': 0.00, 'rec_doc_sai': 2789.81, 'rec_svc': 600.00,
            'venda_comiss': 2440.65, 'aluguel': 3750.00, 'rec_diversas': 1050.00,
            # DEDUÇÕES
            'desc_sw': 24800.00, 'desc_at': 0.00, 'esocial': 514.75, 'fgts': 175.34,
            'pis_cofins': 2352.49, 'icms': 4422.29, 'iss': 1563.09, 'fisc_func': 0.00,
            'iptu': 0.00, 'custas': 0.00, 'das': 0.00, 'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 1786050.00, 'custo_compra_at': 0.00,
            'custo_prep_entrega': 16164.92, 'frete': 0.00, 'multa_veiculo': 0.00,
            'despachante_ent': 400.00, 'ipva': 376.63, 'taxas_transf_ent': 1022.00,
            'comunicado_venda': 0.00, 'multas_nao_abat': 0.00, 'garantia_custo': 3900.00,
            'laudo_custo': 990.50,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 2000.00, 'comissao_c': 16419.22, 'pos_vendas': 8291.84,
            'taxas_transf_sai': 2484.73, 'despachante_sai': 0.00, 'salarios': 17699.00,
            'ferias': 0.00, 'rescisao': 0.00, 'plano_saude': 0.00, 'refeitorio': 0.00,
            'transporte': 0.00, 'uniforme': 0.00, 'medicina': 0.00, 'almoco_meta': 0.00,
            'copa': 588.00, 'cartorio': 85.00, 'mat_aux': 12.00, 'mat_escrit': 0.00,
            'seguros': 850.00, 'contabil': 0.00, 'informatica': 997.00, 'associacoes': 0.00,
            'consultoria': 0.00, 'juridico': 0.00, 'viagens': 0.00, 'estacionamento': 24.00,
            'aluguel_cond': 9000.00, 'agua': 230.86, 'telefonia': 129.79, 'limpeza': 224.26,
            'manutencao_loja': 1982.00, 'publicidade': 4389.49, 'feirao': 124.44,
            'brindes': 904.56, 'pro_labore': 6000.00, 'dividendos': 0.00,
            'emprestimos': 2020.00, 'aj_saida': 1141.05,
            # RES. FINANCEIRO
            'retorno_fin': 7560.40, 'retorno_acordos': 0.00, 'rendimento': 25.02,
            'seguro_rec': 0.00, 'remuner_bank': 0.00, 'retorno_comiss': 0.00,
            'juros_rec': 0.00, 'desc_pagar': 719.17, 'tarifa_bancaria': 0.00,
            'juros_pagar': 0.00, 'iof': 1.73, 'desc_receber': 10.50,
            # QTD/OUTROS
            'q': 12, 'q_sw': 12.00, 'q_consig': 5.00, 'q_proprio': 7.00,
            # OUTROS
            'garantia_venda': 0.00,
        },
        '2': {
            # RECEITAS
            'merch_bruta_sw': 630400.00, 'merch_bruta_at': 99000.00,
            'intermediacao_fin': 35000.00, 'laudo_venda': 600.00, 'transf_venda': 0.00,
            'fotos': 250.00, 'prep_veiculo': 0.00, 'gasolina': 0.00, 'rec_doc_sai': 2082.54,
            'rec_svc': 1050.00, 'venda_comiss': 15464.89, 'aluguel': 3750.00,
            'rec_diversas': 0.00,
            # DEDUÇÕES
            'desc_sw': 24218.00, 'desc_at': 16000.00, 'esocial': 520.86, 'fgts': 129.68,
            'pis_cofins': 2628.00, 'icms': 5573.85, 'iss': 1100.00, 'iptu': 0.00, 'das': 0.00,
            'devolucao': 0.00, 'dev_fin': 34000.00,
            # CUSTOS
            'custo_compra_sw': 532900.00, 'custo_compra_at': 78000.00,
            'custo_prep_entrega': 4427.16, 'frete': 500.00, 'despachante_ent': 300.00,
            'ipva': 5846.31, 'taxas_transf_ent': 7404.60, 'baixa_gravame': 40.00,
            'comunicado_venda': 14.00, 'multas_nao_abat': 0.00, 'garantia_custo': 3400.00,
            'laudo_custo': 780.00,
            # DESPESAS OPERACIONAIS
            'comissao_c': 8200.11, 'pos_vendas': 3985.00, 'taxas_transf_sai': 3948.16,
            'despachante_sai': 0.00, 'salarios': 18233.54, 'rescisao': 0.00,
            'plano_saude': 0.00, 'datas_com': 0.00, 'refeitorio': 0.00, 'transporte': 0.00,
            'medicina': 0.00, 'copa': 222.66, 'cartorio': 158.07, 'mat_aux': 0.00,
            'mat_escrit': 40.00, 'seguros': 850.00, 'contabil': 0.00, 'informatica': 96.95,
            'associacoes': 0.00, 'consultoria': 0.00, 'juridico': 0.00, 'estacionamento': 0.00,
            'aluguel_cond': 9000.00, 'energia': 363.31, 'telefonia': 164.54, 'limpeza': 0.00,
            'manutencao_loja': 0.00, 'publicidade': 1144.55, 'feirao': 0.00, 'brindes': 0.00,
            'pro_labore': 11273.96, 'dividendos': 0.00, 'emprestimos': 2020.00,
            'aj_saida': 0.00, 'maq_equip': 268.00,
            # RES. FINANCEIRO
            'retorno_fin': 918.79, 'retorno_acordos': 70.00, 'rendimento': 4.04,
            'seguro_rec': 0.00, 'juros_rec': 0.00, 'pecld_rec': 0.00, 'desc_pagar': 268.60,
            'tarifa_bancaria': 0.00, 'juros_pagar2': 0.00, 'desc_receber': 0.00,
            # QTD/OUTROS
            'q': 8, 'q_sw': 6.00, 'q_at': 2.00, 'q_consig': 1.00, 'q_proprio': 7.00,
            # OUTROS
            'garantia_venda': 0.00,
        },
        '3': {
            # RECEITAS
            'merch_bruta_sw': 1373894.00, 'merch_bruta_at': 140000.00,
            'intermediacao_fin': 0.00, 'laudo_venda': 1550.00, 'transf_venda': 958.00,
            'fotos': 4300.00, 'prep_veiculo': 1429.00, 'gasolina': 0.00,
            'rec_doc_sai': 2404.20, 'rec_svc': 1650.00, 'venda_comiss': 1681.16,
            'aluguel': 2125.00, 'rec_diversas': 54.90,
            # DEDUÇÕES
            'desc_sw': 30360.00, 'desc_at': 4000.00, 'esocial': 520.86, 'fgts': 129.68,
            'pis_cofins': 4440.59, 'icms': 3459.00, 'iss': 4361.41, 'alvara': 0.00,
            'iptu': 0.00, 'das': 0.00, 'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 1241350.00, 'custo_compra_at': 130000.00,
            'custo_prep_entrega': 5882.64, 'frete': 0.00, 'despachante_ent': 200.00,
            'ipva': 10482.08, 'taxas_transf_ent': 593.07, 'baixa_gravame': 0.00,
            'comunicado_venda': 28.00, 'multas_nao_abat': 0.00, 'garantia_custo': 3900.00,
            'laudo_custo': 299.70,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 0.00, 'comissao_c': 5112.09, 'pos_vendas': 2350.00,
            'taxas_transf_sai': 2038.00, 'despachante_sai': 0.00, 'salarios': 18728.54,
            'plano_saude': 0.00, 'datas_com': 505.27, 'refeitorio': 362.00, 'transporte': 0.00,
            'medicina': 0.00, 'churrasco': 0.00, 'almoco_meta': 0.00, 'aluguel_cond2': 0.00,
            'copa': 998.76, 'cartorio': 0.00, 'mat_aux': 0.00, 'mat_escrit': 0.00,
            'seguros': 850.00, 'contabil': 1203.00, 'informatica': 96.95, 'associacoes': 0.00,
            'consultoria': 0.00, 'estacionamento': 0.00, 'pub_adm': 0.00,
            'aluguel_cond': 9000.00, 'agua': 109.75, 'energia': 238.26, 'telefonia': 132.75,
            'limpeza': 0.00, 'manutencao_loja': 0.00, 'publicidade': 1400.00,
            'portais': 1370.92, 'brindes': 0.00, 'pro_labore': 6000.00, 'dividendos': 0.00,
            'emprestimos': 2020.00, 'maq_equip': 45.90,
            # RES. FINANCEIRO
            'retorno_fin': 4280.14, 'retorno_acordos': 0.00, 'rendimento': 13.07,
            'seguro_rec': 0.00, 'remuner_bank': 0.00, 'juros_rec': 0.00, 'pecld_rec': 0.00,
            'desc_pagar': 220.07, 'tarifa_bancaria': 0.00, 'juros_pagar': 0.00,
            'juros_pagar2': 70.01, 'desc_receber': 19.50,
            # QTD/OUTROS
            'q': 12, 'q_sw': 10.00, 'q_at': 2.00, 'q_consig': 6.00, 'q_proprio': 6.00,
            # OUTROS
            'garantia_venda': 0.00,
        },
        '4': {
            # RECEITAS
            'merch_bruta_sw': 755300.00, 'merch_bruta_at': 46000.00,
            'intermediacao_fin': 104900.00, 'laudo_venda': 2222.70, 'transf_venda': 4236.00,
            'fotos': 200.00, 'prep_veiculo': 4255.00, 'gasolina': 50.00,
            'rec_doc_sai': 1467.38, 'rec_svc': 350.00, 'venda_comiss': 12500.00,
            'aluguel': 0.00, 'rec_diversas': 0.00,
            # DEDUÇÕES
            'desc_sw': 42300.00, 'desc_at': 0.00, 'esocial': 629.06, 'fgts': 143.48,
            'csll_irpj': 19397.35, 'pis_cofins': 489.10, 'icms': 550.00, 'iss': 170.00,
            'fisc_func': 0.00, 'iptu': 0.00, 'das': 0.00, 'devolucao': 2510.00,
            'dev_fin': 94900.00,
            # CUSTOS
            'custo_compra_sw': 608000.00, 'custo_compra_at': 40000.00,
            'custo_prep_entrega': 2668.21, 'frete': 0.00, 'despachante_ent': 200.00,
            'ipva': 6373.77, 'taxas_transf_ent': 428.00, 'baixa_gravame': 0.00,
            'comunicado_venda': 28.00, 'multas_nao_abat': 104.13, 'garantia_custo': 0.00,
            'laudo_custo': 1141.50,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 0.00, 'comissao_c': 11316.10, 'pos_vendas': 370.50,
            'taxas_transf_sai': 2654.00, 'despachante_sai': 0.00, 'salarios': 21238.54,
            'ferias': 0.00, 'rescisao': 0.00, 'fgts_rescis': 0.00, 'plano_saude': 0.00,
            'refeitorio': 142.18, 'transporte': 0.00, 'cursos': 0.00, 'almoco_meta': 0.00,
            'copa': 983.34, 'cartorio': 107.00, 'mat_aux': 44.65, 'mat_escrit': 0.00,
            'seguros': 850.00, 'contabil': 1203.00, 'informatica': 131.85, 'associacoes': 0.00,
            'consultoria': 0.00, 'viagens': 0.00, 'pub_adm': 0.00, 'aluguel_cond': 9000.00,
            'agua': 175.30, 'energia': 328.40, 'telefonia': 166.81, 'limpeza': 112.00,
            'manutencao_loja': 350.00, 'publicidade': 1400.00, 'portais': 1528.31,
            'feirao': 5488.70, 'pro_labore': 6000.00, 'dividendos': 0.00,
            'emprestimos': 2020.00, 'aj_saida': 0.00, 'maq_equip': 61.00,
            # RES. FINANCEIRO
            'retorno_fin': 2725.04, 'retorno_acordos': 0.00, 'rendimento': 28.00,
            'seguro_rec': 0.00, 'remuner_bank': 0.00, 'retorno_comiss': 0.00,
            'juros_rec': 0.00, 'pecld_rec': 0.00, 'desc_pagar': 445.77,
            'tarifa_bancaria': 3.50, 'juros_pagar2': 0.30, 'desc_receber': 0.00,
            # QTD/OUTROS
            'q': 8, 'q_sw': 7.00, 'q_at': 1.00, 'q_consig': 1.00, 'q_proprio': 7.00,
            # OUTROS
            'compras_func': 0.00, 'garantia_venda': 0.00,
        },
        '5': {
            # RECEITAS
            'merch_bruta_sw': 1312300.00, 'merch_bruta_at': 116500.00,
            'intermediacao_fin': 0.00, 'laudo_venda': 2989.90, 'transf_venda': 1140.00,
            'fotos': 1000.00, 'prep_veiculo': 0.00, 'gasolina': 0.00, 'rec_doc_sai': 4849.26,
            'rec_svc': 500.00, 'aluguel': 0.00, 'rec_diversas': 0.00,
            # DEDUÇÕES
            'desc_sw': 34320.00, 'desc_at': 18482.00, 'esocial': 1117.68, 'fgts': 261.14,
            'csll_irpj': 3943.60, 'pis_cofins': 4557.85, 'icms': 1500.40, 'iss': 4748.64,
            'alvara': 746.45, 'iptu': 0.00, 'retencoes': 53.81, 'custas': 0.00, 'das': 0.00,
            'devolucao': 418.00, 'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 1128990.00, 'custo_compra_at': 106000.00,
            'custo_prep_entrega': 14641.71, 'frete': 0.00, 'despachante_ent': 100.00,
            'ipva': 23582.30, 'taxas_transf_ent': 246.00, 'comunicado_venda': 0.00,
            'multas_nao_abat': 0.00, 'garantia_custo': 0.00, 'laudo_custo': 419.40,
            # DESPESAS OPERACIONAIS
            'comissao_c': 5000.00, 'pos_vendas': 15896.00, 'taxas_transf_sai': 1941.00,
            'despachante_sai': 0.00, 'salarios': 20633.54, 'ferias': 0.00, 'rescisao': 0.00,
            'fgts_rescis': 0.00, 'plano_saude': 0.00, 'refeitorio': 150.00, 'transporte': 0.00,
            'uniforme': 0.00, 'copa': 329.81, 'cartorio': 0.00, 'mat_aux': 0.00,
            'mat_escrit': 258.70, 'seguros': 850.00, 'contabil': 1203.00, 'informatica': 96.95,
            'associacoes': 0.00, 'consultoria': 0.00, 'viagens': 0.00, 'aluguel_cond': 9000.00,
            'agua': 87.65, 'energia': 333.24, 'telefonia': 98.06, 'limpeza': 120.00,
            'manutencao_loja': 1200.00, 'publicidade': 2400.00, 'portais': 1789.31,
            'feirao': 339.84, 'brindes': 400.00, 'pro_labore': 6000.00, 'dividendos': 0.00,
            'emprestimos': 2020.00, 'maq_equip': 134.10,
            # RES. FINANCEIRO
            'retorno_fin': 0.00, 'retorno_acordos': 0.00, 'rendimento': 27.36,
            'seguro_rec': 98.31, 'retorno_comiss': 0.00, 'juros_rec': 9309.01,
            'pecld_rec': 0.00, 'desc_pagar': 301.55, 'tarifa_bancaria': 13.40,
            'juros_pagar2': 93.60, 'iof': 0.00, 'desc_receber': 1651.00,
            # QTD/OUTROS
            'q': 11, 'q_sw': 8.00, 'q_at': 3.00, 'q_consig': 2.00, 'q_proprio': 9.00,
            # OUTROS
            'compras_func': 0.00, 'garantia_venda': 0.00,
        },
        '6': {
            # RECEITAS
            'merch_bruta_sw': 641900.00, 'merch_bruta_at': 0.00, 'intermediacao_fin': 0.00,
            'laudo_venda': 2739.80, 'transf_venda': 130.16, 'fotos': 750.00,
            'prep_veiculo': 980.00, 'gasolina': 0.00, 'rec_doc_sai': 794.73, 'rec_svc': 0.00,
            'venda_comiss': 1431.60, 'aluguel': 0.00, 'rec_diversas': 46.22,
            # DEDUÇÕES
            'desc_sw': 12200.00, 'desc_at': 0.00, 'esocial': 1139.14, 'fgts': 265.68,
            'csll_irpj': 1611.96, 'pis_cofins': 2962.40, 'icms': 9844.80, 'iss': 1938.08,
            'alvara': 0.00, 'iptu': 0.00, 'das': 0.00, 'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 577000.00, 'custo_compra_at': 0.00,
            'custo_prep_entrega': 16487.11, 'frete': 0.00, 'despachante_ent': 100.00,
            'ipva': 1613.29, 'taxas_transf_ent': 208.00, 'baixa_gravame': 0.00,
            'comunicado_venda': 74.00, 'multas_nao_abat': 156.18, 'garantia_custo': 0.00,
            'laudo_custo': 839.30,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 1400.00, 'comissao_c': 2221.42, 'pos_vendas': 1299.91,
            'taxas_transf_sai': 2698.00, 'despachante_sai': 0.00, 'salarios': 20158.54,
            'ferias': 0.00, 'rescisao': 0.00, 'plano_saude': 0.00, 'datas_com': 0.00,
            'refeitorio': 64.38, 'transporte': 0.00, 'uniforme': 0.00, 'copa': 415.44,
            'cartorio': 57.00, 'mat_aux': 315.50, 'mat_escrit': 397.49, 'seguros': 721.45,
            'contabil': 1203.00, 'informatica': 96.95, 'associacoes': 0.00,
            'aluguel_cond': 9000.00, 'agua': 90.97, 'energia': 351.36, 'telefonia': 158.68,
            'limpeza': 344.85, 'manutencao_loja': 163.10, 'publicidade': 0.00,
            'portais': 2420.31, 'feirao': 0.00, 'brindes': 1200.00, 'pro_labore': 6000.00,
            'dividendos': 0.00, 'emprestimos': 2020.00, 'aj_saida': 0.00, 'maq_equip': 295.23,
            # RES. FINANCEIRO
            'retorno_fin': 0.00, 'retorno_acordos': 0.00, 'rendimento': 47.72,
            'seguro_rec': 0.00, 'juros_rec': 0.01, 'desc_pagar': 359.67,
            'tarifa_bancaria': 0.00, 'juros_pagar': 0.00, 'juros_pagar2': 133.98,
            'desc_receber': 0.00,
            # QTD/OUTROS
            'q': 5, 'q_sw': 5.00, 'q_consig': 1.00, 'q_proprio': 4.00,
            # OUTROS
            'compras_func': 0.00, 'garantia_venda': 0.00,
        },
        '7': {
            # RECEITAS
            'merch_bruta_sw': 919700.00, 'merch_bruta_at': 107000.00,
            'intermediacao_fin': 0.00, 'laudo_venda': 1119.90, 'transf_venda': 480.16,
            'fotos': 600.00, 'prep_veiculo': 0.00, 'gasolina': 0.00, 'rec_doc_sai': 790.48,
            'rec_svc': 2650.00, 'venda_comiss': 2078.38, 'aluguel': 0.00, 'rec_diversas': 0.00,
            # DEDUÇÕES
            'desc_sw': 8700.00, 'desc_at': 2236.00, 'esocial': 1139.14, 'fgts': 265.68,
            'csll_irpj': 0.01, 'pis_cofins': 2589.05, 'icms': 10437.23, 'iss': 0.00,
            'alvara': 0.00, 'iptu': 0.00, 'custas': 0.00, 'das': 0.00, 'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 854721.30, 'custo_compra_at': 90000.00,
            'custo_prep_entrega': 28679.17, 'frete': 4500.00, 'despachante_ent': 400.00,
            'ipva': 5346.83, 'taxas_transf_ent': 1210.00, 'baixa_gravame': 0.00,
            'comunicado_venda': 14.00, 'multas_nao_abat': 0.00, 'garantia_custo': 5500.00,
            'laudo_custo': 594.30,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 0.00, 'comissao_c': 500.00, 'pos_vendas': 14558.35,
            'taxas_transf_sai': 2569.82, 'despachante_sai': 0.00, 'salarios': 20733.54,
            'ferias': 0.00, 'plano_saude': 0.00, 'refeitorio': 16.00, 'transporte': 114.40,
            'medicina': 20.00, 'churrasco': 0.00, 'almoco_meta': 205.42, 'copa': 356.29,
            'cartorio': 141.76, 'mat_aux': 13.34, 'mat_escrit': 54.68, 'seguros': 721.45,
            'contabil': 1203.00, 'informatica': 96.95, 'associacoes': 250.00,
            'consultoria': 0.00, 'estacionamento': 15.00, 'aluguel_cond': 9000.00,
            'agua': 90.97, 'energia': 333.42, 'telefonia': 167.21, 'limpeza': 174.35,
            'manutencao_loja': 264.00, 'publicidade': 1750.00, 'portais': 2337.55,
            'feirao': 491.90, 'brindes': 0.00, 'pro_labore': 8000.00, 'dividendos': 4000.00,
            'emprestimos': 600.00, 'aj_saida': 0.00, 'maq_equip': 311.08,
            # RES. FINANCEIRO
            'retorno_fin': 0.00, 'retorno_acordos': 600.00, 'rendimento': 7.58,
            'seguro_rec': 0.00, 'juros_rec': 0.01, 'desc_pagar': 366.71,
            'tarifa_bancaria': 3.45, 'juros_pagar2': 0.01, 'desc_receber': 0.00,
            # QTD/OUTROS
            'q': 7, 'q_sw': 5.00, 'q_at': 2.00, 'q_consig': 1.00, 'q_proprio': 6.00,
            # OUTROS
            'compras_func': 0.00, 'garantia_venda': 0.00,
        },
        '8': {
            # RECEITAS
            'merch_bruta_sw': 1481850.00, 'merch_bruta_at': 0.00, 'intermediacao_fin': 0.00,
            'laudo_venda': 500.00, 'transf_venda': 500.00, 'fotos': 0.00,
            'prep_veiculo': 4130.00, 'gasolina': 0.00, 'rec_doc_sai': 1720.27,
            'rec_svc': 350.00, 'venda_comiss': 2082.51, 'aluguel': 0.00, 'rec_diversas': 0.00,
            # DEDUÇÕES
            'desc_sw': 10107.02, 'desc_at': 0.00, 'esocial': 1139.14, 'fgts': 265.68,
            'pis_cofins': 2892.26, 'icms': 5887.40, 'iss': 1365.19, 'iptu': 0.00, 'das': 0.00,
            'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 1307380.00, 'custo_compra_at': 0.00,
            'custo_prep_entrega': 10805.20, 'frete': 4000.00, 'despachante_ent': 380.00,
            'ipva': 2930.43, 'taxas_transf_ent': 1042.28, 'comunicado_venda': 0.00,
            'multas_nao_abat': 0.00, 'garantia_custo': 0.00, 'laudo_custo': 349.50,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 1800.00, 'comissao_c': 12195.71, 'pos_vendas': 3039.55,
            'taxas_transf_sai': 3229.90, 'despachante_sai': 0.00, 'salarios': 24836.04,
            'ferias': 0.00, 'plano_saude': 0.00, 'refeitorio': 354.97, 'transporte': 520.00,
            'medicina': 0.00, 'copa': 725.96, 'cartorio': 232.98, 'mat_aux': 197.49,
            'mat_escrit': 24.39, 'seguros': 721.45, 'contabil': 1203.00, 'informatica': 96.95,
            'associacoes': 250.00, 'consultoria': 0.00, 'aluguel_cond': 9000.00,
            'agua': 216.32, 'energia': 291.63, 'telefonia': 150.30, 'limpeza': 142.18,
            'manutencao_loja': 0.00, 'publicidade': 0.00, 'portais': 2437.55, 'brindes': 0.00,
            'pro_labore': 8000.00, 'dividendos': 4000.00, 'emprestimos': 600.00,
            'aj_saida': 0.00,
            # RES. FINANCEIRO
            'retorno_fin': 2622.27, 'retorno_acordos': 0.00, 'rendimento': 3.66,
            'seguro_rec': 0.00, 'juros_rec': 0.01, 'desc_pagar': 290.26,
            'tarifa_bancaria': 0.00, 'juros_pagar2': 132.40, 'desc_receber': 12.00,
            # QTD/OUTROS
            'q': 8, 'q_sw': 8.00, 'q_consig': 2.00, 'q_proprio': 6.00,
            # OUTROS
            'compras_func': 0.00, 'garantia_venda': 0.00,
        },
        '9': {'desc_pagar': 429.01, 'juros_pagar2': 60.30, 'despachante_sai': 0.00,
              'rec_doc_sai': 187.02, 'custo_prep_entrega': 679.92, 'ipva': 2425.86,
              'despachante_ent': 0.00, 'taxas_transf_ent': 0.00, 'laudo_custo': 0.00},
    
    },
    'cons': {
        '1': {'rec_doc_sai': 12518.20, 'rec_svc': 9521.40, 'prep_veiculo': 1000.0, 'custo_prep_entrega': 100152.51, 'frete': 130.0, 'multa_veiculo': 0.0, 'despachante_ent': 3770.0, 'taxas_transf_ent': 6655.18, 'comunicado_venda': 293.13, 'laudo_custo': 4072.10, 'despachante_sai': 0.0, 'salarios': 101675.32, 'viagens': 40470.68, 'associacoes': 250.0, 'publicidade': 18883.39, 'seguro_rec': 5837.69, 'retorno_comiss': 4493.39, 'juros_rec': 46.88, 'desc_pagar': 27387.42, 'juros_pagar': 14.68, 'desc_receber': 10.50},
        '2': {'rec_doc_sai': 16323.66, 'rec_svc': 5720.0, 'desc_sw': 72545.50, 'custo_prep_entrega': 63811.0, 'frete': 600.0, 'despachante_ent': 1460.0, 'ipva': 18414.83, 'taxas_transf_ent': 11702.84, 'baixa_gravame': 0.0, 'laudo_custo': 3025.0, 'despachante_sai': 0.0, 'seguro_rec': 16862.87, 'juros_rec': 379.35, 'desc_pagar': 15757.74, 'desc_receber': 291.40, 'juros_pagar2': 43.49},
        '3': {'rec_doc_sai': 25043.25, 'rec_svc': 10030.0, 'rec_diversas': 15554.90, 'desc_sw': 118306.96, 'desc_at': 42900.0, 'custo_prep_entrega': 80624.66, 'frete': 0.0, 'despachante_ent': 2300.0, 'ipva': 30297.31, 'taxas_transf_ent': 5793.22, 'comunicado_venda': 149.90, 'laudo_custo': 2620.20, 'despachante_sai': 0.0, 'cartorio': 366.64, 'pub_adm': 1200.0, 'publicidade': 9349.94, 'seguro_rec': 246.34, 'remuner_bank': 1741.50, 'juros_rec': 60.34, 'desc_pagar': 12100.00, 'desc_receber': 84.51, 'juros_pagar': 2201.80, 'juros_pagar2': 82.64, 'retorno_fin': 28417.19},
        '4': {'rec_svc': 7300.0, 'laudo_venda': 9775.90, 'custo_prep_entrega': 40676.10, 'frete': 0.0, 'despachante_ent': 2150.0, 'ipva': 27580.05, 'taxas_transf_ent': 6938.16, 'multas_nao_abat': 104.13, 'laudo_custo': 5156.70, 'taxas_transf_sai': 14389.08, 'despachante_sai': 0.0, 'compras_func': 0.0, 'pub_adm': 1200.0, 'emprestimos': 28130.95, 'publicidade': 10699.00, 'feirao': 18594.66, 'seguro_rec': 8606.03, 'retorno_comiss': 2873.03, 'remuner_bank': 4833.99, 'juros_rec': 201.14, 'desc_pagar': 10125.00, 'desc_receber': 116.44, 'juros_pagar2': 244.47, 'tarifa_bancaria': 241.09},
        '5': {'rec_svc': 6314.0, 'desc_sw': 125020.01, 'desc_at': 20782.0, 'custo_prep_entrega': 57438.43, 'frete': 80.0, 'despachante_ent': 700.0, 'ipva': 40485.04, 'taxas_transf_ent': 3711.0, 'laudo_custo': 2470.50, 'despachante_sai': 0.0, 'compras_func': 0.0, 'viagens': 4810.74, 'seguro_rec': 4091.67, 'retorno_comiss': 652.16, 'juros_rec': 9679.03, 'desc_pagar': 10896.69, 'desc_receber': 2651.00, 'iof': 4.56, 'juros_pagar2': 238.98},
        '6': {'rec_doc_sai': 5310.40, 'rec_svc': 7000.0, 'fotos': 4250.0, 'rec_diversas': 18147.16, 'custo_prep_entrega': 50890.65, 'frete': 0.0, 'despachante_ent': 1200.0, 'ipva': 16883.52, 'taxas_transf_ent': 2306.0, 'laudo_custo': 1977.10, 'despachante_sai': 0.0, 'compras_func': 0.0, 'maq_equip': 3471.76, 'seguro_rec': 9546.18, 'juros_rec': 42.35, 'desc_pagar': 17123.50, 'desc_receber': 263.17, 'juros_pagar': 9531.10, 'juros_pagar2': 139.38, 'retorno_fin': 24060.29,
              'associacoes': 250.00, 'portais': 10425.29},
        '7': {},  # limpo — cons = MM+BK natural, redistribuição vira identidade
    },
}

_DRE_CORR_2025 = {
    'mm': {
        '1': {
            # RECEITAS
            'merch_bruta_sw': 2627749.49, 'merch_bruta_at': 15000.00,
            'intermediacao_fin': 0.00, 'laudo_venda': 6565.00, 'transf_venda': 66.00,
            'rec_doc_sai': 5023.95, 'rec_svc': 9700.00, 'venda_svc': 20763.00,
            'venda_comiss': 1336.93, 'rec_diversas': 0.00,
            # DEDUÇÕES
            'desc_sw': 16300.00, 'desc_at': 0.00, 'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 2305662.98, 'custo_compra_at': 10000.00,
            'custo_prep_entrega': 69539.60, 'frete': 600.00, 'multa_veiculo': 0.00,
            'despachante_ent': 2350.00, 'ipva': 6616.34, 'taxas_transf_ent': 17166.32,
            'garantia_custo': 9850.00, 'laudo_custo': 7808.70,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 768.13, 'comissao_c': 1183.51, 'pos_vendas': 21071.54,
            'taxas_transf_sai': 0.00, 'salarios': 66059.06, 'desp_adm_dem': 2183.95,
            'desp_pessoal_var': 5552.80, 'refeitorio': 600.00, 'transporte': 461.25,
            'uniforme': 0.00, 'aluguel_cond2': 21825.80, 'copa': 47.95, 'cartorio': 409.27,
            'mat_aux': 202.00, 'mat_escrit': 250.43, 'seguros': 1094.33, 'contabil': 60574.88,
            'consultoria': 4695.00, 'juridico': 9265.15, 'viagens': 26516.04,
            'estacionamento': 0.00, 'pub_adm': 250.00, 'agua': 315.00, 'energia': 999.68,
            'telefonia': 630.24, 'limpeza': 275.79, 'manutencao_loja': 0.00,
            'publicidade': 13565.94, 'brindes': 0.00, 'pro_labore': 0.00,
            'dividendos': 59704.77, 'emprestimos': 23204.23, 'aj_saida': 213.13,
            'maq_equip': 1054.82,
            # RES. FINANCEIRO
            'rendimento': 435.58, 'retorno_comiss': 30881.98, 'juros_rec': 2018.44,
            'desc_pagar': 15038.55, 'tarifa_bancaria': 681.74, 'juros_pagar': 290.83,
            'juros_pagar2': 2187.15, 'desc_receber': 330.22,
            # QTD/OUTROS
            'q': 34, 'q_sw': 33.00, 'q_at': 1.00, 'q_consig': 11.00, 'q_proprio': 23.00,
        },
        '2': {
            # RECEITAS
            'merch_bruta_sw': 1817550.00, 'merch_bruta_at': 0.00, 'intermediacao_fin': 0.00,
            'laudo_venda': 3260.00, 'transf_venda': 300.00, 'rec_doc_sai': 1936.17,
            'rec_svc': 7546.00, 'venda_svc': 33281.86, 'venda_comiss': 0.00,
            'rec_diversas': 3000.00,
            # DEDUÇÕES
            'desc_sw': 15700.00, 'desc_at': 0.00, 'custas': 134.35, 'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 1539880.00, 'custo_compra_at': 0.00,
            'custo_prep_entrega': 53494.77, 'frete': 1450.00, 'multa_veiculo': 0.00,
            'despachante_ent': 4460.00, 'ipva': 10151.10, 'taxas_transf_ent': 13141.06,
            'garantia_custo': 8650.00, 'laudo_custo': 5960.20,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 17806.90, 'comissao_c': 12325.39, 'pos_vendas': 6636.49,
            'taxas_transf_sai': 208.00, 'despachante_sai': 3947.29, 'salarios': 79134.04,
            'desp_adm_dem': 2235.37, 'desp_pessoal_var': 825.38, 'refeitorio': 1651.98,
            'transporte': 483.80, 'uniforme': 0.00, 'aluguel_cond2': 21825.80, 'copa': 1286.41,
            'cartorio': 399.59, 'mat_aux': 206.06, 'mat_escrit': 415.40, 'seguros': 2299.03,
            'contabil': 78847.51, 'consultoria': 4500.00, 'juridico': 3829.50,
            'viagens': 19557.04, 'estacionamento': 0.00, 'agua': 208.00, 'energia': 0.00,
            'telefonia': 654.39, 'limpeza': 0.00, 'manutencao_loja': 0.00,
            'publicidade': 9188.46, 'brindes': 265.00, 'pro_labore': 0.00,
            'dividendos': 49660.09, 'emprestimos': 24059.54, 'aj_saida': 15849.51,
            'maq_equip': 418.72,
            # RES. FINANCEIRO
            'rendimento': 117.05, 'retorno_comiss': 21704.96, 'juros_rec': 267.79,
            'desc_pagar': 11836.76, 'tarifa_bancaria': 640.99, 'juros_pagar': 108.41,
            'juros_pagar2': 0.00, 'desc_receber': 1935.00,
            # QTD/OUTROS
            'q': 22, 'q_sw': 22.00, 'q_consig': 7.00, 'q_proprio': 15.00,
            # OUTROS
            'garantia_venda': 0.00,
        },
        '3': {
            # RECEITAS
            'merch_bruta_sw': 1631833.87, 'merch_bruta_at': 266800.00,
            'intermediacao_fin': 0.00, 'laudo_venda': 3900.00, 'transf_venda': 635.38,
            'rec_doc_sai': 12127.04, 'rec_svc': 9015.00, 'venda_svc': 19362.03,
            'venda_comiss': 0.00, 'rec_diversas': 56029.50,
            # DEDUÇÕES
            'desc_sw': 13000.00, 'desc_at': 1000.00, 'custas': 0.00, 'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 1350417.30, 'custo_compra_at': 240097.51,
            'custo_prep_entrega': 66664.00, 'frete': 0.00, 'multa_veiculo': 244.71,
            'despachante_ent': 4000.00, 'ipva': 15172.67, 'taxas_transf_ent': 11701.17,
            'garantia_custo': 6250.00, 'laudo_custo': 4689.00,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 30.00, 'comissao_c': 2824.97, 'pos_vendas': 5790.49,
            'taxas_transf_sai': 220.00, 'despachante_sai': 4045.84, 'salarios': 56720.63,
            'desp_adm_dem': 1401.69, 'desp_pessoal_var': 912.68, 'refeitorio': 683.48,
            'transporte': 668.67, 'uniforme': 0.00, 'aluguel_cond2': 24800.00, 'copa': 219.76,
            'cartorio': 278.09, 'mat_aux': 195.00, 'mat_escrit': 345.40, 'seguros': 524.90,
            'contabil': 42591.00, 'consultoria': 4500.00, 'juridico': 12962.34,
            'viagens': 0.00, 'estacionamento': 0.00, 'agua': 224.00, 'energia': 1258.46,
            'telefonia': 659.75, 'limpeza': 0.00, 'manutencao_loja': 0.00,
            'publicidade': 18300.54, 'brindes': 1023.12, 'pro_labore': 0.00,
            'dividendos': 53500.00, 'emprestimos': 20750.20, 'aj_saida': 44772.01,
            'maq_equip': 13694.00,
            # RES. FINANCEIRO
            'retorno_fin': 0.00, 'rendimento': 80.10, 'retorno_comiss': 15223.34,
            'juros_rec': 249.13, 'desc_pagar': 20953.50, 'tarifa_bancaria': 419.55,
            'juros_pagar': 1174.01, 'juros_pagar2': 0.00, 'desc_receber': 56.50,
            # QTD/OUTROS
            'q': 28, 'q_sw': 21.00, 'q_at': 7.00, 'q_consig': 10.00, 'q_proprio': 18.00,
            # OUTROS
            'garantia_venda': 0.00,
        },
        '4': {
            # RECEITAS
            'merch_bruta_sw': 2215609.30, 'merch_bruta_at': 270560.00, 'laudo_venda': 3410.00,
            'transf_venda': 1300.00, 'rec_doc_sai': 7943.32, 'rec_svc': 5630.00,
            'venda_svc': 10780.00, 'aluguel': 3750.00, 'rec_diversas': 7020.00,
            # DEDUÇÕES
            'desc_sw': 63868.23, 'desc_at': 4400.00, 'devolucao': 413.92,
            # CUSTOS
            'custo_compra_sw': 1829103.74, 'custo_compra_at': 240378.10,
            'custo_prep_entrega': 91339.95, 'frete': 950.00, 'despachante_ent': 5670.00,
            'ipva': 30157.90, 'taxas_transf_ent': 12065.55, 'garantia_custo': 7550.00,
            'laudo_custo': 3007.20,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 250.00, 'comissao_c': 5600.00, 'pos_vendas': 1500.00,
            'salarios': 63037.14, 'desp_adm_dem': 9097.38, 'plano_saude': 65.80,
            'refeitorio': 1190.70, 'transporte': 1167.69, 'uniforme': 0.00,
            'aluguel_cond2': 0.00, 'copa': 399.60, 'cartorio': 560.50, 'mat_aux': 922.11,
            'mat_escrit': 160.00, 'seguros': 524.90, 'contabil': 52861.36,
            'consultoria': 4500.00, 'juridico': 5249.00, 'viagens': 6957.03,
            'estacionamento': 100.50, 'aluguel_cond': 24800.00, 'agua': 120.00,
            'energia': 126.16, 'telefonia': 677.48, 'limpeza': 450.84,
            'manutencao_loja': 150.00, 'publicidade': 5930.49, 'brindes': 90.00,
            'pro_labore': 0.00, 'dividendos': 39600.00, 'emprestimos': 26087.18,
            'aj_saida': 6760.00, 'maq_equip': 4803.82,
            # RES. FINANCEIRO
            'retorno_fin': 0.00, 'rendimento': 184.55, 'retorno_comiss': 25731.27,
            'juros_rec': 187.54, 'desc_pagar': 19573.05, 'tarifa_bancaria': 308.49,
            'juros_pagar': 1217.30, 'desc_receber': 583.16,
            # QTD/OUTROS
            'q': 38, 'q_sw': 30.00, 'q_at': 8.00, 'q_consig': 14.00, 'q_proprio': 24.00,
        },
        '5': {
            # RECEITAS
            'merch_bruta_sw': 2887965.01, 'merch_bruta_at': 239736.00,
            'intermediacao_fin': 119700.00, 'laudo_venda': 3592.00, 'transf_venda': 3302.31,
            'rec_doc_sai': 10406.16, 'rec_svc': 6930.00, 'venda_svc': 19532.66,
            'venda_comiss': 1500.00, 'rec_diversas': 19584.01,
            # DEDUÇÕES
            'desc_sw': 57350.01, 'desc_at': 14200.00, 'dev_fin': 115000.00,
            # CUSTOS
            'custo_compra_sw': 2351869.56, 'custo_compra_at': 207504.03,
            'custo_prep_entrega': 63716.63, 'frete': 950.00, 'despachante_ent': 3500.00,
            'ipva': 25694.41, 'taxas_transf_ent': 17963.98, 'garantia_custo': 5350.00,
            'laudo_custo': 4050.00,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 11222.00, 'comissao_c': 14651.57, 'pos_vendas': 2587.99,
            'despachante_sai': 686.73, 'salarios': 72088.86, 'desp_adm_dem': 4946.44,
            'desp_pessoal_var': 896.80, 'refeitorio': 300.00, 'transporte': 1696.88,
            'uniforme': 260.00, 'aluguel_cond2': 24800.00, 'copa': 35.00, 'cartorio': 501.55,
            'mat_aux': 7.00, 'mat_escrit': 534.15, 'seguros': 524.90, 'contabil': 54724.90,
            'consultoria': 4500.00, 'juridico': 9299.00, 'agua': 80.00, 'energia': 203.63,
            'telefonia': 675.03, 'limpeza': 462.92, 'publicidade': 22541.01, 'brindes': 90.00,
            'pro_labore': 0.00, 'dividendos': 45673.25, 'emprestimos': 25275.30,
            'aj_saida': 14883.55, 'maq_equip': 6824.82,
            # RES. FINANCEIRO
            'rendimento': 51.21, 'retorno_comiss': 41801.33, 'juros_rec': 4.66,
            'desc_pagar': 9398.65, 'tarifa_bancaria': 484.29, 'juros_pagar': 490.75,
            'desc_receber': 44.02,
            # QTD/OUTROS
            'q': 39, 'q_sw': 32.00, 'q_at': 7.00, 'q_consig': 13.00, 'q_proprio': 26.00,
        },
        '6': {
            # RECEITAS
            'merch_bruta_sw': 1008550.00, 'merch_bruta_at': 113918.00, 'laudo_venda': 7110.00,
            'transf_venda': 254.00, 'rec_doc_sai': 8333.04, 'rec_svc': 6350.00,
            'venda_svc': 13868.34, 'venda_comiss': 3121.25, 'aluguel': 7250.00,
            'rec_diversas': 9600.00,
            # DEDUÇÕES
            'desc_sw': 22768.70, 'desc_at': 7772.00,
            # CUSTOS
            'custo_compra_sw': 851410.53, 'custo_compra_at': 98445.96,
            'custo_prep_entrega': 16003.86, 'frete': 0.00, 'multa_veiculo': 0.00,
            'despachante_ent': 5990.00, 'ipva': 26331.16, 'taxas_transf_ent': 15385.83,
            'garantia_custo': 4800.00, 'laudo_custo': 6130.70,
            # DESPESAS OPERACIONAIS
            'comissao_c': 1000.00, 'pos_vendas': 1252.64, 'despachante_sai': 292.00,
            'salarios': 99925.72, 'desp_pessoal_var': 645.80, 'refeitorio': 981.77,
            'transporte': 1349.47, 'uniforme': 1909.00, 'aluguel_cond2': 25550.00,
            'copa': 701.69, 'cartorio': 465.75, 'mat_aux': 464.34, 'mat_escrit': 250.00,
            'seguros': 951.22, 'contabil': 59328.55, 'informatica': 23479.00,
            'juridico': 7198.00, 'agua': 0.00, 'energia': 105.24, 'telefonia': 644.32,
            'limpeza': 716.82, 'publicidade': 17068.04, 'brindes': 863.30, 'pro_labore': 0.00,
            'dividendos': 57600.00, 'emprestimos': 26618.06, 'maq_equip': 293.82,
            # RES. FINANCEIRO
            'rendimento': 1.56, 'retorno_comiss': 8998.67, 'juros_rec': 55.53,
            'desc_pagar': 9220.45, 'tarifa_bancaria': 467.52, 'juros_pagar': 184.50,
            'desc_receber': 265.92,
            # QTD/OUTROS
            'q': 20, 'q_sw': 16.00, 'q_at': 4.00, 'q_consig': 10.00, 'q_proprio': 10.00,
            # OUTROS
            'garantia_venda': 0.00,
        },
        '7': {
            # RECEITAS
            'merch_bruta_sw': 2673700.01, 'merch_bruta_at': 775748.00, 'laudo_venda': 7270.00,
            'transf_venda': 1336.00, 'rec_doc_sai': 30764.70, 'rec_svc': 9710.00,
            'venda_svc': 14998.73, 'venda_comiss': 6028.63, 'rec_diversas': 250.00,
            # DEDUÇÕES
            'desc_sw': 52580.11, 'desc_at': 33774.00,
            # CUSTOS
            'custo_compra_sw': 2287638.30, 'custo_compra_at': 691236.00,
            'custo_prep_entrega': 65128.26, 'frete': 950.00, 'multa_veiculo': 0.00,
            'despachante_ent': 3100.00, 'ipva': 38799.62, 'taxas_transf_ent': 16865.10,
            'garantia_custo': 800.00, 'laudo_custo': 7929.80,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 7736.90, 'comissao_c': 7085.13, 'pos_vendas': 760.00,
            'despachante_sai': 626.90, 'salarios': 67675.02, 'desp_adm_dem': 48.00,
            'desp_pessoal_var': 65.80, 'refeitorio': 883.00, 'transporte': 1337.83,
            'uniforme': 2600.00, 'aluguel_cond2': 25550.00, 'copa': 160.40, 'cartorio': 407.86,
            'mat_aux': 185.82, 'mat_escrit': 474.71, 'seguros': 867.32, 'contabil': 54752.85,
            'informatica': 9900.00, 'consultoria': 1800.00, 'juridico': 8988.90,
            'viagens': 608.00, 'agua': 0.00, 'energia': 144.50, 'telefonia': 664.50,
            'limpeza': 585.90, 'publicidade': 17687.87, 'brindes': 400.00, 'pro_labore': 0.00,
            'dividendos': 42180.00, 'emprestimos': 26391.86, 'aj_saida': 460.91,
            'maq_equip': 15704.51,
            # RES. FINANCEIRO
            'rendimento': 81.04, 'retorno_comiss': 39412.99, 'juros_rec': 981.21,
            'desc_pagar': 11736.80, 'tarifa_bancaria': 1222.29, 'juros_pagar': 2926.62,
            'desc_receber': 250.37,
            # QTD/OUTROS
            'q': 52, 'q_sw': 34.00, 'q_at': 18.00, 'q_consig': 18.00, 'q_proprio': 34.00,
        },
        '8': {
            # RECEITAS
            'merch_bruta_sw': 962900.01, 'merch_bruta_at': 184782.00,
            'intermediacao_fin': 20200.00, 'laudo_venda': 8405.00, 'transf_venda': 650.00,
            'rec_doc_sai': 8281.11, 'rec_svc': 2530.00, 'venda_svc': 16567.86,
            'venda_comiss': 0.00, 'aluguel': 7250.00, 'rec_diversas': 2653.78,
            # DEDUÇÕES
            'desc_sw': 26900.01, 'desc_at': 1636.00, 'devolucao': 0.00, 'dev_fin': 17700.00,
            # CUSTOS
            'custo_compra_sw': 838811.91, 'custo_compra_at': 165400.00,
            'custo_prep_entrega': 32241.11, 'despachante_ent': 3955.00, 'ipva': 18156.89,
            'taxas_transf_ent': 17000.48, 'garantia_custo': 15800.00, 'laudo_custo': 4361.80,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 2779.90, 'comissao_c': 6808.15, 'pos_vendas': 1013.80,
            'despachante_sai': 462.84, 'salarios': 99948.52, 'desp_adm_dem': 474.38,
            'desp_pessoal_var': 65.80, 'refeitorio': 827.00, 'uniforme': 0.00,
            'aluguel_cond2': 25550.00, 'copa': 0.00, 'cartorio': 1122.95, 'mat_aux': 55.21,
            'mat_escrit': 111.70, 'seguros': 1000.32, 'contabil': 56346.71,
            'consultoria': 1800.00, 'juridico': 6249.35, 'viagens': 893.30,
            'estacionamento': 29.70, 'pub_adm': 28.00, 'agua': 0.00, 'energia': 139.09,
            'telefonia': 784.89, 'limpeza': 458.00, 'publicidade': 17390.89, 'brindes': 299.00,
            'pro_labore': 0.00, 'dividendos': 41586.00, 'emprestimos': 25978.14,
            'aj_saida': 2296.22, 'maq_equip': 5727.94,
            # RES. FINANCEIRO
            'rendimento': 37.94, 'retorno_comiss': 26552.02, 'juros_rec': 2194.69,
            'desc_pagar': 12555.60, 'tarifa_bancaria': 437.96, 'juros_pagar': 87.69,
            'desc_receber': 845.15,
            # QTD/OUTROS
            'q': 16, 'q_sw': 11.00, 'q_at': 5.00, 'q_consig': 6.00, 'q_proprio': 10.00,
            # OUTROS
            'garantia_venda': 253.70,
        },
        '9': {
            # RECEITAS
            'merch_bruta_sw': 2356200.01, 'merch_bruta_at': 407614.00,
            'intermediacao_fin': 174600.00, 'laudo_venda': 4445.00, 'transf_venda': 635.00,
            'rec_doc_sai': 9517.91, 'rec_svc': 8639.00, 'venda_svc': 21633.94,
            'venda_comiss': 8930.35, 'aluguel': 7250.00, 'rec_diversas': 3610.28,
            # DEDUÇÕES
            'desc_sw': 42915.70, 'desc_at': 17980.00, 'devolucao': 600.00,
            'dev_fin': 171900.00,
            # CUSTOS
            'custo_compra_sw': 2062393.67, 'custo_compra_at': 356170.00,
            'custo_prep_entrega': 65871.44, 'frete': 130.00, 'despachante_ent': 5570.00,
            'ipva': 26494.56, 'taxas_transf_ent': 13832.58, 'garantia_custo': 5100.00,
            'laudo_custo': 2913.50,
            # DESPESAS OPERACIONAIS
            'comissao_c': 2300.00, 'pos_vendas': 1425.00, 'despachante_sai': 305.91,
            'salarios': 72196.71, 'desp_adm_dem': 9414.85, 'desp_pessoal_var': 65.80,
            'refeitorio': 703.98, 'transporte': 938.29, 'uniforme': 205.99,
            'aluguel_cond2': 25550.00, 'copa': 64.35, 'cartorio': 289.81, 'mat_aux': 368.89,
            'mat_escrit': 50.00, 'seguros': 1121.82, 'contabil': 54748.21,
            'informatica': 250.00, 'consultoria': 1800.00, 'juridico': 6391.00,
            'viagens': 1572.79, 'estacionamento': 10.00, 'agua': 0.00, 'energia': 159.21,
            'telefonia': 664.52, 'limpeza': 830.26, 'publicidade': 9943.57, 'feirao': 2500.00,
            'brindes': 500.00, 'pro_labore': 0.00, 'dividendos': 48000.00,
            'emprestimos': 25265.94, 'aj_saida': 5076.55, 'maq_equip': 1846.78,
            # RES. FINANCEIRO
            'rendimento': 129.74, 'remuner_bank': 6192.50, 'retorno_comiss': 42461.18,
            'juros_rec': 55.54, 'desc_pagar': 16318.95, 'tarifa_bancaria': 428.65,
            'juros_pagar': 3137.89, 'desc_receber': 54.19,
            # QTD/OUTROS
            'q': 36, 'q_sw': 28.00, 'q_at': 8.00, 'q_consig': 16.00, 'q_proprio': 20.00,
            # OUTROS
            'garantia_venda': 51.00,
        },
        '10': {
            # RECEITAS
            'merch_bruta_sw': 3029090.95, 'merch_bruta_at': 412166.00, 'laudo_venda': 7350.00,
            'transf_venda': 240.16, 'rec_doc_sai': 13367.12, 'rec_svc': 7830.00,
            'venda_svc': 16350.00, 'venda_comiss': 1865.63, 'aluguel': 7250.00,
            'rec_diversas': 6060.01,
            # DEDUÇÕES
            'desc_sw': 84890.00, 'desc_at': 15030.00, 'csll_irpj': 18313.61,
            # CUSTOS
            'custo_compra_sw': 2542828.47, 'custo_compra_at': 360000.00,
            'custo_prep_entrega': 87799.53, 'frete': 0.00, 'despachante_ent': 5100.00,
            'ipva': 31784.54, 'taxas_transf_ent': 14657.80, 'garantia_custo': 5750.00,
            'laudo_custo': 3274.50,
            # DESPESAS OPERACIONAIS
            'comissao_c': 3088.15, 'pos_vendas': 4639.62, 'despachante_sai': 61.90,
            'salarios': 92539.75, 'desp_adm_dem': 35.17, 'desp_pessoal_var': 2922.19,
            'refeitorio': 472.67, 'transporte': 888.51, 'aluguel_cond2': 25550.00,
            'copa': 335.32, 'cartorio': 1654.77, 'mat_aux': 866.84, 'mat_escrit': 113.69,
            'seguros': 1016.08, 'contabil': 48937.53, 'consultoria': 1800.00,
            'juridico': 6299.00, 'viagens': 0.00, 'agua': 54.00, 'energia': 139.40,
            'telefonia': 557.19, 'limpeza': 425.57, 'publicidade': 24978.25,
            'brindes': 2900.00, 'pro_labore': 0.00, 'dividendos': 54809.16,
            'emprestimos': 25007.38, 'aj_saida': 4442.90, 'maq_equip': 0.00,
            # RES. FINANCEIRO
            'rendimento': 67.01, 'remuner_bank': 5987.50, 'retorno_comiss': 43161.58,
            'juros_rec': 0.01, 'desc_pagar': 16992.03, 'tarifa_bancaria': 552.73,
            'juros_pagar': 2980.78, 'desc_receber': 1533.91,
            # QTD/OUTROS
            'q': 52, 'q_sw': 42.00, 'q_at': 10.00, 'q_consig': 18.00, 'q_proprio': 34.00,
            # OUTROS
            'compras_func': 3149.00, 'garantia_venda': 103.50,
        },
        '11': {
            # RECEITAS
            'merch_bruta_sw': 2909665.00, 'merch_bruta_at': 806522.01,
            'intermediacao_fin': 299507.00, 'laudo_venda': 3854.90, 'rec_doc_sai': 25869.47,
            'rec_svc': 3820.00, 'venda_svc': 12739.47, 'venda_comiss': 16241.91,
            'aluguel': 3500.00, 'rec_diversas': 6861.04,
            # DEDUÇÕES
            'desc_sw': 82421.30, 'desc_at': 23740.01, 'csll_irpj': 18313.59,
            'dev_fin': 294110.13,
            # CUSTOS
            'custo_compra_sw': 2435093.00, 'custo_compra_at': 746118.22,
            'custo_prep_entrega': 58326.92, 'despachante_ent': 3720.00, 'ipva': 17730.91,
            'taxas_transf_ent': 16541.00, 'garantia_custo': 6300.00, 'laudo_custo': 4156.10,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 500.00, 'comissao_c': 10231.31, 'pos_vendas': 745.00,
            'despachante_sai': 61.90, 'salarios': 97872.64, 'desp_pessoal_var': 2461.80,
            'refeitorio': 347.19, 'transporte': 952.42, 'aluguel_cond2': 28460.00,
            'copa': 332.61, 'cartorio': 693.26, 'mat_aux': 175.20, 'mat_escrit': 987.46,
            'seguros': 968.70, 'contabil': 419784.32, 'juridico': 8199.00, 'viagens': 257.64,
            'agua': 0.00, 'energia': 107.54, 'telefonia': 617.19, 'limpeza': 524.50,
            'publicidade': 17335.20, 'brindes': 700.00, 'pro_labore': 0.00,
            'dividendos': 42500.00, 'emprestimos': 28754.68, 'aj_saida': 7845.03,
            # RES. FINANCEIRO
            'rendimento': 48.34, 'retorno_comiss': 78307.11, 'juros_rec': 4.61,
            'desc_pagar': 5186.93, 'tarifa_bancaria': 142.73, 'juros_pagar': 597.76,
            'desc_receber': 1344.64,
            # QTD/OUTROS
            'q': 53, 'q_sw': 35.00, 'q_at': 18.00, 'q_consig': 25.00, 'q_proprio': 28.00,
            # OUTROS
            'compras_func': 2943.26, 'garantia_venda': 119.25,
        },
        '12': {
            # RECEITAS
            'merch_bruta_sw': 1416850.00, 'merch_bruta_at': 574243.80,
            'intermediacao_fin': 83990.00, 'laudo_venda': 6290.00, 'prep_veiculo': 0.00,
            'gasolina': 0.00, 'rec_doc_sai': 6681.73, 'rec_svc': 6806.00,
            'venda_svc': 16365.00, 'venda_comiss': 10642.76, 'aluguel': 8253.00,
            'rec_diversas': 5791.92,
            # DEDUÇÕES
            'desc_sw': 10150.00, 'desc_at': 60673.84, 'csll_irpj': 18313.59,
            'devolucao': 586.94, 'dev_fin': 81290.00,
            # CUSTOS
            'custo_compra_sw': 1197980.00, 'custo_compra_at': 497750.00,
            'custo_prep_entrega': 35301.28, 'frete': 0.00, 'despachante_ent': 6290.00,
            'ipva': 3276.07, 'taxas_transf_ent': 16862.58, 'garantia_custo': 8800.00,
            'laudo_custo': 4549.80,
            # DESPESAS OPERACIONAIS
            'comissao_c': 6568.94, 'pos_vendas': 4210.75, 'taxas_transf_sai': 450.00,
            'despachante_sai': 61.90, 'salarios': 143286.26, 'desp_adm_dem': 6342.75,
            'desp_pessoal_var': 0.00, 'refeitorio': 254.00, 'transporte': 1035.26,
            'aluguel_cond2': 25550.00, 'copa': 608.72, 'cartorio': 422.30, 'mat_aux': 106.90,
            'mat_escrit': 880.00, 'seguros': 1036.20, 'contabil': 38698.53,
            'informatica': 1000.00, 'consultoria': 750.00, 'juridico': 6408.80,
            'viagens': 3159.98, 'agua': 0.00, 'energia': 1074.78, 'telefonia': 592.19,
            'limpeza': 347.16, 'publicidade': 21149.50, 'pro_labore': 0.00,
            'dividendos': 41000.00, 'emprestimos': 28391.81, 'aj_saida': 5730.80,
            'maq_equip': 150.00,
            # RES. FINANCEIRO
            'retorno_acordos': 0.00, 'rendimento': 96.75, 'remuner_bank': 1300.00,
            'retorno_comiss': 46030.70, 'juros_rec': 0.91, 'desc_pagar': 14419.41,
            'tarifa_bancaria': 266.86, 'juros_pagar': 2073.51, 'desc_receber': 52.06,
            # QTD/OUTROS
            'q': 29, 'q_sw': 15.00, 'q_at': 14.00, 'q_consig': 9.00, 'q_proprio': 20.00,
        },
        },
    'bk': {
        '1': {
            # RECEITAS
            'merch_bruta_sw': 972100.00, 'merch_bruta_at': 0.00, 'intermediacao_fin': 49500.00,
            'laudo_venda': 0.00, 'transf_venda': 900.00, 'rec_doc_sai': 915.00,
            'rec_svc': 350.00, 'venda_svc': 19.50, 'venda_comiss': 5833.51,
            'rec_diversas': 0.00,
            # DEDUÇÕES
            'desc_sw': 8900.00, 'desc_at': 0.00, 'dev_fin': 49500.00,
            # CUSTOS
            'custo_compra_sw': 883900.00, 'custo_compra_at': 0.00,
            'custo_prep_entrega': 3176.09, 'frete': 3750.00, 'multa_veiculo': 0.00,
            'despachante_ent': 0.00, 'ipva': 463.95, 'taxas_transf_ent': 110.00,
            'garantia_custo': 0.00, 'laudo_custo': 54.90,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 0.00, 'comissao_c': 1836.93, 'pos_vendas': 1888.94,
            'taxas_transf_sai': 0.00, 'salarios': 1642.00, 'desp_adm_dem': 0.00,
            'desp_pessoal_var': 92.00, 'refeitorio': 0.00, 'transporte': 0.00,
            'uniforme': 0.00, 'aluguel_cond2': 9000.00, 'copa': 0.00, 'cartorio': 0.00,
            'mat_aux': 134.28, 'mat_escrit': 13.89, 'seguros': 0.00, 'contabil': 0.00,
            'consultoria': 0.00, 'juridico': 3399.00, 'viagens': 0.00, 'estacionamento': 0.00,
            'pub_adm': 0.00, 'agua': 82.22, 'energia': 1845.53, 'telefonia': 89.99,
            'limpeza': 431.07, 'manutencao_loja': 0.00, 'publicidade': 1000.00,
            'brindes': 0.00, 'pro_labore': 6000.00, 'dividendos': 0.00, 'emprestimos': 0.00,
            'aj_saida': 0.00, 'maq_equip': 0.00,
            # RES. FINANCEIRO
            'rendimento': 17.83, 'retorno_comiss': 0.00, 'juros_rec': 0.00,
            'desc_pagar': 549.99, 'tarifa_bancaria': 133.50, 'juros_pagar': 0.30,
            'juros_pagar2': 0.00, 'desc_receber': 50.00,
            # QTD/OUTROS
            'q': 9, 'q_sw': 9.00, 'q_consig': 5.00, 'q_proprio': 4.00,
        },
        '2': {
            # RECEITAS
            'merch_bruta_sw': 129000.00, 'merch_bruta_at': 0.00, 'intermediacao_fin': 0.00,
            'laudo_venda': 1029.11, 'transf_venda': 0.00, 'rec_doc_sai': 0.00, 'rec_svc': 0.00,
            'venda_svc': 910.00, 'venda_comiss': 9825.39, 'rec_diversas': 0.00,
            # DEDUÇÕES
            'desc_sw': 0.00, 'desc_at': 0.00, 'custas': 0.00, 'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 120000.00, 'custo_compra_at': 0.00,
            'custo_prep_entrega': 191.00, 'frete': 0.00, 'multa_veiculo': 0.00,
            'despachante_ent': 0.00, 'ipva': 3212.10, 'taxas_transf_ent': 512.38,
            'garantia_custo': 0.00, 'laudo_custo': 800.00,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 50.00, 'comissao_c': 0.00, 'pos_vendas': 39.90,
            'taxas_transf_sai': 0.00, 'despachante_sai': 0.00, 'salarios': 1642.00,
            'desp_adm_dem': 0.00, 'desp_pessoal_var': 0.00, 'refeitorio': 0.00,
            'transporte': 20.00, 'uniforme': 1029.40, 'aluguel_cond2': 9000.00, 'copa': 773.14,
            'cartorio': 70.16, 'mat_aux': 0.00, 'mat_escrit': 0.00, 'seguros': 0.00,
            'contabil': 190.91, 'consultoria': 0.00, 'juridico': 0.00, 'viagens': 0.00,
            'estacionamento': 15.00, 'agua': 59.73, 'energia': 0.00, 'telefonia': 40.00,
            'limpeza': 0.00, 'manutencao_loja': 0.00, 'publicidade': 710.00, 'brindes': 0.00,
            'pro_labore': 9707.37, 'dividendos': 0.00, 'emprestimos': 0.00, 'aj_saida': 0.00,
            'maq_equip': 781.91,
            # RES. FINANCEIRO
            'rendimento': 1.98, 'retorno_comiss': 6289.79, 'juros_rec': 291.18,
            'desc_pagar': 0.00, 'tarifa_bancaria': 142.50, 'juros_pagar': 0.00,
            'juros_pagar2': 0.00, 'desc_receber': 0.00,
            # QTD/OUTROS
            'q': 1, 'q_sw': 1.00, 'q_proprio': 1.00,
            # OUTROS
            'garantia_venda': 0.00,
        },
        '3': {
            # RECEITAS
            'merch_bruta_sw': 655000.00, 'merch_bruta_at': 0.00, 'intermediacao_fin': 0.00,
            'laudo_venda': 1050.00, 'transf_venda': 0.00, 'rec_doc_sai': 0.00, 'rec_svc': 0.00,
            'venda_svc': 2566.00, 'venda_comiss': 12824.97, 'rec_diversas': 0.00,
            # DEDUÇÕES
            'desc_sw': 0.00, 'desc_at': 0.00, 'custas': 0.00, 'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 604000.00, 'custo_compra_at': 0.00,
            'custo_prep_entrega': 265.00, 'frete': 0.00, 'multa_veiculo': 0.00,
            'despachante_ent': 450.00, 'ipva': 0.00, 'taxas_transf_ent': 464.00,
            'garantia_custo': 1500.00, 'laudo_custo': 404.90,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 1659.20, 'comissao_c': 0.00, 'pos_vendas': 0.00,
            'taxas_transf_sai': 0.00, 'despachante_sai': 0.00, 'salarios': 1442.00,
            'desp_adm_dem': 0.00, 'desp_pessoal_var': 0.00, 'refeitorio': 225.00,
            'transporte': 0.00, 'uniforme': 70.00, 'aluguel_cond2': 9000.00, 'copa': 386.00,
            'cartorio': 0.00, 'mat_aux': 0.00, 'mat_escrit': 4.30, 'seguros': 0.00,
            'contabil': 0.00, 'consultoria': 0.00, 'juridico': 100.00, 'viagens': 4.90,
            'estacionamento': 0.00, 'agua': 56.44, 'energia': 0.00, 'telefonia': 179.98,
            'limpeza': 76.84, 'manutencao_loja': 0.00, 'publicidade': 500.00, 'brindes': 0.00,
            'pro_labore': 6000.00, 'dividendos': 0.00, 'emprestimos': 0.00, 'aj_saida': 0.00,
            'maq_equip': 1505.86,
            # RES. FINANCEIRO
            'retorno_fin': 1305.92, 'rendimento': 4.84, 'retorno_comiss': 848.85,
            'juros_rec': 0.00, 'desc_pagar': 0.01, 'tarifa_bancaria': 49.00,
            'juros_pagar': 19.91, 'juros_pagar2': 0.00, 'desc_receber': 0.00,
            # QTD/OUTROS
            'q': 3, 'q_sw': 3.00, 'q_consig': 3.00,
            # OUTROS
            'garantia_venda': 0.00,
        },
        '4': {
            # RECEITAS
            'merch_bruta_sw': 381000.00, 'merch_bruta_at': 0.00, 'laudo_venda': 0.00,
            'transf_venda': 900.00, 'rec_doc_sai': 0.00, 'rec_svc': 0.00, 'venda_svc': 400.00,
            'aluguel': 0.00, 'rec_diversas': 316.96,
            # DEDUÇÕES
            'desc_sw': 0.00, 'desc_at': 0.00, 'devolucao': 0.00,
            # CUSTOS
            'custo_compra_sw': 367877.43, 'custo_compra_at': 0.00, 'custo_prep_entrega': 80.00,
            'frete': 3755.00, 'despachante_ent': 300.00, 'ipva': 2588.49,
            'taxas_transf_ent': 648.00, 'garantia_custo': 1477.50, 'laudo_custo': 514.70,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 0.00, 'comissao_c': 500.00, 'pos_vendas': 3075.40,
            'salarios': 4125.13, 'desp_adm_dem': 0.00, 'plano_saude': 0.00, 'refeitorio': 0.00,
            'transporte': 8.46, 'uniforme': 140.00, 'aluguel_cond2': 9000.00, 'copa': 214.14,
            'cartorio': 0.00, 'mat_aux': 0.00, 'mat_escrit': 32.00, 'seguros': 0.00,
            'contabil': 6838.17, 'consultoria': 0.00, 'juridico': 150.00, 'viagens': 0.00,
            'estacionamento': 12.00, 'aluguel_cond': 0.00, 'agua': 142.90, 'energia': 179.48,
            'telefonia': 92.99, 'limpeza': 194.07, 'manutencao_loja': 150.00,
            'publicidade': 1750.00, 'brindes': 637.00, 'pro_labore': 6000.00,
            'dividendos': 0.00, 'emprestimos': 0.00, 'aj_saida': 0.00, 'maq_equip': 227.50,
            # RES. FINANCEIRO
            'retorno_fin': 1320.35, 'rendimento': 2.57, 'retorno_comiss': 0.00,
            'juros_rec': 1235.57, 'desc_pagar': 325.10, 'tarifa_bancaria': 181.00,
            'juros_pagar': 35.37, 'desc_receber': 0.00,
            # QTD/OUTROS
            'q': 2, 'q_sw': 2.00, 'q_proprio': 2.00,
        },
        '5': {
            # RECEITAS
            'merch_bruta_sw': 1106800.00, 'merch_bruta_at': 0.00, 'intermediacao_fin': 0.00,
            'laudo_venda': 3250.00, 'transf_venda': 610.00, 'rec_doc_sai': 10013.72,
            'rec_svc': 0.00, 'venda_svc': 2950.00, 'venda_comiss': 11951.57,
            'rec_diversas': 366.04,
            # DEDUÇÕES
            'desc_sw': 4900.00, 'desc_at': 0.00, 'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 1104470.00, 'custo_compra_at': 0.00,
            'custo_prep_entrega': 3238.00, 'frete': 0.00, 'despachante_ent': 100.00,
            'ipva': 6698.68, 'taxas_transf_ent': 835.36, 'garantia_custo': 0.00,
            'laudo_custo': 0.00,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 0.00, 'comissao_c': 1220.22, 'pos_vendas': 804.80,
            'despachante_sai': 0.00, 'salarios': 1262.40, 'desp_adm_dem': 700.00,
            'desp_pessoal_var': 0.00, 'refeitorio': 150.00, 'transporte': 0.00,
            'uniforme': 0.00, 'aluguel_cond2': 9000.00, 'copa': 822.32, 'cartorio': 1699.33,
            'mat_aux': 0.00, 'mat_escrit': 59.44, 'seguros': 0.00, 'contabil': 2589.93,
            'consultoria': 0.00, 'juridico': 0.00, 'agua': 259.52, 'energia': 1747.49,
            'telefonia': 92.99, 'limpeza': 90.79, 'publicidade': 2500.00, 'brindes': 215.99,
            'pro_labore': 6000.00, 'dividendos': 0.00, 'emprestimos': 0.00,
            'aj_saida': 3366.04, 'maq_equip': 961.52,
            # RES. FINANCEIRO
            'rendimento': 4.04, 'retorno_comiss': 358.90, 'juros_rec': 95.97,
            'desc_pagar': 3116.10, 'tarifa_bancaria': 20.00, 'juros_pagar': 37.60,
            'desc_receber': 0.00,
            # QTD/OUTROS
            'q': 7, 'q_sw': 7.00, 'q_consig': 4.00, 'q_proprio': 3.00,
        },
        '6': {
            # RECEITAS
            'merch_bruta_sw': 468800.00, 'merch_bruta_at': 0.00, 'laudo_venda': 1250.00,
            'transf_venda': 0.00, 'rec_doc_sai': 256.25, 'rec_svc': 700.00, 'venda_svc': 0.00,
            'venda_comiss': 0.00, 'aluguel': 0.00, 'rec_diversas': 0.00,
            # DEDUÇÕES
            'desc_sw': 14900.00, 'desc_at': 0.00,
            # CUSTOS
            'custo_compra_sw': 410000.00, 'custo_compra_at': 0.00,
            'custo_prep_entrega': 1616.44, 'frete': 0.00, 'multa_veiculo': 0.00,
            'despachante_ent': 490.00, 'ipva': 10377.15, 'taxas_transf_ent': 694.00,
            'garantia_custo': 5300.00, 'laudo_custo': 0.00,
            # DESPESAS OPERACIONAIS
            'comissao_c': 3121.25, 'pos_vendas': 1800.00, 'despachante_sai': 0.00,
            'salarios': 1768.60, 'desp_pessoal_var': 0.00, 'refeitorio': 0.00,
            'transporte': 20.00, 'uniforme': 0.00, 'aluguel_cond2': 9000.00, 'copa': 295.38,
            'cartorio': 258.84, 'mat_aux': 540.00, 'mat_escrit': 0.00, 'seguros': 846.44,
            'contabil': 4116.08, 'informatica': 0.00, 'juridico': 1400.00, 'agua': 120.80,
            'energia': 499.22, 'telefonia': 98.06, 'limpeza': 250.06, 'publicidade': 750.00,
            'brindes': 285.00, 'pro_labore': 6000.00, 'dividendos': 300.00,
            'emprestimos': 0.00, 'maq_equip': 140.00,
            # RES. FINANCEIRO
            'rendimento': 12.06, 'retorno_comiss': 3746.13, 'juros_rec': 0.00,
            'desc_pagar': 193.35, 'tarifa_bancaria': 0.50, 'juros_pagar': 32.33,
            'desc_receber': 659.91,
            # QTD/OUTROS
            'q': 3, 'q_sw': 3.00, 'q_consig': 3.00,
            # OUTROS
            'garantia_venda': 0.00,
        },
        '7': {
            # RECEITAS
            'merch_bruta_sw': 369800.00, 'merch_bruta_at': 55000.00, 'laudo_venda': 350.00,
            'transf_venda': 0.00, 'rec_doc_sai': 1301.26, 'rec_svc': 0.00,
            'venda_svc': 3790.00, 'venda_comiss': 26035.13, 'rec_diversas': 32.00,
            # DEDUÇÕES
            'desc_sw': 35802.00, 'desc_at': 0.00,
            # CUSTOS
            'custo_compra_sw': 300000.00, 'custo_compra_at': 50000.00,
            'custo_prep_entrega': 3997.50, 'frete': 0.00, 'multa_veiculo': 0.00,
            'despachante_ent': 280.00, 'ipva': 3657.31, 'taxas_transf_ent': 1306.00,
            'garantia_custo': 0.00, 'laudo_custo': 700.00,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 119.79, 'comissao_c': 3528.63, 'pos_vendas': 0.00,
            'despachante_sai': 0.00, 'salarios': 1992.60, 'desp_adm_dem': 0.00,
            'desp_pessoal_var': 0.00, 'refeitorio': 0.00, 'transporte': 0.00, 'uniforme': 0.00,
            'aluguel_cond2': 9000.00, 'copa': 332.90, 'cartorio': 65.74, 'mat_aux': 5.50,
            'mat_escrit': 100.00, 'seguros': 870.68, 'contabil': 15527.32, 'informatica': 0.00,
            'consultoria': 0.00, 'juridico': 1000.00, 'viagens': 0.00, 'agua': 87.65,
            'energia': 0.00, 'telefonia': 98.06, 'limpeza': 307.49, 'publicidade': 1000.00,
            'brindes': 0.00, 'pro_labore': 6035.00, 'dividendos': 0.00, 'emprestimos': 0.00,
            'aj_saida': 0.00, 'maq_equip': 0.00,
            # RES. FINANCEIRO
            'rendimento': 23.02, 'retorno_comiss': 55.61, 'juros_rec': 0.00,
            'desc_pagar': 4070.96, 'tarifa_bancaria': 51.45, 'juros_pagar': 243.26,
            'desc_receber': 0.00,
            # QTD/OUTROS
            'q': 3, 'q_sw': 2.00, 'q_at': 1.00, 'q_consig': 2.00, 'q_proprio': 1.00,
        },
        '8': {
            # RECEITAS
            'merch_bruta_sw': 422200.00, 'merch_bruta_at': 0.00, 'intermediacao_fin': 0.00,
            'laudo_venda': 500.00, 'transf_venda': 2014.00, 'rec_doc_sai': 2873.88,
            'rec_svc': 350.00, 'venda_svc': 1280.00, 'venda_comiss': 8308.15, 'aluguel': 0.00,
            'rec_diversas': 0.00,
            # DEDUÇÕES
            'desc_sw': 10068.00, 'desc_at': 0.00, 'devolucao': 354.00, 'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 373000.00, 'custo_compra_at': 0.00,
            'custo_prep_entrega': 188.70, 'despachante_ent': 900.00, 'ipva': 5684.93,
            'taxas_transf_ent': 1762.86, 'garantia_custo': 0.00, 'laudo_custo': 1119.60,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 100.00, 'comissao_c': 2000.00, 'pos_vendas': 1347.00,
            'despachante_sai': 0.00, 'salarios': 2033.00, 'desp_adm_dem': 0.00,
            'desp_pessoal_var': 0.00, 'refeitorio': 0.00, 'uniforme': 140.00,
            'aluguel_cond2': 9000.00, 'copa': 594.00, 'cartorio': 92.92, 'mat_aux': 0.00,
            'mat_escrit': 0.00, 'seguros': 846.44, 'contabil': 5325.50, 'consultoria': 0.00,
            'juridico': 1859.00, 'viagens': 0.00, 'estacionamento': 0.00, 'pub_adm': 0.00,
            'agua': 87.65, 'energia': 1100.29, 'telefonia': 77.45, 'limpeza': 121.66,
            'publicidade': 1450.00, 'brindes': 895.00, 'pro_labore': 6000.00,
            'dividendos': 0.00, 'emprestimos': 0.00, 'aj_saida': 0.00, 'maq_equip': 60.47,
            # RES. FINANCEIRO
            'rendimento': 14.16, 'retorno_comiss': 0.00, 'juros_rec': 0.00,
            'desc_pagar': 1345.22, 'tarifa_bancaria': 18.50, 'juros_pagar': 12.79,
            'desc_receber': 0.00,
            # QTD/OUTROS
            'q': 3, 'q_sw': 3.00, 'q_consig': 3.00,
            # OUTROS
            'garantia_venda': 0.00,
        },
        '9': {
            # RECEITAS
            'merch_bruta_sw': 1034980.00, 'merch_bruta_at': 21369.50,
            'intermediacao_fin': 0.00, 'laudo_venda': 950.00, 'transf_venda': 650.00,
            'rec_doc_sai': 2789.61, 'rec_svc': 800.00, 'venda_svc': 7408.46,
            'venda_comiss': 5000.00, 'aluguel': 0.00, 'rec_diversas': 5000.00,
            # DEDUÇÕES
            'desc_sw': 5200.00, 'desc_at': 0.00, 'devolucao': 4630.50, 'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 915120.00, 'custo_compra_at': 21369.50,
            'custo_prep_entrega': 4666.79, 'frete': 90.33, 'despachante_ent': 380.00,
            'ipva': 5754.75, 'taxas_transf_ent': 1862.16, 'garantia_custo': 1100.00,
            'laudo_custo': 1094.70,
            # DESPESAS OPERACIONAIS
            'comissao_c': 11430.35, 'pos_vendas': 3013.11, 'despachante_sai': 0.00,
            'salarios': 2264.00, 'desp_adm_dem': 0.00, 'desp_pessoal_var': 0.00,
            'refeitorio': 0.00, 'transporte': 0.00, 'uniforme': 0.00, 'aluguel_cond2': 9000.00,
            'copa': 294.00, 'cartorio': 0.00, 'mat_aux': 86.02, 'mat_escrit': 0.00,
            'seguros': 872.87, 'contabil': 5711.21, 'informatica': 0.00, 'consultoria': 0.00,
            'juridico': 2800.00, 'viagens': 0.00, 'estacionamento': 0.00, 'agua': 178.48,
            'energia': 194.76, 'telefonia': 77.45, 'limpeza': 43.26, 'publicidade': 3400.00,
            'feirao': 0.00, 'brindes': 0.00, 'pro_labore': 6000.00, 'dividendos': 133.12,
            'emprestimos': 0.00, 'aj_saida': 5740.28, 'maq_equip': 320.00,
            # RES. FINANCEIRO
            'rendimento': 11.98, 'remuner_bank': 0.00, 'retorno_comiss': 1766.85,
            'juros_rec': 121.63, 'desc_pagar': 906.53, 'tarifa_bancaria': 0.00,
            'juros_pagar': 0.00, 'desc_receber': 0.00,
            # QTD/OUTROS
            'q': 9, 'q_sw': 8.00, 'q_at': 1.00, 'q_consig': 8.00, 'q_proprio': 1.00,
            # OUTROS
            'garantia_venda': 0.00,
        },
        '10': {
            # RECEITAS
            'merch_bruta_sw': 504400.00, 'merch_bruta_at': 0.00, 'laudo_venda': 1950.00,
            'transf_venda': 0.00, 'rec_doc_sai': 134.00, 'rec_svc': 1000.00,
            'venda_svc': 750.00, 'venda_comiss': 2588.15, 'aluguel': 0.00,
            'rec_diversas': 0.00,
            # DEDUÇÕES
            'desc_sw': 1650.00, 'desc_at': 0.00, 'csll_irpj': 1715.92,
            # CUSTOS
            'custo_compra_sw': 466243.44, 'custo_compra_at': 0.00,
            'custo_prep_entrega': 13224.83, 'frete': 0.00, 'despachante_ent': 660.00,
            'ipva': 3088.69, 'taxas_transf_ent': 1294.16, 'garantia_custo': 0.00,
            'laudo_custo': 179.90,
            # DESPESAS OPERACIONAIS
            'comissao_c': 2865.63, 'pos_vendas': 5883.30, 'despachante_sai': 0.00,
            'salarios': 2139.00, 'desp_adm_dem': 0.00, 'desp_pessoal_var': 522.08,
            'refeitorio': 0.00, 'transporte': 0.00, 'aluguel_cond2': 9000.00, 'copa': 588.00,
            'cartorio': 67.95, 'mat_aux': 7.50, 'mat_escrit': 0.00, 'seguros': 846.44,
            'contabil': 10698.05, 'consultoria': 0.00, 'juridico': 2600.00, 'viagens': 638.00,
            'agua': 190.34, 'energia': 218.54, 'telefonia': 77.45, 'limpeza': 74.91,
            'publicidade': 2250.00, 'brindes': 512.50, 'pro_labore': 7135.61,
            'dividendos': 0.00, 'emprestimos': 0.00, 'aj_saida': 0.00, 'maq_equip': 302.05,
            # RES. FINANCEIRO
            'rendimento': 5.04, 'remuner_bank': 0.00, 'retorno_comiss': 0.00,
            'juros_rec': 0.00, 'desc_pagar': 2680.96, 'tarifa_bancaria': 0.00,
            'juros_pagar': 0.00, 'desc_receber': 27.30,
            # QTD/OUTROS
            'q': 4, 'q_sw': 4.00, 'q_consig': 1.00, 'q_proprio': 3.00,
            # OUTROS
            'compras_func': 0.00, 'garantia_venda': 0.00,
        },
        '11': {
            # RECEITAS
            'merch_bruta_sw': 1040600.00, 'merch_bruta_at': 73000.00,
            'intermediacao_fin': 0.00, 'laudo_venda': 350.00, 'rec_doc_sai': 130.16,
            'rec_svc': 1400.00, 'venda_svc': 510.00, 'venda_comiss': 7531.31,
            'aluguel': 3750.00, 'rec_diversas': 0.00,
            # DEDUÇÕES
            'desc_sw': 33763.00, 'desc_at': 10000.00, 'csll_irpj': 1715.90, 'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 887500.00, 'custo_compra_at': 68000.00,
            'custo_prep_entrega': 20971.33, 'despachante_ent': 300.00, 'ipva': 1844.43,
            'taxas_transf_ent': 2010.00, 'garantia_custo': 0.00, 'laudo_custo': 720.00,
            # DESPESAS OPERACIONAIS
            'comissao_venda': 1000.00, 'comissao_c': 7441.91, 'pos_vendas': 2760.60,
            'despachante_sai': 0.00, 'salarios': 2049.00, 'desp_pessoal_var': 120.00,
            'refeitorio': 0.00, 'transporte': 0.00, 'aluguel_cond2': 9000.00, 'copa': 325.15,
            'cartorio': 0.00, 'mat_aux': 111.44, 'mat_escrit': 0.00, 'seguros': 846.44,
            'contabil': 1654.96, 'juridico': 0.00, 'viagens': 606.14, 'agua': 288.18,
            'energia': 156.99, 'telefonia': 108.44, 'limpeza': 78.92, 'publicidade': 6591.05,
            'brindes': 3747.50, 'pro_labore': 6000.00, 'dividendos': 0.00,
            'emprestimos': 2020.00, 'aj_saida': 0.00,
            # RES. FINANCEIRO
            'rendimento': 0.03, 'retorno_comiss': 1152.82, 'juros_rec': 1.83,
            'desc_pagar': 1735.34, 'tarifa_bancaria': 0.58, 'juros_pagar': 1.48,
            'desc_receber': 0.04,
            # QTD/OUTROS
            'q': 9, 'q_sw': 8.00, 'q_at': 1.00, 'q_consig': 2.00, 'q_proprio': 7.00,
            # OUTROS
            'compras_func': 0.00, 'garantia_venda': 0.00,
        },
        '12': {
            # RECEITAS
            'merch_bruta_sw': 758600.00, 'merch_bruta_at': 165170.00,
            'intermediacao_fin': 0.00, 'laudo_venda': 350.00, 'prep_veiculo': 2458.00,
            'gasolina': 50.00, 'rec_doc_sai': 1105.79, 'rec_svc': 830.16, 'venda_svc': 789.07,
            'venda_comiss': 5568.94, 'aluguel': 3750.00, 'rec_diversas': 5000.00,
            # DEDUÇÕES
            'desc_sw': 10760.00, 'desc_at': 25050.00, 'csll_irpj': 1715.90, 'devolucao': 0.00,
            'dev_fin': 0.00,
            # CUSTOS
            'custo_compra_sw': 697000.00, 'custo_compra_at': 151000.00,
            'custo_prep_entrega': 7772.42, 'frete': 0.00, 'despachante_ent': 1154.00,
            'ipva': 4749.20, 'taxas_transf_ent': 2206.00, 'garantia_custo': 0.00,
            'laudo_custo': 360.00,
            # DESPESAS OPERACIONAIS
            'comissao_c': 12642.76, 'pos_vendas': 1910.00, 'taxas_transf_sai': 0.00,
            'despachante_sai': 0.00, 'salarios': 3201.67, 'desp_adm_dem': 0.00,
            'desp_pessoal_var': 347.00, 'refeitorio': 0.00, 'transporte': 0.00,
            'aluguel_cond2': 9000.00, 'copa': 588.56, 'cartorio': 89.50, 'mat_aux': 21.94,
            'mat_escrit': 0.00, 'seguros': 850.00, 'contabil': 2363.93, 'informatica': 0.00,
            'consultoria': 0.00, 'juridico': 65.80, 'viagens': 0.00, 'agua': 761.07,
            'energia': 314.79, 'telefonia': 129.94, 'limpeza': 38.70, 'publicidade': 6570.16,
            'pro_labore': 6842.79, 'dividendos': 0.00, 'emprestimos': 2020.00,
            'aj_saida': 2000.00, 'maq_equip': 53.00,
            # RES. FINANCEIRO
            'retorno_acordos': 0.00, 'rendimento': 0.03, 'remuner_bank': 0.00,
            'retorno_comiss': 1474.33, 'juros_rec': 13.60, 'desc_pagar': 328.90,
            'tarifa_bancaria': 0.00, 'juros_pagar': 10.00, 'desc_receber': 0.00,
            # QTD/OUTROS
            'q': 9, 'q_sw': 6.00, 'q_at': 3.00, 'q_consig': 1.00, 'q_proprio': 8.00,
        },
        },
    'cons': {
        '1': {
            # RECEITAS — consolidado AutoConf jan/2025
            'merch_bruta_sw':   3599849.49,
            'merch_bruta_at':     15000.00,
            'rec_doc_sai':         5938.95,
            'rec_svc':            10050.00,
            'venda_svc':          20782.50,
            'laudo_venda':         6565.00,
            'transf_venda':         966.00,
            'intermediacao_fin':  49500.00,
            'venda_comiss':        7170.44,
            'rec_diversas':           0.00,
            # DEDUÇÕES
            'desc_sw':            25200.00,
            'dev_fin':            49500.00,
            # CUSTOS
            'custo_compra_sw':  3189562.98,
            'custo_compra_at':    10000.00,
            'custo_prep_entrega': 72715.69,
            'frete':               4350.00,
            'multa_veiculo':          0.00,
            'despachante_ent':     2350.00,
            'ipva':                7080.29,
            'taxas_transf_ent':   17276.32,
            'garantia_custo':      9850.00,
            'laudo_custo':         7863.60,
            # DESP. OPERACIONAIS
            'comissao_venda':       768.13,  # Outras despesas com vendas
            'comissao_c':          3020.44,
            'pos_vendas':         22960.48,
            'taxas_transf_sai':       0.00,
            'salarios':           67701.06,
            'desp_adm_dem':        2183.95,
            'desp_pessoal_var':    5644.80,
            'refeitorio':           600.00,
            'transporte':           461.25,
            'uniforme':               0.00,
            'aluguel_cond2':      30825.80,
            'copa':                  47.95,
            'cartorio':             409.27,
            'estacionamento':         0.00,
            'agua':                 397.22,
            'energia':             2845.21,
            'limpeza':              706.86,
            'manutencao_loja':      250.00,
            'mat_aux':              336.28,
            'mat_escrit':           264.32,
            'publicidade':        14565.94,
            'brindes':                0.00,
            'seguros':             1094.33,
            'contabil':           60574.88,  # Impostos e Taxas
            'consultoria':         4695.00,  # Serviços Consultoria
            'juridico':           12664.15,  # Serviços de Terceiros
            'viagens':            26516.04,
            'telefonia':            720.23,
            'maq_equip':           1054.82,  # Bens de Natureza Permanente
            'aj_saida':             213.13,
            'dividendos':         59704.77,
            'pro_labore':          6000.00,
            'emprestimos':        23204.23,
            # RES. FINANCEIRO
            'retorno_comiss':     30881.98,
            'rendimento':           453.41,
            'desc_pagar':         15588.54,
            'juros_rec':           2018.44,
            'tarifa_bancaria':      815.24,
            'desc_receber':         380.22,
            'juros_pagar':          290.83,
            'juros_pagar2':        2187.45,
        },
        '2': {
            # RECEITAS — consolidado AutoConf fev/2025
            'merch_bruta_sw':   1946550.00,
            'merch_bruta_at':         0.00,
            'rec_doc_sai':         1936.17,
            'rec_svc':             7546.00,
            'venda_svc':          34191.86,
            'laudo_venda':         4289.11,
            'transf_venda':         300.00,
            'intermediacao_fin':      0.00,
            'venda_comiss':        9825.39,
            'rec_diversas':        3000.00,  # Ajuste de saldo – Entrada
            # DEDUÇÕES
            'desc_sw':            15700.00,
            'desc_at':                0.00,
            'custas':               134.35,
            'dev_fin':                0.00,
            # CUSTOS
            'custo_compra_sw':  1659880.00,
            'custo_compra_at':        0.00,
            'custo_prep_entrega':  53685.77,
            'frete':               1450.00,
            'multa_veiculo':          0.00,
            'despachante_ent':     4460.00,
            'ipva':               13363.20,
            'taxas_transf_ent':   13653.44,
            'garantia_custo':      8650.00,
            'laudo_custo':         6760.20,
            # DESP. OPERACIONAIS
            'comissao_venda':     21804.19,  # Comissão S/ Venda (17806.90) + Outras (3997.29)
            'comissao_c':         12325.39,
            'pos_vendas':          6676.39,
            'taxas_transf_sai':     208.00,
            'salarios':           80776.04,
            'desp_adm_dem':        2235.37,
            'desp_pessoal_var':     825.38,
            'refeitorio':          1651.98,
            'transporte':           503.80,
            'uniforme':            1029.40,
            'aluguel_cond2':      30825.80,
            'copa':                2059.55,
            'cartorio':             469.75,
            'estacionamento':        15.00,
            'mat_aux':              206.06,
            'mat_escrit':           415.40,
            'seguros':             2299.03,
            'contabil':           79038.42,  # Impostos e Taxas
            'juridico':            3829.50,  # Serviços de Terceiros
            'consultoria':         4500.00,
            'viagens':            19557.04,
            'agua':                 267.73,
            'energia':                0.00,
            'limpeza':                0.00,
            'manutencao_loja':        0.00,
            'telefonia':            694.39,
            'publicidade':         9898.46,
            'brindes':              265.00,
            'maq_equip':           1200.63,
            'aj_saida':           15849.51,
            'emprestimos':        24059.54,
            'dividendos':         49660.09,
            'pro_labore':          9707.37,
            # RES. FINANCEIRO
            'retorno_comiss':     27994.74,
            'rendimento':           119.03,
            'desc_pagar':         11836.76,
            'juros_rec':            558.97,
            'tarifa_bancaria':      783.49,
            'desc_receber':        1935.00,
            'juros_pagar':          108.41,
            'juros_pagar2':           0.00,
        },
        '3': {
            # RECEITAS — consolidado AutoConf mar/2025
            'merch_bruta_sw':   2286833.87,
            'merch_bruta_at':    266800.00,
            'rec_doc_sai':        12127.04,
            'rec_svc':             9015.00,
            'venda_svc':          21928.03,
            'laudo_venda':         4950.00,
            'transf_venda':         635.38,
            'intermediacao_fin':      0.00,
            'venda_comiss':       12824.97,
            'rec_diversas':       56029.50,  # Ajuste de saldo – Entrada
            # DEDUÇÕES
            'desc_sw':            13000.00,
            'desc_at':             1000.00,
            'custas':                 0.00,
            'dev_fin':                0.00,
            # CUSTOS
            'custo_compra_sw':  1954417.30,
            'custo_compra_at':   240097.51,
            'custo_prep_entrega':  66929.00,
            'frete':                  0.00,
            'multa_veiculo':        244.71,
            'despachante_ent':     4450.00,
            'ipva':               15172.67,
            'taxas_transf_ent':   12165.17,
            'garantia_custo':      7750.00,
            'laudo_custo':         5093.90,
            # DESP. OPERACIONAIS
            'comissao_venda':      5735.04,  # Comissão S/ Venda (1689.20) + Outras (4045.84)
            'comissao_c':          2824.97,
            'pos_vendas':          5790.49,
            'taxas_transf_sai':     220.00,
            'despachante_sai':        0.00,
            'salarios':           58162.63,
            'desp_adm_dem':        1401.69,
            'desp_pessoal_var':     912.68,
            'refeitorio':           908.48,
            'transporte':           668.67,
            'uniforme':              70.00,
            'aluguel_cond2':      33800.00,
            'copa':                 605.76,
            'cartorio':             278.09,
            'estacionamento':         0.00,
            'mat_aux':              195.00,
            'mat_escrit':           349.70,
            'seguros':              524.90,
            'contabil':           42591.00,  # Impostos e Taxas
            'juridico':           13062.34,  # Serviços de Terceiros
            'consultoria':         4500.00,
            'viagens':                4.90,
            'agua':                 280.44,
            'energia':             1258.46,
            'limpeza':               76.84,
            'manutencao_loja':        0.00,
            'telefonia':            839.73,
            'publicidade':        18800.54,
            'brindes':             1023.12,
            'maq_equip':          15199.86,  # Bens Nat. Perm. Desp.Adm (2332.90) + Máquinas (12866.96)
            'aj_saida':           44772.01,
            'emprestimos':        20750.20,
            'dividendos':         53500.00,
            'pro_labore':          6000.00,
            # RES. FINANCEIRO
            'retorno_comiss':     16072.19,
            'retorno_fin':         1305.92,
            'rendimento':            84.94,
            'desc_pagar':         20953.51,
            'juros_rec':            249.13,
            'tarifa_bancaria':      468.55,
            'desc_receber':          56.50,
            'juros_pagar':            0.00,
            'juros_pagar2':        1193.92,
        },
    },
}

_DRE_CORR_2024 = {
    'mm':   {
        '1': {
            # RECEITAS
            'garantia_venda': 2299.00,
            # CUSTOS
            'custo_prep_entrega': 41551.71, 'frete': 1500.00, 'multa_veiculo': 533.29,
            'laudo_custo': 4806.14,
            # DESPESAS OPERACIONAIS
            'despachante_sai': 489.42, 'desp_pessoal_var': 8750.64,
            'agua': 464.00, 'manutencao_loja': 510.00, 'contabil': 36079.06,
            'consultoria': 4049.00, 'maq_equip': 32145.50,
            # RES. FINANCEIRO
            'retorno_comiss': 25725.60, 'desc_pagar': 9711.84, 'juros_rec': 3609.40,
            'desc_receber': 897.44, 'juros_pagar2': 1232.10,
        },
        '2': {
            # RECEITAS
            'venda_svc': 6844.00,
            # CUSTOS
            'custo_prep_entrega': 32092.04, 'frete': 1000.00, 'multa_veiculo': 299.33,
            # DESPESAS OPERACIONAIS
            'despachante_sai': 1088.75, 'desp_adm_dem': 7636.45, 'desp_pessoal_var': 3506.21,
            'agua': 300.00, 'informatica': 207.40, 'contabil': 10936.52,
            'consultoria': 6245.38, 'maq_equip': 193915.54,
            # RES. FINANCEIRO
            'retorno_comiss': 27194.97, 'retorno_fin': 1738.15, 'desc_pagar': 7887.64,
            'desc_receber': 2178.99, 'juros_pagar': 337.68,
        },
        '3': {
            # RECEITAS
            'rec_doc_sai': 0.00, 'intermediacao_fin': 37456.30,
            # DEDUÇÕES
            'desc_sw': 35694.77, 'dev_fin': 37456.29,
            # CUSTOS
            'custo_prep_entrega': 78398.64, 'frete': 500.00, 'multa_veiculo': 478.96,
            'garantia_custo': 6898.00,
            # DESPESAS OPERACIONAIS
            'despachante_sai': 384.41, 'desp_adm_dem': 540.87, 'desp_pessoal_var': 2120.80,
            'agua': 187.00, 'informatica': 87.50, 'contabil': 15962.80,
            'consultoria': 6622.06, 'maq_equip': 91090.65, 'emprestimos': 833.33,
            # RES. FINANCEIRO
            'retorno_comiss': 31220.20, 'retorno_fin': 2201.85, 'desc_pagar': 9873.45,
            'desc_receber': 34.73, 'juros_pagar': 413.92,
        },
        '4': {
            # DEDUÇÕES
            'desc_sw': 77600.00, 'desc_at': 3686.00,
            # CUSTOS
            'custo_prep_entrega': 30178.07, 'frete': 500.00, 'multa_veiculo': 104.13,
            # DESPESAS OPERACIONAIS
            'despachante_sai': 74.92, 'desp_adm_dem': 200.00, 'desp_pessoal_var': 2709.37,
            'agua': 374.00, 'informatica': 102.90, 'contabil': 31361.91,
            'manutencao_loja': 129.90, 'juridico': 9735.72,
            'maq_equip': 110742.28, 'emprestimos': 16887.73,
            # RES. FINANCEIRO
            'retorno_fin': 3481.86, 'desc_pagar': 10517.45, 'juros_pagar2': 833.54,
            'desc_receber': 793.94, 'iof': 51.23,
        },
        '5': {
            # RECEITAS
            'rec_doc_sai': 0.00, 'rec_svc': 0.00, 'venda_svc': 7657.58,
            # CUSTOS
            'custo_prep_entrega': 44907.34, 'multa_veiculo': 569.54, 'garantia_custo': 13400.00,
            # DESPESAS OPERACIONAIS
            'despachante_sai': 2673.84, 'desp_pessoal_var': 14787.55,
            'agua': 297.50, 'pub_adm': 44.21, 'contabil': 11722.89, 'juridico': 13102.45,
            'maq_equip': 489.10, 'emprestimos': 12927.98,
            # RES. FINANCEIRO
            'rendimento': 19.15, 'desc_pagar': 16030.62, 'juros_rec': 1662.83,
            'tarifa_bancaria': 622.67, 'juros_pagar2': 147.46, 'desc_receber': 1130.00,
            'iof': 881.03,
        },
        '6': {
            # RECEITAS
            'rec_doc_sai': 0.00,
            # CUSTOS
            'custo_prep_entrega': 15064.79, 'multa_veiculo': 0.00,
            # DESPESAS OPERACIONAIS
            'despachante_sai': 161.90, 'desp_adm_dem': 4499.28, 'desp_pessoal_var': 320.30,
            'agua': 306.00, 'pub_adm': 4003.90, 'informatica': 100.00, 'contabil': 21692.65,
            'associacoes': 556.35, 'juridico': 6158.93,
            'maq_equip': 13180.37, 'emprestimos': 12813.26,
            # RES. FINANCEIRO
            'retorno_comiss': 25697.68, 'desc_pagar': 11815.42, 'juros_rec': 392.31,
            'desc_receber': 3323.48, 'juros_pagar': 226.33,
        },
        '7': {
            # RECEITAS
            'rec_doc_sai': 0.00, 'venda_svc': 25478.00,
            # DEDUÇÕES
            'desc_sw': 69650.00, 'desc_at': 13938.00,
            # CUSTOS
            'custo_prep_entrega': 83403.93, 'multa_veiculo': 639.37, 'garantia_custo': 19349.00,
            # DESPESAS OPERACIONAIS
            'pos_vendas': 24733.31, 'despachante_sai': 1086.91,
            'desp_adm_dem': 7354.36, 'desp_pessoal_var': 159.80,
            'agua': 221.00, 'pub_adm': 72020.46, 'informatica': 110.00, 'contabil': 51730.05,
            'manutencao_loja': 196.68, 'juridico': 11492.68, 'associacoes': 615.03,
            'maq_equip': 49916.85, 'emprestimos': 71397.44,
            # RES. FINANCEIRO
            'retorno_comiss': 33379.71, 'desc_pagar': 17210.51, 'juros_rec': 622.79,
            'juros_pagar2': 61.93, 'desc_receber': 496.74, 'iof': 2000.09,
        },
        '8': {
            # DEDUÇÕES
            'desc_at': 22800.00,
            # CUSTOS
            'custo_prep_entrega': 42311.86, 'multa_veiculo': 400.88, 'garantia_custo': 3320.00,
            # DESPESAS OPERACIONAIS
            'despachante_sai': 443.80, 'desp_adm_dem': 4828.56, 'desp_pessoal_var': 2790.50,
            'agua': 272.00, 'pub_adm': 494.90, 'contabil': 28832.55, 'associacoes': 399.00,
            'juridico': 4345.00, 'informatica': 11518.13,
            'maq_equip': 28777.76, 'emprestimos': 19917.78,
            # RES. FINANCEIRO
            'retorno_fin': 1785.00, 'desc_pagar': 18677.96, 'juros_pagar2': 371.46,
            'desc_receber': 1076.99, 'iof': 3009.41,
        },
        '9': {
            # RECEITAS
            'rec_doc_sai': 0.00, 'venda_svc': 11749.36, 'garantia_venda': 0.00,
            # CUSTOS
            'custo_prep_entrega': 36248.44, 'multa_veiculo': 0.00,
            # DESPESAS OPERACIONAIS
            'despachante_sai': 311.39, 'desp_adm_dem': 105.00, 'desp_pessoal_var': 404.80,
            'agua': 326.00, 'pub_adm': 10244.90, 'informatica': 311.40, 'contabil': 29098.74,
            'associacoes': 40.00, 'juridico': 8846.00,
            'maq_equip': 25531.62, 'emprestimos': 18625.35,
            # RES. FINANCEIRO
            'retorno_fin': 1389.79, 'desc_pagar': 11048.16, 'juros_pagar2': 1861.80,
            'desc_receber': 133.28, 'juros_pagar': 3981.18,
        },
        '10': {
            # RECEITAS
            'rec_doc_sai': 115.00,
            # CUSTOS
            'custo_prep_entrega': 44464.66, 'multa_veiculo': 599.22, 'garantia_custo': 5300.00,
            # DESPESAS OPERACIONAIS
            'despachante_sai': 2019.89, 'desp_adm_dem': 4390.89, 'desp_pessoal_var': 960.68,
            'agua': 166.00, 'pub_adm': 10310.79, 'informatica': 11.30, 'contabil': 60318.70,
            'associacoes': 112.00, 'juridico': 7149.00, 'estacionamento': 240.00,
            'maq_equip': 489.10, 'emprestimos': 24031.00,
            # RES. FINANCEIRO
            'retorno_comiss': 41507.77, 'desc_pagar': 14696.89, 'juros_rec': 416.41,
            'desc_receber': 1437.94, 'juros_pagar': 815.83,
        },
        '11': {
            # RECEITAS
            'rec_doc_sai': 9018.86,
            # CUSTOS
            'custo_prep_entrega': 42241.37, 'multa_veiculo': 104.13, 'despachante_ent': 3400.00,
            'taxas_transf_ent': 16371.88, 'garantia_custo': 5250.00, 'laudo_custo': 6717.00,
            # DESPESAS OPERACIONAIS
            'despachante_sai': 327.54, 'desp_adm_dem': 6452.40, 'desp_pessoal_var': 99.30,
            'agua': 352.00, 'pub_adm': 10424.90, 'informatica': 26.00, 'contabil': 39994.07,
            'manutencao_loja': 200.00, 'juridico': 10698.00, 'associacoes': 922.22,
            'maq_equip': 10385.58, 'emprestimos': 18895.62,
            # RES. FINANCEIRO
            'retorno_comiss': 36920.84, 'desc_pagar': 8605.20, 'juros_rec': 677.32,
            'desc_receber': 17.80, 'juros_pagar2': 4881.49,
        },
        '12': {
            # RECEITAS
            'rec_doc_sai': 2955.43, 'laudo_venda': 4310.00, 'venda_svc': 18699.00,
            # CUSTOS
            'custo_prep_entrega': 129779.47, 'frete': 600.00, 'multa_veiculo': 234.78,
            'ipva': 7088.96, 'taxas_transf_ent': 11959.36, 'garantia_custo': 11989.38,
            'laudo_custo': 5428.90, 'cartorio': 248.18,
            # DESPESAS OPERACIONAIS
            'despachante_sai': 879.04, 'desp_adm_dem': 6019.16, 'desp_pessoal_var': 65.80,
            'agua': 279.00, 'pub_adm': 51450.70, 'contabil': 27259.61, 'juridico': 6631.18,
            'maq_equip': 0.00, 'emprestimos': 25694.32,
            # RES. FINANCEIRO
            'desc_pagar': 21107.89, 'juros_rec': 362.28,
            'desc_receber': 817.12, 'juros_pagar': 3102.84,
        },
    },
    'bk':   {
        '3': {
            # loja ainda não existia — zera contaminação vinda da MM (API)
            'intermediacao_fin': 0.00, 'dev_fin': 0.00,
        },
        '8': {
            # CUSTOS
            'custo_prep_entrega': 8.25,
            # DESPESAS OPERACIONAIS
            'juridico': 700.00, 'pub_adm': 178.13, 'maq_equip': 0.00,
        },
        '9': {
            # CUSTOS
            'custo_prep_entrega': 0.00,
            # DESPESAS OPERACIONAIS
            'desp_pessoal_var': 373.99, 'agua': 313.38, 'juridico': 1020.00,
        },
        '10': {
            # RECEITAS
            'venda_svc': 25815.37,
            # CUSTOS
            'custo_prep_entrega': 605.45,
            # DESPESAS OPERACIONAIS
            'pub_adm': 1293.00, 'contabil': 107.00, 'juridico': 1535.00,
            'maq_equip': 23364.42,
            # RES. FINANCEIRO
            'juros_rec': 50.00,
        },
        '11': {
            # CUSTOS
            'custo_prep_entrega': 647.00,
            # DESPESAS OPERACIONAIS
            'agua': 308.74, 'contabil': 99.64, 'juridico': 300.00,
            # RES. FINANCEIRO
            'juros_pagar': 85.22,
        },
        '12': {
            # CUSTOS
            'custo_prep_entrega': 20.00, 'frete': 0.00,
            # DESPESAS OPERACIONAIS
            'agua': 288.75, 'contabil': 261.25, 'manutencao_loja': 100.00,
            # RES. FINANCEIRO
            'juros_pagar': 0.75,
        },
    },
    'cons': {},
}

def apply_dre_corrections(raw, store, corr=None):
    if corr is None: corr = _DRE_CORR
    c = corr.get(store, {})
    for mes_str, fixes in c.items():
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
        estoque = (row.get('Estoque','') or '').strip()
        d['q'] += 1
        if estoque == 'Consignado':
            d['q_consig'] += 1
        else:
            d['q_proprio'] += 1
        if sw:
            d['q_sw'] += 1
        else:
            d['q_at'] += 1
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

def parse_lv_txns(csv_text, rev):
    """Per-vehicle txns from lucro-venda: merch_bruta, custo_compra, desc, rec_doc_sai, rec_svc."""
    d = defaultdict(list)
    if not csv_text: return d
    def pus(s): s=(s or '').strip(); return float(s) if s else 0.0
    for row in csv.DictReader(io.StringIO(csv_text)):
        if (row.get('Saida','') or '').strip().lower() == 'total': continue
        if (row.get('Revenda Saída ID','') or '').strip() != rev: continue
        tipo   = (row.get('Tipo Venda','') or '').strip()
        sw     = tipo != 'Atacado'
        saida  = (row.get('Saida','') or '').strip()
        marca  = (row.get('Marca','') or '').strip()
        modelo = (row.get('Modelo','') or '').strip()
        placa  = (row.get('Placa','') or '').strip()
        vb     = pus(row.get('Venda Bruta'))
        desc   = pus(row.get('Valor Desconto'))
        compra = pus(row.get('Compra'))
        rec_ds = pus(row.get('Receita com Documentos Saída'))
        rec_de = pus(row.get('Receita com Documentos Entrada'))
        rec_se = pus(row.get('Receita com Serviços Agregados Entrada'))
        rec_ss = pus(row.get('Receita com Serviços Agregados Saída'))
        if vb <= 0 and compra <= 0: continue
        ident = f"{marca} {modelo} {placa}".strip()
        if sw:
            if vb > 0:     d['merch_bruta_sw'].append({'comp':saida,'liq':saida,'id':ident,'val':vb})
            if desc > 0:   d['desc_sw'].append({'comp':saida,'liq':saida,'id':ident,'val':desc})
            if compra > 0: d['custo_compra_sw'].append({'comp':saida,'liq':saida,'id':ident,'val':compra})
        else:
            if vb > 0:     d['merch_bruta_at'].append({'comp':saida,'liq':saida,'id':ident,'val':vb})
            if desc > 0:   d['desc_at'].append({'comp':saida,'liq':saida,'id':ident,'val':desc})
            if compra > 0: d['custo_compra_at'].append({'comp':saida,'liq':saida,'id':ident,'val':compra})
        rec_doc = rec_ds + rec_de
        if rec_doc > 0: d['rec_doc_sai'].append({'comp':saida,'liq':saida,'id':ident,'val':rec_doc})
        rec_svc = rec_se + rec_ss
        if rec_svc > 0: d['rec_svc'].append({'comp':saida,'liq':saida,'id':ident,'val':rec_svc})
    return d

def _parse_txns(rev_filter, target_mes, target_ano):
    """Returns per-transaction list per field: {field: [{comp,liq,id,val}, ...]}"""
    d = defaultdict(list)
    seen = set()
    target_str = f"{target_mes:02d}/{target_ano}"
    for (m, ano), csv_text in _extrato_cache.items():
        if not csv_text: continue
        for row in csv.DictReader(io.StringIO(csv_text)):
            rid = (row.get('Revenda Origem Id','') or '').strip()
            if rev_filter is None:
                if rid != '': continue      # group-level: blank rid
            else:
                if rid != rev_filter: continue
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
            dl    = (row.get('Data Liquidação','') or '').strip()
            ident = (row.get('Identificação','') or '').strip()
            d[field].append({'comp': dc, 'liq': dl, 'id': ident or conta, 'val': valor})
    return {f: sorted(v, key=lambda x: x['comp']) for f, v in d.items()}

# ── PROCESS ONE CALENDAR YEAR ──────────────────────────────────────────────
def process_year(year, dre_corr, today):
    """Fetch and process all DRE/COMP/FLUXO data for a single year."""
    active_months = [m for m in range(1, 13) if date(year, m, 1) <= today]
    if not active_months:
        return None

    print(f"\n=== [{year}] {len(active_months)} meses ===")

    # ── 1. COMPETÊNCIA (lucro-venda) ──────────────────────────────────────
    print(f"[1] lucro-venda {year}...")
    comp_mm_raw = {}; comp_bk_raw = {}
    _lv_cache = {}
    for m in active_months:
        print(f"  {m:02d}/{year}...", end=" ", flush=True)
        txt = api_get("relatorio/financeiro/lucro-venda", m, year)
        if txt:
            _lv_cache[m] = txt
            mm = parse_comp(txt, store_filter='mm')
            bk = parse_comp(txt, store_filter='bk')
            if mm: comp_mm_raw[m] = mm
            if bk: comp_bk_raw[m] = bk
            print(f"MM:{sum(v['q'] for v in mm.values())}v BK:{sum(v['q'] for v in bk.values())}v")
        else:
            print("sem dados")

    apply_comp_manual(comp_mm_raw, 'mm', year)
    apply_comp_manual(comp_bk_raw, 'bk', year)
    comp_mm   = build_store_comp(comp_mm_raw)
    comp_bk   = build_store_comp(comp_bk_raw)
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
    print(f"[2] extrato-titulos {year}...")
    fetch_all_extratos(year, active_months)
    if active_months[0] > 1:
        fetch_all_extratos(year, [active_months[0] - 1])
    if year > 2024:
        fetch_all_extratos(year - 1, [12])

    fluxo_mm_raw = {}; fluxo_bk_raw = {}
    for m in active_months:
        print(f"  fluxo {m:02d}/{year}...", end=" ", flush=True)
        mm = parse_fluxo_month(m, year, store_filter='mm')
        bk = parse_fluxo_month(m, year, store_filter='bk')
        if mm: fluxo_mm_raw[m] = mm
        if bk: fluxo_bk_raw[m] = bk
        tf = sum(v['fin'] for v in mm.values())
        print(f"fin=R${tf:,.0f} q={sum(v['q'] for v in mm.values())}")

    apply_fluxo_manual(fluxo_mm_raw, 'mm', year)
    apply_fluxo_manual(fluxo_bk_raw, 'bk', year)
    fluxo_mm  = build_store_fluxo(fluxo_mm_raw)
    fluxo_bk  = build_store_fluxo(fluxo_bk_raw)

    seguro_mm_raw = {}; seguro_bk_raw = {}
    for m in active_months:
        mm_s = parse_seguro_month(m, year, store_filter='mm')
        bk_s = parse_seguro_month(m, year, store_filter='bk')
        if mm_s: seguro_mm_raw[str(m)] = mm_s
        if bk_s: seguro_bk_raw[str(m)] = bk_s

    seguro_cons_raw = {}
    all_seg_months = set(seguro_mm_raw) | set(seguro_bk_raw)
    for mes in all_seg_months:
        merged = defaultdict(float)
        for b, v in seguro_mm_raw.get(mes, {}).items(): merged[b] += v
        for b, v in seguro_bk_raw.get(mes, {}).items(): merged[b] += v
        seguro_cons_raw[mes] = {b: round(v, 2) for b, v in merged.items()}

    seguro_final = {'mm': seguro_mm_raw, 'bk': seguro_bk_raw, 'cons': seguro_cons_raw}

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

    # ── 2b. DRE ──────────────────────────────────────────────────────────
    print(f"[2b] DRE {year}...")
    dre_mm_raw = {}; dre_bk_raw = {}
    dre_txns_mm = {}; dre_txns_bk = {}; dre_txns_cons = {}
    for m in active_months:
        txt = _lv_cache.get(m, '')
        lv_mm = parse_lv_dre(txt, REV_MM)
        lv_bk = parse_lv_dre(txt, REV_BK)
        ex_mm = parse_ext_dre(REV_MM, m, year)
        ex_bk = parse_ext_dre(REV_BK, m, year)
        def merge_dre(a, b):
            d = dict(a)
            for k, v2 in b.items(): d[k] = round(d.get(k, 0) + v2, 2)
            return d
        dre_mm_raw[str(m)] = merge_dre(lv_mm, ex_mm)
        dre_bk_raw[str(m)] = merge_dre(lv_bk, ex_bk)
        print(f"  {m:02d}/{year} MM:{dre_mm_raw[str(m)].get('q',0):.0f}v BK:{dre_bk_raw[str(m)].get('q',0):.0f}v")
        txns_mm  = _parse_txns(REV_MM, m, year)
        txns_bk  = _parse_txns(REV_BK, m, year)
        txns_grp = _parse_txns(None,   m, year)
        lv_txt = _lv_cache.get(m, '')
        lv_mm = parse_lv_txns(lv_txt, REV_MM)
        lv_bk = parse_lv_txns(lv_txt, REV_BK)
        for f, lst in lv_mm.items(): txns_mm[f] = sorted(lst + txns_mm.get(f,[]), key=lambda x: x['comp'])
        for f, lst in lv_bk.items(): txns_bk[f] = sorted(lst + txns_bk.get(f,[]), key=lambda x: x['comp'])
        dre_txns_mm[str(m)] = txns_mm
        dre_txns_bk[str(m)] = txns_bk
        merged_cons = {}
        for f in set(txns_mm) | set(txns_bk) | set(txns_grp):
            merged_cons[f] = sorted(txns_mm.get(f,[]) + txns_bk.get(f,[]) + txns_grp.get(f,[]), key=lambda x: x['comp'])
        dre_txns_cons[str(m)] = merged_cons

    apply_dre_corrections(dre_mm_raw, 'mm', dre_corr)
    apply_dre_corrections(dre_bk_raw, 'bk', dre_corr)
    dre_cons_raw = {}
    for m in [str(x) for x in active_months]:
        all_keys = set(dre_mm_raw.get(m,{}).keys()) | set(dre_bk_raw.get(m,{}).keys())
        dre_cons_raw[m] = {k: round(dre_mm_raw.get(m,{}).get(k,0)+dre_bk_raw.get(m,{}).get(k,0),2) for k in all_keys}
        grp = parse_ext_dre_group(int(m), year)
        for k, v in grp.items():
            dre_cons_raw[m][k] = round(dre_cons_raw[m].get(k, 0) + v, 2)
        cons = dre_cons_raw[m]
        ci = cons.get('intermediacao_fin', 0)
        cd = cons.get('dev_fin', 0)
        if ci > 0 and cd > 0 and abs(ci - cd) < 1.0:
            for store in (cons, dre_mm_raw[m], dre_bk_raw[m]):
                store['intermediacao_fin'] = 0
                store['dev_fin'] = 0
    apply_dre_corrections(dre_cons_raw, 'cons', dre_corr)

    _COUNT_FIELDS = {'q', 'q_sw', 'q_at', 'q_proprio', 'q_consig'}
    for m_str in [str(x) for x in active_months]:
        cons_m = dre_cons_raw[m_str]
        mm_m   = dre_mm_raw[m_str]
        bk_m   = dre_bk_raw[m_str]
        mm_q   = mm_m.get('q', 0) or 0
        bk_q   = bk_m.get('q', 0) or 0
        total_q = (mm_q + bk_q) or 1
        new_mm = {k: mm_m[k] for k in _COUNT_FIELDS if k in mm_m}
        new_bk = {k: bk_m[k] for k in _COUNT_FIELDS if k in bk_m}
        for k, cons_val in cons_m.items():
            if k in _COUNT_FIELDS: continue
            mm_v = mm_m.get(k, 0)
            bk_v = bk_m.get(k, 0)
            raw_total = mm_v + bk_v
            ratio = (mm_v / raw_total) if raw_total != 0 else (mm_q / total_q)
            mm_share = round(cons_val * ratio, 2)
            new_mm[k] = mm_share
            new_bk[k] = round(cons_val - mm_share, 2)
        dre_mm_raw[m_str] = new_mm
        dre_bk_raw[m_str] = new_bk

    for m_str, fixes in dre_corr.get('mm', {}).items():
        if m_str not in dre_cons_raw: continue
        for k, mm_val in fixes.items():
            dre_mm_raw[m_str][k] = mm_val
            dre_bk_raw[m_str][k] = round(dre_cons_raw[m_str].get(k, 0) - mm_val, 2)

    for m_str, fixes in dre_corr.get('bk', {}).items():
        if m_str not in dre_cons_raw: continue
        for k, bk_val in fixes.items():
            dre_bk_raw[m_str][k] = bk_val
            mm_val = dre_mm_raw[m_str].get(k, 0) or 0
            dre_cons_raw[m_str][k] = round(mm_val + bk_val, 2)

    return {
        'generated': today.strftime('%d/%m/%Y'),
        'comp':   {'mm': comp_mm,   'bk': comp_bk,   'cons': comp_cons},
        'fluxo':  {'mm': fluxo_mm,  'bk': fluxo_bk,  'cons': fluxo_cons},
        'seguro': seguro_final,
        'dre':    {'mm': dre_mm_raw, 'bk': dre_bk_raw, 'cons': dre_cons_raw,
                   'txns': {'mm': dre_txns_mm, 'bk': dre_txns_bk, 'cons': dre_txns_cons}},
    }


# ── BI MODULE (Visão Geral / gráficos) ──────────────────────────────────────
# Espelha exatamente a fórmula c(d) usada em index.html na aba DRE, garantindo
# que a Visão Geral sempre bata com o DRE oficial (nunca mais fica desatualizada).
def compute_bi_month(d):
    def v(f):
        return d.get(f, 0) or 0
    merch = v('merch_bruta_sw') + v('merch_bruta_at')
    rec_svc = (v('intermediacao_fin') + v('laudo_venda') + v('transf_venda') + v('fotos') +
               v('prep_veiculo') + v('gasolina') + v('rec_doc_sai') + v('rec_svc') +
               v('venda_svc') + v('venda_comiss') + v('aluguel') + v('garantia_venda'))
    total_rec = merch + rec_svc + v('rec_diversas')
    desc = v('desc_sw') + v('desc_at')
    imp = (v('esocial') + v('fgts') + v('csll_irpj') + v('pis_cofins') + v('icms') + v('iss') +
           v('alvara') + v('fisc_func') + v('iptu') + v('retencoes') + v('custas') + v('das'))
    dev = v('devolucao') + v('dev_fin')
    total_ded = desc + imp + dev
    fat_liq = total_rec - total_ded
    custo_compra = v('custo_compra_sw') + v('custo_compra_at')
    custo_prep = v('custo_prep_entrega') + v('frete') + v('multa_veiculo') + v('custos_prep_lv')
    custo_docs = (v('despachante_ent') + v('ipva') + v('taxas_transf_ent') + v('baixa_gravame') +
                  v('comunicado_venda') + v('multas_nao_abat'))
    custo_svc = v('garantia_custo') + v('laudo_custo')
    total_cust = custo_compra + custo_prep + custo_docs + custo_svc
    margem = fat_liq - total_cust
    desp_vend = v('comissao_venda') + v('comissao_c') + v('pos_vendas') + v('taxas_transf_sai') + v('despachante_sai')
    desp_pess = (v('salarios') + v('desp_adm_dem') + v('desp_pessoal_var') + v('ferias') +
                 v('rescisao') + v('fgts_rescis') + v('plano_saude') + v('datas_com') +
                 v('refeitorio') + v('transporte') + v('uniforme') + v('medicina') +
                 v('cursos') + v('churrasco') + v('almoco_meta'))
    desp_adm = (v('aluguel_cond2') + v('copa') + v('cartorio') + v('mat_aux') + v('mat_escrit') +
                v('seguros') + v('contabil') + v('informatica') + v('associacoes') +
                v('consultoria') + v('juridico') + v('viagens') + v('estacionamento') + v('pub_adm'))
    desp_est = v('aluguel_cond') + v('agua') + v('energia') + v('telefonia') + v('limpeza') + v('manutencao_loja')
    desp_mkt = v('publicidade') + v('portais') + v('feirao') + v('brindes')
    desp_soc = v('pro_labore') + v('dividendos')
    desp_outros = v('emprestimos') + v('aj_saida') + v('maq_equip')
    total_desp = desp_vend + desp_pess + desp_adm + desp_est + desp_mkt + desp_soc + desp_outros
    lucro_op = margem - total_desp
    res_fin_pos = (v('retorno_fin') + v('retorno_acordos') + v('rendimento') + v('seguro_rec') +
                   v('remuner_bank') + v('retorno_comiss') + v('juros_rec') + v('pecld_rec') + v('desc_pagar'))
    res_fin_neg = v('tarifa_bancaria') + v('juros_pagar') + v('juros_pagar2') + v('iof') + v('desc_receber')
    res_fin = res_fin_pos - res_fin_neg
    resultado = lucro_op + res_fin
    return {
        'rec': total_rec, 'lb': margem, 'res': resultado, 'qtd': v('q'),
        'pess': desp_pess, 'vend': desp_vend, 'prop': desp_mkt,
        'adm': desp_adm + desp_est + desp_soc + desp_outros,
        'fin': res_fin, 'ret': v('retorno_comiss'), 'div': v('dividendos'),
        'pl': v('pro_labore'), 'imp': imp,
        'cshow': v('custo_compra_sw'), 'catac': v('custo_compra_at'),
        'cprep': custo_prep, 'cdocs': custo_docs, 'csa': custo_svc,
        'rshow': v('merch_bruta_sw'), 'ratac': v('merch_bruta_at'),
        'dshow': v('desc_sw'), 'datac': v('desc_at'),
    }

BI_FIELDS = ['rec','lb','res','qtd','pess','adm','prop','ret','fin','vend','div','pl','imp',
             'cshow','catac','cprep','cdocs','csa','rshow','ratac','dshow','datac']

def build_bi_year(dre_store_raw):
    """dre_store_raw: {'1':{...},...,'12':{...}} (meses presentes = meses já processados)."""
    months = sorted(int(k) for k in dre_store_raw.keys())
    n = max(months) if months else 0
    out = {f: [0]*12 for f in BI_FIELDS}
    out['n'] = n
    for mo in range(1, n+1):
        d = dre_store_raw.get(str(mo))
        metrics = compute_bi_month(d) if d else {}
        for f in BI_FIELDS:
            out[f][mo-1] = round(metrics.get(f, 0), 2)
    return out

def build_bi_module(html, new_final):
    """Regenera var DRE={...} (bi-module usado na Visão Geral) a partir do FINAL
    recém-calculado (2024, 2025, 2026 — todos recalculados a cada run)."""
    m = re.search(r'var DRE=(\{.*?\});', html, re.DOTALL)
    if not m:
        return html
    new_bi = {'mm': {}, 'bk': {}, 'cons': {}}
    for store in ('mm', 'bk', 'cons'):
        for year in ('2024', '2025', '2026'):
            year_data = new_final.get(year, {})
            dre = year_data.get('dre', {}) if year_data else {}
            store_raw = dre.get(store, {})
            new_bi[store][year] = build_bi_year(store_raw)
    new_json = json.dumps(new_bi, ensure_ascii=False, separators=(',', ':'))
    return html[:m.start(1)] + new_json + html[m.end(1):]


# ── MAIN ───────────────────────────────────────────────────────────────────
def main():
    today = date.today()
    print(f"=== Atualizando dashboard 2026 + 2025 + 2024 — {today.strftime('%d/%m/%Y')} ===")

    with open(INDEX, 'r', encoding='utf-8') as f:
        html = f.read()
    m_pat = re.search(r'var FINAL=(\{.*?\});', html, re.DOTALL)
    if not m_pat:
        print("ERRO: var FINAL não encontrado em index.html"); return
    old_final = json.loads(m_pat.group(1))

    def preserved(year_key, field):
        """Preserve gvop/acordo from old FINAL (handles flat→keyed migration)."""
        if year_key in old_final:
            return old_final[year_key].get(field, {})
        # Old flat format (pre-multi-year): treat as 2026
        if year_key == '2026':
            return old_final.get(field, {})
        return {}

    data_2026 = process_year(2026, _DRE_CORR, today)
    if data_2026:
        data_2026['gvop']   = preserved('2026', 'gvop')
        data_2026['acordo'] = preserved('2026', 'acordo')

    data_2025 = process_year(2025, _DRE_CORR_2025, today)
    if data_2025:
        data_2025['gvop']   = preserved('2025', 'gvop')
        data_2025['acordo'] = preserved('2025', 'acordo')

    data_2024 = process_year(2024, _DRE_CORR_2024, today)
    if data_2024:
        data_2024['gvop']   = preserved('2024', 'gvop')
        data_2024['acordo'] = preserved('2024', 'acordo')

    new_final = {}
    if data_2026: new_final['2026'] = data_2026
    if data_2025: new_final['2025'] = data_2025
    if data_2024: new_final['2024'] = data_2024

    new_json = json.dumps(new_final, ensure_ascii=False, separators=(',', ':'))
    new_html = html[:m_pat.start(1)] + new_json + html[m_pat.end(1):]
    new_html = build_bi_module(new_html, new_final)
    with open(INDEX, 'w', encoding='utf-8') as f:
        f.write(new_html)

    print(f"\n✓ index.html atualizado")
    if data_2026:
        cc = data_2026['comp']['cons']
        print(f"2026 COMP cons: fin=R${cc['kpi']['fin']:,.0f} ret=R${cc['kpi']['ret']:,.0f} q={cc['kpi']['q']}")
        fm = data_2026['fluxo']['mm']['monthly']
        print("2026 FLUXO mm:")
        for mn in sorted(fm, key=int):
            fd = fm[mn]
            print(f"  Mês {mn:>2}: fin=R${fd.get('fin',0):,.0f} ret=R${fd.get('ret',0):,.0f} q={fd.get('q',0)}")
    if data_2025:
        cc = data_2025['comp']['cons']
        print(f"2025 COMP cons: fin=R${cc['kpi']['fin']:,.0f} ret=R${cc['kpi']['ret']:,.0f} q={cc['kpi']['q']}")
    if data_2024:
        cc = data_2024['comp']['cons']
        print(f"2024 COMP cons: fin=R${cc['kpi']['fin']:,.0f} ret=R${cc['kpi']['ret']:,.0f} q={cc['kpi']['q']}")

if __name__ == '__main__':
    main()
