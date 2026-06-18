# AGENTS.md

始终使用中文回复。

本仓库是 `goh` skill，兼容 Codex/OpenClaw 风格 agent。处理 SWGOH 数据查询、网络商店登录、免费礼物、每日好礼、Kessel Run/科舍尔航程奖励领取时，必须先读取并遵循 `SKILL.md`。

## Webstore 长连接规则

- 用户说“帮我领取网络商店”“领取每日好礼”“领取科舍尔航程/Kessel Run”时，使用：`python3 {baseDir}/goh.py webstore claim --wait`。
- 如果状态变成 `awaiting_email`，向用户询问 EA 账号邮箱；收到后执行：`python3 {baseDir}/goh.py webstore email <邮箱> --wait`。
- 如果状态变成 `awaiting_code`，提示验证码已发送到邮箱；收到 6 位验证码后执行：`python3 {baseDir}/goh.py webstore code <验证码> --wait`。
- 不要重新启动新登录流程来替代等待中的流程；服务会跨多轮对话保留浏览器长连接。
- 登录完成、领取完成或验证码等待超时后，服务会关闭浏览器；必要时用 `python3 {baseDir}/goh.py webstore cleanup` 手动清理。
- 不得点击或调用 `BUY NOW`、真实货币、HKD、水晶/PREMIUM、Pass Plus 等购买动作。

## 每天 0 点领取

用户说“每天0点帮我领取网络商店”时，安装每日任务：

```bash
cd {baseDir}/webstore && npm install
python3 {baseDir}/goh.py webstore install-service
python3 {baseDir}/goh.py webstore start-service
python3 {baseDir}/goh.py webstore install-daily 0 0
python3 {baseDir}/goh.py webstore start-daily
```
