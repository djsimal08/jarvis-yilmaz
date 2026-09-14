$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\JARVIS-Yilmaz"
$DataRoot = Join-Path $env:LOCALAPPDATA "JarvisYilmaz"

Write-Host ""
Write-Host "JARVIS Windows Kurulumu" -ForegroundColor Cyan
Write-Host "Yalnızca bu bilgisayarda, localhost üzerinden çalışır." -ForegroundColor DarkCyan
Write-Host ""

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null

$PackagedExe = Join-Path $ProjectRoot "JARVIS.exe"
if (Test-Path $PackagedExe) {
    Copy-Item $PackagedExe (Join-Path $InstallRoot "JARVIS.exe") -Force
    $OrbExe = Join-Path $ProjectRoot "JARVIS-Orb.exe"
    if (Test-Path $OrbExe) {
        Copy-Item $OrbExe (Join-Path $InstallRoot "JARVIS-Orb.exe") -Force
    }
    if (Test-Path (Join-Path $ProjectRoot "chrome-extension")) {
        Copy-Item (Join-Path $ProjectRoot "chrome-extension") $InstallRoot -Recurse -Force
    }
    $LaunchTarget = Join-Path $InstallRoot "JARVIS.exe"
}
else {
    Write-Host "Kaynak kod kurulumu algılandı." -ForegroundColor Yellow
    $Python = Get-Command py -ErrorAction SilentlyContinue
    if (-not $Python) {
        throw "Python bulunamadı. Python 3.11 kurun: https://www.python.org/downloads/windows/"
    }
    Set-Location $ProjectRoot
    & py -3.11 -m venv .venv
    & (Join-Path $ProjectRoot ".venv\Scripts\python.exe") -m pip install --upgrade pip
    & (Join-Path $ProjectRoot ".venv\Scripts\python.exe") -m pip install -r requirements.txt
    $LaunchTarget = Join-Path $ProjectRoot "Start-JARVIS.bat"
}

$Name = Read-Host "JARVIS size nasıl hitap etsin? Adınızı yazın"
if ([string]::IsNullOrWhiteSpace($Name)) { $Name = "Efendim" }

$Config = @{
    host = "127.0.0.1"
    port = 8765
    user_name = $Name
    language = "tr-TR"
    whisper_model = "small"
    whisper_compute_type = "int8"
    ollama_url = "http://127.0.0.1:11434"
    ollama_model = "qwen3:4b"
    enable_local_llm = $true
    enable_voice_reply = $true
    allowed_file_roots = @("Desktop", "Documents", "Downloads")
    extra_applications = @{}
}
$ConfigJson = $Config | ConvertTo-Json -Depth 5
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $DataRoot "config.json"), $ConfigJson, $Utf8NoBom)

$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $DataRoot /inheritance:r /grant:r "$($CurrentUser):(OI)(CI)F" | Out-Null

$Shell = New-Object -ComObject WScript.Shell
$Desktop = [Environment]::GetFolderPath("Desktop")
$Shortcut = $Shell.CreateShortcut((Join-Path $Desktop "JARVIS.lnk"))
$Shortcut.TargetPath = $LaunchTarget
$Shortcut.WorkingDirectory = Split-Path -Parent $LaunchTarget
$Shortcut.Description = "JARVIS Yerel Kontrol Merkezi"
$Shortcut.Save()

Write-Host ""
Write-Host "Kurulum tamamlandı." -ForegroundColor Green
Write-Host "Masaüstündeki JARVIS kısayolunu kullanabilirsiniz." -ForegroundColor Green
Write-Host ""
Write-Host "Chrome eklentisi için:" -ForegroundColor Cyan
Write-Host "1. Chrome'da chrome://extensions adresini açın."
Write-Host "2. Geliştirici modu'nu açın."
Write-Host "3. Paketlenmemiş öğe yükle deyip chrome-extension klasörünü seçin."
Write-Host "4. JARVIS Ayarlar ekranındaki 6 haneli kodu eklentiye girin."
Write-Host ""

Start-Process $LaunchTarget
