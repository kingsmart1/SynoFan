/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 LiuFudi
 *
 * This file is part of synofan (a Synology port of niufan), licensed under the
 * GNU General Public License version 3 or (at your option) any later version.
 * See the LICENSE file for the full text.
 *
 * Synology build: password login overlay for the NiuFan web UI.
 * The nginx bridge exposes /api/ without authenticating, so every API call
 * that comes back 401/403 pops a login (or "set a password") dialog and the
 * successful login reloads the page.
 */
(function () {
  'use strict';

  var BASE = (window.FANCONTROL_BASE || '/').replace(/\/+$/, '');
  var AUTH_API = BASE + '/api/auth/';
  var API_PREFIX = BASE + '/api/';
  var nativeFetch = window.fetch.bind(window);
  var overlay = null;

  function post(path, payload) {
    return nativeFetch(AUTH_API + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload || {})
    });
  }

  var FIELD = 'width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #444;' +
    'border-radius:6px;background:#111;color:#eee;margin-bottom:12px;';
  var BOX = 'background:#1b1b1f;color:#eee;padding:28px;border-radius:10px;max-width:360px;' +
    'width:100%;box-shadow:0 10px 40px rgba(0,0,0,.5);font-family:system-ui,sans-serif;';
  var BTN = 'width:100%;padding:10px;border:0;border-radius:6px;background:#2d7bd6;' +
    'color:#fff;font-size:14px;cursor:pointer;';

  function show(html) {
    if (overlay) { return; }
    overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;z-index:99999;display:flex;' +
      'align-items:center;justify-content:center;background:rgba(0,0,0,.62);';
    overlay.innerHTML = html;
    document.body.appendChild(overlay);
  }

  function loginForm() {
    return '<div style="' + BOX + '">' +
      '<h2 style="margin:0 0 6px;font-size:18px;">SynoFan 登录</h2>' +
      '<p style="margin:0 0 16px;font-size:13px;color:#aaa;">请输入访问密码</p>' +
      '<input id="sf-pass" type="password" placeholder="密码" style="' + FIELD + '" />' +
      '<div id="sf-err" style="color:#f66;font-size:12px;margin-bottom:10px;display:none;"></div>' +
      '<button id="sf-go" style="' + BTN + '">登录</button></div>';
  }

  function changeForm() {
    return '<div style="' + BOX + '">' +
      '<h2 style="margin:0 0 6px;font-size:18px;">设置新密码</h2>' +
      '<p style="margin:0 0 16px;font-size:13px;color:#aaa;">首次登录须设置一个新密码（至少 8 位）</p>' +
      '<input id="sf-new" type="password" placeholder="新密码" style="' + FIELD + '" />' +
      '<input id="sf-new2" type="password" placeholder="确认新密码" style="' + FIELD + '" />' +
      '<div id="sf-err" style="color:#f66;font-size:12px;margin-bottom:10px;display:none;"></div>' +
      '<button id="sf-go" style="' + BTN + '">保存</button></div>';
  }

  function fail(msg) {
    var err = document.getElementById('sf-err');
    if (err) { err.textContent = msg; err.style.display = 'block'; }
  }

  function wire(kind) {
    var go = document.getElementById('sf-go');
    if (!go) { return; }
    go.onclick = function () {
      go.disabled = true;
      if (kind === 'login') {
        var p = document.getElementById('sf-pass').value;
        post('login', { password: p }).then(function (r) {
          return r.json().then(function (d) { return { r: r, d: d }; });
        }).then(function (o) {
          if (o.r.ok && o.d && o.d.ok) {
            if (o.d.change_required) {
              overlay.remove(); overlay = null;
              show(changeForm()); wire('change');
            } else {
              location.reload();
            }
          } else {
            go.disabled = false;
            fail((o.d && o.d.error) || '登录失败');
          }
        }).catch(function () { go.disabled = false; fail('网络错误'); });
      } else {
        var n = document.getElementById('sf-new').value;
        var n2 = document.getElementById('sf-new2').value;
        if (n !== n2) { go.disabled = false; fail('两次输入不一致'); return; }
        post('password', { new: n }).then(function (r) {
          return r.json().then(function (d) { return { r: r, d: d }; });
        }).then(function (o) {
          if (o.r.ok && o.d && o.d.ok) { location.reload(); }
          else { go.disabled = false; fail((o.d && o.d.error) || '保存失败'); }
        }).catch(function () { go.disabled = false; fail('网络错误'); });
      }
    };
  }

  window.fetch = function (input, init) {
    var url = typeof input === 'string' ? input : (input && input.url);
    if (url && url.indexOf(AUTH_API) === 0) { return nativeFetch(input, init); }
    return nativeFetch(input, init).then(function (res) {
      if (url && url.indexOf(API_PREFIX) === 0) {
        if (res.status === 401) {
          show(loginForm()); wire('login');
        } else if (res.status === 403) {
          res.clone().json().then(function (d) {
            if (d && d.error === '需要先设置新密码') {
              show(changeForm()); wire('change');
            }
          }).catch(function () {});
        }
      }
      return res;
    });
  };

  // Ask the daemon on load whether the password still has to be set.
  nativeFetch(AUTH_API + 'session').then(function (r) { return r.json(); })
    .then(function (d) { if (d && d.change_required) { show(changeForm()); wire('change'); } })
    .catch(function () {});
})();
