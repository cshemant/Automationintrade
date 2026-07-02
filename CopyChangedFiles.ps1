param(
    [string]$Source = "E:\StocksMarket\DevelopmentServer\Website\V155",
    [string]$Destination = "E:\StocksMarket\DevelopmentServer\Website\Devlopement\V99",
    [switch]$Apply
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $Source)) {
    throw "Source path not found: $Source"
}

if (!(Test-Path $Destination)) {
    throw "Destination path not found: $Destination"
}

Write-Host ""
Write-Host "Source      : $Source"
Write-Host "Destination : $Destination"
Write-Host "Mode        : $(if ($Apply) { 'COPY WITH BACKUP' } else { 'PREVIEW ONLY' })"
Write-Host ""

$changes = Get-ChildItem $Source -Recurse -File -Force | Where-Object {
    $rel = $_.FullName.Substring($Source.Length).TrimStart('\')
    $rel -notmatch '(^|\\)(\.git|__pycache__)(\\|$)' -and $_.Extension -ne ".pyc"
} | ForEach-Object {
    $rel = $_.FullName.Substring($Source.Length).TrimStart('\')
    $target = Join-Path $Destination $rel

    if (!(Test-Path $target)) {
        [PSCustomObject]@{
            Status       = "NEW"
            RelativePath = $rel
            Source       = $_.FullName
            Target       = $target
        }
    }
    elseif ($_.Length -ne (Get-Item $target).Length) {
        [PSCustomObject]@{
            Status       = "MODIFIED"
            RelativePath = $rel
            Source       = $_.FullName
            Target       = $target
        }
    }
    else {
        $srcHash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
        $dstHash = (Get-FileHash $target -Algorithm SHA256).Hash

        if ($srcHash -ne $dstHash) {
            [PSCustomObject]@{
                Status       = "MODIFIED"
                RelativePath = $rel
                Source       = $_.FullName
                Target       = $target
            }
        }
    }
}

$changes = @($changes)

if ($changes.Count -eq 0) {
    Write-Host "No new or modified files found."
    exit 0
}

$changes | Sort-Object Status, RelativePath | Format-Table Status, RelativePath -AutoSize
Write-Host ""
Write-Host "Total changed/new files: $($changes.Count)"

if (!$Apply) {
    Write-Host ""
    Write-Host "Preview only. Nothing copied."
    Write-Host "To copy these files with backup, run:"
    Write-Host "powershell -ExecutionPolicy Bypass -File .\CopyChangedFiles.ps1 -Apply"
    exit 0
}

$backup = Join-Path (Split-Path $Destination -Parent) ("Backup_V99_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Force -Path $backup | Out-Null

foreach ($change in $changes) {
    New-Item -ItemType Directory -Force -Path (Split-Path $change.Target) | Out-Null

    if (Test-Path $change.Target) {
        $backupTarget = Join-Path $backup $change.RelativePath
        New-Item -ItemType Directory -Force -Path (Split-Path $backupTarget) | Out-Null
        Copy-Item $change.Target $backupTarget -Force
    }

    Copy-Item $change.Source $change.Target -Force
}

$changes | Sort-Object Status, RelativePath | Select-Object Status, RelativePath |
    Out-File (Join-Path $backup "changed-files.txt") -Encoding UTF8

Write-Host ""
Write-Host "Copied changed/new files: $($changes.Count)"
Write-Host "Backup created at: $backup"
Write-Host ""
Write-Host "To revert overwritten files, run:"
Write-Host "robocopy `"$backup`" `"$Destination`" /E /R:1 /W:1"
