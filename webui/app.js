// ── State ──
const state = {
  token: localStorage.getItem('ha_token') || '',
  userName: localStorage.getItem('ha_user_name') || '',
  userRole: localStorage.getItem('ha_user_role') || '',
  userId: localStorage.getItem('ha_user_id') || '',
  apiUrl: localStorage.getItem('ha_api_url') || '',
  activePanel: 'chat',
  conversations: [],
  currentConversationId: null,
  messages: [],
  isStreaming: false,
  abortController: null,
};

// ── DOM refs ──
const $ = (sel) => document.querySelector(sel);
const registerView = $('#register-view');
const mainView = $('#main-view');
const settingsModal = $('#settings-modal');
const messagesEl = $('#messages');
const emptyState = $('#empty-state');
const messageInput = $('#message-input');
const chatTitle = $('#chat-title');
const streamingIndicator = $('#streaming-indicator');
const conversationList = $('#conversation-list');
const userInfo = $('#user-info');
const deleteConvBtn = $('#delete-conv-btn');
const apiEndpointDisplay = $('#api-endpoint-display');

// ── Init ──
function init() {
  if (!state.apiUrl || (window.location.protocol === 'https:' && state.apiUrl.startsWith('http://'))) {
    state.apiUrl = window.location.origin;
    localStorage.setItem('ha_api_url', state.apiUrl);
  }

  if (state.token) {
    showMainView();
  } else {
    showRegisterView();
  }
}

function showRegisterView() {
  registerView.classList.remove('hidden');
  mainView.classList.add('hidden');
  if (state.apiUrl) {
    $('#api-url-input').value = state.apiUrl;
  }
}

function showMainView() {
  registerView.classList.add('hidden');
  mainView.classList.remove('hidden');
  userInfo.textContent = state.userName;
  updateApiEndpointDisplay();
  verifyAndUpdateRole();
  loadConversations();
  messageInput.focus();
}

// ── Navigation ──
function switchPanel(panelName) {
  state.activePanel = panelName;
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.panel === panelName);
  });
  document.querySelectorAll('.panel').forEach(el => {
    el.classList.toggle('active', el.id === `panel-${panelName}`);
  });
  const navLabel = document.querySelector(`.nav-item[data-panel="${panelName}"] .nav-label`);
  if (navLabel) {
    $('#panel-title').textContent = navLabel.textContent;
  }

  // Close mobile sidebar
  $('#sidebar').classList.remove('open');

  // Load panel data
  if (panelName === 'members') loadMembers();
  else if (panelName === 'family-tree') loadFamilyTree();
  else if (panelName === 'agent-templates') loadAgentTemplates();
  else if (panelName === 'app-settings') loadSettingsPanel();
}

function toggleSidebar() {
  $('#sidebar').classList.toggle('open');
}

// ── Settings ──
function openSettings() {
  $('#api-url-input').value = state.apiUrl;
  settingsModal.classList.remove('hidden');
}

function closeSettings() {
  settingsModal.classList.add('hidden');
}

function saveSettings() {
  const url = $('#api-url-input').value.trim().replace(/\/+$/, '');
  if (!url) { alert('API URL is required'); return; }
  state.apiUrl = url;
  localStorage.setItem('ha_api_url', url);
  updateApiEndpointDisplay();
  closeSettings();
}

// ── Auth Tab Switching ──
function switchAuthTab(tab) {
  document.querySelectorAll('.auth-tab').forEach((el, i) => {
    el.classList.toggle('active', (tab === 'register') === (i === 0));
  });
  $('#register-form').classList.toggle('hidden', tab !== 'register');
  $('#login-form').classList.toggle('hidden', tab !== 'login');
}

// ── Auth: Token Login ──
async function handleTokenLogin(e) {
  e.preventDefault();
  const errEl = $('#login-error');
  errEl.classList.add('hidden');

  const token = $('#login-token').value.trim();
  if (!token) return;

  try {
    const res = await fetch(`${state.apiUrl}/api/auth/verify`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    });

    const data = await res.json();
    if (!res.ok || !data.valid) {
      errEl.textContent = data.error || 'Invalid token';
      errEl.classList.remove('hidden');
      return;
    }

    state.token = token;
    state.userName = data.name || 'User';
    state.userRole = data.role || '';
    state.userId = data.user_id || '';
    localStorage.setItem('ha_token', token);
    localStorage.setItem('ha_user_name', state.userName);
    localStorage.setItem('ha_user_role', state.userRole);
    localStorage.setItem('ha_user_id', state.userId);
    showMainView();
  } catch (err) {
    errEl.textContent = `Connection failed: ${err.message}`;
    errEl.classList.remove('hidden');
  }
}

// ── Register Page: Generate Invite Code ──
async function generateInviteCodeFromRegister() {
  const btn = $('#register-invite-btn');
  const token = prompt('Enter your admin device token to generate an invite code:');
  if (!token) return;

  btn.disabled = true;
  btn.textContent = '...';

  try {
    const res = await fetch(`${state.apiUrl}/api/admin/invite-codes`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    });

    const data = await res.json();
    if (!res.ok) {
      alert(data.error || 'Failed to generate invite code');
      return;
    }
    prompt('New invite code (share with family member):', data.code);
  } catch (err) {
    alert(`Error: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generate Invite Code';
  }
}

// ── Auth: Register ──
async function handleRegister(e) {
  e.preventDefault();
  const errEl = $('#register-error');
  errEl.classList.add('hidden');

  if (!state.apiUrl) {
    errEl.textContent = 'Please configure the API endpoint first (click link below).';
    errEl.classList.remove('hidden');
    return;
  }

  const inviteCode = $('#invite-code').value.trim();
  const displayName = $('#display-name').value.trim();

  try {
    const res = await fetch(`${state.apiUrl}/api/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        invite_code: inviteCode,
        display_name: displayName,
        device_name: 'Debug Console',
        platform: 'web',
      }),
    });

    const data = await res.json();
    if (!res.ok) {
      errEl.textContent = data.error || 'Registration failed';
      errEl.classList.remove('hidden');
      return;
    }

    state.token = data.device_token;
    state.userName = displayName;
    localStorage.setItem('ha_token', data.device_token);
    localStorage.setItem('ha_user_name', displayName);
    showMainView();
  } catch (err) {
    errEl.textContent = `Connection failed: ${err.message}`;
    errEl.classList.remove('hidden');
  }
}

// ── API Helpers ──
function apiHeaders() {
  return {
    'Authorization': `Bearer ${state.token}`,
    'Content-Type': 'application/json',
  };
}

async function apiGet(path) {
  const res = await fetch(`${state.apiUrl}${path}`, { headers: apiHeaders() });
  if (res.status === 401) { logout(); throw new Error('Unauthorized'); }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed: ${res.status}`);
  }
  return res.json();
}

async function apiPost(path, data) {
  const res = await fetch(`${state.apiUrl}${path}`, {
    method: 'POST',
    headers: apiHeaders(),
    body: data !== undefined ? JSON.stringify(data) : undefined,
  });
  if (res.status === 401) { logout(); throw new Error('Unauthorized'); }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed: ${res.status}`);
  }
  return res.json();
}

async function apiPut(path, data) {
  const res = await fetch(`${state.apiUrl}${path}`, {
    method: 'PUT',
    headers: apiHeaders(),
    body: JSON.stringify(data),
  });
  if (res.status === 401) { logout(); throw new Error('Unauthorized'); }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed: ${res.status}`);
  }
  return res.json();
}

async function apiDelete(path) {
  const res = await fetch(`${state.apiUrl}${path}`, { method: 'DELETE', headers: apiHeaders() });
  if (res.status === 401) { logout(); throw new Error('Unauthorized'); }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed: ${res.status}`);
  }
  return res.json();
}

function logout() {
  localStorage.removeItem('ha_token');
  localStorage.removeItem('ha_user_name');
  localStorage.removeItem('ha_user_role');
  localStorage.removeItem('ha_user_id');
  state.token = '';
  state.userName = '';
  state.userRole = '';
  state.userId = '';
  showRegisterView();
}

// ── Conversations ──
async function loadConversations() {
  try {
    const data = await apiGet('/api/conversations?limit=50');
    state.conversations = data.conversations || [];
    renderConversationList();
  } catch {
    // Silently fail
  }
}

function renderConversationList() {
  conversationList.textContent = '';
  state.conversations.forEach((c) => {
    const div = document.createElement('div');
    div.className = `conversation-item${c.conversation_id === state.currentConversationId ? ' active' : ''}`;
    div.addEventListener('click', () => selectConversation(c.conversation_id));

    const titleDiv = document.createElement('div');
    titleDiv.textContent = c.title || 'Untitled';
    div.appendChild(titleDiv);

    const timeDiv = document.createElement('div');
    timeDiv.className = 'conv-time';
    timeDiv.textContent = formatTime(c.updated_at || c.created_at);
    div.appendChild(timeDiv);

    conversationList.appendChild(div);
  });
}

async function selectConversation(id) {
  state.currentConversationId = id;
  const conv = state.conversations.find((c) => c.conversation_id === id);
  chatTitle.textContent = conv ? conv.title : 'Conversation';
  deleteConvBtn.style.display = 'flex';
  renderConversationList();

  try {
    const data = await apiGet(`/api/conversations/${id}/messages?limit=50`);
    state.messages = (data.messages || []).map((m) => ({ role: m.role, content: m.content }));
    renderMessages();
  } catch {
    state.messages = [];
    renderMessages();
  }
}

function startNewConversation() {
  state.currentConversationId = null;
  state.messages = [];
  chatTitle.textContent = 'New Conversation';
  deleteConvBtn.style.display = 'none';
  renderConversationList();
  renderMessages();
  messageInput.focus();
  $('#sidebar').classList.remove('open');
}

async function deleteCurrentConversation() {
  if (!state.currentConversationId) return;
  if (!confirm('Delete this conversation?')) return;

  try {
    await apiDelete(`/api/conversations/${state.currentConversationId}`);
    state.conversations = state.conversations.filter(
      (c) => c.conversation_id !== state.currentConversationId
    );
    startNewConversation();
    renderConversationList();
  } catch {
    // Ignore
  }
}

// ── Safe DOM Helpers ──

/**
 * Sanitize a markdown-rendered string to only allow safe HTML tags.
 * This prevents XSS by stripping all tags except a known-safe allowlist.
 */
function sanitizeHtml(html) {
  const template = document.createElement('template');
  template.innerHTML = html;
  const fragment = template.content;
  sanitizeNode(fragment);
  const wrapper = document.createElement('div');
  wrapper.appendChild(fragment.cloneNode(true));
  return wrapper.innerHTML;
}

const ALLOWED_TAGS = new Set([
  'strong', 'em', 'code', 'pre', 'br', 'p', 'span',
  'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3', 'h4',
]);

function sanitizeNode(node) {
  const children = Array.from(node.childNodes);
  for (const child of children) {
    if (child.nodeType === Node.ELEMENT_NODE) {
      if (!ALLOWED_TAGS.has(child.tagName.toLowerCase())) {
        const text = document.createTextNode(child.textContent);
        node.replaceChild(text, child);
      } else {
        while (child.attributes.length > 0) {
          child.removeAttribute(child.attributes[0].name);
        }
        sanitizeNode(child);
      }
    }
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

/**
 * Convert plain text with markdown-like syntax to safe HTML.
 * All content is first escaped, then safe formatting is applied.
 */
function renderMarkdown(text) {
  if (!text) return '';
  let html = escapeHtml(text);
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, _lang, code) => `<pre><code>${code}</code></pre>`);
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
  return sanitizeHtml(html);
}

/**
 * Set the inner HTML of an element using sanitized content.
 * Only use this for markdown-rendered assistant messages.
 */
function setSanitizedContent(el, sanitizedHtml) {
  el.innerHTML = sanitizedHtml;
}

/**
 * Build DOM for a panel content area using escaped HTML.
 * All dynamic values MUST be passed through escapeHtml() before insertion.
 * This is safe because escapeHtml converts all special characters to entities.
 */
function setEscapedContent(el, escapedHtml) {
  el.innerHTML = escapedHtml;
}

// ── Messages ──
function renderMessages() {
  messagesEl.querySelectorAll('.message').forEach((el) => el.remove());
  if (state.messages.length === 0) {
    emptyState.classList.remove('hidden');
    return;
  }
  emptyState.classList.add('hidden');
  state.messages.forEach((msg) => appendMessageEl(msg.role, msg.content));
  scrollToBottom();
}

function appendMessageEl(role, content) {
  const div = document.createElement('div');
  div.className = `message ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = role === 'user' ? (state.userName[0]?.toUpperCase() || 'U') : 'AI';
  div.appendChild(avatar);

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  if (role === 'assistant') {
    setSanitizedContent(bubble, renderMarkdown(content));
  } else {
    bubble.textContent = content;
  }
  div.appendChild(bubble);
  messagesEl.appendChild(div);
  return div;
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// ── Chat / SSE Streaming ──
function processSSELine(line, assistantMsg, bubbleEl) {
  if (!line.startsWith('data: ')) return;
  const jsonStr = line.slice(6);
  if (!jsonStr) return;

  try {
    const event = JSON.parse(jsonStr);
    if (event.type === 'text_delta') {
      assistantMsg.content += event.content;
      setSanitizedContent(bubbleEl, renderMarkdown(assistantMsg.content));
      scrollToBottom();
      if (event.conversation_id && !state.currentConversationId) {
        state.currentConversationId = event.conversation_id;
        deleteConvBtn.style.display = 'flex';
      }
    } else if (event.type === 'message_done') {
      if (event.conversation_id) {
        state.currentConversationId = event.conversation_id;
      }
      loadConversations();
    } else if (event.type === 'error') {
      const errorSpan = document.createElement('span');
      errorSpan.style.color = 'var(--danger)';
      errorSpan.textContent = event.content;
      bubbleEl.textContent = '';
      bubbleEl.appendChild(errorSpan);
    }
  } catch {
    // Skip malformed JSON
  }
}

async function handleSendMessage(e) {
  e.preventDefault();
  const text = messageInput.value.trim();
  if (!text || state.isStreaming) return;

  messageInput.value = '';
  autoResizeTextarea(messageInput);

  state.messages.push({ role: 'user', content: text });
  emptyState.classList.add('hidden');
  appendMessageEl('user', text);
  scrollToBottom();

  state.isStreaming = true;
  streamingIndicator.classList.remove('hidden');
  $('#send-btn').disabled = true;

  const assistantMsg = { role: 'assistant', content: '' };
  state.messages.push(assistantMsg);
  const assistantEl = appendMessageEl('assistant', '');
  const bubbleEl = assistantEl.querySelector('.message-bubble');

  state.abortController = new AbortController();

  try {
    const body = { message: text };
    if (state.currentConversationId) {
      body.conversation_id = state.currentConversationId;
    }

    const res = await fetch(`${state.apiUrl}/api/chat`, {
      method: 'POST',
      headers: apiHeaders(),
      body: JSON.stringify(body),
      signal: state.abortController.signal,
    });

    if (res.status === 401) { logout(); return; }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: 'Request failed' }));
      throw new Error(err.error || `HTTP ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        processSSELine(line, assistantMsg, bubbleEl);
      }
    }
    if (buffer) {
      processSSELine(buffer, assistantMsg, bubbleEl);
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      if (!assistantMsg.content) {
        state.messages.pop();
        assistantEl.remove();
      }
    } else {
      const errorSpan = document.createElement('span');
      errorSpan.style.color = 'var(--danger)';
      errorSpan.textContent = `Error: ${err.message}`;
      bubbleEl.textContent = '';
      bubbleEl.appendChild(errorSpan);
    }
  } finally {
    state.isStreaming = false;
    state.abortController = null;
    streamingIndicator.classList.add('hidden');
    $('#send-btn').disabled = false;
    messageInput.focus();
  }
}

function abortStream() {
  if (state.abortController) {
    state.abortController.abort();
  }
}

// ── Input Handling ──
function handleInputKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    $('#chat-form').requestSubmit();
  }
}

function autoResizeTextarea(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

// ── Time Formatting ──
function formatTime(isoStr) {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    const now = new Date();
    const diffMs = now - d;
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;
    return d.toLocaleDateString();
  } catch {
    return '';
  }
}

// ── API Endpoint Display ──
function updateApiEndpointDisplay() {
  if (state.apiUrl) {
    apiEndpointDisplay.textContent = state.apiUrl;
    apiEndpointDisplay.title = state.apiUrl;
  } else {
    apiEndpointDisplay.textContent = '';
  }
}

// ── Admin: Verify Role ──
async function verifyAndUpdateRole() {
  try {
    const data = await apiGet('/api/auth/verify');
    state.userRole = data.role || '';
    state.userId = data.user_id || '';
    state.userName = data.name || state.userName;
    localStorage.setItem('ha_user_role', state.userRole);
    localStorage.setItem('ha_user_id', state.userId);
    localStorage.setItem('ha_user_name', state.userName);
    userInfo.textContent = state.userName;
  } catch {
    // If verify fails, continue with cached data
  }
}

// ══════════════════════════════════════
// ── Members Panel ──
// ══════════════════════════════════════

async function loadMembers() {
  const listEl = $('#members-list');
  const detailEl = $('#member-detail');
  detailEl.classList.add('hidden');
  listEl.style.display = '';

  listEl.textContent = '';
  const loadingDiv = document.createElement('div');
  loadingDiv.className = 'text-muted text-sm';
  loadingDiv.textContent = 'Loading members...';
  listEl.appendChild(loadingDiv);

  try {
    const data = await apiGet('/api/admin/profiles');
    const profiles = data.profiles || [];

    listEl.textContent = '';

    if (profiles.length === 0) {
      const emptyDiv = document.createElement('div');
      emptyDiv.className = 'text-muted text-sm';
      emptyDiv.textContent = 'No family members yet.';
      listEl.appendChild(emptyDiv);
      return;
    }

    profiles.forEach(p => {
      const card = document.createElement('div');
      card.className = 'data-card';
      card.addEventListener('click', () => openMemberDetail(p.user_id));

      const header = document.createElement('div');
      header.className = 'data-card-header';

      const title = document.createElement('span');
      title.className = 'data-card-title';
      title.textContent = p.display_name;
      header.appendChild(title);

      const badge = document.createElement('span');
      badge.className = `badge ${p.role === 'admin' ? 'badge-admin' : 'badge-member'}`;
      badge.textContent = p.role;
      header.appendChild(badge);

      card.appendChild(header);

      const subtitle = document.createElement('div');
      subtitle.className = 'data-card-subtitle';
      subtitle.textContent = p.family_role || 'No role set';
      card.appendChild(subtitle);

      listEl.appendChild(card);
    });
  } catch (err) {
    listEl.textContent = '';
    const errDiv = document.createElement('div');
    errDiv.className = 'text-danger text-sm';
    errDiv.textContent = `Error: ${err.message}`;
    listEl.appendChild(errDiv);
  }
}

async function openMemberDetail(userId) {
  const listEl = $('#members-list');
  const detailEl = $('#member-detail');
  const contentEl = $('#member-detail-content');

  listEl.style.display = 'none';
  detailEl.classList.remove('hidden');
  contentEl.textContent = '';
  const loadingDiv = document.createElement('div');
  loadingDiv.className = 'text-muted text-sm';
  loadingDiv.textContent = 'Loading...';
  contentEl.appendChild(loadingDiv);

  try {
    const [profile, configsData, typesData] = await Promise.all([
      apiGet(`/api/admin/profiles/${userId}`),
      apiGet(`/api/admin/agents/${userId}`),
      apiGet('/api/admin/agents/types'),
    ]);

    const agentConfigs = configsData.agent_configs || [];
    const agentTypes = typesData.agent_types || {};
    const isEnabled = (type) => agentConfigs.some(c => c.agent_type === type && c.enabled);

    contentEl.textContent = '';

    // Member Info section
    const infoSection = document.createElement('div');
    infoSection.className = 'member-detail-section';
    const infoH3 = document.createElement('h3');
    infoH3.textContent = 'Member Info';
    infoSection.appendChild(infoH3);

    [['Name', profile.display_name], ['Role', profile.role], ['User ID', profile.user_id]].forEach(([label, value]) => {
      const row = document.createElement('div');
      row.className = 'info-row';
      const labelSpan = document.createElement('span');
      labelSpan.className = 'info-label';
      labelSpan.textContent = label;
      row.appendChild(labelSpan);
      const valueSpan = document.createElement('span');
      valueSpan.className = 'info-value';
      valueSpan.textContent = value;
      row.appendChild(valueSpan);
      infoSection.appendChild(row);
    });
    contentEl.appendChild(infoSection);

    // Profile editing section
    const profileSection = document.createElement('div');
    profileSection.className = 'member-detail-section';
    const profileH3 = document.createElement('h3');
    profileH3.textContent = 'Profile';
    profileSection.appendChild(profileH3);

    const roleGroup = document.createElement('div');
    roleGroup.className = 'form-group';
    const roleLabel = document.createElement('label');
    roleLabel.textContent = 'Family Role';
    roleGroup.appendChild(roleLabel);
    const roleInput = document.createElement('input');
    roleInput.type = 'text';
    roleInput.className = 'form-input';
    roleInput.id = 'member-family-role';
    roleInput.value = profile.family_role || '';
    roleInput.placeholder = 'e.g., Parent, Child';
    roleGroup.appendChild(roleInput);
    profileSection.appendChild(roleGroup);

    const notesGroup = document.createElement('div');
    notesGroup.className = 'form-group';
    const notesLabel = document.createElement('label');
    notesLabel.textContent = 'Health Notes';
    notesGroup.appendChild(notesLabel);
    const notesTextarea = document.createElement('textarea');
    notesTextarea.className = 'form-input form-textarea';
    notesTextarea.id = 'member-health-notes';
    notesTextarea.placeholder = 'Allergies, restrictions, etc.';
    notesTextarea.textContent = profile.health_notes || '';
    notesGroup.appendChild(notesTextarea);
    profileSection.appendChild(notesGroup);

    const saveBtn = document.createElement('button');
    saveBtn.className = 'btn btn-primary';
    saveBtn.textContent = 'Save Profile';
    saveBtn.addEventListener('click', () => saveMemberProfile(userId));
    profileSection.appendChild(saveBtn);
    contentEl.appendChild(profileSection);

    // Agent configs section
    const agentSection = document.createElement('div');
    agentSection.className = 'member-detail-section';
    const agentH3 = document.createElement('h3');
    agentH3.textContent = 'AI Agents';
    agentSection.appendChild(agentH3);

    Object.entries(agentTypes).forEach(([type, info]) => {
      const row = document.createElement('div');
      row.className = 'toggle-row';

      const infoDiv = document.createElement('div');
      infoDiv.className = 'toggle-info';
      const nameDiv = document.createElement('div');
      nameDiv.className = 'toggle-name';
      nameDiv.textContent = info.name;
      infoDiv.appendChild(nameDiv);
      const descDiv = document.createElement('div');
      descDiv.className = 'toggle-description';
      descDiv.textContent = info.description;
      infoDiv.appendChild(descDiv);
      if (!info.implemented) {
        const soonDiv = document.createElement('div');
        soonDiv.className = 'toggle-description';
        soonDiv.style.color = 'var(--warning)';
        soonDiv.textContent = 'Coming soon';
        infoDiv.appendChild(soonDiv);
      }
      row.appendChild(infoDiv);

      const toggle = document.createElement('button');
      toggle.className = `toggle-switch ${isEnabled(type) ? 'active' : ''}`;
      if (!info.implemented) toggle.disabled = true;
      toggle.addEventListener('click', () => toggleMemberAgent(userId, type, toggle));
      row.appendChild(toggle);

      agentSection.appendChild(row);
    });
    contentEl.appendChild(agentSection);

    // Danger zone (non-admin only)
    if (profile.role !== 'admin') {
      const dangerSection = document.createElement('div');
      dangerSection.className = 'member-detail-section';
      const dangerH3 = document.createElement('h3');
      dangerH3.className = 'text-danger';
      dangerH3.textContent = 'Danger Zone';
      dangerSection.appendChild(dangerH3);

      const removeBtn = document.createElement('button');
      removeBtn.className = 'btn btn-danger-solid';
      removeBtn.textContent = 'Remove Member';
      removeBtn.addEventListener('click', () => removeMember(userId, profile.display_name));
      dangerSection.appendChild(removeBtn);
      contentEl.appendChild(dangerSection);
    }
  } catch (err) {
    contentEl.textContent = '';
    const errDiv = document.createElement('div');
    errDiv.className = 'text-danger text-sm';
    errDiv.textContent = `Error: ${err.message}`;
    contentEl.appendChild(errDiv);
  }
}

function closeMemberDetail() {
  $('#members-list').style.display = '';
  $('#member-detail').classList.add('hidden');
}

async function saveMemberProfile(userId) {
  const familyRole = $('#member-family-role').value.trim();
  const healthNotes = $('#member-health-notes').value.trim();

  try {
    await apiPut(`/api/admin/profiles/${userId}`, {
      family_role: familyRole,
      health_notes: healthNotes,
    });
    alert('Profile updated successfully');
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

async function toggleMemberAgent(userId, agentType, btn) {
  const wasActive = btn.classList.contains('active');

  try {
    if (wasActive) {
      await apiDelete(`/api/admin/agents/${userId}/${agentType}`);
      btn.classList.remove('active');
    } else {
      await apiPut(`/api/admin/agents/${userId}/${agentType}`, { enabled: true });
      btn.classList.add('active');
    }
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

async function removeMember(userId, name) {
  if (!confirm(`Remove ${name}? This will permanently delete all their data. This cannot be undone.`)) return;

  try {
    await apiDelete(`/api/admin/profiles/${userId}`);
    alert('Member removed');
    loadMembers();
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

// ══════════════════════════════════════
// ── Family Tree Panel ──
// ══════════════════════════════════════

const RELATIONSHIP_OPTIONS = [
  { value: '', label: 'No relationship' },
  { value: 'parent_of', label: 'My child' },
  { value: 'child_of', label: 'My parent' },
  { value: 'spouse_of', label: 'My spouse / partner' },
  { value: 'sibling_of', label: 'My sibling' },
];

async function loadFamilyTree() {
  const contentEl = $('#family-tree-content');
  contentEl.textContent = '';
  const loadingDiv = document.createElement('div');
  loadingDiv.className = 'text-muted text-sm';
  loadingDiv.textContent = 'Loading family tree...';
  contentEl.appendChild(loadingDiv);

  try {
    const [profilesData, relData] = await Promise.all([
      apiGet('/api/admin/profiles'),
      state.userId ? apiGet(`/api/admin/family/relationships/${state.userId}`) : { relationships: [] },
    ]);

    const profiles = (profilesData.profiles || []).filter(p => p.user_id !== state.userId);
    const relationships = relData.relationships || [];

    const relMap = {};
    relationships.forEach(r => { relMap[r.related_user_id] = r.relationship_type; });

    contentEl.textContent = '';

    if (profiles.length === 0) {
      const emptyDiv = document.createElement('div');
      emptyDiv.className = 'text-muted text-sm';
      emptyDiv.textContent = 'No other family members yet. Invite members first.';
      contentEl.appendChild(emptyDiv);
      return;
    }

    const hint = document.createElement('p');
    hint.className = 'text-muted text-sm';
    hint.style.marginBottom = '16px';
    hint.textContent = "Set each member's relationship to you.";
    contentEl.appendChild(hint);

    const grid = document.createElement('div');
    grid.className = 'relationship-grid';

    profiles.forEach(p => {
      const card = document.createElement('div');
      card.className = 'relationship-card';
      const currentRel = relMap[p.user_id] || '';

      const header = document.createElement('div');
      header.className = 'relationship-card-header';

      const nameSpan = document.createElement('span');
      nameSpan.className = 'relationship-card-name';
      nameSpan.textContent = p.display_name;
      header.appendChild(nameSpan);

      const select = document.createElement('select');
      select.className = 'relationship-select';
      RELATIONSHIP_OPTIONS.forEach(o => {
        const option = document.createElement('option');
        option.value = o.value;
        option.textContent = o.label;
        if (o.value === currentRel) option.selected = true;
        select.appendChild(option);
      });
      const capturedCurrentRel = currentRel;
      select.addEventListener('change', () => setRelationship(p.user_id, select.value, capturedCurrentRel));
      header.appendChild(select);

      card.appendChild(header);

      const subtitle = document.createElement('div');
      subtitle.className = 'data-card-subtitle';
      subtitle.textContent = p.family_role || 'No role set';
      card.appendChild(subtitle);

      grid.appendChild(card);
    });

    contentEl.appendChild(grid);
  } catch (err) {
    contentEl.textContent = '';
    const errDiv = document.createElement('div');
    errDiv.className = 'text-danger text-sm';
    errDiv.textContent = `Error: ${err.message}`;
    contentEl.appendChild(errDiv);
  }
}

async function setRelationship(memberId, newType, oldType) {
  try {
    if (oldType) {
      await apiDelete(`/api/admin/family/relationships/${state.userId}/${memberId}`);
    }
    if (newType) {
      await apiPost('/api/admin/family/relationships', {
        user_id: state.userId,
        related_user_id: memberId,
        relationship_type: newType,
      });
    }
    loadFamilyTree();
  } catch (err) {
    alert(`Error: ${err.message}`);
    loadFamilyTree();
  }
}

// ══════════════════════════════════════
// ── Agent Templates Panel ──
// ══════════════════════════════════════

async function loadAgentTemplates() {
  const listEl = $('#templates-list');
  const editorEl = $('#template-editor');
  editorEl.classList.add('hidden');
  listEl.style.display = '';

  listEl.textContent = '';
  const loadingDiv = document.createElement('div');
  loadingDiv.className = 'text-muted text-sm';
  loadingDiv.textContent = 'Loading agent templates...';
  listEl.appendChild(loadingDiv);

  try {
    const data = await apiGet('/api/admin/agent-templates');
    const templates = data.templates || [];

    listEl.textContent = '';

    if (templates.length === 0) {
      const emptyDiv = document.createElement('div');
      emptyDiv.className = 'text-muted text-sm';
      emptyDiv.textContent = 'No agent templates found.';
      listEl.appendChild(emptyDiv);
      return;
    }

    templates.forEach(t => {
      const card = document.createElement('div');
      card.className = 'data-card';
      card.addEventListener('click', () => openTemplateEditor(t));

      const header = document.createElement('div');
      header.className = 'data-card-header';

      const title = document.createElement('span');
      title.className = 'data-card-title';
      title.textContent = t.name;
      header.appendChild(title);

      if (t.is_builtin) {
        const badge = document.createElement('span');
        badge.className = 'badge badge-builtin';
        badge.textContent = 'Built-in';
        header.appendChild(badge);
      }
      card.appendChild(header);

      const slug = document.createElement('div');
      slug.className = 'data-card-subtitle';
      slug.textContent = t.agent_type;
      card.appendChild(slug);

      const desc = document.createElement('div');
      desc.className = 'data-card-description';
      desc.textContent = t.description;
      card.appendChild(desc);

      const avail = document.createElement('div');
      avail.className = 'data-card-subtitle mt-12';
      avail.textContent = `Available to: ${t.available_to === 'all' ? 'Everyone' : `${(t.available_to || []).length} members`}`;
      card.appendChild(avail);

      listEl.appendChild(card);
    });
  } catch (err) {
    listEl.textContent = '';
    const errDiv = document.createElement('div');
    errDiv.className = 'text-danger text-sm';
    errDiv.textContent = `Error: ${err.message}`;
    listEl.appendChild(errDiv);
  }
}

function openTemplateEditor(template) {
  const listEl = $('#templates-list');
  const editorEl = $('#template-editor');
  const contentEl = $('#template-editor-content');

  listEl.style.display = 'none';
  editorEl.classList.remove('hidden');
  contentEl.textContent = '';

  const isEdit = !!template;
  const isBuiltin = template?.is_builtin || false;

  const heading = document.createElement('h2');
  heading.style.marginBottom = '20px';
  heading.textContent = isEdit ? 'Edit Agent Template' : 'New Agent Template';
  contentEl.appendChild(heading);

  // Name
  const nameGroup = document.createElement('div');
  nameGroup.className = 'form-group';
  const nameLabel = document.createElement('label');
  nameLabel.textContent = 'Name';
  nameGroup.appendChild(nameLabel);
  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.className = 'form-input';
  nameInput.id = 'tpl-name';
  nameInput.value = template?.name || '';
  nameInput.placeholder = 'e.g. Meal Planner';
  if (isBuiltin) nameInput.disabled = true;
  nameGroup.appendChild(nameInput);
  contentEl.appendChild(nameGroup);

  // Agent type slug
  const typeGroup = document.createElement('div');
  typeGroup.className = 'form-group';
  const typeLabel = document.createElement('label');
  typeLabel.textContent = 'Agent Type (slug)';
  typeGroup.appendChild(typeLabel);
  const typeInput = document.createElement('input');
  typeInput.type = 'text';
  typeInput.className = 'form-input form-input-mono';
  typeInput.id = 'tpl-agent-type';
  typeInput.value = template?.agent_type || '';
  typeInput.placeholder = 'e.g. meal_planner';
  if (isEdit) typeInput.disabled = true;
  typeGroup.appendChild(typeInput);
  if (isEdit) {
    const note = document.createElement('div');
    note.className = 'text-muted text-sm mt-12';
    note.textContent = 'Agent type cannot be changed after creation';
    typeGroup.appendChild(note);
  }
  contentEl.appendChild(typeGroup);

  // Description
  const descGroup = document.createElement('div');
  descGroup.className = 'form-group';
  const descLabel = document.createElement('label');
  descLabel.textContent = 'Description';
  descGroup.appendChild(descLabel);
  const descTextarea = document.createElement('textarea');
  descTextarea.className = 'form-input form-textarea';
  descTextarea.id = 'tpl-description';
  descTextarea.placeholder = 'What does this agent do?';
  descTextarea.textContent = template?.description || '';
  descGroup.appendChild(descTextarea);
  contentEl.appendChild(descGroup);

  // System prompt
  const promptGroup = document.createElement('div');
  promptGroup.className = 'form-group';
  const promptLabel = document.createElement('label');
  promptLabel.textContent = 'System Prompt';
  promptGroup.appendChild(promptLabel);
  const promptTextarea = document.createElement('textarea');
  promptTextarea.className = 'form-input form-textarea-large';
  promptTextarea.id = 'tpl-system-prompt';
  promptTextarea.placeholder = 'Instructions for the agent...';
  if (isBuiltin) promptTextarea.disabled = true;
  promptTextarea.textContent = template?.system_prompt || '';
  promptGroup.appendChild(promptTextarea);
  if (isBuiltin) {
    const note = document.createElement('div');
    note.className = 'text-muted text-sm mt-12';
    note.textContent = 'System prompt is read-only for built-in agents';
    promptGroup.appendChild(note);
  }
  contentEl.appendChild(promptGroup);

  // Availability toggle
  const availGroup = document.createElement('div');
  availGroup.className = 'form-group';
  const availLabel = document.createElement('label');
  availLabel.textContent = 'Availability';
  availGroup.appendChild(availLabel);

  const toggleRow = document.createElement('div');
  toggleRow.className = 'toggle-row';
  toggleRow.style.borderBottom = 'none';
  toggleRow.style.padding = '0';

  const toggleInfo = document.createElement('div');
  toggleInfo.className = 'toggle-info';
  const toggleName = document.createElement('div');
  toggleName.className = 'toggle-name';
  toggleName.textContent = 'Available to all members';
  toggleInfo.appendChild(toggleName);
  toggleRow.appendChild(toggleInfo);

  const toggleBtn = document.createElement('button');
  toggleBtn.className = `toggle-switch ${(!template || template.available_to === 'all') ? 'active' : ''}`;
  toggleBtn.id = 'tpl-available-toggle';
  toggleBtn.addEventListener('click', () => toggleBtn.classList.toggle('active'));
  toggleRow.appendChild(toggleBtn);

  availGroup.appendChild(toggleRow);
  contentEl.appendChild(availGroup);

  // Action buttons
  const actions = document.createElement('div');
  actions.style.display = 'flex';
  actions.style.gap = '10px';
  actions.style.marginTop = '24px';

  const saveBtn = document.createElement('button');
  saveBtn.className = 'btn btn-primary';
  saveBtn.textContent = 'Save';
  saveBtn.addEventListener('click', () => saveTemplate(isEdit ? template.template_id : null));
  actions.appendChild(saveBtn);

  if (isEdit && !isBuiltin) {
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn btn-danger-solid';
    deleteBtn.textContent = 'Delete';
    deleteBtn.addEventListener('click', () => deleteTemplate(template.template_id, template.name));
    actions.appendChild(deleteBtn);
  }

  contentEl.appendChild(actions);
}

function closeTemplateEditor() {
  $('#templates-list').style.display = '';
  $('#template-editor').classList.add('hidden');
}

async function saveTemplate(templateId) {
  const name = $('#tpl-name').value.trim();
  const agentType = $('#tpl-agent-type').value.trim().toLowerCase().replace(/\s+/g, '_');
  const description = $('#tpl-description').value.trim();
  const systemPrompt = $('#tpl-system-prompt').value.trim();
  const availableToAll = $('#tpl-available-toggle').classList.contains('active');

  if (!name || !description) {
    alert('Name and description are required');
    return;
  }

  try {
    if (templateId) {
      await apiPut(`/api/admin/agent-templates/${templateId}`, {
        name,
        description,
        system_prompt: systemPrompt,
        available_to: availableToAll ? 'all' : [],
      });
    } else {
      if (!agentType || !systemPrompt) {
        alert('Agent type slug and system prompt are required for new agents');
        return;
      }
      await apiPost('/api/admin/agent-templates', {
        name,
        agent_type: agentType,
        description,
        system_prompt: systemPrompt,
        available_to: availableToAll ? 'all' : [],
      });
    }
    closeTemplateEditor();
    loadAgentTemplates();
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

async function deleteTemplate(templateId, name) {
  if (!confirm(`Delete "${name}"? This will also remove all member configurations for this agent.`)) return;

  try {
    await apiDelete(`/api/admin/agent-templates/${templateId}`);
    closeTemplateEditor();
    loadAgentTemplates();
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

// ══════════════════════════════════════
// ── Settings Panel ──
// ══════════════════════════════════════

function loadSettingsPanel() {
  $('#settings-api-url').value = state.apiUrl;
  $('#info-user').textContent = state.userName;
  $('#info-role').textContent = state.userRole;
  $('#info-api').textContent = state.apiUrl;
}

function saveApiUrl() {
  const url = $('#settings-api-url').value.trim().replace(/\/+$/, '');
  if (!url) { alert('API URL is required'); return; }
  state.apiUrl = url;
  localStorage.setItem('ha_api_url', url);
  updateApiEndpointDisplay();
  $('#info-api').textContent = url;
  alert('API URL updated');
}

async function generateInviteCode() {
  const btn = $('#settings-invite-btn');
  const resultEl = $('#invite-code-result');
  btn.disabled = true;
  btn.textContent = 'Generating...';
  resultEl.classList.add('hidden');

  try {
    const data = await apiPost('/api/admin/invite-codes');
    resultEl.textContent = data.code;
    resultEl.classList.remove('hidden');
  } catch (err) {
    alert(`Error: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generate Invite Code';
  }
}

// ── Boot ──
init();
