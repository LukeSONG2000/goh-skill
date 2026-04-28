---
name: goh
description: "SWGOH (Star Wars: Galaxy of Heroes) 数据查询工具。爬取 swgoh.gg 获取角色属性、技能、GAC counter、best mods 等数据。"
version: 1.0.0
user-invocable: true
allowed-tools:
  - Bash(python3 {baseDir}/goh.py *)
metadata: >-
  {"openclaw":{"requires":{"anyBins":["python3"],"bins":["python3"],"install":[{"id":"pip-curl-cffi","kind":"pip","package":"curl_cffi","label":"Install curl_cffi (pip)"},{"id":"pip-drissionpage","kind":"pip","package":"DrissionPage","label":"Install DrissionPage 4.1+ (pip, 需图形界面Chrome 115-146, 如遇WebSocket错误请升级pip包)"}]},"emoji":"🎮","os":["darwin","linux"]}}
---

## 触发规则

当用户对话涉及以下内容时，应主动使用本 skill 查询并回复：

- SWGOH / swgoh / 星球大战银河英雄传 / 银河英雄传 / GAC
- 角色的 mod / 插件 / 配队 / counter / 技能 / 属性 / 数据 / 速度 / 血量 / Speed / Health / Protection
- 舰船编队 / 装备 / Gear / Relic
- 具体角色名（英文或中文），如 "老卢"、"JML"、"Darth Vader"、"达斯维达"
- GAC 赛季配置、counter 关系、胜率、banner
- Best Mods 推荐、mod 数据分析

## 语言规则

- **使用中文作为主要交流语言**
- **保持爬取内容的原文**：游戏内英文名称、技能描述、API 返回的原始数据不要自行翻译
- **中文注释放在括号内**：仅在用户使用中文名查询或首次提到时，在英文名后用括号补充中文，格式：`English Name（中文翻译）`
  - 示例：Jedi Master Luke Skywalker（绝地大师卢克天行者）
  - 示例：Critical Damage（暴击伤害）
  - 已有 cn/nickname 记录的角色直接使用中文，无需再标注英文
- **缩写/简称直接使用**：如 JML、JMK、SEE、SLKR 等，不需要展开全称

## 执行行为规则

- **逐步执行，每步汇报**：不要在一个 turn 里连续调用多个命令。每执行一步后，先向用户输出当前进展，再执行下一步
- 示例流程（查询角色属性时）：
  1. 先输出："正在查找角色..."
  2. 执行 `names search` 确认角色
  3. 输出："找到了 Darth Vader（达斯维达），正在获取属性数据..."
  4. 执行 `stats` 命令
  5. 输出结果
- **耗时操作提前告知**：需要浏览器的命令（stats、mods、gac counters）需要 5-10 秒过 CF，执行前告知用户
- **失败时立即反馈**：如果某步失败，不要继续执行后续步骤，立即告知用户错误原因

# goh — SWGOH 数据查询

所有命令通过 `python3 {baseDir}/goh.py` 调用。下文示例省略此前缀，用 `goh` 代指。

## 依赖

- `python3` 3.9+
- `curl_cffi` — API 请求（TLS 指纹伪装），`pip install curl_cffi`
- `DrissionPage` — CF Turnstile 绕过，`pip install DrissionPage`（**需 4.1.0+**）
- **图形界面的 Chromium 系浏览器**（headed 模式，CF Turnstile 必须有真实渲染环境）
  - 自动检测顺序：Chrome > Chromium > Edge
  - **必须是有头浏览器（headed）**，headless 会被 CF 拦截
  - **Chrome 版本需与 DrissionPage 兼容**：DrissionPage 4.1.x 支持 Chrome 115-131。如果环境是 Chrome 132+（如 Chrome 146），需升级 DrissionPage 到最新版（`pip install --upgrade DrissionPage`），或安装兼容的 Chrome 版本
  - macOS 路径：`/Applications/Google Chrome.app`、`/Applications/Chromium.app`、`/Applications/Microsoft Edge.app`
  - Linux 路径：`/usr/bin/google-chrome`、`/usr/bin/chromium-browser`、`/snap/bin/chromium`

### 命令与数据源对照

| 命令 | 数据源 | 需要浏览器 |
|------|--------|-----------|
| `characters` / `abilities` / `ships` / `gear` | `/api/` 直连 | 否 |
| `gac config` | `/api/v1/` 直连 | 否 |
| `gac counters` | `/gac/counters/` 页面 | **是** |
| `stats` | `/units/` 页面 | **是** |
| `mods` | `/characters/*/best-mods/` 页面 | **是** |
| `names` / `search` / `cache` | 本地文件 / API | 否 |

**如果浏览器不可用或版本不兼容**，`stats`、`mods`、`gac counters` 命令会失败并提示错误。其余命令正常工作。

## 命令参考

### 名称数据库

```bash
goh names init [--force]           # 从 API 初始化（保留已有 cn/nickname）
goh names search "luke"            # 搜索（英文名/base_id/中文/简称/缩写如 JML）
goh names search "JML"             # 缩写匹配
goh names update GRANDMASTERLUKE --cn "绝地武士大师卢克" --nickname "JML/老卢"
goh names stats                    # 统计翻译进度
goh names missing                  # 导出未翻译条目
goh names export [--json]          # 导出全部（TSV 或 JSON）
```

### 基础数据（API 直连，无需 CF）

```bash
goh characters [--json] [--force]  # 所有角色（325+），已关联 cn/nickname
goh abilities [--json] [--force] [--filter KEYWORD]  # 所有技能（1796+）
goh ships [--json] [--force]      # 所有飞船（70+），已关联 cn/nickname
goh gear [--json] [--force]       # 所有装备（694+）
```

### 角色属性（需 DrissionPage headed 过 CF）

```bash
goh stats darth-vader [--json] [--gear-tier RELIC_7]  # 单角色属性
goh stats "老卢" --json                                # 支持中文查询
goh stats JMK --gear-tier RELIC_9                      # 指定 Gear/Relic 等级
```

返回：Power、Health、Protection、Speed、Critical Damage/Chance、Potency、Tenacity、
Physical/Special Offense（Damage、Armor Penetration、Accuracy）、
Physical/Special Survivability（Armor、Dodge、Critical Avoidance）等。

Gear Tier 选项：`GEAR_12`、`GEAR_13`、`RELIC_1` ~ `RELIC_10`，默认 `GEAR_12`。

### GAC 数据

```bash
goh gac config [--json]                    # 当前赛季配置
goh gac counters BOKATAN [--json]          # 角色 counter（支持中文名/简称）
goh gac counters "老卢" --sort count --exclude-gl
```

GAC counters 参数：`--season-id`、`--sort win_pct|count|banners`、`--exclude-gl`

### Best Mods（需 DrissionPage headed 过 CF）

```bash
goh mods darth-vader [--json] [--slice KYBER]  # 单角色
goh mods "老卢" --json                           # 支持中文查询
goh mods "darth-vader,JML" --batch --json      # 批量
```

### 搜索与缓存

```bash
goh search "counter attack"     # 搜索角色和技能
goh cache [--json]              # 缓存状态
goh cache --clear               # 清除全部缓存
```

## 名称确认工作流

当用户用中文/简称查询角色时：

1. `names search` 匹配到唯一结果且已有 cn/nickname → 直接使用
2. 匹配到多个结果 → 列出选项让用户选择
3. 匹配到结果但无 cn/nickname → 确认后询问中文和简称，用 `names update` 保存
4. 无匹配 → 提示用英文名或 base_id 再试

## 注意事项

- **API 数据**通过 `curl_cffi` 直接访问 `/api/`，缓存 24h（GAC 1h，mods 12h）
- **stats / mods / gac counters** 受 CF Turnstile 保护，需 DrissionPage **headed 模式**（真实图形界面浏览器，5-10s 过 CF）。headless / curl / fetch 全部被 403
- **DrissionPage 与 Chrome 版本必须兼容**：如果遇到 `WebSocket handshake failed` 或 `Protocol error`，说明版本不匹配。解决方案：
  1. 升级 DrissionPage：`pip install --upgrade DrissionPage`
  2. 或降级 Chrome 到 115-131 范围
- **Cookie 不可跨客户端复用**：CF `cf_clearance` 绑定 TLS 指纹，DrissionPage 提取的 cookie 给 curl_cffi 用仍然 403
- `--force` 跳过缓存 | `--json` 输出原始 JSON
