#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os
import re
import glob
from datetime import date


def get_journal_file():
    ledger_file = os.environ.get("LEDGER_FILE") or os.environ.get("HLEDGER_FILE")
    if ledger_file:
        return os.path.expanduser(ledger_file)
    return os.path.expanduser("~/hledger.journal")


def run_hledger(*args, journal_file=None):
    cmd = ["hledger", "-f", journal_file or get_journal_file()] + list(args)
    try:
        return subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        class _R:
            returncode = 127
            stdout = ""
            stderr = "hledger no está instalado o no está en PATH"
        return _R()


def parse_include_paths(journal_file):
    seen = set()
    found = []

    def walk_file(fp):
        fp = os.path.abspath(os.path.expanduser(fp))
        if fp in seen or not os.path.exists(fp):
            return
        seen.add(fp)
        found.append(fp)
        base = os.path.dirname(fp)
        try:
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith(";") or s.startswith("#"):
                        continue
                    if s.startswith("include "):
                        pattern = s[len("include "):].strip()
                        pattern = os.path.expanduser(pattern)
                        if not os.path.isabs(pattern):
                            pattern = os.path.join(base, pattern)
                        for match in glob.glob(pattern, recursive=True):
                            if os.path.isfile(match):
                                walk_file(match)
        except Exception:
            return

    walk_file(journal_file)
    return found


def scan_declared_accounts_and_payees(files):
    accounts = set()
    payees = set()
    tx_header_re = re.compile(r'^(\d{4}[-/]\d{2}[-/]\d{2})(?:\s+[*!])?(?:\s+\([^)]*\))?\s+(.*)$')
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    raw = line.rstrip("\n")
                    s = raw.strip()
                    if not s or s.startswith(";") or s.startswith("#") or s.startswith("include "):
                        continue
                    if raw.startswith(" ") or raw.startswith("\t"):
                        m = re.match(r'^\s+([^;\s][^;]*?)(?:\s{2,}.*)?(?:\s+;.*)?$', raw)
                        if m:
                            acct = m.group(1).strip()
                            if acct:
                                accounts.add(acct)
                    else:
                        m = tx_header_re.match(s)
                        if m:
                            rest = m.group(2).strip()
                            payee = rest.split(' | ', 1)[0].strip()
                            if payee:
                                payees.add(payee)
        except Exception:
            continue
    return accounts, payees






def scan_commodity_styles(files):
    styles = {}
    for fp in files:
        try:
            with open(fp, encoding='utf-8') as f:
                current_commodity = None
                for line in f:
                    s = line.strip()
                    if not s or s.startswith(';') or s.startswith('#'):
                        continue
                    m1 = re.match(r'^commodity\s+(.+)$', s)
                    if m1:
                        rest = m1.group(1).strip()
                        current_commodity = None
                        m_inline = re.match(r'^(.*\d[\d.,]*\d|.*\d)\s+([A-Z][A-Z0-9]*)$', rest)
                        if m_inline:
                            sample = m_inline.group(1).strip() + ' ' + m_inline.group(2).strip()
                            styles[m_inline.group(2).strip()] = infer_style_from_sample(sample)
                        elif re.match(r'^[A-Z][A-Z0-9]*$', rest):
                            current_commodity = rest
                        continue
                    if current_commodity:
                        m2 = re.match(r'^format\s+(.+)$', s)
                        if m2:
                            sample = m2.group(1).strip()
                            styles[current_commodity] = infer_style_from_sample(sample)
                            current_commodity = None
        except Exception:
            continue
    return styles


def infer_style_from_sample(sample):
    sample = sample.strip()
    commodity = None
    side = 'right'
    space = True
    number = sample

    m = re.match(r'^([€$£¥]|[A-Z][A-Z0-9]*)\s*(.+)$', sample)
    if m and re.search(r'\d', m.group(2)):
        commodity = m.group(1)
        number = m.group(2)
        side = 'left'
        space = bool(re.match(r'^([€$£¥]|[A-Z][A-Z0-9]*)\s+.+$', sample))
    else:
        m = re.match(r'^(.+?)\s*([€$£¥]|[A-Z][A-Z0-9]*)$', sample)
        if m and re.search(r'\d', m.group(1)):
            number = m.group(1)
            commodity = m.group(2)
            side = 'right'
            space = bool(re.match(r'^.+\s+([€$£¥]|[A-Z][A-Z0-9]*)$', sample))

    dec = None
    prec = 0
    group = ''
    if ',' in number and '.' in number:
        dec = ',' if number.rfind(',') > number.rfind('.') else '.'
        group = '.' if dec == ',' else ','
    elif ',' in number:
        tail = number.split(',')[-1]
        dec = ',' if len(tail) != 3 else None
        group = '' if dec == ',' else ','
    elif '.' in number:
        tail = number.split('.')[-1]
        dec = '.' if len(tail) != 3 else None
        group = '' if dec == '.' else '.'
    if dec:
        prec = len(number.split(dec)[-1])
    return {
        'commodity': commodity,
        'side': side,
        'space': space,
        'decimal': dec or '.',
        'thousands': group,
        'precision': prec,
    }


def symbol_to_code(styles):
    mapping = {}
    for code, st in styles.items():
        c = st.get('commodity') or code
        if c in ['€', '$', '£', '¥']:
            mapping[c] = code
    if 'EUR' not in mapping.values():
        mapping['€'] = 'EUR'
    if 'USD' not in mapping.values():
        mapping['$'] = 'USD'
    return mapping


def format_number_style(value, style):
    precision = style.get('precision', 2)
    decimal = style.get('decimal', '.')
    thousands = style.get('thousands', '')
    s = f"{abs(value):,.{precision}f}"
    if thousands == '.':
        s = s.replace(',', 'X').replace('.', ',').replace('X', '.')
    elif thousands == ',':
        pass
    elif thousands == ' ':
        s = s.replace(',', ' ')
    else:
        s = s.replace(',', '')
        if decimal == ',':
            s = s.replace('.', ',')
    if decimal == ',' and thousands != '.':
        s = s.replace('.', ',')
    sign = '-' if value < 0 else ''
    return sign + s


def format_amount_by_style(number, commodity, styles):
    value = float(number)
    style = styles.get(commodity, {
        'commodity': commodity,
        'side': 'right',
        'space': True,
        'decimal': '.',
        'thousands': '',
        'precision': 2,
    })
    num = format_number_style(value, style)
    symbol = style.get('commodity') or commodity
    sep = ' ' if style.get('space', True) else ''
    if style.get('side') == 'left':
        return f"{symbol}{sep}{num}"
    return f"{num}{sep}{commodity}"

def build_leaf_account_map(accounts):
    leaf_map = {}
    duplicates = set()
    for acct in accounts:
        leaf = acct.split(':')[-1].strip()
        if not leaf:
            continue
        if leaf in leaf_map and leaf_map[leaf] != acct:
            duplicates.add(leaf)
        else:
            leaf_map[leaf] = acct
    for d in duplicates:
        leaf_map.pop(d, None)
    return leaf_map, sorted(duplicates)


def resolve_account_name(account, known_accounts, leaf_map):
    if account in known_accounts:
        return account, None
    if ':' not in account and account in leaf_map:
        return leaf_map[account], f'Cuenta abreviada resuelta: {account} -> {leaf_map[account]}'
    return account, None

def get_existing_accounts(journal_file):
    r = run_hledger("accounts", journal_file=journal_file)
    if r.returncode != 0:
        return set()
    return set(line.strip() for line in r.stdout.splitlines() if line.strip())


def get_existing_payees(journal_file):
    r = run_hledger("payees", journal_file=journal_file)
    if r.returncode != 0:
        return set()
    return set(line.strip() for line in r.stdout.splitlines() if line.strip())


def normalize_amount_input(raw):
    raw = raw.strip()
    code_from_symbol = symbol_to_code(CURRENT_COMMODITY_STYLES) if 'CURRENT_COMMODITY_STYLES' in globals() else {'€':'EUR','$':'USD'}
    m = re.match(r'^(-?[\d.]+,[\d]+)\s+([A-Z][A-Z0-9]*)$', raw)
    if m:
        number = m.group(1).replace('.', '').replace(',', '.')
        commodity = m.group(2)
        if commodity == 'EUE':
            raise ValueError('Commodity desconocida: EUE. ¿Querías EUR?')
        return f"{number} {commodity}"
    m = re.match(r'^(-?[\d,]+(?:\.\d+)?)\s*([A-Z€$£¥]+)$', raw, re.IGNORECASE)
    if m:
        number = m.group(1).replace(',', '')
        commodity = code_from_symbol.get(m.group(2), m.group(2))
        if commodity == 'EUE':
            raise ValueError('Commodity desconocida: EUE. ¿Querías EUR?')
        return f"{number} {commodity}"
    m = re.match(r'^([A-Z€$£¥]+)\s*(-?[\d,]+(?:\.\d+)?)$', raw, re.IGNORECASE)
    if m:
        commodity = code_from_symbol.get(m.group(1), m.group(1))
        number = m.group(2).replace(',', '')
        if commodity == 'EUE':
            raise ValueError('Commodity desconocida: EUE. ¿Querías EUR?')
        return f"{number} {commodity}"
    if re.match(r'^-?[\d.]+,[\d]+$', raw):
        raise ValueError('El importe usa coma decimal pero no commodity, ej: 25,00 EUR')
    if re.match(r'^-?[\d,]+(?:\.\d+)?$', raw):
        raise ValueError('Falta commodity en el importe, ej: 25.00 EUR')
    return raw


def parse_amount(raw):
    raw = normalize_amount_input(raw).strip()
    m = re.match(r'^(-?[\d,]+(?:\.\d+)?)\s*([A-Z€$£¥]+)?$', raw, re.IGNORECASE)
    if not m:
        m = re.match(r'^([A-Z€$£¥]+)\s*(-?[\d,]+(?:\.\d+)?)$', raw, re.IGNORECASE)
        if m:
            return m.group(2), m.group(1)
        return None, None
    number = m.group(1).replace(',', '')
    commodity = m.group(2) or ''
    return number, commodity


def format_amount(number, commodity):
    if not commodity:
        return number
    if commodity in ('$', '£', '¥', '€'):
        return f'{commodity}{number}'
    return f'{number} {commodity}'


def format_cost(cost_str, cost_type='unit'):
    if not cost_str:
        return ''
    number, commodity = parse_amount(cost_str)
    op = '@@' if cost_type == 'total' else '@'
    if number is None:
        return f' {op} {cost_str}'
    return f' {op} {format_amount_by_style(number, commodity, CURRENT_COMMODITY_STYLES)}'


def format_assertion(assertion, assertion_cost):
    if not assertion:
        return ''
    number, commodity = parse_amount(assertion)
    if number is None:
        return f' = {assertion}'
    base = format_amount_by_style(number, commodity, CURRENT_COMMODITY_STYLES)
    if assertion_cost:
        an, ac = parse_amount(assertion_cost)
        if an:
            base += f' @@ {format_amount_by_style(an, ac, CURRENT_COMMODITY_STYLES)}'
        else:
            base += f' @@ {assertion_cost}'
    return f' = {base}'




def align_posting(account, rendered_amount, comment=None, target_col=60, base_indent='    '):
    left = f"{base_indent}{account}"
    min_gap = 2
    current_col = len(left)
    gap = max(min_gap, target_col - current_col)
    line = left + (' ' * gap) + rendered_amount
    if comment:
        line += f"  ; {comment}"
    return line

def build_posting(account, amount, cost, assertion, assertion_cost, comment, commodity_styles=None, amount_column=60, cost_type='unit'):
    if amount is None:
        line = f'    {account}'
    else:
        number, commodity = parse_amount(amount)
        if number is None:
            print(f'[ERROR] Importe no reconocido: {amount}', file=sys.stderr)
            sys.exit(2)
        if not commodity:
            print('[ERROR] Todos los importes deben llevar commodity, ej: 25.00 EUR', file=sys.stderr)
            sys.exit(2)
        rendered = format_amount_by_style(number, commodity, commodity_styles or {})
        rendered += format_cost(cost, cost_type=cost_type)
        rendered += format_assertion(assertion, assertion_cost)
        return align_posting(account, rendered, comment=comment, target_col=amount_column)
    if comment:
        line += f'  ; {comment}'
    return line


def build_transaction(args_ns, posting_lines):
    date_str = args_ns.date or str(date.today())
    mark = args_ns.mark or ''
    code = f'({args_ns.code})' if args_ns.code else ''
    payee = args_ns.payee or ''
    note = args_ns.note or ''
    description = args_ns.description or ''

    if payee and note:
        desc_part = f'{payee} | {note}'
    elif payee:
        desc_part = payee
    elif note:
        desc_part = f'| {note}'
    elif description:
        desc_part = description
    else:
        desc_part = '(sin descripción)'

    header_parts = [date_str]
    if mark:
        header_parts.append(mark)
    if code:
        header_parts.append(code)
    header = ' '.join(header_parts) + ' ' + desc_part
    if args_ns.txcomment:
        header += f'  ; {args_ns.txcomment}'
    return '\n'.join([header] + posting_lines + [''])


def check_balance(postings_data):
    total = {}
    has_inferred = False
    for posting in postings_data:
        amount = posting[1]
        if amount is None:
            has_inferred = True
            continue
        number, commodity = parse_amount(amount)
        if number is None or not commodity:
            continue
        total[commodity] = total.get(commodity, 0) + float(number)
    if has_inferred:
        return True, 'Balance no verificado (posting sin importe, hledger lo inferirá)'
    for commodity, val in total.items():
        if abs(val) > 1e-9:
            return False, f'Balance no es 0: suma de {commodity} = {val:.4f}'
    return True, 'Balance OK'


def make_parser():
    p = argparse.ArgumentParser(
        prog='hledger-add-tx',
        description='Añade una transacción a hledger de forma no interactiva, validando cuentas, payees, includes y commodities.',
        epilog='''
EJEMPLOS
--------
1) Gasto simple:
   hledger-add-tx -d "Café" \
     expenses:food "2,50 EUR" \
     assets:cash "-2,50 EUR"

2) Con payee, nota y código:
   hledger-add-tx -D 2026-04-04 -m "*" --code GIFT01 \
     -p "Regalo recibido" -n "cumpleaños" \
     activos:efectivo:cartera "25,00 EUR" --assertion1 "27,79 EUR" \
     ingresos:regalos_recibidos "-25,00 EUR"

3) Solo validar sin escribir:
   hledger-add-tx --dry-run --json -d "Test" \
     expenses:food "10,00 EUR" assets:cash "-10,00 EUR"

REGLAS
------
- El journal de destino se toma de LEDGER_FILE, HLEDGER_FILE o ~/hledger.journal.
- Se revisan los include del journal para validar cuentas y payees.
- Todas las cantidades deben llevar commodity explícita, por ejemplo: 25,00 EUR.
- Si una cuenta no existe en journal/include, el script falla antes de escribir.
- Si el payee no existe, se emite warning.
- Tras escribir, puede ejecutarse hledger check.

CONSULTA RÁPIDA PARA IA
----------------------
- Usa: hledger-add-tx --help
- Usa también: hledger-add-tx --help-ai
  para obtener una guía corta y estructurada fácil de interpretar por otra IA.
''',
        formatter_class=argparse.RawTextHelpFormatter
    )
    p.add_argument('-D', '--date')
    p.add_argument('-m', '--mark')
    p.add_argument('-d', '--description')
    p.add_argument('-p', '--payee')
    p.add_argument('-n', '--note')
    p.add_argument('--code')
    p.add_argument('--txcomment')
    p.add_argument('-f', '--file')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--no-check', action='store_true')
    p.add_argument('--json', action='store_true')
    p.add_argument('--amount-column', type=int, default=60, help='Columna objetivo para alinear importes (default: 60)')
    for i in range(1, 10):
        p.add_argument(f'--cost{i}')
        p.add_argument(f'--costtype{i}', choices=['unit', 'total'], default='total')
        p.add_argument(f'--assertion{i}')
        p.add_argument(f'--assertioncost{i}')
        p.add_argument(f'--comment{i}')
    p.add_argument('postings', nargs='+')
    return p


def parse_postings(positional, args_ns):
    result = []
    i = 0
    idx = 1
    while i < len(positional):
        account = positional[i]
        i += 1
        amount = None
        if i < len(positional):
            candidate = positional[i]
            try:
                n, _ = parse_amount(candidate)
            except Exception:
                n = None
            if n is not None:
                amount = candidate
                i += 1
        result.append((
            account,
            amount,
            getattr(args_ns, f'cost{idx}', None),
            getattr(args_ns, f'assertion{idx}', None),
            getattr(args_ns, f'assertioncost{idx}', None),
            getattr(args_ns, f'comment{idx}', None),
            getattr(args_ns, f'costtype{idx}', 'total'),
        ))
        idx += 1
    return result




def print_ai_help():
    print("""{
  "name": "hledger-add-tx",
  "purpose": "Añadir una transacción a un journal de hledger de forma no interactiva",
  "journal_resolution": [
    "$LEDGER_FILE",
    "$HLEDGER_FILE",
    "~/hledger.journal"
  ],
  "validations": [
    "Revisa include del journal",
    "Permite cuentas abreviadas por leaf si son únicas",
    "Verifica que las cuentas existan en journal/include",
    "Revisa payees existentes y avisa si uno es nuevo",
    "Exige commodity explícita en todos los importes",
    "Comprueba balance 0 si todos los postings tienen importe",
    "Puede ejecutar hledger check tras escribir"
  ],
  "header_format": "YYYY-MM-DD * (CODE) PAYEE | NOTE  (o YYYY-MM-DD * (CODE) | NOTE si no hay payee)",
  "posting_format": "cuenta[espacios hasta columna configurable]IMPORTE COMMODITY [@ COSTE_UNITARIO|@@ COSTE_TOTAL por defecto] [= ASSERTION]",
  "amount_alignment": "Los importes se alinean por defecto a la columna 60 con --amount-column",
  "amount_examples": [
    "25,00 EUR",
    "-25,00 EUR",
    "EUR 25.00",
    "€2.50 -> 2,50 EUR si el estilo de EUR es 1.000,00 EUR",
    "$2.50 -> 2.50 USD o 2,50 USD según el estilo declarado"
  ],
  "common_errors": [
    "Cuenta no existente en journal/include",
    "Commodity ausente",
    "Commodity desconocida como EUE",
    "Balance no igual a 0"
  ],
  "examples": [
    "hledger-add-tx -d \"Café\" expenses:food \"2,50 EUR\" assets:cash \"-2,50 EUR\"",
    "hledger-add-tx -D 2026-04-04 -m \"*\" --code GIFT01 -p \"Regalo recibido\" -n \"cumpleaños\" activos:efectivo:cartera \"25,00 EUR\" --assertion1 \"27,79 EUR\" ingresos:regalos_recibidos \"-25,00 EUR\"",
    "hledger-add-tx --dry-run --json -d \"Test\" expenses:food \"10,00 EUR\" assets:cash \"-10,00 EUR\""
  ]
}""")

def emit(output, as_json):
    if as_json:
        import json
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        if output.get('transaction'):
            print('─' * 60)
            print('Transacción generada:')
            print('─' * 60)
            print(output['transaction'])
        if output['errors']:
            for e in output['errors']:
                print(f'[ERROR] {e}', file=sys.stderr)
        if output['warnings']:
            print('\nAvisos:')
            for w in output['warnings']:
                print(f'  ⚠  {w}')


CURRENT_COMMODITY_STYLES = {}

def main():
    if '--help-ai' in sys.argv:
        print_ai_help()
        return
    args = make_parser().parse_args()
    journal_file = args.file or get_journal_file()
    output = {
        'status': 'ok',
        'journal_file': journal_file,
        'warnings': [],
        'errors': [],
        'checks': {},
        'transaction': None,
        'written': False,
    }

    postings_data = parse_postings(args.postings, args)
    if len(postings_data) < 2:
        output['status'] = 'error'
        output['errors'].append('Se necesitan al menos 2 postings.')
        emit(output, args.json)
        sys.exit(1)

    include_files = parse_include_paths(journal_file)
    scanned_accounts, scanned_payees = scan_declared_accounts_and_payees(include_files)
    commodity_styles = scan_commodity_styles(include_files)
    global CURRENT_COMMODITY_STYLES
    CURRENT_COMMODITY_STYLES = commodity_styles

    balance_ok, balance_msg = check_balance(postings_data)
    output['checks']['balance'] = {'ok': balance_ok, 'message': balance_msg}
    if not balance_ok:
        output['status'] = 'error'
        output['errors'].append(balance_msg)

    known_accounts = get_existing_accounts(journal_file) or scanned_accounts
    leaf_map, duplicate_leafs = build_leaf_account_map(known_accounts)
    acct_errors = []
    acct_warnings = []
    resolved_postings = []
    if known_accounts:
        for posting in postings_data:
            acct = posting[0]
            resolved, warning = resolve_account_name(acct, known_accounts, leaf_map)
            if warning:
                acct_warnings.append(warning)
            if resolved not in known_accounts:
                if ':' not in acct and acct in duplicate_leafs:
                    acct_errors.append(f'Nombre abreviado ambiguo: {acct}. Coincide con varias cuentas completas')
                else:
                    acct_errors.append(f'Cuenta no existente en journal/include: {acct}')
            resolved_postings.append((resolved, *posting[1:]))
    else:
        resolved_postings = postings_data
        acct_warnings.append('No se pudo verificar cuentas (journal/includes vacíos o hledger no disponible)')
    output['checks']['commodity_styles'] = commodity_styles
    output['checks']['accounts'] = {
        'errors': acct_errors,
        'warnings': acct_warnings,
        'known_accounts_count': len(known_accounts),
        'include_files': include_files,
        'duplicate_leafs': duplicate_leafs,
    }
    output['warnings'].extend(acct_warnings)
    output['errors'].extend(acct_errors)

    if args.payee:
        known_payees = get_existing_payees(journal_file) or scanned_payees
        payee_warnings = []
        if known_payees and args.payee not in known_payees:
            payee_warnings.append(f'Payee nuevo/no encontrado en journal/include: {args.payee}')
        output['checks']['payees'] = {
            'warnings': payee_warnings,
            'known_payees_count': len(known_payees),
        }
        output['warnings'].extend(payee_warnings)

    if output['errors']:
        output['status'] = 'error'
        emit(output, args.json)
        sys.exit(1)

    posting_lines = [build_posting(p[0], p[1], p[2], p[3], p[4], p[5], commodity_styles=commodity_styles, amount_column=args.amount_column, cost_type=p[6] if len(p) > 6 else 'total') for p in resolved_postings]
    tx_text = build_transaction(args, posting_lines)
    output['transaction'] = tx_text

    if args.dry_run:
        emit(output, args.json)
        return

    os.makedirs(os.path.dirname(os.path.abspath(journal_file)), exist_ok=True)
    if not os.path.exists(journal_file):
        open(journal_file, 'a').close()
    with open(journal_file, 'a', encoding='utf-8') as f:
        f.write('\n' + tx_text + '\n')
    output['written'] = True

    if not args.no_check:
        r = run_hledger('check', journal_file=journal_file)
        output['checks']['hledger_check'] = {
            'ok': r.returncode == 0,
            'stdout': r.stdout.strip(),
            'stderr': r.stderr.strip(),
            'returncode': r.returncode,
        }
        if r.returncode != 0:
            output['status'] = 'warning'
            output['warnings'].append(f'hledger check encontró problemas: {r.stderr.strip()}')

    emit(output, args.json)


if __name__ == '__main__':
    main()
