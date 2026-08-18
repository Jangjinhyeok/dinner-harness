param([switch]$NoWait)

function Format-RolloutLine {
    param([string]$Line)
    try {
        $evt = $Line | ConvertFrom-Json -ErrorAction Stop
    } catch {
        return $null
    }
    switch ($evt.payload.type) {
        "agent_message" {
            return [PSCustomObject]@{ Text = $evt.payload.message; Color = "Cyan" }
        }
        "custom_tool_call" {
            $preview = [string]$evt.payload.input
            if ($preview.Length -gt 200) { $preview = $preview.Substring(0,200) + "..." }
            return [PSCustomObject]@{ Text = "[tool] $($evt.payload.name): $preview"; Color = "DarkGray" }
        }
        "patch_apply_end" {
            $status = if ($evt.payload.success) { "OK" } else { "FAIL" }
            $lines = foreach ($path in $evt.payload.changes.PSObject.Properties.Name) {
                $changeType = $evt.payload.changes.$path.type
                "[patch $status] $changeType : $path"
            }
            return [PSCustomObject]@{ Text = ($lines -join "`n"); Color = "Yellow" }
        }
        "task_complete" {
            $seconds = [math]::Round($evt.payload.duration_ms / 1000, 1)
            return [PSCustomObject]@{ Text = "[done] turn complete in ${seconds}s"; Color = "Green" }
        }
        default {
            return $null
        }
    }
}

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if (-not $NoWait) {
    $latest = Get-ChildItem "$env:USERPROFILE\.codex\sessions" -Recurse -Filter "rollout-*.jsonl" |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Get-Content $latest.FullName -Encoding UTF8 -Wait -Tail 20 | ForEach-Object {
        $result = Format-RolloutLine $_
        if ($result) { Write-Host $result.Text -ForegroundColor $result.Color }
    }
}
