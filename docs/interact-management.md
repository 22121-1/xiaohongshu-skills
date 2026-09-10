# 私信、通知与关注管理

所有命令均从 `python scripts/cli.py` 运行；页面读取沿用 XHS Bridge。离线链接生成和已有数据导出不连接浏览器。

## 1. 私信读取与待回复管理

目标：知道谁发了什么、哪些会话可能需要回复，以及哪些已由自己处理。

```bash
python scripts/cli.py list-inbox --limit 100 --max-scrolls 3
python scripts/cli.py get-messages --user-id USER_ID --expected-name '完整昵称' --limit 100
python scripts/cli.py list-pending-replies --limit 20 --message-limit 100 --max-scrolls 3
python scripts/cli.py mark-conversation --user-id USER_ID --expected-name '完整昵称' \
  --message-id LAST_INCOMING_MESSAGE_ID --status handled
```

- 读取单人会话、未读数、最后消息时间和历史消息，保留收发方向及图片等内容信息。群聊和陌生人文件夹不在本次范围。
- “未读”是网页状态；“待回复”依据已读取的有效消息和本地处理标记判断。不能把二者等同。`pending` 是候选，是否需要回复仍要结合内容判断；如一句“谢谢”可能只需知悉。
- `list-pending-replies` 的 `pending` 是候选子集，`conversations` 保留已检查会话及 `pending/replied/handled/empty/unknown` 状态，`errors` 记录失败。不要丢弃未知项；处理标记使用会话中的 `last_incoming_message_id`。
- 没有默认的“上次运行以来”增量边界。用户说“其中一条已处理”时，先明确具体会话及处理到哪条消息，不将其后新消息一并标记。
- 本地处理标记绑定当前账号、会话及最新入站消息 ID；新消息到来后不继承旧的“已处理”。使用 `--status pending` 可恢复待处理标记。
- 状态库只保存处理标记，不保存消息正文。需要改变位置时传绝对路径 `--state-file`。
- 网页未提供会话列表的完整结束标志，所以会话清单明确是已加载范围。单个会话历史能取得 `hasMoreHistory` 时据此判断是否完整。
- 疑似“相互关注，开始聊天”的欢迎文字保留不确定标记；无法确定发送者或内容性质时，不自动认定需要回复。
- 打开会话可能由网页自然标记已读；命令不会额外发送已读请求、回复或清空草稿。发送仍使用已有的独立私信命令及授权流程。

## 2. 评论、回复、提及及其他通知

目标：集中读取账号收到的互动，保留通知对应的用户、评论和目标内容。

```bash
python scripts/cli.py get-notifications --kind all --limit 100 --max-pages 3
python scripts/cli.py get-notifications --kind comments
python scripts/cli.py get-notifications --kind mentions
```

- 分类：`comments` 包含评论和回复，`mentions` 为提及，另有 `likes`（赞和收藏）、`follows`（新增关注）、`all`。
- 网页把评论和提及放在同一分组，命令读取后按实际类型区分；不认识的类型保留为未知，不根据标题强猜。
- 保留专辑与附属笔记的类型关系，不把专辑编号误当成笔记编号。
- 返回分页完整性、用户字段完整性、未知类型数量和停止原因。加载失败不能返回“成功且零条”。
- 打开通知页可能自然改变网页未读状态。本命令只读取，不自动回复、点赞或关注。

## 4. 关注关系管理

目标：查询指定用户的关注状态，在有明确授权时准确切换一次。

```bash
python scripts/cli.py get-follow-status --user-id USER_ID --expected-name '完整昵称'
python scripts/cli.py set-follow --user-id USER_ID --expected-name '完整昵称' --state followed
# 确认要执行时追加 --confirm；取消关注使用 --state not-followed。
```

- 默认预览，核对路径中的用户 ID 和主页完整昵称；“互相关注”识别为已关注。
- 已达到目标状态时不点击。确认变更后最多点击一次，并重新读取页面核验；超时或结果不明返回 `unknown`，不能自动再点一次。
- 当前实测网页版主页没有打开关注／粉丝完整列表的入口，因此本次不提供全量关注列表管理。新增关注通知也不能代替完整粉丝列表。

## 完整性与验收

- 返回 `complete=false` 时，结合 `has_more`、`stop_reason` 或 `stopped_reason` 判断是条数限制、页数限制、未证实结束、未知类型还是加载停滞；不可汇报为“已读完”。
- 限制参数约束一次命令的读取量，不是持续定时监控。需要持续运行时另行设计调度、增量保存和任务恢复。
- 新管理命令在跨页前保护当前私信草稿和创作编辑内容；存在未处理内容时停止导航，不擅自保存、覆盖或清空。
- 验证分三层：实际脚本和原始结构的离线测试、已登录网页的只读读取、写操作的授权后实测。原汇总分支已进行只读实测；拆分后重新执行离线测试。关注变更、草稿打开编辑等路径未在真实账号执行，不将模拟验证当作实测。
