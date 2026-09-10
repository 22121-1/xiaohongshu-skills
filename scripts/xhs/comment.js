(params) => {
    const unwrap = value => {
        for (let i = 0; i < 4 && value && typeof value === 'object'; i++) {
            if (value.value !== undefined) value = value.value;
            else if (value._value !== undefined) value = value._value;
            else break;
        }
        return value;
    };
    const array = value => {
        value = unwrap(value);
        if (Array.isArray(value)) return value;
        if (value && typeof value === 'object' && Object.keys(value).every(k => /^\d+$/.test(k))) {
            return Object.keys(value).sort((a, b) => Number(a) - Number(b)).map(k => value[k]);
        }
        return [];
    };
    const text = value => String(value == null ? '' : value).replace(/\r\n/g, '\n').trim();
    const visible = el => {
        if (!el) return false;
        const rect = el.getBoundingClientRect?.() || {};
        const style = typeof getComputedStyle === 'function' ? getComputedStyle(el) : {};
        return Number(rect.width || 0) > 0 && Number(rect.height || 0) > 0 &&
            style.display !== 'none' && style.visibility !== 'hidden';
    };
    const done = value => JSON.stringify(value);
    const idOf = value => String(value?.id || value?.commentId || value?.comment_id || '');
    const userOf = value => {
        value = unwrap(value) || {};
        return {
            user_id: String(value.userId || value.user_id || value.userid || ''),
            nickname: text(value.nickname || value.nickName || value.userName),
        };
    };

    const noteState = unwrap(window.__INITIAL_STATE__?.note) || {};
    const detailMap = unwrap(noteState.noteDetailMap);
    const expectedPaths = [`/explore/${params.feed_id}`, `/discovery/item/${params.feed_id}`];
    if (location.origin !== 'https://www.xiaohongshu.com' ||
        !expectedPaths.includes(location.pathname.replace(/\/$/, ''))) {
        return done({error: '当前页面 URL 与目标笔记不一致，未执行互动'});
    }
    if (!detailMap || typeof detailMap !== 'object' ||
        !Object.prototype.hasOwnProperty.call(detailMap, params.feed_id)) {
        return done({error: '当前页面状态中没有目标笔记，未执行互动'});
    }
    const detail = unwrap(detailMap[params.feed_id]);
    const note = unwrap(detail?.note) || {};
    const stateFeedId = String(note.noteId || note.id || params.feed_id);
    if (stateFeedId !== params.feed_id) {
        return done({error: '当前页面状态中的笔记 ID 与目标不一致'});
    }

    const userState = unwrap(window.__INITIAL_STATE__?.user) || {};
    const account = userOf(userState.userInfo);
    const loggedIn = unwrap(userState.loggedIn);
    if (loggedIn === false || unwrap(userState.userInfo)?.guest === true || !account.user_id ||
        visible(document.querySelector?.('.login-container'))) {
        return done({error: '无法确认当前登录账号身份'});
    }

    const stateComments = [];
    const visit = (rawValue, rootId = '') => {
        const raw = unwrap(rawValue) || {};
        const commentId = idOf(raw);
        if (!commentId) return;
        const author = userOf(raw.userInfo || raw.user || raw.author);
        const root = rootId || commentId;
        const target = unwrap(raw.targetComment || raw.target_comment || raw.replyToComment) || {};
        const targetUser = userOf(raw.targetUserInfo || raw.replyToUser || target.userInfo || target.user);
        stateComments.push({
            id: commentId,
            content: text(raw.content),
            author_id: author.user_id,
            author_name: author.nickname,
            root_id: root,
            reply_to_comment_id: String(raw.targetCommentId || raw.target_comment_id ||
                raw.replyToCommentId || idOf(target) || ''),
            reply_to_user_id: String(raw.targetUserId || raw.target_user_id ||
                raw.replyToUserId || targetUser.user_id || ''),
            source: 'state',
        });
        for (const child of array(raw.subComments || raw.sub_comments)) visit(child, root);
    };
    const commentRoot = unwrap(detail?.comments) || {};
    for (const raw of array(commentRoot.list || commentRoot.comments || commentRoot)) visit(raw);

    const elementId = el => {
        const raw = String(el?.id || el?.getAttribute?.('data-comment-id') || '');
        return raw.startsWith('comment-') ? raw.slice(8) : raw;
    };
    const directNodes = (el, selector) => [...(el?.querySelectorAll?.(selector) || [])]
        .filter(node => !node.closest || node.closest('.comment-item') === el);
    const domRecord = el => {
        const id = elementId(el);
        if (!id) return null;
        const userNodes = directNodes(el, '[data-user-id]');
        const author = directNodes(el, '.author .name[data-user-id]')[0] || userNodes[0];
        const contentNode = directNodes(el,
            '.note-text, .comment-content, .content-text, .comment-text')[0];
        const floor = el.closest?.('.parent-comment');
        const floorItems = [...(floor?.querySelectorAll?.('.comment-item') || [])];
        const rootEl = floorItems.find(item => !item.closest || item.closest('.parent-comment') === floor);
        const rootId = elementId(rootEl) || id;
        const authorId = String(author?.getAttribute?.('data-user-id') || '');
        const replyUser = [...new Set(userNodes.map(node =>
            String(node.getAttribute?.('data-user-id') || '')).filter(Boolean))]
            .find(userId => userId !== authorId) || '';
        const replyNode = directNodes(el,
            '[data-target-comment-id], [data-reply-comment-id], [data-reply-to-comment-id]')[0];
        const replyCommentId = String(replyNode?.getAttribute?.('data-target-comment-id') ||
            replyNode?.getAttribute?.('data-reply-comment-id') ||
            replyNode?.getAttribute?.('data-reply-to-comment-id') || '');
        return {
            id,
            content: text(contentNode?.innerText ?? contentNode?.textContent ?? ''),
            author_id: authorId,
            author_name: text(author?.innerText ?? author?.textContent ?? ''),
            root_id: rootId,
            reply_to_comment_id: replyCommentId,
            reply_to_user_id: replyUser,
            source: 'dom',
        };
    };
    const domElements = [...document.querySelectorAll('.comment-item')];
    const domComments = domElements.map(domRecord).filter(Boolean);
    const merged = new Map();
    // DOM 负责证明元素已渲染，响应式状态负责保留表情文本、targetComment 等
    // 结构化字段；同一 ID 时以状态为准。
    for (const item of [...domComments, ...stateComments]) {
        const old = merged.get(item.id) || {};
        const next = {...old};
        for (const [key, value] of Object.entries(item)) {
            if (value !== '' && value != null) next[key] = value;
        }
        merged.set(item.id, next);
    }
    const comments = [...merged.values()];
    const meta = {ready: true, feed_id: params.feed_id, account, comments};

    if (params.action === 'snapshot') return done(meta);

    if (params.action === 'lookup') {
        let matches = [];
        if (params.comment_id) {
            matches = domComments.filter(item => item.id === params.comment_id);
        } else if (params.user_id) {
            matches = domComments.filter(item => item.author_id === params.user_id);
        } else {
            return done({error: '缺少评论 ID 或用户 ID'});
        }
        if (matches.length > 1) return done({error: '目标评论不唯一，请改用 comment_id'});
        if (!matches.length) return done({...meta, found: false});
        const target = matches[0];
        if (params.expected_user_id && target.author_id !== params.expected_user_id) {
            return done({error: '目标评论作者身份已变化'});
        }
        const el = domElements.find(item => elementId(item) === target.id);
        el?.scrollIntoView?.({behavior: 'smooth', block: 'center'});
        return done({...meta, found: true, target});
    }

    if (params.action === 'reply_binding') {
        const editors = [...document.querySelectorAll('.engage-bar.active .reply-content')]
            .filter(visible);
        if (editors.length !== 1) return done({...meta, bound: false});
        const replyLabel = text(editors[0].querySelector?.('.reply')?.innerText ??
            editors[0].querySelector?.('.reply')?.textContent);
        const targetContent = text(editors[0].querySelector?.('.content')?.innerText ??
            editors[0].querySelector?.('.content')?.textContent);
        const authorMatches = params.target_author && replyLabel.includes(params.target_author);
        return done({...meta, bound: Boolean(authorMatches &&
            targetContent === text(params.target_content)), reply_label: replyLabel,
            target_content: targetContent});
    }

    if (params.action === 'post_binding') {
        const replyTargets = [...document.querySelectorAll('.engage-bar.active .reply-content')]
            .filter(visible);
        return done({...meta, bound: replyTargets.length === 0});
    }

    if (params.action === 'mark_expand') {
        for (const old of document.querySelectorAll('[data-xhs-expand-token]')) {
            old.removeAttribute?.('data-xhs-expand-token');
        }
        const buttons = [...document.querySelectorAll('.show-more')].filter(el =>
            visible(el) && !el.hasAttribute?.('data-xhs-expand-attempted') &&
            el.closest?.('.parent-comment') &&
            /(?:展开|更多|查看).*(?:回复|评论)|(?:回复|评论).*(?:展开|更多|查看)/.test(text(el.innerText ?? el.textContent))
        );
        if (!buttons.length) return done({...meta, found: false});
        buttons[0].setAttribute?.('data-xhs-expand-attempted', '1');
        buttons[0].setAttribute?.('data-xhs-expand-token', params.token);
        return done({...meta, found: true,
            selector: `[data-xhs-expand-token="${params.token}"]`});
    }

    if (params.action === 'verify_new') {
        const before = new Set(array(params.before_ids).map(String));
        let candidates = comments.filter(item => !before.has(item.id) &&
            item.author_id === params.account_id && text(item.content) === text(params.content));
        if (params.target_root_id) {
            candidates = candidates.filter(item => item.root_id === params.target_root_id);
            if (params.target_id !== params.target_root_id) {
                candidates = candidates.filter(item =>
                    item.reply_to_comment_id === params.target_id ||
                    (params.target_user_id && item.reply_to_user_id === params.target_user_id));
            }
        } else {
            candidates = candidates.filter(item => item.root_id === item.id &&
                !item.reply_to_comment_id);
        }
        if (candidates.length > 1) {
            return done({...meta, verified: false, ambiguous: true});
        }
        return done({...meta, verified: candidates.length === 1,
            comment: candidates[0] || null});
    }

    return done({error: '未知评论页操作'});
}
