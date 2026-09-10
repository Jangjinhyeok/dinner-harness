param(
    [switch]$NoWait,
    [string]$SessionMarkerPath
)

# Monitor public exec JSONL metadata, never private rollout files or newest sessions.
function Read-DispatchStatus {
    param([string]$MarkerPath)
    if (-not $MarkerPath -or -not (Test-Path -LiteralPath $MarkerPath)) { return $null }
    try {
        return (Get-Content -LiteralPath $MarkerPath -Raw -Encoding UTF8 -ErrorAction Stop |
            ConvertFrom-Json -ErrorAction Stop)
    } catch {
        # A concurrent write may briefly be incomplete; retry next tick.
        return $null
    }
}

if (-not $NoWait) {
    if (-not $SessionMarkerPath) {
        throw 'Pass -SessionMarkerPath <audit-dir>/watch-builder-<dispatch-id>.json.'
    }
    $previous = ''
    while ($true) {
        $status = Read-DispatchStatus -MarkerPath $SessionMarkerPath
        if ($status) {
            $summary = $status | Select-Object dispatch_id, thread_id, role, model, effort,
                status, elapsed_s, usage | ConvertTo-Json -Compress
            if ($summary -ne $previous) {
                Write-Host $summary
                $previous = $summary
            }
            if ($status.status -in @('completed', 'failed')) { break }
        }
        Start-Sleep -Milliseconds 500
    }
}
