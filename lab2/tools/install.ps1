# Download pinned official tools; local binaries and archives are Git-ignored.
# Does not change PATH, install Java, or modify machine-wide settings.
[CmdletBinding()]
param([ValidateSet('All', 'PlantUML', 'Drawio')][string]$Tool = 'All')
$ErrorActionPreference = 'Stop'
$toolRoot = $PSScriptRoot
$versions = Get-Content -LiteralPath (Join-Path $toolRoot 'versions.json') -Raw | ConvertFrom-Json

function Assert-Hash([string]$Path, [string]$Expected) {
    $stream = [System.IO.File]::OpenRead($Path)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $actual = [System.BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '')
    } finally {
        $stream.Dispose()
        $hasher.Dispose()
    }
    if ($actual -ne $Expected) {
        throw "SHA-256 mismatch: $Path"
    }
}

if ($Tool -in @('All', 'PlantUML')) {
    $jarPath = Join-Path $toolRoot 'plantuml.jar'
    if (-not (Test-Path -LiteralPath $jarPath)) {
        $partPath = Join-Path $toolRoot 'plantuml.jar.part'
        Invoke-WebRequest -Uri $versions.plantuml.url -OutFile $partPath
        Assert-Hash $partPath $versions.plantuml.sha256
        Move-Item -LiteralPath $partPath -Destination $jarPath
    }
    Assert-Hash $jarPath $versions.plantuml.sha256
    Write-Host "PlantUML $($versions.plantuml.version) ready."
}

if ($Tool -in @('All', 'Drawio')) {
    $appDir = Join-Path $toolRoot 'drawio'
    $exePath = Join-Path $appDir 'draw.io.exe'
    if (-not (Test-Path -LiteralPath $exePath)) {
        if (Test-Path -LiteralPath $appDir) {
            throw 'Existing drawio folder is incomplete; preserve it and inspect it before installing.'
        }
        $downloadDir = Join-Path $toolRoot 'downloads'
        New-Item -Path $downloadDir -ItemType Directory -Force | Out-Null
        $archivePath = Join-Path $downloadDir "drawio-$($versions.drawio.version).zip"
        if (-not (Test-Path -LiteralPath $archivePath)) {
            Invoke-WebRequest -Uri $versions.drawio.url -OutFile $archivePath
        }
        Assert-Hash $archivePath $versions.drawio.archive_sha256
        # The official portable archive contains draw.io.exe at its root.
        Expand-Archive -LiteralPath $archivePath -DestinationPath $appDir
    }
    Assert-Hash $exePath $versions.drawio.exe_sha256
    Write-Host "diagrams.net $($versions.drawio.version) ready."
}
