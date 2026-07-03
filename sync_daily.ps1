$log = "D:\TOPPULS\外贸开发\sync_daily_log.txt"
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$ts] ===== Start Shopee Sync =====" | Out-File -FilePath $log -Encoding utf8

$py = "C:\Users\Stanley\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$script = "D:\TOPPULS\外贸开发\sync_shopee_orders.py"

try {
    $result = & $py $script 2>&1
    foreach ($line in $result) {
        "  $line" | Out-File -FilePath $log -Encoding utf8 -Append
    }
} catch {
    "  ERROR: $_" | Out-File -FilePath $log -Encoding utf8 -Append
}

$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$ts] ===== End =====" | Out-File -FilePath $log -Encoding utf8 -Append
