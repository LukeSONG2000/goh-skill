---
name: goh
description: SWGOH (Star Wars: Galaxy of Heroes) 数据查询工具。爬取 swgoh.gg 获取角色属性、技能、GAC counter、best mods 等数据。
allowed-tools:
  - Bash(python3 ~/.claude/skills/goh/goh.py *)
---

# goh — SWGOH 数据查询

## 依赖

- `curl_cffi` — API 请求（TLS 指纹伪装）
- `DrissionPage` — CF Turnstile 绕过（best-mods、GAC counters 页面）
- Chromium 系浏览器（Chrome/Chromium/Edge，自动检测）

## 命令参考

### 名称数据库

```bash
# 从 API 初始化（保留已有 cn/nickname）
python3 ~/.claude/skills/goh/goh.py names init [--force]

# 搜索（支持英文名、base_id、中文、简称、缩写如 JML）
python3 ~/.claude/skills/goh/goh.py names search "luke"
python3 ~/.claude/skills/goh/goh.py names search "JML"

# 更新中文/简称
python3 ~/.claude/skills/goh/goh.py names update GRANDMASTERLUKE --cn "绝地武士大师卢克" --nickname "JML/老卢"

# 统计
python3 ~/.claude/skills/goh/goh.py names stats

# 导出未翻译条目
python3 ~/.claude/skills/goh/goh.py names missing

# 导出全部（TSV 或 JSON）
python3 ~/.claude/skills/goh/goh.py names export [--json]
```

### 基础数据（API 直连，无需 CF）

```bash
# 所有角色（325+）— 已关联 cn/nickname 显示
python3 ~/.claude/skills/goh/goh.py characters [--json] [--force]

# 所有技能（1796+）
python3 ~/.claude/skills/goh/goh.py abilities [--json] [--force] [--filter KEYWORD]

# 所有飞船（70+）— 已关联 cn/nickname 显示
python3 ~/.claude/skills/goh/goh.py ships [--json] [--force]

# 所有装备（694+）
python3 ~/.claude/skills/goh/goh.py gear [--json] [--force]
```

### GAC 数据

```bash
# 当前赛季配置
python3 ~/.claude/skills/goh/goh.py gac config [--json]

# 角色 countered（支持中文名/简称查询）
python3 ~/.claude/skills/goh/goh.py gac counters BOKATAN [--json]
python3 ~/.claude/skills/goh/goh.py gac counters "老卢" [--json]
python3 ~/.claude/skills/goh/goh.py gac counters JML --sort count --exclude-gl
```

### Best Mods（需 DrissionPage headed 过 CF）

```bash
# 单角色（支持中文名/简称查询）
python3 ~/.claude/skills/goh/goh.py mods darth-vader [--json] [--slice KYBER] [--force]
python3 ~/.claude/skills/goh/goh.py mods "老卢" --json

# 批量查询
python3 ~/.claude/skills/goh/goh.py mods "darth-vader,JML" --batch --json
```

### 搜索与缓存

```bash
# 搜索角色和技能
python3 ~/.claude/skills/goh/goh.py search "counter attack"

# 缓存管理
python3 ~/.claude/skills/goh/goh.py cache [--json]
python3 ~/.claude/skills/goh/goh.py cache --clear
```

## 名称确认工作流

当用户用中文/简称查询角色时，按以下流程处理：

1. 用 `names search` 查询，如果匹配到唯一结果且已有 cn/nickname → 直接使用
2. 如果匹配到多个结果 → 列出选项让用户选择
3. 如果匹配到结果但该角色尚无 cn/nickname → 先确认是否是用户要找的，确认后询问中文和简称，用 `names update` 保存
4. 如果没有匹配 → 提示用户用英文名或 base_id 再试

示例：
```
用户: 查一下老卢的 GAC counter
→ names search "老卢" → 命中 Jedi Master Luke Skywalker (GRANDMASTERLUKE)
→ gac counters GRANDMASTERLUKE → 返回结果
```

## 注意事项

- **API 数据**通过 `curl_cffi` 直接访问 `/api/`，缓存 24h
- **Best mods / GAC counters** 受 CF Turnstile 保护，需 DrissionPage headed 模式。首次访问需 5-10s 过 CF。需要图形界面环境（Linux 需安装 Chrome/Chromium + display）
- **浏览器兼容**：自动检测 Chrome > Chromium > Edge，支持 macOS 和 Linux
- **Cookie 不可跨客户端复用**：CF `cf_clearance` 绑定 TLS 指纹
- `--force` 跳过缓存 | `--json` 输出原始 JSON
