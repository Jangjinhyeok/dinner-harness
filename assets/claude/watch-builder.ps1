param(
    [switch]$NoWait,
    [string]$SessionMarkerPath = (Join-Path $PSScriptRoot "logs\watch-builder-session.txt")
)

function Format-RolloutLine {
    param([string]$Line)
    try {
        $evt = $Line | ConvertFrom-Json -ErrorAction Stop
    } catch {
        return $null
    }
    $payload = $evt.payload
    switch ($payload.type) {
        "message" {
            if ($payload.role -ne "assistant") { return $null }
            $text = ($payload.content | Where-Object { $_.type -eq "output_text" } | ForEach-Object { $_.text }) -join "`n"
            if (-not $text) { return $null }
            return [PSCustomObject]@{ Text = $text; Color = "Cyan" }
        }
        "custom_tool_call" {
            $preview = [string]$payload.input
            if ($preview.Length -gt 200) { $preview = $preview.Substring(0,200) + "..." }
            return [PSCustomObject]@{ Text = "[tool] $($payload.name): $preview"; Color = "DarkGray" }
        }
        "item_completed" {
            $item = $payload.item
            switch ($item.type) {
                "FileChange" {
                    $lines = foreach ($path in $item.changes.PSObject.Properties.Name) {
                        $changeType = $item.changes.$path.type
                        "[patch $($item.status)] $changeType : $path"
                    }
                    return [PSCustomObject]@{ Text = ($lines -join "`n"); Color = "Yellow" }
                }
                "CommandExecution" {
                    $cmd = ($item.command -join " ")
                    if ($cmd.Length -gt 150) { $cmd = $cmd.Substring(0,150) + "..." }
                    $color = if ($item.exit_code -ne 0) { "Red" } else { "DarkGray" }
                    return [PSCustomObject]@{ Text = "[cmd exit=$($item.exit_code)] $cmd"; Color = $color }
                }
                default {
                    return $null
                }
            }
        }
        "task_complete" {
            $seconds = [math]::Round($payload.duration_ms / 1000, 1)
            return [PSCustomObject]@{ Text = "[done] turn complete in ${seconds}s"; Color = "Green" }
        }
        default {
            return $null
        }
    }
}

function Get-PinnedSessionId {
    param([string]$MarkerPath)
    if (-not $MarkerPath -or -not (Test-Path $MarkerPath)) { return $null }
    try {
        $id = (Get-Content -Path $MarkerPath -Raw -ErrorAction Stop).Trim()
        if ($id) { return $id }
    } catch {}
    return $null
}

function Get-RolloutFileForSession {
    param([string]$SessionId, [string]$SessionsRoot)
    Get-ChildItem $SessionsRoot -Recurse -Filter "rollout-*-$SessionId.jsonl" -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Get-LatestRolloutFile {
    param(
        [string]$SessionsRoot = "$env:USERPROFILE\.codex\sessions",
        [string]$MarkerPath
    )
    $pinnedId = Get-PinnedSessionId -MarkerPath $MarkerPath
    if ($pinnedId) {
        $pinned = Get-RolloutFileForSession -SessionId $pinnedId -SessionsRoot $SessionsRoot
        if ($pinned) { return $pinned }
    }
    Get-ChildItem $SessionsRoot -Recurse -Filter "rollout-*.jsonl" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

function Read-RolloutUpdate {
    param(
        [string]$CurrentPath,
        [long]$Position,
        [string]$SessionsRoot = "$env:USERPROFILE\.codex\sessions",
        [string]$MarkerPath
    )
    $latest = Get-LatestRolloutFile -SessionsRoot $SessionsRoot -MarkerPath $MarkerPath
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
        $update = Read-RolloutUpdate -CurrentPath $currentPath -Position $position -MarkerPath $SessionMarkerPath
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
