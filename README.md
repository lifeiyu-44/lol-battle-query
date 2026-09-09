# LOL 国服战绩查询

输入玩家 ID 查询《英雄联盟》国服战绩的桌面工具。基于客户端本地 LCU 接口，
数据来自你自己登录的官方客户端，无第三方服务、不上传任何数据。

## 使用方法

1. 双击 `LOL战绩查询.exe`（无需安装，免费分享）。
2. 通过 WeGame 登录《英雄联盟》客户端，进入大厅（工具会自动检测并连接）。
3. 在工具顶部输入玩家 ID，点「查询」：
   - 支持 `名字` 或 `名字#Tag` 两种格式；
   - 首次进入自动加载最近 20 场，「加载全部战绩」可一直往前翻历史战绩；
   - 点击任意一场可查看两队 10 人的对局详情；
   - 「导出 CSV」把已加载战绩导出为表格（Excel 可直接打开）。

## 限制说明

- 必须在本机登录游戏客户端（LCU 接口只对登录客户端的本机开放，这也是
  Seraphine、League-Toolkit 等工具的工作方式）。
- 按名字精确查询只覆盖**当前登录大区**；跨大区玩家需输入完整 `名字#Tag`，
  且只有匹配到过的玩家才能查到。
- 英雄名称/头像来自腾讯官方资料站 CDN（game.gtimg.cn），首次联网自动缓存。

## 开发

```
python -m venv .venv
.venv\Scripts\pip install pywebview pyinstaller requests psutil
.venv\Scripts\python -m app.main        # 本地运行（需登录客户端）
build.bat                               # 打包单文件 exe 到 dist\
test\mock.html                          # 假数据页面，浏览器打开可调试 UI
```

## 目录结构

- `app/lcu.py` — LCU 连接（进程检测、认证、请求封装）
- `app/query.py` — 查人 / 战绩分页 / 单局详情 / 数据精简
- `app/champions.py` — 英雄、装备中文名与图片映射（腾讯 CDN + 本地缓存）
- `app/ui/` — 界面（原生 JS，无框架）
- `app/main.py` — pywebview 窗口与 JS API 桥
