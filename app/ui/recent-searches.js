"use strict";
const RecentSearches = (() => {
  let players=[], current=null, busy=false;
  const fullId = p => p.name+(p.tagLine?'#'+p.tagLine:'');
  function render() {
    const self=$('currentAccount');
    self.textContent=current ? `我的战绩 · ${fullId(current)}` : '查询当前登录账号';
    self.title=self.textContent; self.disabled=busy||state.loading||state.loadingAll||state.pageLoading;
    $('recentCount').textContent=`历史搜索 · ${players.length} / 20`;
    $('clearSearchHistory').disabled=!players.length;
    const body=$('recentPlayers');body.replaceChildren();
    if(!players.length) {body.textContent='还没有搜索记录，成功查询后自动保存到本机。';return;}
    for(const p of players) {
      const chip=document.createElement('div');chip.className='recent-player';
      const select=document.createElement('button');select.className='ghost recent-select';select.textContent=fullId(p);select.title=`查询 ${fullId(p)}`;
      select.disabled=busy||state.loading||state.loadingAll||state.pageLoading;
      select.addEventListener('click',()=>{
        if(state.loading||state.loadingAll||state.pageLoading)return;
        $('queryInput').value=fullId(p);
        doSearch({...p,refreshIdentity:true});
      });
      const remove=document.createElement('button');remove.className='ghost recent-remove';remove.textContent='×';remove.title=`删除 ${fullId(p)} 的搜索记录`;remove.setAttribute('aria-label',remove.title);
      remove.addEventListener('click',()=>removeHistory(p.puuid));
      chip.append(select,remove);body.appendChild(chip);
    }
  }
  async function removeHistory(puuid=null) {
    try {const r=await window.pywebview.api.remove_search(puuid);if(!r.ok)throw new Error(r.error);players=r.players;render();}
    catch(e){toast(e.message||'删除搜索历史失败');}
  }
  async function remember(player) {
    try {const r=await window.pywebview.api.remember_search(player);if(!r.ok)throw new Error(r.error);players=r.players;render();}
    catch(e){toast(e.message||'保存搜索历史失败，本次查询不受影响');}
  }
  async function showSelf() {
    if(busy||state.loading||state.loadingAll||state.pageLoading)return;
    busy=true;render();
    try {
      const r=await window.pywebview.api.get_status();
      if(!r.ok||!r.me?.puuid)throw new Error(r.error||'请先登录英雄联盟客户端');
      current=r.me;$('queryInput').value=fullId(current);
      await doSearch(current);
    } catch(e){toast(e.message||'读取当前账号失败');}
    finally{busy=false;render();}
  }
  function setCurrent(player) {current=player?.puuid?player:null;render();}
  async function load() {
    try {const r=await window.pywebview.api.get_search_history();if(!r.ok)throw new Error(r.error);players=r.players;render();}
    catch(e){$('recentPlayers').textContent=e.message||'历史搜索暂不可用';}
  }
  function init() {
    const row=document.createElement('section');row.className='account-shortcuts';
    row.innerHTML='<button id="currentAccount" class="ghost">查询当前登录账号</button><details id="recentSearches"><summary id="recentCount">历史搜索 · 0 / 20</summary><div class="recent-toolbar"><span>按最近查询排序 · 重启后保留</span><button id="clearSearchHistory" class="ghost">清空记录</button></div><div id="recentPlayers" class="recent-players">读取中…</div></details>';
    document.querySelector('.search-row').insertAdjacentElement('afterend',row);
    $('currentAccount').addEventListener('click',showSelf);
    $('clearSearchHistory').addEventListener('click',()=>removeHistory());
    load();
  }
  return {init,render,setCurrent,remember,load};
})();
