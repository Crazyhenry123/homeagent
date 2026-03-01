// ── State ──
const state = {
  token: localStorage.getItem('ha_token') || '',
  userName: localStorage.getItem('ha_user_name') || '',
  userRole: localStorage.getItem('ha_user_role') || '',
  apiUrl: localStorage.getItem('ha_api_url') || '',
  conversations: [],
  currentConversationId: null,
  messages: [],
  isStreaming: false,
  abortController: null,
};

// ── DOM refs ──
const $ = (sel) => document.querySelector(sel);
const registerView = $('#register-view');
const chatView = $('#chat-view');
const settingsModal = $('#settings-modal');
const messagesEl = $('#messages');
const emptyState = $('#empty-state');
const messageInput = $('#message-input');
const chatTitle = $('#chat-title');
const streamingIndicator = $('#streaming-indicator');
const conversationList = $('#conversation-list');
const userInfo = $('#user-info');
const deleteConvBtn = $('#delete-conv-btn');
const generateInviteBtn = $('#generate-invite-btn');
const apiEndpointDisplay = $('#api-endpoint-display');

// ── Init ──
function init() {
  // Default to same origin (API proxied through CloudFront)
  if (!state.apiUrl) {
    state.apiUrl = window.location.origin;
    localStorage.setItem('ha_api_url', state.apiUrl);
  }

  if (state.token) {
    showChatView();
  } else {
    showRegisterView();
  }
}

function showRegisterView() {
  registerView.classList.remove('hidden');
  chatView.classList.add('hidden');
  if (state.apiUrl) {
    $('#api-url-input').value = state.apiUrl;
  }
}

function showChatView() {
  registerView.classList.add('hidden');
  chatView.classList.remove('hidden');
  userInfo.textContent = state.userName;
  updateApiEndpointDisplay();
  verifyAndUpdateRole();
  loadConversations();
  messageInput.focus();
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

// ── Auth ──
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
    showChatView();
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
  state.token = '';
  state.userName = '';
  state.userRole = '';
  showRegisterView();
}

// ── Conversations ──
async function loadConversations() {
  try {
    const data = await apiGet('/api/conversations?limit=50');
    state.conversations = data.conversations || [];
    renderConversationList();
  } catch {
    // Silently fail — sidebar just stays empty
  }
}

function renderConversationList() {
  // Clear existing items
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
    state.messages = (data.messages || []).map((m) => ({
      role: m.role,
      content: m.content,
    }));
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
  // Close sidebar on mobile
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
        // Replace disallowed element with its text content
        const text = document.createTextNode(child.textContent);
        node.replaceChild(text, child);
      } else {
        // Remove all attributes from allowed elements
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

  // Code blocks: ```lang\n...\n```
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, _lang, code) => {
    return `<pre><code>${code}</code></pre>`;
  });

  // Inline code: `...`
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Bold: **...**
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // Italic: *...*
  html = html.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');

  // Since we escaped first and only insert safe tags, sanitize as defense-in-depth
  return sanitizeHtml(html);
}

/**
 * Set the inner HTML of an element using sanitized content.
 * Only use this for markdown-rendered assistant messages.
 */
function setSanitizedContent(el, sanitizedHtml) {
  // Content has already been escaped + sanitized via renderMarkdown
  el.innerHTML = sanitizedHtml;
}

// ── Messages ──
function renderMessages() {
  // Remove old message elements
  messagesEl.querySelectorAll('.message').forEach((el) => el.remove());

  if (state.messages.length === 0) {
    emptyState.classList.remove('hidden');
    return;
  }

  emptyState.classList.add('hidden');

  state.messages.forEach((msg) => {
    appendMessageEl(msg.role, msg.content);
  });
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

  // Add user message
  state.messages.push({ role: 'user', content: text });
  emptyState.classList.add('hidden');
  appendMessageEl('user', text);
  scrollToBottom();

  // Start streaming
  state.isStreaming = true;
  streamingIndicator.classList.remove('hidden');
  $('#send-btn').disabled = true;

  const assistantMsg = { role: 'assistant', content: '' };
  state.messages.push(assistantMsg);
  const assistantEl = appendMessageEl('assistant', '');
  const bubbleEl = assistantEl.querySelector('.message-bubble');

  state.abortController = new AbortController();

  try {
    const body = {
      message: text,
    };
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

    // Read SSE stream
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // Keep incomplete line in buffer

      for (const line of lines) {
        processSSELine(line, assistantMsg, bubbleEl);
      }
    }

    // Process any remaining buffered data
    if (buffer) {
      processSSELine(buffer, assistantMsg, bubbleEl);
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      if (!assistantMsg.content) {
        // Remove empty assistant message
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

function toggleSidebar() {
  $('#sidebar').classList.toggle('open');
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
    localStorage.setItem('ha_user_role', state.userRole);
    if (state.userRole === 'admin') {
      generateInviteBtn.classList.remove('hidden');
    } else {
      generateInviteBtn.classList.add('hidden');
    }
  } catch {
    // If verify fails, hide the button
    generateInviteBtn.classList.add('hidden');
  }
}

// ── Admin: Generate Invite Code ──
async function generateInviteCode() {
  generateInviteBtn.disabled = true;
  generateInviteBtn.textContent = '...';

  try {
    const res = await fetch(`${state.apiUrl}/api/admin/invite-codes`, {
      method: 'POST',
      headers: apiHeaders(),
    });

    if (res.status === 401) { logout(); return; }
    if (res.status === 403) { alert('Admin access required'); return; }

    const data = await res.json();
    if (!res.ok) {
      alert(data.error || 'Failed to generate invite code');
      return;
    }

    prompt('New invite code (share with family member):', data.code);
  } catch (err) {
    alert(`Error: ${err.message}`);
  } finally {
    generateInviteBtn.disabled = false;
    generateInviteBtn.textContent = 'Invite';
  }
}

// ── Boot ──
init();
