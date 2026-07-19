/** 同步自定义 tabBar 选中态（兼容 Skyline 异步 getTabBar）。 */

const TAB_BY_ROUTE = {
  'pages/collect/collect': 'collect',
  'pages/knowledge/knowledge': 'knowledge',
  'pages/chat/chat': 'chat',
};

function syncTabBar(page, value) {
  if (typeof page.getTabBar !== 'function') return;
  const bar = page.getTabBar();
  if (bar && typeof bar.setData === 'function') {
    bar.setData({ value });
    return;
  }
  page.getTabBar((tabBar) => {
    if (tabBar && typeof tabBar.setData === 'function') {
      tabBar.setData({ value });
    }
  });
}

function syncTabBarForRoute(page) {
  const route = (page.route || '').replace(/^\//, '');
  const value = TAB_BY_ROUTE[route];
  if (value) syncTabBar(page, value);
}

module.exports = { syncTabBar, syncTabBarForRoute };
