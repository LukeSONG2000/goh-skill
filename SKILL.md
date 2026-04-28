---
name: goh
description: "SWGOH (Star Wars: Galaxy of Heroes) 数据查询工具。爬取 swgoh.gg 获取角色属性、技能、GAC counter、best mods 等数据。"
version: 1.0.0
user-invocable: true
allowed-tools:
  - Bash(python3 {baseDir}/goh.py *)
metadata: >-
  {"openclaw":{"requires":{"anyBins":["python3"],"bins":["python3"],"install":[{"id":"pip-curl-cffi","kind":"pip","package":"curl_cffi","label":"Install curl_cffi (pip)"},{"id":"pip-drissionpage","kind":"pip","package":"DrissionPage","label":"Install DrissionPage (pip)"}]},"emoji":"🎮","os":["darwin","linux"]}}
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

# goh — SWGOH 数据查询

所有命令通过 `python3 {baseDir}/goh.py` 调用。下文示例省略此前缀，用 `goh` 代指。

## 依赖

- `python3` 3.9+
- `curl_cffi` — API 请求（TLS 指纹伪装）
- `DrissionPage` — CF Turnstile 绕过（best-mods、GAC counters）
- Chromium 系浏览器（Chrome/Chromium/Edge，自动检测，需图形界面）

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
- **Best mods / GAC counters** 受 CF Turnstile 保护，需 DrissionPage headed 模式（5-10s 过 CF）
- **浏览器兼容**：自动检测 Chrome > Chromium > Edge，支持 macOS 和 Linux
- **Cookie 不可跨客户端复用**：CF `cf_clearance` 绑定 TLS 指纹
- `--force` 跳过缓存 | `--json` 输出原始 JSON
