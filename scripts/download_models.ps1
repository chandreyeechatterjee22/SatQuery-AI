<#
.SYNOPSIS
  Download the SatQuery AI model files into data\models\ and verify their SHA256 checksums.
  Run this once after cloning (from any folder):  .\scripts\download_models.ps1

  - Trained heads (from the GitHub release assets):
      rsvqa_lr_head.pt        -> data\models\vqa_head\
      resnet18_4band_ben.pt   -> data\models\landcover_patch\
  - RemoteCLIP ViT-B/32 (Apache-2.0, ~605 MB) from Hugging Face (chendelong/RemoteCLIP) via
    backend\scripts\download_remoteclip.py. Needs the ML Python packages (backend\requirements-ml.txt).

  Override the release location with -BaseUrl or $env:SATQUERY_MODELS_URL.
  Files that already exist with the right checksum are skipped. Checksums: scripts\models.sha256.
#>
param(
    [string]$BaseUrl = $(if ($env:SATQUERY_MODELS_URL) { $env:SATQUERY_MODELS_URL } else {
        "https://github.com/chandreyeechatterjee22/SatQuery-AI/releases/download/v1.0-prototype" }),
    [switch]$SkipRemoteClip
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest is much faster without the progress bar
$root = Split-Path -Parent $PSScriptRoot

$expected = @{}
foreach ($line in Get-Content (Join-Path $PSScriptRoot "models.sha256")) {
    if ($line.Trim()) { $hash, $rel = $line -split "\s+", 2; $expected[$rel.Trim()] = $hash.ToLower() }
}

function Test-Model([string]$rel) {
    $path = Join-Path $root $rel
    if (-not (Test-Path $path)) { return $false }
    return (Get-FileHash -Algorithm SHA256 $path).Hash.ToLower() -eq $expected[$rel]
}

$failed = @()
$assets = @(
    @{ name = "rsvqa_lr_head.pt";      rel = "data/models/vqa_head/rsvqa_lr_head.pt" },
    @{ name = "resnet18_4band_ben.pt"; rel = "data/models/landcover_patch/resnet18_4band_ben.pt" }
)
foreach ($a in $assets) {
    $path = Join-Path $root $a.rel
    if (Test-Model $a.rel) { Write-Host "ok (already present)  $($a.rel)"; continue }
    New-Item -ItemType Directory -Force (Split-Path -Parent $path) | Out-Null
    $url = "$BaseUrl/$($a.name)"
    Write-Host "downloading  $url"
    try {
        Invoke-WebRequest -Uri $url -OutFile "$path.part" -UseBasicParsing
        Move-Item -Force "$path.part" $path
    } catch {
        Remove-Item -Force "$path.part" -ErrorAction SilentlyContinue
        Write-Warning "download failed: $url ($($_.Exception.Message))"; $failed += $a.rel; continue
    }
    if (Test-Model $a.rel) { Write-Host "ok (sha256 verified)  $($a.rel)" }
    else { Remove-Item -Force $path; Write-Warning "checksum mismatch, deleted: $($a.rel)"; $failed += $a.rel }
}

$clip = "data/models/remoteclip/RemoteCLIP-ViT-B-32.pt"
if (-not $SkipRemoteClip) {
    if (Test-Model $clip) { Write-Host "ok (already present)  $clip" }
    else {
        $venvPy = Join-Path $root ".venv\Scripts\python.exe"
        $py = if (Test-Path $venvPy) { $venvPy } else { "python" }
        Write-Host "downloading  RemoteCLIP from Hugging Face (~605 MB) with $py"
        & $py (Join-Path $root "backend\scripts\download_remoteclip.py")
        if (Test-Model $clip) { Write-Host "ok (sha256 verified)  $clip" }
        else { Write-Warning "RemoteCLIP missing or checksum mismatch: $clip"; $failed += $clip }
    }
}

if ($failed.Count) { Write-Error "Some model files are missing or invalid: $($failed -join ', ')"; exit 1 }
Write-Host "All model files present and verified."
