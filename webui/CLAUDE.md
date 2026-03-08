# WebUI Subagent — Debug Console (Vanilla HTML/CSS/JS)

## Scope
- You work ONLY on files under `webui/`.
- You may READ `backend/app/routes/` to understand API endpoints, but never modify backend code.
- You may READ `mobile/src/types/index.ts` to stay consistent with data models.
- This is a debug/testing tool, not a production-facing app.

## Tech Stack
- **Vanilla HTML5, CSS3, ES6+ JavaScript** — zero dependencies, zero build step.
- No frameworks, no bundlers, no npm, no TypeScript.
- 4 files total: `index.html`, `styles.css`, `app.js`, `error.html`.
- Served as static files via S3 + CloudFront (or local `python -m http.server`).

## File Responsibilities

| File | Purpose | Lines |
|------|---------|-------|
| `index.html` | Page structure, modals, script/style includes | ~125 |
| `styles.css` | All styling, dark theme, CSS variables, responsive layout | ~414 |
| `app.js` | All logic: auth, API calls, SSE streaming, DOM manipulation, state | ~680 |
| `error.html` | 404 error page for CloudFront | ~23 |

### Rules
- Keep it as 4 files — no splitting into modules or adding a build step.
- No external CDN dependencies — everything is self-contained.
- This is a debug tool: prioritize functionality and clarity over polish.

## JavaScript Patterns

### State Management
- Auth state (token, user info) in `localStorage` with `ha_` prefix.
- UI state (current conversation, messages) in module-level variables.
- No state management library — plain variables and DOM updates.

### API Communication
```javascript
// Standard request pattern
async function apiRequest(path, options = {}) {
    const headers = { 'Content-Type': 'application/json' };
    const token = localStorage.getItem('ha_token');
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const response = await fetch(`${getBaseUrl()}${path}`, { ...options, headers });
    if (!response.ok) throw new Error(`${response.status}`);
    return response.json();
}
```

### SSE Streaming
```javascript
// SSE via fetch + ReadableStream (not EventSource, for POST support)
const response = await fetch(`${baseUrl}/api/chat`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_id }),
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
// Read chunks, split by "data: ", parse JSON events
```

### Rules
- All API calls go through a shared request helper — no inline `fetch` calls.
- Handle 401 responses globally by clearing auth state and showing login.
- SSE parsing must handle partial chunks (data split across reads).
- Sanitize any user-generated content before inserting into DOM (prevent XSS).

## CSS Patterns

### Theme Variables
```css
:root {
    --bg-primary: #1a1a2e;
    --bg-secondary: #16213e;
    --text-primary: #e0e0e0;
    --accent: #0f3460;
    --accent-hover: #1a4a80;
    --border: #2a2a4a;
    --error: #e74c3c;
    --success: #2ecc71;
}
```

### Rules
- All colors reference CSS variables — never hardcode hex values in component styles.
- Dark theme is the default and only theme (debug tool, not user-facing).
- Use flexbox for layout.
- Keep responsive: the console should work on both desktop and tablet widths.

## HTML Structure

### Rules
- Semantic HTML elements (`header`, `main`, `section`, `nav`).
- IDs for JavaScript-targeted elements, classes for styling.
- Modals use a simple show/hide pattern with CSS classes.
- No inline styles or inline event handlers — all in `styles.css` and `app.js`.

## Security

- Tokens stored in `localStorage` (acceptable for debug tool, not for production).
- Never log tokens to console in committed code.
- Sanitize markdown/HTML rendering to prevent XSS from chat content.
- API base URL is configurable — don't trust it for security decisions.

## Deployment

- Files sync directly to S3 via CDK pipeline (`aws s3 sync webui/ s3://bucket`).
- CloudFront invalidation runs after each deploy.
- No build step — what you see in the directory is what gets deployed.
- `error.html` is the CloudFront custom error response for 404s.

## Pre-Completion Checklist

Before considering any task done, verify:
- [ ] No JavaScript errors in browser console
- [ ] Auth flow works (register, login with token, logout)
- [ ] Chat streaming works (messages appear incrementally)
- [ ] No inline styles or hardcoded colors
- [ ] No XSS vulnerabilities in DOM insertions
- [ ] File still works when opened directly (`file://`) and via HTTP server
