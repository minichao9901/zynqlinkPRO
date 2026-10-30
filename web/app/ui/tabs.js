/**
 * 顶部标签页的切换。支持 #serial / #terminal / #rtt / #flash / #gen 直达（也方便做演示链接）。
 * 不记忆上次标签：每次打开（URL 上没有 #hash）都从「烧录器」开始——2026-10-18 用户明确要求。
 */
export function initTabs(onSwitch){
  const tabs = [...document.querySelectorAll('#tabs .tab')];
  const panels = [...document.querySelectorAll('.panel')];
  const names = tabs.map(t => t.dataset.tab);   // 从 DOM 取，别再手写一份（加页时容易漏）
  function show(name, push = true){
    for (const t of tabs){
      const active=t.dataset.tab===name;
      t.classList.toggle('active',active);
      if(active)t.setAttribute('aria-current','page');else t.removeAttribute('aria-current');
    }
    for (const p of panels) p.classList.toggle('active', p.id === 'tab-' + name);
    if (push) try { history.replaceState(null, '', '#' + name); } catch {}
    onSwitch?.(name);
  }
  for (const t of tabs) t.addEventListener('click', () => show(t.dataset.tab));
  const hash = (location.hash || '').replace('#', '');
  show(names.includes(hash) ? hash : 'flash', false);
  window.addEventListener('hashchange', () => {
    const h = (location.hash || '').replace('#', '');
    if (names.includes(h)) show(h, false);
  });
  return { show };
}
