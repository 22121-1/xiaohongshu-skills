const test = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');
const script = readFileSync(join(__dirname, '../scripts/xhs/search_filters.js'), 'utf8');
function fixture({stale = false, empty = false, same = false, missing = false} = {}) {
    const state = {state: 'success', feeds: [{id: 'old'}], searchContext: {keyword: 'test', searchId: 'a'}};
    const clicked = [];
    let opened = false;
    function group(label, names) {
        const options = names.map((text, i) => ({textContent: text, active: i === 0,
            classList: {contains(){return options[i].active}},
            click() {
                options.forEach(o => o.active = false);this.active = true;clicked.push([label, text]);
                if (!stale) {
                    state.state = 'loading';state.feeds = [];
                    setTimeout(() => {state.state = 'success';state.feeds = empty ? [] : [{id: same ? 'old' : text}];}, 1);
                }
            }
        }));
        return {querySelector: () => ({textContent: label}), querySelectorAll: () => options};
    }
    // Reversed groups and duplicate words outside the panel must not affect selection.
    const groups = [group('笔记类型', ['不限', '视频', '图文']), group('排序依据', ['综合', '最新'])];
    const document = {querySelectorAll: selector => opened && selector === 'div.filter-panel div.filters' ? (missing ? groups.slice(0,1) : groups) : [],
        querySelector: selector => selector === 'div.filter' ? {click(){opened = true}} : null};
    const run = (filters = [['排序依据','最新'], ['笔记类型','图文']]) => vm.runInNewContext(`(${script})(params)`, {
        params: {filters, keyword: 'test', timeout_ms: 350}, document,
        window: {__INITIAL_STATE__: {search: state}}, location: {pathname: '/search_result'}, setTimeout, Date
    });
    return {run, clicked, state};
}
test('filter groups are located by label, not array order', async () => {
    const f = fixture();assert.equal((await f.run()).verified, true);
    assert.deepEqual(f.clicked, [['排序依据','最新'], ['笔记类型','图文']]);
});
test('same IDs after an observed loading cycle are valid', async () => {
    assert.equal((await fixture({same:true}).run()).verified, true);
});
test('a loaded empty result is valid', async () => {
    assert.equal((await fixture({empty:true}).run()).verified, true);
});
test('selected but stale result must fail rather than return old notes', async () => {
    await assert.rejects(fixture({stale:true}).run(), /未确认完成/);
});
test('missing named group cannot fall back to a different group', async () => {
    await assert.rejects(fixture({missing:true}).run(), /选项不存在/);
});

test('already selected options cannot approve a stale search keyword', async () => {
    const f=fixture();f.state.searchContext.keyword='old';
    await assert.rejects(f.run([['排序依据','综合']]), /未确认完成/);
});
