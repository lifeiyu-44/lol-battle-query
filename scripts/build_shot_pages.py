# -*- coding: utf-8 -*-
"""生成两个停留在加载中状态的临时页面（截图验证加载特效用，跑完即删）。"""
from pathlib import Path

root = Path(__file__).resolve().parent.parent
mock = (root / "test" / "mock.html").read_text(encoding="utf-8")


def build(driver: str, name: str):
    markup = mock[: mock.rindex("</body>")] + driver + "</body>\n</html>"
    target = root / "test" / name
    target.write_text(markup, encoding="utf-8")
    print("built", target.name)


# 英雄弹窗：扫描挂起，保持加载条可见
build("""
<script>
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  $('queryInput').value = '截图玩家';
  await doSearch();
  state.historySource = 'sgp'; state.historyFetchedAt = Date.now();
  window.pywebview.api.get_analysis_matches = () => new Promise(() => {});
  HeroAnalysis.open({puuid:'abc', name:'截图玩家'}, 1, '安妮');
  await sleep(400);
})();
</script>
""", "_shot_hero_tmp.html")

# 查询页：第二页挂起，保持批量加载条可见
build("""
<script>
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const api = window.pywebview.api;
  const fast = api.get_matches;
  api.get_matches = (puuid, beg, count) => beg >= 20
    ? new Promise(() => {})
    : fast(puuid, beg, count);
  document.querySelector('#historyLimit').value = '100';
  $('queryInput').value = '截图玩家';
  doSearch();  // 故意不等待：第二页请求挂起，页面停留在批量加载状态
  for (let i = 0; i < 100 && $('loadingAll').hidden; i++) await sleep(20);
  // mock.html 的 loadingAll 是空壳，注入与 index.html 相同的内部结构
  $('loadingAll').innerHTML = '<span class="spinner" aria-hidden="true"></span><div class="load-body"><b id="loadingText"></b><div class="load-track"><i id="loadingFill"></i></div></div>';
  renderAll();
  // 无头截图不支持滚动：临时隐藏加载条上方区块，让它顶到可视区顶部
  ['.page-heading', 'section[data-page="game"]', '.query-panel', '.connection-help',
   '#playerBar', '#summaryCards', '#damageSummary', '#listHead', '#historyProgress',
   '#augmentAnalysis', '.rating-rules', '#matchList'].forEach(sel => {
    const el = document.querySelector(sel); if (el) el.style.display = 'none';
  });
  await sleep(400);
})();
</script>
""", "_shot_query_tmp.html")
