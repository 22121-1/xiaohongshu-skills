async (params) => {
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const unwrap = value => value?.value ?? value?._value ?? value;
    const deadline = Date.now() + (params.timeout_ms ?? 60000);
    const groups = () => [...document.querySelectorAll('div.filter-panel div.filters')];
    const option = ([label, text]) => {
        const group = groups().find(el => el.querySelector(':scope > span')?.textContent.trim() === label);
        return group && [...group.querySelectorAll('div.tags')].find(el => el.textContent.trim() === text);
    };
    const snapshot = () => {
        if (location.pathname !== '/search_result') throw new Error('搜索页已变化，未继续筛选');
        const search = window.__INITIAL_STATE__?.search;
        const feeds = unwrap(search?.feeds);
        const context = unwrap(search?.searchContext) || {};
        return {state: unwrap(search?.state), keyword: context.keyword,
            signature: JSON.stringify([context.searchId, Array.isArray(feeds) ? feeds.map(f => f.id) : null]),
            loaded: Array.isArray(feeds)};
    };
    const wait = async predicate => {
        while (Date.now() < deadline) {
            if (predicate()) return;
            await sleep(100);
        }
        throw new Error('筛选未确认完成：面板、选中状态或结果刷新超时，未返回旧结果');
    };
    await wait(() => {
        const current = snapshot();
        return current.loaded && current.state === 'success' &&
            (!params.keyword || current.keyword === params.keyword);
    });
    const button = document.querySelector('div.filter');
    if (!button) throw new Error('筛选按钮不存在');
    // 当前网页通过 click 展开；两个面板类名同时存在，按外层面板限定作用域。
    if (!groups().length) button.click();
    await wait(() => groups().length > 0);
    for (const item of params.filters) {
        const target = option(item);
        if (!target) throw new Error(`筛选选项不存在：${item.join(' / ')}`);
        if (target.classList.contains('active')) continue;
        const before = snapshot();
        target.click();
        let loadingSeen = false;
        await wait(() => {
            const current = snapshot();
            loadingSeen ||= current.state === 'loading';
            if (['error', 'failed', 'fail'].includes(current.state)) throw new Error('筛选搜索加载失败');
            if (params.keyword && current.state === 'success' && current.keyword !== params.keyword) {
                throw new Error('搜索关键词发生变化，未返回其他搜索的结果');
            }
            return option(item)?.classList.contains('active') && current.loaded &&
                current.state === 'success' && (loadingSeen || current.signature !== before.signature);
        });
    }
    if (!params.filters.every(item => option(item)?.classList.contains('active'))) {
        throw new Error('筛选组合未全部生效，未返回结果');
    }
    if (params.keyword && snapshot().keyword !== params.keyword) {
        throw new Error('搜索关键词未确认，未返回结果');
    }
    return {verified: true};
}
