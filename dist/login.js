'use strict';
const form = document.querySelector('#login-form');
form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = document.querySelector('#login-submit');
  const error = document.querySelector('#login-error');
  button.disabled = true; error.textContent = '';
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST', credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
      headers: {'Content-Type': 'application/json', 'X-Voyager-Request': '1'},
      body: JSON.stringify({username: form.username.value.trim(), password: form.password.value})
    });
    if (!response.ok) {
      if (response.status === 429) throw new Error('登录尝试过多，请在 5 分钟后重试。');
      if (response.status === 401) throw new Error('用户名或密码不正确。');
      throw new Error('暂时无法登录，请稍后重试。');
    }
    // The session is an HttpOnly cookie. No password or session token goes into storage or URLs.
    form.password.value = '';
    location.replace('/');
  } catch (ex) {
    error.textContent = ex.name === 'AbortError' ? '连接超时，请重试。' : ex.message;
    form.password.value = ''; button.disabled = false;
  } finally { clearTimeout(timeout); }
});
