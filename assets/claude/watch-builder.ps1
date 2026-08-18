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

function Get-LatestRolloutFile {
    param([string]$SessionsRoot = "$env:USERPROFILE\.codex\sessions")
    Get-ChildItem $SessionsRoot -Recurse -Filter "rollout-*.jsonl" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

function Read-RolloutUpdate {
    param(
        [string]$CurrentPath,
        [long]$Position,
        [string]$SessionsRoot = "$env:USERPROFILE\.codex\sessions"
    )
    $latest = Get-LatestRolloutFile -SessionsRoot $SessionsRoot
    $switched = $false
    if ($latest -and $latest.FullName -ne $CurrentPath) {
        $CurrentPath = $latest.FullName
        $Position = 0
        $switched = $true
    }
    $lines = @()
    if ($CurrentPath -and (Test-Path $CurrentPath)) {
        $stream = [System.IO.File]::Open(
            $CurrentPath, [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite
        )
        try {
            $stream.Seek($Position, [System.IO.SeekOrigin]::Begin) | Out-Null
            $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
            while (-not $reader.EndOfStream) {
                $lines += $reader.ReadLine()
            }
            $Position = $stream.Position
        } finally {
            $stream.Close()
        }
    }
    return [PSCustomObject]@{
        CurrentPath = $CurrentPath
        Position    = $Position
        Lines       = $lines
        Switched    = $switched
    }
}

$Host.UI.RawUI.WindowTitle = "Codex Builder Monitor"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if (-not $NoWait) {
    $currentPath = $null
    $position = 0
    while ($true) {
        $update = Read-RolloutUpdate -CurrentPath $currentPath -Position $position
        if ($update.Switched) {
            Write-Host "[session] watching $(Split-Path $update.CurrentPath -Leaf)" -ForegroundColor DarkCyan
        }
        $currentPath = $update.CurrentPath
        $position = $update.Position
        foreach ($line in $update.Lines) {
            $result = Format-RolloutLine $line
            if ($result) { Write-Host $result.Text -ForegroundColor $result.Color }
        }
        Start-Sleep -Milliseconds 500
    }
}
