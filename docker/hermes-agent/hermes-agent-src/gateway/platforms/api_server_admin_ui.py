from __future__ import annotations

from textwrap import dedent


def render_admin_shell() -> str:
    return dedent(
        """\
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hermes 配置控制台</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f1ea;
      --bg-panel: rgba(255, 251, 245, 0.92);
      --paper: #fffdf8;
      --line: rgba(66, 52, 36, 0.14);
      --line-strong: rgba(66, 52, 36, 0.26);
      --text: #241a11;
      --muted: #766555;
      --accent: #9a3412;
      --accent-soft: rgba(154, 52, 18, 0.1);
      --accent-strong: #7c2d12;
      --success: #166534;
      --success-soft: rgba(22, 101, 52, 0.12);
      --warning: #b45309;
      --warning-soft: rgba(180, 83, 9, 0.12);
      --danger: #b91c1c;
      --danger-soft: rgba(185, 28, 28, 0.12);
      --shadow: 0 24px 80px rgba(64, 35, 12, 0.12);
      --radius-xl: 28px;
      --radius-lg: 20px;
      --radius-md: 14px;
    }

    * { box-sizing: border-box; }

    html, body {
      margin: 0;
      min-height: 100%;
      background:
        radial-gradient(circle at top left, rgba(154, 52, 18, 0.16), transparent 28%),
        radial-gradient(circle at bottom right, rgba(180, 83, 9, 0.1), transparent 24%),
        linear-gradient(180deg, #f7f3eb 0%, #f0e7da 100%);
      color: var(--text);
      font-family: "Avenir Next", "Segoe UI", sans-serif;
    }

    body {
      padding: 24px;
    }

    .shell {
      max-width: 1460px;
      margin: 0 auto;
    }

    .locked {
      min-height: calc(100vh - 48px);
      display: grid;
      place-items: center;
    }

    .hero-card,
    .card {
      background: var(--bg-panel);
      backdrop-filter: blur(14px);
      border: 1px solid rgba(255, 255, 255, 0.5);
      box-shadow: var(--shadow);
    }

    .hero-card {
      width: min(560px, 100%);
      padding: 36px;
      border-radius: 32px;
      position: relative;
      overflow: hidden;
    }

    .hero-card::before {
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(135deg, rgba(154, 52, 18, 0.08), transparent 42%);
      pointer-events: none;
    }

    .eyebrow {
      display: inline-flex;
      padding: 6px 12px;
      border-radius: 999px;
      background: rgba(36, 26, 17, 0.06);
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }

    h1, h2, h3 {
      font-family: "Iowan Old Style", "Palatino Linotype", serif;
      margin: 0;
      letter-spacing: -0.02em;
    }

    h1 {
      font-size: clamp(38px, 5vw, 58px);
      line-height: 0.98;
      margin-top: 18px;
    }

    h2 {
      font-size: 26px;
      line-height: 1.05;
    }

    p {
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }

    .hero-copy {
      display: grid;
      gap: 16px;
      margin-bottom: 28px;
      position: relative;
      z-index: 1;
    }

    .input-grid,
    .stack,
    .form-grid,
    .button-grid,
    .layout {
      display: grid;
      gap: 14px;
    }

    .layout {
      grid-template-columns: 340px minmax(0, 1fr);
      align-items: start;
      min-height: calc(100vh - 48px);
    }

    .sidebar,
    .main {
      display: grid;
      gap: 18px;
    }

    .card {
      border-radius: var(--radius-xl);
      padding: 22px;
    }

    .sidebar .card {
      position: sticky;
      top: 24px;
    }

    label {
      display: grid;
      gap: 8px;
      font-size: 13px;
      color: var(--muted);
      font-weight: 600;
      letter-spacing: 0.01em;
    }

    input,
    select,
    button,
    textarea {
      font: inherit;
    }

    input,
    select,
    textarea {
      width: 100%;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.82);
      color: var(--text);
      border-radius: 14px;
      padding: 13px 14px;
      outline: none;
      transition: border-color 140ms ease, box-shadow 140ms ease, transform 140ms ease;
    }

    input:focus,
    select:focus,
    textarea:focus {
      border-color: rgba(154, 52, 18, 0.52);
      box-shadow: 0 0 0 4px rgba(154, 52, 18, 0.08);
      transform: translateY(-1px);
    }

    .button,
    button {
      border: 0;
      border-radius: 999px;
      padding: 12px 16px;
      cursor: pointer;
      transition: transform 140ms ease, box-shadow 140ms ease, opacity 140ms ease;
    }

    button:hover { transform: translateY(-1px); }
    button:disabled { opacity: 0.58; cursor: not-allowed; transform: none; }

    .primary {
      background: linear-gradient(135deg, var(--accent), var(--accent-strong));
      color: #fff9f3;
      box-shadow: 0 12px 28px rgba(154, 52, 18, 0.24);
    }

    .secondary {
      background: rgba(255, 255, 255, 0.72);
      color: var(--text);
      border: 1px solid var(--line);
    }

    .warning {
      background: var(--warning-soft);
      color: #8a4b00;
      border: 1px solid rgba(180, 83, 9, 0.16);
    }

    .danger {
      background: var(--danger-soft);
      color: #991b1b;
      border: 1px solid rgba(185, 28, 28, 0.16);
    }

    .button-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .muted-note {
      font-size: 13px;
      color: var(--muted);
    }

    .list {
      display: grid;
      gap: 10px;
    }

    .profile-item {
      width: 100%;
      text-align: left;
      border-radius: 18px;
      border: 1px solid transparent;
      background: rgba(255, 255, 255, 0.65);
      padding: 14px;
      display: grid;
      gap: 10px;
    }

    .profile-item.is-active {
      border-color: rgba(154, 52, 18, 0.28);
      background: rgba(255, 247, 237, 0.96);
      box-shadow: inset 0 0 0 1px rgba(154, 52, 18, 0.06);
    }

    .profile-title-row,
    .status-row,
    .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }

    .profile-name {
      font-weight: 700;
      color: var(--text);
      font-size: 15px;
    }

    .profile-meta {
      font-size: 12px;
      color: var(--muted);
      line-height: 1.5;
    }

    .badges {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .badge {
      padding: 4px 9px;
      border-radius: 999px;
      font-size: 11px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      background: rgba(36, 26, 17, 0.06);
      color: var(--muted);
    }

    .badge.default { background: rgba(180, 83, 9, 0.12); color: #8a4b00; }
    .badge.active { background: rgba(22, 101, 52, 0.14); color: var(--success); }
    .badge.safe { background: rgba(15, 23, 42, 0.08); color: #475569; }

    .status-panel {
      display: grid;
      gap: 18px;
    }

    .status-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }

    .status-cell {
      padding: 14px;
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.74);
      border: 1px solid rgba(36, 26, 17, 0.08);
      display: grid;
      gap: 6px;
    }

    .status-label {
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }

    .status-value {
      font-size: 16px;
      font-weight: 700;
      color: var(--text);
      word-break: break-word;
    }

    .operation-log {
      min-height: 220px;
      display: grid;
      gap: 10px;
      align-content: start;
    }

    .log-row {
      display: grid;
      gap: 6px;
      padding: 14px;
      border-radius: 16px;
      border: 1px solid rgba(36, 26, 17, 0.08);
      background: rgba(255, 255, 255, 0.76);
    }

    .log-row.ok { background: var(--success-soft); }
    .log-row.warn { background: var(--warning-soft); }
    .log-row.error { background: var(--danger-soft); }

    .log-time {
      font-size: 11px;
      color: var(--muted);
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }

    .empty-state {
      padding: 18px;
      border-radius: 20px;
      background: rgba(255, 255, 255, 0.55);
      border: 1px dashed rgba(36, 26, 17, 0.14);
      color: var(--muted);
      line-height: 1.6;
    }

    [hidden] { display: none !important; }

    @media (max-width: 1080px) {
      body { padding: 14px; }
      .layout { grid-template-columns: 1fr; }
      .sidebar .card { position: static; }
      .status-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }

    @media (max-width: 720px) {
      .hero-card,
      .card { padding: 18px; border-radius: 22px; }
      .button-grid,
      .status-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section id="locked-view" class="locked">
      <div class="hero-card">
        <div class="hero-copy">
          <span class="eyebrow">本地管理控制台</span>
          <h1>Hermes 配置控制台</h1>
          <p>在这里维护多套上游模型配置。Open WebUI 始终连 Hermes，本页只负责切换 Hermes 的上游 URL、密钥和模型。</p>
        </div>
        <div class="stack">
          <label>
            当前 HERMES_API_KEY
            <input id="unlock-key" type="password" autocomplete="current-password" placeholder="请输入当前 HERMES_API_KEY">
          </label>
          <button id="unlock-button" class="primary" type="button">进入控制台</button>
          <p class="muted-note" id="unlock-hint">登录后可保存多套配置档案、设置默认启动档案，并立即生效。</p>
        </div>
      </div>
    </section>

    <section id="app" class="layout" hidden>
      <aside class="sidebar">
        <div class="card stack">
          <div class="toolbar">
            <div>
              <span class="eyebrow">配置档案</span>
              <h2 style="margin-top: 10px;">上游配置库</h2>
            </div>
            <button id="new-profile" class="secondary" type="button">新建档案</button>
          </div>
          <div id="profiles-list" class="list"></div>
        </div>
      </aside>

      <main class="main">
        <section class="card status-panel" id="status-panel">
          <div class="status-row">
            <div>
              <span class="eyebrow">运行状态</span>
              <h2 style="margin-top: 10px;">当前应用状态</h2>
            </div>
            <button id="refresh-dashboard" class="secondary" type="button">刷新</button>
          </div>
          <div class="status-grid" id="status-grid"></div>
        </section>

        <section class="card stack">
          <div class="toolbar">
            <div>
              <span class="eyebrow">编辑</span>
              <h2 style="margin-top: 10px;">档案详情</h2>
            </div>
            <p class="muted-note" id="selected-profile-note">创建一套新档案，或从左侧选择已有配置。</p>
          </div>

          <form id="profile-form" class="form-grid">
            <label>
              档案名称
              <input name="name" placeholder="例如：OpenAI 生产环境">
            </label>
            <label>
              提供方类型
              <select name="provider_type">
                <option value="openai-compatible">OpenAI 兼容接口</option>
                <option value="openrouter">OpenRouter</option>
                <option value="gemini">Gemini OpenAI 接口</option>
              </select>
            </label>
            <label>
              接口地址（Base URL）
              <input name="base_url" placeholder="https://api.openai.com/v1">
            </label>
            <label>
              密钥（API Key）
              <input name="api_key" type="password" placeholder="sk-...">
            </label>
            <label>
              模型名称
              <input name="model_name" placeholder="gpt-4.1">
            </label>
          </form>

          <div class="button-grid">
            <button id="test-connection" class="secondary" type="button">测试连接</button>
            <button id="save-profile" class="primary" type="button">保存档案</button>
            <button id="set-default" class="secondary" type="button">设为默认</button>
            <button id="apply-profile" class="primary" type="button">立即应用</button>
            <button id="delete-profile" class="warning" type="button">删除档案</button>
            <button id="rollback-runtime" class="danger" type="button">回滚上一版运行配置</button>
          </div>

          <p class="muted-note">模型名称先手填；点击“测试连接”会返回该上游可见的模型列表，方便你核对是否能选到模型。</p>
        </section>

        <section class="card operation-log" id="operation-log"></section>
      </main>
    </section>
  </div>

  <script>
    const state = {
      profiles: [],
      selectedProfileId: null,
      defaultProfileId: null,
      activeProfileId: null,
      lastKnownGoodProfileId: null,
      status: { phase: 'locked' },
    };

    const lockedView = document.getElementById('locked-view');
    const appView = document.getElementById('app');
    const unlockButton = document.getElementById('unlock-button');
    const unlockKeyInput = document.getElementById('unlock-key');
    const profilesList = document.getElementById('profiles-list');
    const profileForm = document.getElementById('profile-form');
    const statusGrid = document.getElementById('status-grid');
    const operationLog = document.getElementById('operation-log');
    const selectedProfileNote = document.getElementById('selected-profile-note');

    const providerTypeLabels = {
      'openai-compatible': 'OpenAI 兼容接口',
      openrouter: 'OpenRouter',
      gemini: 'Gemini OpenAI 接口',
    };

    const phaseLabels = {
      locked: '未登录',
      unknown: '未知',
      idle: '空闲',
      pending_verification: '待验证',
      writing_runtime_config: '写入运行配置',
      syncing_open_webui: '同步 Open WebUI',
      restarting_open_webui: '重启 Open WebUI',
      verifying_open_webui: '验证 Open WebUI',
      ready: '已就绪',
      failed: '失败',
      probe_failed: '探测失败',
      restored: '已恢复',
      rollback_complete: '回滚完成',
      restore_failed: '恢复失败',
    };

    function escapeHtml(value) {
      return String(value || '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }

    async function api(path, options = {}) {
      const headers = { ...(options.headers || {}) };
      let body = options.body;
      if (body !== undefined && body !== null && typeof body !== 'string') {
        headers['Content-Type'] = headers['Content-Type'] || 'application/json';
        body = JSON.stringify(body);
      }
      const response = await fetch(path, {
        credentials: 'same-origin',
        ...options,
        headers,
        body,
      });
      const contentType = response.headers.get('content-type') || '';
      const data = contentType.includes('application/json') ? await response.json() : await response.text();
      return { ok: response.ok, status: response.status, data };
    }

    function nowStamp() {
      return new Date().toLocaleTimeString('zh-CN');
    }

    function appendLog(message, tone = 'info') {
      const row = document.createElement('div');
      row.className = `log-row ${tone === 'info' ? '' : tone}`.trim();
      row.innerHTML = `<div class="log-time">${nowStamp()}</div><div>${escapeHtml(message)}</div>`;
      operationLog.prepend(row);
      while (operationLog.children.length > 8) {
        operationLog.removeChild(operationLog.lastChild);
      }
    }

    function formValues() {
      const form = new FormData(profileForm);
      return {
        name: String(form.get('name') || '').trim(),
        provider_type: String(form.get('provider_type') || 'openai-compatible').trim(),
        base_url: String(form.get('base_url') || '').trim(),
        api_key: String(form.get('api_key') || '').trim(),
        model_name: String(form.get('model_name') || '').trim(),
      };
    }

    function formatProviderType(value) {
      return providerTypeLabels[value] || String(value || '');
    }

    function formatPhase(value) {
      return phaseLabels[value] || String(value || '空闲');
    }

    function formatProfileRef(profileId) {
      const profile = state.profiles.find((item) => item.id === profileId);
      return profile?.name || profileId || '无';
    }

    function setFormValues(profile) {
      profileForm.elements.name.value = profile?.name || '';
      profileForm.elements.provider_type.value = profile?.provider_type || 'openai-compatible';
      profileForm.elements.base_url.value = profile?.base_url || '';
      profileForm.elements.api_key.value = '';
      profileForm.elements.api_key.placeholder = state.selectedProfileId ? '留空则保留当前密钥' : 'sk-...';
      profileForm.elements.model_name.value = profile?.model_name || '';
      selectedProfileNote.textContent = state.selectedProfileId
        ? `正在编辑：${profile.name}`
        : '创建一套新档案，或从左侧选择已有配置。';
    }

    function currentProfile() {
      return state.profiles.find((profile) => profile.id === state.selectedProfileId) || null;
    }

    function resetComposer() {
      state.selectedProfileId = null;
      setFormValues(null);
      renderProfiles();
    }

    function renderProfiles() {
      if (!state.profiles.length) {
        profilesList.innerHTML = '<div class="empty-state">还没有保存的配置档案。先在右侧填一套 Base URL、API Key 和模型名，然后点“保存档案”。</div>';
        return;
      }

      profilesList.innerHTML = state.profiles.map((profile) => {
        const badges = [];
        if (profile.id === state.defaultProfileId) badges.push('<span class="badge default">默认</span>');
        if (profile.id === state.activeProfileId) badges.push('<span class="badge active">当前生效</span>');
        if (profile.id === state.lastKnownGoodProfileId) badges.push('<span class="badge safe">上次可用</span>');
        const activeClass = profile.id === state.selectedProfileId ? 'is-active' : '';
        return `
          <button class="profile-item ${activeClass}" type="button" data-profile-id="${escapeHtml(profile.id)}">
            <div class="profile-title-row">
              <div class="profile-name">${escapeHtml(profile.name || '未命名档案')}</div>
              <div class="badges">${badges.join('')}</div>
            </div>
            <div class="profile-meta">
              <div>${escapeHtml(formatProviderType(profile.provider_type || 'openai-compatible'))}</div>
              <div>${escapeHtml(profile.base_url || '')}</div>
              <div>模型 · ${escapeHtml(profile.model_name || '')}</div>
              <div>密钥 · ${escapeHtml(profile.api_key_masked || '未设置')}</div>
            </div>
          </button>
        `;
      }).join('');

      for (const button of profilesList.querySelectorAll('[data-profile-id]')) {
        button.addEventListener('click', () => {
          state.selectedProfileId = button.getAttribute('data-profile-id');
          setFormValues(currentProfile());
          renderProfiles();
        });
      }
    }

    function renderStatus() {
      const status = state.status || { phase: 'unknown' };
      const cells = [
        ['阶段', formatPhase(status.phase || 'idle')],
        ['档案', formatProfileRef(status.profile_id || state.activeProfileId)],
        ['提供方', status.provider ? formatProviderType(status.provider) : '未应用'],
        ['模型', status.model || '未选择'],
      ];
      if (status.base_url) {
        cells.push(['接口地址（Base URL）', status.base_url]);
      }
      if (status.error) {
        cells.push(['错误', status.error]);
      }

      statusGrid.innerHTML = cells.map(([label, value]) => `
        <div class="status-cell">
          <div class="status-label">${escapeHtml(label)}</div>
          <div class="status-value">${escapeHtml(value)}</div>
        </div>
      `).join('');
    }

    async function refreshProfiles(preserveSelection = true) {
      const response = await api('/api/admin/profiles');
      if (!response.ok) {
        if (response.status === 401) {
          showLocked();
          return false;
        }
        appendLog(`载入配置档案失败：${JSON.stringify(response.data)}`, 'error');
        return false;
      }
      state.profiles = response.data.profiles || [];
      state.defaultProfileId = response.data.default_profile_id || null;
      state.activeProfileId = response.data.active_profile_id || null;
      state.lastKnownGoodProfileId = response.data.last_known_good_profile_id || null;
      if (!preserveSelection || !state.profiles.some((profile) => profile.id === state.selectedProfileId)) {
        state.selectedProfileId = state.profiles[0]?.id || null;
      }
      setFormValues(currentProfile());
      renderProfiles();
      return true;
    }

    async function refreshStatus() {
      const response = await api('/api/admin/status');
      if (!response.ok) {
        if (response.status === 401) {
          showLocked();
          return false;
        }
        appendLog(`载入状态失败：${JSON.stringify(response.data)}`, 'error');
        return false;
      }
      state.status = response.data || { phase: 'idle' };
      renderStatus();
      return true;
    }

    async function refreshDashboard() {
      await Promise.all([refreshProfiles(true), refreshStatus()]);
    }

    function showApp() {
      lockedView.hidden = true;
      appView.hidden = false;
    }

    function showLocked() {
      appView.hidden = true;
      lockedView.hidden = false;
    }

    async function unlockConsole() {
      const submitted = unlockKeyInput.value.trim();
      if (!submitted) {
        appendLog('先输入当前 HERMES_API_KEY。', 'warn');
        return;
      }
      const response = await api('/api/admin/auth', { method: 'POST', body: { api_key: submitted } });
      if (!response.ok) {
        appendLog('登录失败：HERMES_API_KEY 不匹配。', 'error');
        return;
      }
      showApp();
      appendLog('控制台已解锁。', 'ok');
      await refreshDashboard();
    }

    async function saveProfile() {
      const payload = formValues();
      if (!payload.name || !payload.base_url || !payload.model_name) {
        appendLog('保存前请填完整的名称、Base URL 和模型名。', 'warn');
        return;
      }
      const editing = currentProfile();
      if (editing && !payload.api_key) {
        delete payload.api_key;
      }
      if (!editing && !payload.api_key) {
        appendLog('新建档案时必须填写 API Key。', 'warn');
        return;
      }

      const response = await api(
        editing ? `/api/admin/profiles/${editing.id}` : '/api/admin/profiles',
        { method: editing ? 'PATCH' : 'POST', body: payload },
      );
      if (!response.ok) {
        appendLog(`保存失败：${JSON.stringify(response.data)}`, 'error');
        return;
      }
      if (!editing) {
        state.selectedProfileId = response.data.id;
      }
      await refreshProfiles(true);
      appendLog(editing ? '档案已更新。' : '档案已创建。', 'ok');
    }

    async function testConnection() {
      const editing = currentProfile();
      const response = editing
        ? await api(`/api/admin/profiles/${editing.id}/test`, { method: 'POST' })
        : await api('/api/admin/test-connection', { method: 'POST', body: formValues() });
      if (!response.ok) {
        appendLog(`连通性测试失败：${JSON.stringify(response.data)}`, 'error');
        return;
      }
      const models = (response.data.model_ids || []).slice(0, 8).join(', ') || '未返回模型列表';
      appendLog(`连通性测试成功。可见模型：${models}`, 'ok');
      await refreshProfiles(true);
    }

    async function setDefaultProfile() {
      const editing = currentProfile();
      if (!editing) {
        appendLog('请先保存并选中一个档案。', 'warn');
        return;
      }
      const response = await api(`/api/admin/profiles/${editing.id}/default`, { method: 'POST' });
      if (!response.ok) {
        appendLog(`设置默认失败：${JSON.stringify(response.data)}`, 'error');
        return;
      }
      await refreshProfiles(true);
      appendLog('默认启动档案已更新。', 'ok');
    }

    async function applyProfile() {
      const editing = currentProfile();
      if (!editing) {
        appendLog('“立即应用”只能作用在已保存的档案上。', 'warn');
        return;
      }
      const response = await api(`/api/admin/profiles/${editing.id}/activate`, { method: 'POST' });
      if (!response.ok) {
        appendLog(`应用失败：${JSON.stringify(response.data)}`, 'error');
        await refreshStatus();
        return;
      }
      appendLog('档案已提交应用，正在重启服务并执行健康检查。', 'ok');
      await refreshDashboard();
    }

    async function deleteProfile() {
      const editing = currentProfile();
      if (!editing) {
        appendLog('当前没有选中的档案。', 'warn');
        return;
      }
      const response = await api(`/api/admin/profiles/${editing.id}`, { method: 'DELETE' });
      if (!response.ok) {
        appendLog(`删除失败：${JSON.stringify(response.data)}`, 'error');
        return;
      }
      state.selectedProfileId = null;
      await refreshProfiles(false);
      appendLog('档案已删除。', 'ok');
    }

    async function rollbackRuntime() {
      const response = await api('/api/admin/restore', { method: 'POST' });
      if (!response.ok) {
        appendLog(`回滚失败：${JSON.stringify(response.data)}`, 'error');
        return;
      }
      await refreshDashboard();
      appendLog('已请求恢复上一份运行时配置。', 'warn');
    }

    document.getElementById('new-profile').addEventListener('click', () => {
      resetComposer();
      appendLog('已切换到新建模式。', 'info');
    });
    document.getElementById('refresh-dashboard').addEventListener('click', refreshDashboard);
    document.getElementById('save-profile').addEventListener('click', saveProfile);
    document.getElementById('test-connection').addEventListener('click', testConnection);
    document.getElementById('set-default').addEventListener('click', setDefaultProfile);
    document.getElementById('apply-profile').addEventListener('click', applyProfile);
    document.getElementById('delete-profile').addEventListener('click', deleteProfile);
    document.getElementById('rollback-runtime').addEventListener('click', rollbackRuntime);
    unlockButton.addEventListener('click', unlockConsole);
    unlockKeyInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        unlockConsole();
      }
    });

    async function bootstrap() {
      const statusResponse = await api('/api/admin/status');
      if (statusResponse.ok) {
        showApp();
        state.status = statusResponse.data || { phase: 'idle' };
        renderStatus();
        await refreshProfiles(true);
      } else {
        renderStatus();
        showLocked();
      }
      appendLog('控制台就绪。', 'info');
      window.setInterval(refreshStatus, 5000);
    }

    bootstrap();
  </script>
</body>
</html>
"""
    )
