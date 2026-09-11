# ============================================================
#  Iroh P2P Chat - stop-server.ps1
#  Stop ONLY this project's backend (port 8000) and frontend
#  dev server (port 5173), located by listening port.
#  Never kills unrelated node/python processes (e.g. the DSH
#  web service, or your other projects).
#  NOTE: keep this file pure ASCII (English only) so it parses
#  correctly under Windows PowerShell 5.1 regardless of encoding.
# ============================================================
$ErrorActionPreference = 'SilentlyContinue'

# Executable names we are allowed to kill (node=frontend/npm, python=backend, cmd=launcher window)
$allowedNames = @('node.exe', 'python.exe', 'py.exe', 'cmd.exe', 'conhost.exe')

$ports = @(8000, 5173)

foreach ($port in $ports) {
  $conns = Get-NetTCPConnection -LocalPort $port -State Listen
  if (-not $conns) {
    Write-Host "[stop] port $port : no listener, skip."
    continue
  }

  foreach ($c in $conns) {
    $leafPid = $c.OwningProcess

    # 1) collect descendants (recurse downward from the listener)
    $toKill = New-Object System.Collections.Generic.List[int]
    $toKill.Add($leafPid)
    $added = $true
    while ($added) {
      $added = $false
      $allProcs = Get-CimInstance Win32_Process
      foreach ($p in $allProcs) {
        if ($toKill.Contains([int]$p.ParentProcessId) -and -not $toKill.Contains([int]$p.ProcessId)) {
          $toKill.Add([int]$p.ProcessId)
          $added = $true
        }
      }
    }

    # 2) collect ancestors upward (npm/cmd/python), stop at explorer/system
    $cur = $leafPid
    for ($depth = 0; $depth -lt 15; $depth++) {
      $curProc = Get-CimInstance Win32_Process -Filter "ProcessId=$cur"
      if (-not $curProc) { break }
      $parent = [int]$curProc.ParentProcessId
      $parent = [int]$parent
      $parProc = Get-CimInstance Win32_Process -Filter "ProcessId=$parent"
      if (-not $parProc) { break }
      $parName = $parProc.Name.ToLower()
      if ($parName -in @('explorer.exe', 'services.exe', 'winlogon.exe', 'csrss.exe', 'svchost.exe')) { break }
      if ($allowedNames -contains $parName) {
        if (-not $toKill.Contains($parent)) { $toKill.Add($parent) }
        $cur = $parent
      } else {
        break
      }
    }

    # 3) kill children first, then parents
    foreach ($id in ($toKill | Sort-Object -Descending)) {
      Stop-Process -Id $id -Force
    }
    Write-Host "[stop] port $port : process tree stopped (listener PID=$leafPid)."
  }
}

Write-Host "[OK] Iroh backend & frontend stopped."
