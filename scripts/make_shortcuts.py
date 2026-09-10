# -*- coding: utf-8 -*-
"""生成桌面与开机自启快捷方式：PowerShell -EncodedCommand 全程无编码损耗。"""
import base64
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent
# WScript.Shell 的 TargetPath 拒绝含 emoji（非 BMP 字符）的路径，
# 因此快捷方式指向无 emoji 名的部署副本 LOL战绩查询.exe，快捷方式名保留应用原名。
exe = root / "dist_new" / "LOL战绩查询.exe"
icon = root / "app" / "ui" / "app-icon.ico"
ps = r"""
$ErrorActionPreference = 'Stop'
try {
  $ws = New-Object -ComObject WScript.Shell
  $exe  = '@EXE@'
  $dir  = '@DIR@'
  $icon = '@ICON@'
  $desktop = $ws.SpecialFolders('Desktop')
  $startup = $ws.SpecialFolders('Startup')
  foreach ($folder in @($desktop, $startup)) {
    $s = $ws.CreateShortcut((Join-Path $folder 'LOL战绩查询.lnk'))
    $s.TargetPath = $exe
    $s.WorkingDirectory = $dir
    $s.IconLocation = $icon
    $s.Description = '英雄联盟国服战绩查询'
    $s.Save()
    Write-Output ('created in ' + $folder + ' -> ' + (Test-Path (Join-Path $folder 'LOL战绩查询.lnk')))
  }
} catch {
  Write-Output ('ERROR: ' + $_.Exception.Message)
}
""".replace("@EXE@", str(exe)).replace("@DIR@", str(root / "dist_new")).replace("@ICON@", str(icon))

encoded = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
result = subprocess.run(
    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
    capture_output=True, timeout=60)
print(result.stdout.decode("gbk", "replace").strip())
if result.returncode != 0:
    print("stderr:", result.stderr.decode("gbk", "replace").strip())
