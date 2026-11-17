# Build portable Interpreter Lag Analyzer (Windows).
#
# Pemakaian:
#   .\scripts\build_portable.ps1                    -> bundel model "small"
#   .\scripts\build_portable.ps1 -IncludeModels @() -> tanpa model (unduh saat run pertama)
#   .\scripts\build_portable.ps1 -IncludeModels @("small","medium")
#   .\scripts\build_portable.ps1 -SkipZip           -> hanya folder dist, tanpa zip
#
# Hasil: release\EVSAE.zip
# Catatan: PyInstaller tidak bisa cross-compile - build macOS harus dilakukan di Mac.
param(
    [string[]]$IncludeModels = @("small"),
    [switch]$SkipZip
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$AppName = "EVSAE"
$DistApp = Join-Path $Root "dist\$AppName"
$ReleaseDir = Join-Path $Root "release"
$ZipPath = Join-Path $ReleaseDir "$AppName-portable.zip"

Set-Location $Root

# Stack runtime: faster-whisper (ctranslate2 + PyAV). Tidak butuh torch/ffmpeg.exe.
# torch/whisper lama di-exclude eksplisit agar tidak ikut terseret bila masih
# terpasang di environment build.
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name $AppName `
    --collect-all faster_whisper `
    --collect-all ctranslate2 `
    --collect-all av `
    --collect-all sounddevice `
    --exclude-module torch `
    --exclude-module torchaudio `
    --exclude-module torchvision `
    --exclude-module tensorflow `
    --exclude-module keras `
    --exclude-module transformers `
    --exclude-module datasets `
    --exclude-module pyarrow `
    --exclude-module h5py `
    --exclude-module whisper `
    --exclude-module tiktoken `
    --exclude-module numba `
    --exclude-module llvmlite `
    --exclude-module scipy `
    --exclude-module matplotlib `
    --exclude-module pandas `
    --exclude-module IPython `
    --exclude-module jupyter `
    --exclude-module nvidia `
    .\interpreter_lag_gui.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller gagal (exit $LASTEXITCODE)."
}

# Folder kerja di samping exe (app_base_dir membaca folder exe saat frozen).
New-Item -ItemType Directory -Force -Path (Join-Path $DistApp "models") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DistApp "exports") | Out-Null

# Logo institusi dibaca dari folder exe.
foreach ($asset in @("logo-upi-fpbs.png", "kemendiktisaintek.png")) {
    if (Test-Path (Join-Path $Root $asset)) {
        Copy-Item -Force (Join-Path $Root $asset) $DistApp
    }
}

if (Test-Path (Join-Path $Root "README_PORTABLE.txt")) {
    Copy-Item -Force (Join-Path $Root "README_PORTABLE.txt") (Join-Path $DistApp "README_CARA_PAKAI.txt")
}

# Bundel model faster-whisper agar bisa dipakai offline tanpa unduh.
foreach ($model in $IncludeModels) {
    $srcModel = Join-Path $Root "models\models--Systran--faster-whisper-$model"
    if (Test-Path $srcModel) {
        Write-Host "Menyalin model '$model'..."
        Copy-Item -Recurse -Force $srcModel (Join-Path $DistApp "models\")
    } else {
        Write-Warning "Model '$model' tidak ditemukan di folder models\ - dilewati. Aplikasi akan mengunduhnya saat run pertama."
    }
}

if (-not $SkipZip) {
    New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
    if (Test-Path $ZipPath) {
        Remove-Item -Force $ZipPath
    }
    Write-Host "Membuat zip (bisa beberapa menit)..."
    Compress-Archive -Path $DistApp -DestinationPath $ZipPath
    Write-Host ""
    Write-Host "Portable app berhasil dibuat:"
    Write-Host $ZipPath
} else {
    Write-Host ""
    Write-Host "Build selesai (tanpa zip):"
    Write-Host $DistApp
}
