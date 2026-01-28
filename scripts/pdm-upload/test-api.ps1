# Test the bulk BOM endpoint
$body = @{
    parent_item_number = "wma99999"
    children = @(
        @{item_number = "wmp00001"; quantity = 2; description = "Test Part 1"; material = "Steel"}
        @{item_number = "wmp00002"; quantity = 1; description = "Test Part 2"; material = "Aluminum"}
    )
    source_file = "test.txt"
} | ConvertTo-Json -Depth 5

Write-Host "Testing bulk BOM endpoint..."
Write-Host "Request body:"
Write-Host $body
Write-Host ""

try {
    $result = Invoke-RestMethod -Uri 'http://localhost:8000/api/bom/bulk' -Method Post -Body $body -ContentType 'application/json'
    Write-Host "SUCCESS!" -ForegroundColor Green
    Write-Host ($result | ConvertTo-Json -Depth 3)
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.ErrorDetails.Message) {
        Write-Host "Response: $($_.ErrorDetails.Message)" -ForegroundColor Yellow
    }
}
