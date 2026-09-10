# 后台笔记与本地草稿管理

所有命令均从 `python scripts/cli.py` 运行；页面读取沿用 XHS Bridge。离线链接生成和已有数据导出不连接浏览器。

## 3. 自己的笔记与草稿管理

目标：查自己发布的内容及状态，找到浏览器已有草稿并定位恢复编辑入口。

```bash
python scripts/cli.py list-managed-notes --status all --limit 100 --max-pages 3
python scripts/cli.py get-note-status --note-id NOTE_ID
python scripts/cli.py list-drafts --kind all
python scripts/cli.py open-draft --draft-id DRAFT_ID --expected-title '完整草稿标题' --kind image
# 明确要继续编辑时，追加 --open；不会保存或发布。
```

- `list-managed-notes` 读取创作平台，状态筛选为 `all/published/reviewing/rejected`；未确认的状态代码保留未知，不假定为已发布。附带数据仅是管理列表快照，不等同完整分析后台。
- `list-drafts` 支持 `image/video/long/audio/all`。这些草稿存储于当前浏览器本地，不是账号在所有设备上的全部草稿。
- `open-draft` 默认只预览目标。只有加 `--open` 才点击对应草稿的编辑入口，并核对 UUID、分类和完整标题。
- 本次不提供删除、修改已发布笔记或自动保存草稿。已有 `fill-publish`、`save-draft`、`click-publish` 继续负责原发布流程，调用前仍须遵守其内容及确认约束。

## 完整性与验收

- 返回 `complete=false` 时，结合 `has_more`、`stop_reason` 或 `stopped_reason` 判断是条数限制、页数限制、未证实结束、未知类型还是加载停滞；不可汇报为“已读完”。
- 限制参数约束一次命令的读取量，不是持续定时监控。需要持续运行时另行设计调度、增量保存和任务恢复。
- 新管理命令在跨页前保护当前私信草稿和创作编辑内容；存在未处理内容时停止导航，不擅自保存、覆盖或清空。
- 验证分三层：实际脚本和原始结构的离线测试、已登录网页的只读读取、写操作的授权后实测。原汇总分支已进行只读实测；拆分后重新执行离线测试。关注变更、草稿打开编辑等路径未在真实账号执行，不将模拟验证当作实测。

已有图文/视频发布命令在没有成功反馈时返回未确认，不把超时视为发布完成；原创声明失败会阻止发布。定时参数须带明确时区，时间窗口为未来 1 小时至 14 天，按北京时间填写。
