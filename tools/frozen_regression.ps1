param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9_]+$')]
    [string]$EvidencePrefix
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
if ((Split-Path -Leaf $repoRoot) -ne 'pmw-engine-v2') {
    throw 'Frozen regression must stay inside the PMW repository.'
}
$env:PMW_FROZEN_ROOT = $repoRoot
$env:PMW_FROZEN_PREFIX = $EvidencePrefix
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'

@'
from pathlib import Path
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import time

root = Path(os.environ['PMW_FROZEN_ROOT']).resolve()
prefix = os.environ['PMW_FROZEN_PREFIX']
assert root.name == 'pmw-engine-v2' and re.fullmatch('[a-z0-9_]+', prefix)

def git(*args):
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()

assert git('branch', '--show-current') == 'feature/alpha-v02-seventh-night'
evidence = root / 'docs/agent_bootstrap/evidence'
log_path = evidence / (prefix + '_full_regression.txt')
meta_path = evidence / (prefix + '_full_regression_meta.json')
assert not log_path.exists() and not meta_path.exists(), 'Preserve previous evidence; choose a new prefix.'
paths = sorted(set(git('ls-files', '--cached', '--others', '--exclude-standard', '*.py').splitlines()))

def hashes(selected):
    result = {}
    for name in selected:
        path = (root / name).resolve()
        assert path.is_relative_to(root)
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result

before = hashes(paths)
temp = evidence / 'test_tmp'
assert temp.resolve().is_relative_to(root)
temp.mkdir(exist_ok=True)
environment = dict(os.environ, PYTHONPATH='src', PYTHONDONTWRITEBYTECODE='1',
                   PYTHONIOENCODING='utf-8', TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp))
command = [sys.executable, '-m', 'pytest', '-q', '-ra', '-p', 'no:cacheprovider',
           'tests', 'experiments/generative_mechanics/next_tracks_v06/tests',
           'experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests',
           'examples/pmw_alpha/tests', 'examples/storm_relay/tests']
metadata = dict(checkpoint=git('rev-parse', 'HEAD'), branch=git('branch', '--show-current'),
                started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                command=command, source_sha256_before=before, status='running',
                python_file_count=len(paths), temporary_directory=str(temp))

def save():
    sibling = meta_path.with_suffix('.tmp')
    sibling.write_bytes((json.dumps(metadata, indent=2) + '\n').encode())
    os.replace(sibling, meta_path)

save()
started = time.monotonic()
print('Frozen full regression started:', prefix, len(paths), 'Python files', flush=True)
with log_path.open('xb') as output:
    code = subprocess.call(command, cwd=root, env=environment, stdout=output, stderr=subprocess.STDOUT)
after_paths = sorted(set(git('ls-files', '--cached', '--others', '--exclude-standard', '*.py').splitlines()))
after = hashes(after_paths)
changed = [name for name in sorted(set(before) | set(after)) if before.get(name) != after.get(name)]
metadata.update(finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                elapsed_seconds=round(time.monotonic() - started, 3), exit_code=code,
                source_sha256_after=after, changed_python_paths=changed,
                status='passed' if code == 0 and not changed else 'failed')
save()
print(json.dumps({k: v for k, v in metadata.items() if not k.startswith('source_sha256')}, indent=2))
print(log_path.read_text(encoding='utf-8')[-4000:])
sys.exit(code if code else int(bool(changed)))
'@ | python -

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
