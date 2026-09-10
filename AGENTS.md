# AGENTS.md

## 打包发版（每次功能改动后必须执行）

用户要求：每次改动代码后由助手完成打包，不要只改源码。

1. 改完代码先把 `app/main.py` 里的 `Api.VERSION` 递增一档（格式 `YYYY-MM-DD.N`）。
2. 打包命令（不要直接跑 build.bat，它结尾有 pause 会卡住；参数保持纯 ASCII）：

   ```bash
   PYTHONUTF8=1 PYTHONIOENCODING=utf-8 .venv/Scripts/pyinstaller.exe --noconfirm --clean build.spec
   ```

3. 打包前先关掉正在运行的旧实例，否则写出 `dist/恁🐎战绩查询.exe` 时报 WinError 5 拒绝访问：

   ```python
   # 用 .venv 的 python + psutil 找 name 含「战绩查询」的进程并 terminate
   ```

4. 产物同步到交付目录：`cp -f "dist/恁🐎战绩查询.exe" "dist_new/"`。
5. 打包后做启动冒烟：`subprocess.Popen` 拉起 exe，8 秒后确认进程仍存活再 terminate。

## 测试环境须知

- 本机没有 node/npm/playwright，`test/*.cjs` 的 Playwright 用例跑不了；改前端后用
  `scripts/build_smoke_page.py`（复制 test/mock.html 注入驱动脚本）+ 无头 Edge
  `--headless=new --dump-dom / --screenshot --virtual-time-budget` 做冒烟与截图验证。
- 后端单测：`.venv/Scripts/python.exe -m unittest discover -s test -p "test_*.py"`（pytest 未安装）。
- 无头 Edge 路径：`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`。
