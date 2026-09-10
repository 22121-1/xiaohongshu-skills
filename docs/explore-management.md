# 个人内容库、链接与导出

所有命令均从 `python scripts/cli.py` 运行；页面读取沿用 XHS Bridge。离线链接生成和已有数据导出不连接浏览器。

## 自己的主页笔记

```bash
python scripts/cli.py list-my-notes --keyword '标题关键词'
```

读取当前账号主页笔记元数据，不提供创作后台审核状态。

## 5. 收藏、网页专辑与个人检索

目标：找到自己存过的内容，并明确检索覆盖范围。

```bash
python scripts/cli.py list-favorites --limit 100 --max-pages 3
python scripts/cli.py list-collections
python scripts/cli.py search-library --scope all --keyword '关键词' --limit 100 --max-pages 3
```

- `search-library` 范围为 `notes/favorites/all`，当前检索列表中的标题、作者，不宣称全文检索。
- 笔记和收藏共用分页、去重及身份核对机制，按网页正确的数据分组读取。
- `list-collections` 对应网页“专辑”，非空记录保留其原始结构；不等于 App 的所有收藏夹。
- 本次不提供专辑创建、改名、删除或内容移动，也没有未经证实的专辑详情入口。

## 6. 链接与内容导出

上游 PR #66 提供分享地址生成和搜索结果 `shareUrl`。本次沿用其能力范围，增加正确的 URL 参数编码、链接解析和本地导出；不是把 #66 当成完整导出功能。

```bash
python scripts/cli.py get-share-url --feed-id NOTE_ID --xsec-token TOKEN
python scripts/cli.py resolve-link --link '完整链接或含链接的分享文案'
python scripts/cli.py export-note --link '笔记链接' --output /绝对路径/note.md --format markdown
python scripts/cli.py export-content --input /绝对路径/已读取.json \
  --output /绝对路径/归档.json --format json
```

- 支持主站笔记长链接、个人主页下的笔记链接，以及通过 HTTP 重定向跳转的 `xhslink.com` 短链接。每一跳验证域名和网络目标；依赖网页脚本的短链会明确报出限制。
- 生成或解析链接不代表已验证笔记可访问，也不延长访问令牌有效期。
- 搜索、主页等笔记序列化结果附带 `shareUrl`；缺令牌或有效笔记编号时返回空地址。
- `export-note` 读取笔记详情并校验实际笔记编号；只导出已读取的评论，不假称全部评论完整。
- JSON 保留结构化数据；Markdown 提供可读正文、图片地址、评论及完整数据。媒体默认只记录地址，不下载图片或视频。
- 输出必须是绝对路径，父目录需已存在，默认不覆盖文件；明确覆盖时加 `--overwrite`。导出包含账号可见的个人内容，应由用户选择保存和分享位置。

## 完整性与验收

- 返回 `complete=false` 时，结合 `has_more`、`stop_reason` 或 `stopped_reason` 判断是条数限制、页数限制、未证实结束、未知类型还是加载停滞；不可汇报为“已读完”。
- 限制参数约束一次命令的读取量，不是持续定时监控。需要持续运行时另行设计调度、增量保存和任务恢复。
- 新管理命令在跨页前保护当前私信草稿和创作编辑内容；存在未处理内容时停止导航，不擅自保存、覆盖或清空。
- 验证分三层：实际脚本和原始结构的离线测试、已登录网页的只读读取、写操作的授权后实测。原汇总分支已进行只读实测；拆分后重新执行离线测试。关注变更、草稿打开编辑等路径未在真实账号执行，不将模拟验证当作实测。

## 既有读取接口的兼容说明

`get-feed-detail` 保留原 `comments` 数组，新增 `comment_pagination` 说明一级和子评论完整性；默认读取更多时的一级上限改为 20。视频详情保留媒体流和字幕，JSON/Markdown 导出继续只记录地址。`user-profile --tab note|fav|liked` 只读取选定分组，不能把私密或未加载分组当作空列表成功。
