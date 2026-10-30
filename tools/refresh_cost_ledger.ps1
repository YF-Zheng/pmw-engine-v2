param(
    [switch]$Bootstrap,
    [switch]$CheckBudget
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$manifestPath = Join-Path $repoRoot 'docs\agent_bootstrap\project_run.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$scriptPath = Join-Path $PSScriptRoot 'agent_cost_ledger.py'
$cliArgs = @($scriptPath, '--main-session', $manifest.main_session)

if ($Bootstrap) {
    $cliArgs += @('--project-turn', $manifest.bootstrap.project_turn)
    foreach ($id in $manifest.bootstrap.agent_ids) {
        $cliArgs += @('--agent-id', $id)
    }
    $outputPath = Join-Path $repoRoot $manifest.bootstrap.output
} else {
    foreach ($turn in $manifest.project_turns) {
        $cliArgs += @('--project-turn', $turn)
    }
    $cliArgs += @('--phase', $manifest.default_phase)
    foreach ($agent in $manifest.agents) {
        $cliArgs += @('--agent-id', $agent.id)
        $cliArgs += @('--agent-stage', "$($agent.id)=$($agent.stage)")
    }
    foreach ($entry in $manifest.turn_stages.PSObject.Properties) {
        $cliArgs += @('--turn-stage', "$($entry.Name)=$($entry.Value)")
    }
    # User-authorised limit overrides live in the manifest, not in code defaults.
    if ($manifest.budget_limits_cny) {
        foreach ($entry in $manifest.budget_limits_cny.PSObject.Properties) {
            $cliArgs += @('--budget-limit', "$($entry.Name)=$($entry.Value)")
        }
    }
    $outputPath = Join-Path $repoRoot 'docs\agent_bootstrap\evidence'
}

$cliArgs += @('--output', $outputPath)
if ($CheckBudget) {
    $cliArgs += '--check-budget'
}

& python @cliArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
