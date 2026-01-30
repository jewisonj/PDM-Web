# Load iTextSharp
Add-Type -Path "D:\PDM-Libraries\iTextSharp\lib\itextsharp.dll"

Write-Host "iTextSharp loaded successfully!" -ForegroundColor Green
Write-Host "Version: " -NoNewline
[iTextSharp.text.Document]::Version
