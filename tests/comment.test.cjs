// Execute the shipped comment DOM contract against isolated state/DOM fixtures.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../scripts/xhs/comment.js'), 'utf8');
const FEED = 'a'.repeat(24);
const ACCOUNT = 'b'.repeat(24);
const ROOT = 'c'.repeat(24);
const CHILD = 'd'.repeat(24);

function userNode(comment, userId, name = '') {
    return {
        innerText: name, textContent: name,
        getAttribute: key => key === 'data-user-id' ? userId : null,
        closest: selector => selector === '.comment-item' ? comment : null,
    };
}

function commentElement(id, userId, content) {
    const comment = {
        id: `comment-${id}`, floor: null, scrolled: false,
        getAttribute: () => null,
        closest(selector) {
            if (selector === '.comment-item') return this;
            if (selector === '.parent-comment') return this.floor;
            return null;
        },
        scrollIntoView() { this.scrolled = true; },
    };
    const avatar = userNode(comment, userId);
    const author = userNode(comment, userId, `用户-${userId[0]}`);
    const body = {innerText: content, textContent: content,
        closest: selector => selector === '.comment-item' ? comment : null};
    comment.querySelectorAll = selector => {
        if (selector === '[data-user-id]') return [avatar, author];
        if (selector === '.author .name[data-user-id]') return [author];
        if (selector.startsWith('.note-text')) return [body];
        return [];
    };
    return comment;
}

function floor(...items) {
    const value = {querySelectorAll: selector => selector === '.comment-item' ? items : []};
    for (const item of items) item.floor = value;
    return value;
}

function expandButton(label, owner) {
    const attrs = {};
    return {
        innerText: label, textContent: label,
        getBoundingClientRect: () => ({width: 100, height: 20}),
        closest: selector => selector === '.parent-comment' ? owner : null,
        hasAttribute: key => Object.hasOwn(attrs, key),
        setAttribute: (key, value) => { attrs[key] = value; },
        removeAttribute: key => { delete attrs[key]; },
        attrs,
    };
}

function rawComment(id, userId, content, subComments = [], targetComment = null) {
    return {id, content, userInfo: {userId, nickname: `用户-${userId[0]}`},
        subComments, ...(targetComment ? {targetComment} : {})};
}

function fixture({pathName = `/explore/${FEED}`, comments, elements, buttons = [], editor = null} = {}) {
    const rootRaw = rawComment(ROOT, 'e'.repeat(24), '一级评论', [
        rawComment(CHILD, 'f'.repeat(24), '楼中楼', [],
            {id: ROOT, userInfo: {userId: 'e'.repeat(24)}}),
    ]);
    const state = {note: {noteDetailMap: {[FEED]: {note: {noteId: FEED},
        comments: {list: comments || [rootRaw]}}}},
        user: {loggedIn: {_value: true}, userInfo: {_value: {
            userId: ACCOUNT, nickname: '当前账号', guest: false,
        }}}};
    const rootEl = commentElement(ROOT, 'e'.repeat(24), '一级评论');
    const childEl = commentElement(CHILD, 'f'.repeat(24), '楼中楼');
    floor(rootEl, childEl);
    const dom = elements || [rootEl, childEl];
    const document = {querySelectorAll(selector) {
        if (selector === '.comment-item') return dom;
        if (selector === '.show-more') return buttons;
        if (selector === '.engage-bar.active .reply-content') return editor ? [editor] : [];
        if (selector === '[data-xhs-expand-token]') {
            return buttons.filter(button => button.hasAttribute('data-xhs-expand-token'));
        }
        return [];
    }};
    const context = {window: {__INITIAL_STATE__: state}, document,
        location: {origin: 'https://www.xiaohongshu.com', pathname: pathName},
        getComputedStyle: () => ({display: 'block', visibility: 'visible'})};
    const run = params => JSON.parse(vm.runInNewContext(
        `(${source})(${JSON.stringify({feed_id: FEED, ...params})})`, context));
    return {run, state, dom};
}

function replyEditor(author, content) {
    const child = value => ({innerText: value, textContent: value});
    return {getBoundingClientRect: () => ({width: 500, height: 80}),
        querySelector: selector => selector === '.reply' ? child(`回复 ${author}`) :
            selector === '.content' ? child(content) : null};
}

test('snapshot binds both URL and exact note state key', () => {
    assert.equal(fixture().run({action: 'snapshot'}).ready, true);
    assert.match(fixture({pathName: `/explore/${'9'.repeat(24)}`})
        .run({action: 'snapshot'}).error, /URL/);
});

test('state keeps exact content and targetComment for nested replies', () => {
    const item = fixture().run({action: 'snapshot'}).comments.find(row => row.id === CHILD);
    assert.equal(item.content, '楼中楼');
    assert.equal(item.root_id, ROOT);
    assert.equal(item.reply_to_comment_id, ROOT);
    assert.equal(item.reply_to_user_id, 'e'.repeat(24));
});

test('comment_id miss never falls back to matching user_id', () => {
    const result = fixture().run({action: 'lookup', comment_id: '9'.repeat(24),
        user_id: 'e'.repeat(24)});
    assert.equal(result.found, false);
});

test('user-only lookup refuses ambiguous targets', () => {
    const one = commentElement('1'.repeat(24), 'e'.repeat(24), '一');
    const two = commentElement('2'.repeat(24), 'e'.repeat(24), '二');
    floor(one, two);
    assert.match(fixture({elements: [one, two]}).run({action: 'lookup',
        user_id: 'e'.repeat(24)}).error, /不唯一/);
});

test('lookup returns the exact nested comment and its root floor', () => {
    const result = fixture().run({action: 'lookup', comment_id: CHILD});
    assert.equal(result.target.id, CHILD);
    assert.equal(result.target.root_id, ROOT);
});

test('reply editor must expose the bound author and target content', () => {
    const params = {action: 'reply_binding', target_author: '用户-e',
        target_content: '一级评论'};
    assert.equal(fixture({editor: replyEditor('用户-e', '一级评论')}).run(params).bound, true);
    assert.equal(fixture({editor: replyEditor('另一用户', '一级评论')}).run(params).bound, false);
});

test('post editor refuses a stale reply target', () => {
    assert.equal(fixture().run({action: 'post_binding'}).bound, true);
    assert.equal(fixture({editor: replyEditor('用户-e', '一级评论')})
        .run({action: 'post_binding'}).bound, false);
});

test('only a reply expansion control is marked once', () => {
    const owner = {};
    const reply = expandButton('展开 20 条回复', owner);
    const unrelated = expandButton('展开正文', owner);
    const f = fixture({buttons: [unrelated, reply]});
    const result = f.run({action: 'mark_expand', token: 'fixture'});
    assert.equal(result.found, true);
    assert.equal(reply.attrs['data-xhs-expand-token'], 'fixture');
    assert.equal(unrelated.attrs['data-xhs-expand-token'], undefined);
    assert.equal(f.run({action: 'mark_expand', token: 'again'}).found, false);
});

test('old same-content comment cannot satisfy post-submit verification', () => {
    const old = rawComment('1'.repeat(24), ACCOUNT, '相同正文');
    const f = fixture({comments: [old]});
    const result = f.run({action: 'verify_new', before_ids: [old.id],
        account_id: ACCOUNT, content: '相同正文'});
    assert.equal(result.verified, false);
});

test('new post needs new ID, current account and exact content', () => {
    const old = rawComment('1'.repeat(24), ACCOUNT, '相同正文');
    const fresh = rawComment('2'.repeat(24), ACCOUNT, '相同正文');
    const result = fixture({comments: [old, fresh]}).run({action: 'verify_new',
        before_ids: [old.id], account_id: ACCOUNT, content: '相同正文'});
    assert.equal(result.verified, true);
    assert.equal(result.comment.id, fresh.id);
});

test('new sub-comment cannot satisfy top-level post verification', () => {
    const accidentalReply = rawComment('2'.repeat(24), ACCOUNT, '相同正文', [],
        {id: ROOT, userInfo: {userId: 'e'.repeat(24)}});
    const root = rawComment(ROOT, 'e'.repeat(24), '一级评论', [accidentalReply]);
    const result = fixture({comments: [root]}).run({action: 'verify_new',
        before_ids: [ROOT], account_id: ACCOUNT, content: '相同正文'});
    assert.equal(result.verified, false);
});

test('nested reply must identify the direct target, not only the same floor', () => {
    const target = rawComment(CHILD, 'f'.repeat(24), '目标', [],
        {id: ROOT, userInfo: {userId: 'e'.repeat(24)}});
    const wrong = rawComment('1'.repeat(24), ACCOUNT, '回复正文', [],
        {id: ROOT, userInfo: {userId: 'e'.repeat(24)}});
    const right = rawComment('2'.repeat(24), ACCOUNT, '回复正文', [],
        {id: CHILD, userInfo: {userId: 'f'.repeat(24)}});
    const root = rawComment(ROOT, 'e'.repeat(24), '一级评论', [target, wrong]);
    const base = {action: 'verify_new', before_ids: [ROOT, CHILD], account_id: ACCOUNT,
        content: '回复正文', target_id: CHILD, target_root_id: ROOT,
        target_user_id: 'f'.repeat(24)};
    assert.equal(fixture({comments: [root]}).run(base).verified, false);
    root.subComments.push(right);
    assert.equal(fixture({comments: [root]}).run(base).verified, true);
});
