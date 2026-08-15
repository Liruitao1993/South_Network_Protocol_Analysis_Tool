$ErrorActionPreference = "Stop"
$ProgressPreference = 'SilentlyContinue'

$zip = "C:\Users\lirt3\Downloads\JetBrainsMono_NF.zip"
$extractDir = "C:\Users\lirt3\Downloads\JetBrainsMono_NF"

# Try multiple Chinese mirrors
$mirrors = @(
    "https://mirror.ghproxy.com/https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.zip",
    "https://gh-proxy.com/https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.zip",
    "https://ghproxy.net/https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.zip",
    "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.zip"
)

$downloaded = $false
foreach ($url in $mirrors) {
    Write-Host "Trying: $($url.Substring(0, 60))..."
    try {
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing -TimeoutSec 60
        $downloaded = $true
        Write-Host "Download OK!"
        break
    } catch {
        Write-Host "Failed: $($_.Exception.Message)"
    }
}

if (-not $downloaded) {
    Write-Host "All mirrors failed!"
    exit 1
}

Write-Host "Extracting..."
if (Test-Path $extractDir) { Remove-Item -Recurse -Force $extractDir }
Expand-Archive -Path $zip -DestinationPath $extractDir

$ttfFiles = Get-ChildItem -Path $extractDir -Filter "*.ttf" -Recurse
Write-Host "Found $($ttfFiles.Count) font files. Installing..."

$shellApp = New-Object -ComObject Shell.Application
$fontsFolder = $shellApp.Namespace(0x14)
foreach ($f in $ttfFiles) {
    Write-Host "  $($f.Name)"
    $fontsFolder.CopyHere($f.FullName, 0x10)
}

Write-Host "Done! Installed $($ttfFiles.Count) JetBrainsMono Nerd Font files."
