$procs = Get-Process python* -ErrorAction SilentlyContinue | Where-Object {
    try {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
        $cmd -like '*uvicorn*' -or $cmd -like '*upload-manager*'
    } catch { $false }
}
foreach ($p in $procs) {
    Write-Host "Killing upload-manager PID: $($p.Id)"
    Stop-Process -Id $p.Id -Force
}
Start-Sleep -Seconds 1
Start-Process python3 -ArgumentList '-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8003' -WorkingDirectory 'C:\Users\w10\upload-manager' -WindowStyle Hidden
Write-Host "Upload Manager restarted on port 8003"
Start-Sleep -Seconds 1
try {
    $null = Invoke-WebRequest -Uri 'http://localhost:8099/load' -UseBasicParsing -TimeoutSec 3
    Write-Host "Chat server: OK (port 8099)"
} catch {
    Write-Host "Chat server was down - restarting..."
    Start-Process python3 -ArgumentList 'C:\Users\w10\chat_server.py' -WindowStyle Hidden
    Write-Host "Chat server restarted on port 8099"
}
