param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9_]+$')]
    [string]$TaskId,
    [Parameter(Mandatory = $true)]
    [string[]]$ChildIds
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
if ((Split-Path -Leaf $repoRoot) -ne 'pmw-engine-v2') { throw 'PMW scope required.' }
$env:PMW_ACCOUNTING_ROOT = $repoRoot
$env:PMW_ACCOUNTING_TASK = $TaskId
$env:PMW_ACCOUNTING_CHILDREN = ConvertTo-Json -InputObject @($ChildIds) -Compress
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'

@'
from pathlib import Path
import json
import os
root = Path(os.environ['PMW_ACCOUNTING_ROOT']).resolve()
path = root / 'docs/agent_bootstrap/project_run.json'
manifest = json.loads(path.read_text(encoding='utf-8'))
run = manifest.setdefault('continuous_run', {
    'started_at_utc': '2026-10-29T05:39:29.235Z', 'main_turns': [],
    'accounted_tasks': [], 'main_ordinal_cursor': 0,
})
files = list((Path.home() / '.codex/sessions').rglob('*' + manifest['main_session'] + '*.jsonl'))
assert len(files) == 1
with files[0].open(encoding='utf-8') as stream:
    for line in stream:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get('type') != 'turn_context' or row.get('timestamp', '') < run['started_at_utc']:
            continue
        context = row['payload']
        assert context.get('model') == 'tencent/gpt-6.1-sol'
        turn = context['turn_id']
        if turn not in manifest['project_turns']:
            manifest['project_turns'].append(turn)
        if turn not in run['main_turns']:
            run['main_turns'].append(turn)
        manifest['turn_stages'][turn] = 'P1'
assert run['main_turns']
temporary = path.with_suffix('.tmp')
temporary.write_bytes((json.dumps(manifest, indent=2) + '\n').encode())
os.replace(temporary, path)
'@ | python -
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $PSScriptRoot 'refresh_cost_ledger.ps1') -CheckBudget
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

@'
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import os
import re

root = Path(os.environ['PMW_ACCOUNTING_ROOT']).resolve()
task = os.environ['PMW_ACCOUNTING_TASK']
children = json.loads(os.environ['PMW_ACCOUNTING_CHILDREN'])
assert root.name == 'pmw-engine-v2' and re.fullmatch('[a-z0-9_]+', task)
assert children and len(children) == len(set(children))
docs = root / 'docs/agent_bootstrap'
evidence = docs / 'evidence'
manifest_path = docs / 'project_run.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
ledger_path = evidence / 'agent_cost_ledger.json'
ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
assert ledger['status'] == 'complete' and ledger['budget']['within_budget']
assert not ledger['budget']['incomplete_accounting']
assert ledger['totals']['unknown_record_count'] == ledger['totals']['malformed_usage_record_count'] == 0
registered = {item['id'] for item in manifest['agents']}
assert set(children) <= registered
run = manifest.setdefault('continuous_run', {
    'started_at_utc': '2026-10-29T05:39:29.235Z',
    'main_turns': ['01a1862b-a31c-7351-ac83-5a77abdf3769'],
    'accounted_tasks': [], 'main_ordinal_cursor': 0,
})
assert task not in {item['task'] for item in run['accounted_tasks']}, 'Never charge a checkpoint twice.'
main = manifest['main_session']
turns = set(run['main_turns'])
assert turns <= set(manifest['project_turns'])
start = run['main_ordinal_cursor']
end = ledger['snapshot']['source_max_ordinals'][main]
families = {}
seen = set()
for family, bucket in ledger['families'].items():
    records = [row for row in bucket['responses'] if row['source_session_id'] in children or (
        row['source_session_id'] == main and row['turn_id'] in turns and start < row['source_ordinal'] <= end)]
    for row in records:
        key = (row['thread_id'], row['response_id'])
        assert key not in seen and row['usage_complete'] and row['pricing']['priced']
        seen.add(key)
        assert row['model'] == ('tencent/gpt-6.1-sol' if row['source_session_id'] == main
                                else 'tencent/deepseek-v4.1-flash')
    usage = {key: sum(row['actual_usage'][key] for row in records) for key in bucket['actual_usage']}
    amount = sum((Decimal(str(row['pricing']['estimated_usd']['total'])) for row in records), Decimal(0))
    families[family] = dict(record_count=len(records), actual_usage=usage,
                            estimated_usd=str(amount) if family != 'Unknown' else None, responses=records)
for child in children:
    assert any(row['source_session_id'] == child for bucket in families.values() for row in bucket['responses'])
total = sum((Decimal(bucket['estimated_usd']) for bucket in families.values()
             if bucket['estimated_usd'] is not None), Decimal(0))
fx = Decimal(str(ledger['budget']['reference_fx_usd_cny']))

def money(value):
    return str(Decimal(str(value)).quantize(Decimal('.00000001'), rounding=ROUND_HALF_UP))

def save(path, value):
    assert path.resolve().is_relative_to(root)
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes((json.dumps(value, indent=2) + '\n').encode())
    os.replace(temporary, path)

snapshot = dict(task=task, main_session=main, main_turns=sorted(turns), child_ids=children,
                main_source_ordinal_range=dict(exclusive_start=start, inclusive_end=end),
                cutoff_utc=ledger['snapshot']['max_observed_usage_timestamp'],
                ledger_sha256=hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
                families=families, estimated_usd=money(total), estimated_cny_reference=money(total * fx),
                cumulative_totals=ledger['totals'], budget=ledger['budget'],
                cache_ratio_cost_assumption=0.97, actual_cache_untouched=True,
                reference_price_date=ledger['reference_date'], pricing_sources=ledger['pricing_sources'],
                bootstrap_included=False, closing_usage_finalized=False,
                note='Subset already included once in cumulative ledger; ordinal boundaries allocate shared closing overhead to the next item, not exact semantic task inference.')
path = evidence / (task + '_cost_snapshot.json')
assert not path.exists()
save(path, snapshot)
run['accounted_tasks'].append(dict(task=task, main_end_ordinal=end, snapshot=str(path.relative_to(root))))
run['main_ordinal_cursor'] = end
save(manifest_path, manifest)
heading = '## Continuous ' + task.upper() + ' Snapshot'
cost_path = docs / 'COST_LEDGER.md'
old = cost_path.read_text(encoding='utf-8')
assert heading not in old
lines = ['', heading, '', 'Observed cutoff: **' + snapshot['cutoff_utc'] + '**; complete, Unknown 0, malformed 0.',
         'Snapshot: `evidence/' + path.name + '`. This subset is already in cumulative totals; never add it again.',
         '97% cache is a price assumption only. Actual cache is preserved; pricing/FX remain pinned to verified 2026-10-28 sources.',
         '', '| Family | Responses | Actual input | Actual cache | Actual output | Reasoning (included) | Reference USD |',
         '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for family in ['GPT', 'DeepSeek', 'Unknown']:
    bucket = families[family]
    usage = bucket['actual_usage']
    price = money(bucket['estimated_usd']) if bucket['estimated_usd'] is not None else 'N/A (no records)'
    lines.append(f"| {family} | {bucket['record_count']} | {usage['input_tokens']:,} | {usage['cached_input_tokens']:,} | {usage['output_tokens']:,} | {usage['reasoning_output_tokens']:,} | {price} |")
lines.extend(['', 'Subset: USD ' + snapshot['estimated_usd'] + ' / CNY ' + snapshot['estimated_cny_reference'] + '.',
              'Project cumulative: **USD ' + money(ledger['totals']['estimated_usd']) + ' / CNY ' + money(ledger['totals']['estimated_cny_reference']) + '**.',
              'Safety-reserved: **CNY ' + money(ledger['budget']['reserved_cny']) + ' / 2,000**; all stage gates within budget.',
              'Bootstrap remains separate. Closing response usage is pending the next refresh. Ordinal boundary allocation of shared overhead is not exact semantic task attribution.', ''])
temporary = cost_path.with_suffix('.tmp')
temporary.write_bytes((old.rstrip() + '\n' + '\n'.join(lines)).encode())
os.replace(temporary, cost_path)
print(json.dumps({key: snapshot[key] for key in ['task', 'cutoff_utc', 'estimated_usd', 'estimated_cny_reference']}))
print(json.dumps(dict(cumulative=ledger['totals'], budget=ledger['budget']), indent=2))
'@ | python -
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
