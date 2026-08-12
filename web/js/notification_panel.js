/**
 * 通知面板 UI 模块 (Notification Panel Module)
 *
 * 功能定位：
 * - 通知面板的 DOM 创建与渲染
 * - 系统消息 / 互动消息 的分 Tab 展示
 * - 设置面板（互动消息提醒开关）
 * - 时间格式化工具
 */
(function () {
    var _panel = null;
    var _overlay = null;
    var _activeTab = 'system';
    var _settingsOpen = false;
    var _renderedSystemMessages = [];

    function isNotificationCenterEnabled() {
        if (window.app && typeof window.app.getServerUserFeatures === 'function') {
            return window.app.getServerUserFeatures('notification_center_enabled');
        }
        if (window._aimerUserFeatures && window._aimerUserFeatures.notification_center_enabled === false) {
            return false;
        }
        return false;
    }

    function t(key, params) {
        return window.I18N && typeof I18N.t === 'function' ? I18N.t(key, params) : key;
    }

    function showStorageFailure(key) {
        if (window.app && typeof window.app.showAlert === 'function') {
            window.app.showAlert(t('common.error'), t(key), 'error');
        }
    }

    /* ---- 时间格式化 ---- */

    function formatRelativeTime(ts) {
        if (!ts) return '';
        var now = Date.now();
        var diff = now - ts;
        if (diff < 0) diff = 0;

        var seconds = Math.floor(diff / 1000);
        if (seconds < 60) return t('notification.time_just_now');
        var minutes = Math.floor(seconds / 60);
        if (minutes < 60) return t('notification.time_minutes_ago', { count: minutes });
        var hours = Math.floor(minutes / 60);
        if (hours < 24) return t('notification.time_hours_ago', { count: hours });
        var days = Math.floor(hours / 24);
        if (days < 30) return t('notification.time_days_ago', { count: days });
        // 超过 30 天直接显示日期
        var d = new Date(ts);
        return d.toLocaleDateString(document.documentElement.lang || undefined);
    }

    /* ---- DOM 创建 ---- */

    function ensurePanel() {
        if (!isNotificationCenterEnabled()) return;
        if (_panel && document.body.contains(_panel)) return;

        // 透明遮罩（用于点击外部关闭）
        _overlay = document.createElement('div');
        _overlay.className = 'notif-panel-overlay';
        _overlay.addEventListener('click', function () {
            if (window.NotificationBellModule) {
                window.NotificationBellModule.closePanel();
            }
        });
        document.body.appendChild(_overlay);

        // 面板主体
        _panel = document.createElement('div');
        _panel.className = 'notif-panel';
        _panel.id = 'notif-panel';
        _panel.innerHTML = buildPanelHTML();
        document.body.appendChild(_panel);

        // 阻止面板内点击冒泡到遮罩
        _panel.addEventListener('click', function (e) {
            e.stopPropagation();
        });

        bindEvents();
        if (window.I18N) I18N.applyToDOM(_panel);
    }

    function buildPanelHTML() {
        return [
            '<div class="notif-panel-header">',
            '  <h3 class="notif-panel-title"><i class="ri-notification-3-line"></i><span data-i18n="notification.title">消息中心</span></h3>',
            '  <div class="notif-panel-actions">',
            '    <button class="notif-panel-action-btn" id="notif-btn-settings" title="设置" data-i18n-title="notification.settings"><i class="ri-settings-3-line"></i></button>',
            '    <button class="notif-panel-action-btn" id="notif-btn-mark-read" title="全部已读" data-i18n-title="notification.mark_all_read"><i class="ri-check-double-line"></i></button>',
            '    <button class="notif-panel-action-btn" id="notif-btn-close" title="关闭" data-i18n-title="common.close"><i class="ri-close-line"></i></button>',
            '  </div>',
            '</div>',
            '<div class="notif-tab-bar">',
            '  <button class="notif-tab-btn active" data-tab="system">',
            '    <i class="ri-megaphone-line"></i> <span data-i18n="notification.system_tab">系统消息</span>',
            '    <span class="notif-tab-count" id="notif-count-system"></span>',
            '  </button>',
            '  <button class="notif-tab-btn" data-tab="interact">',
            '    <i class="ri-chat-heart-line"></i> <span data-i18n="notification.interact_tab">互动消息</span>',
            '    <span class="notif-tab-count" id="notif-count-interact"></span>',
            '  </button>',
            '</div>',
            '<div class="notif-list-wrap" id="notif-list-wrap">',
            '  <div class="notif-list" id="notif-list"></div>',
            '</div>',
            '<div class="notif-settings-panel" id="notif-settings-panel">',
            '  <div class="notif-settings-row">',
            '    <span class="notif-settings-label"><i class="ri-hearts-line"></i><span data-i18n="notification.interact_notify">互动消息提醒</span></span>',
            '    <label class="notif-toggle-switch">',
            '      <input type="checkbox" id="notif-toggle-interact" checked>',
            '      <span class="notif-toggle-slider"></span>',
            '    </label>',
            '  </div>',
            '</div>',
            '<div class="notif-panel-footer">',
            '  <p class="notif-panel-footer-text" data-i18n="notification.retention">系统消息与互动消息均最多保留 10 条 · 15 天后过期</p>',
            '</div>'
        ].join('\n');
    }

    function bindEvents() {
        // Tab 切换
        var tabs = _panel.querySelectorAll('.notif-tab-btn');
        for (var i = 0; i < tabs.length; i++) {
            tabs[i].addEventListener('click', function () {
                _activeTab = this.getAttribute('data-tab');
                updateTabUI();
                renderList();
            });
        }

        // 关闭按钮
        var closeBtn = _panel.querySelector('#notif-btn-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function () {
                if (window.NotificationBellModule) {
                    window.NotificationBellModule.closePanel();
                }
            });
        }

        // 标记全部已读
        var markReadBtn = _panel.querySelector('#notif-btn-mark-read');
        if (markReadBtn) {
            markReadBtn.addEventListener('click', function () {
                if (window.NotificationBellModule) {
                    window.NotificationBellModule.markAllRead();
                }
            });
        }

        // 设置按钮
        var settingsBtn = _panel.querySelector('#notif-btn-settings');
        if (settingsBtn) {
            settingsBtn.addEventListener('click', function () {
                _settingsOpen = !_settingsOpen;
                var settingsPanel = _panel.querySelector('#notif-settings-panel');
                if (settingsPanel) {
                    settingsPanel.classList.toggle('open', _settingsOpen);
                }
            });
        }

        // 互动提醒开关
        var toggleInput = _panel.querySelector('#notif-toggle-interact');
        if (toggleInput) {
            toggleInput.addEventListener('change', function () {
                if (!window.NotificationBellModule) return;
                var enabled = this.checked;
                if (!window.NotificationBellModule.setInteractionNotifyEnabled(enabled)) {
                    this.checked = !enabled;
                    showStorageFailure('notification.storage_setting_failed');
                }
            });
        }

        var listEl = _panel.querySelector('#notif-list');
        if (listEl) {
            listEl.addEventListener('click', function (event) {
                var trigger = event.target.closest('.notif-system-action');
                if (!trigger || !listEl.contains(trigger)) return;
                var index = Number(trigger.getAttribute('data-message-index'));
                if (!Number.isInteger(index) || !_renderedSystemMessages[index]) return;
                openSystemMessage(_renderedSystemMessages[index]);
            });
        }
    }

    /* ---- 渲染 ---- */

    function updateTabUI() {
        if (!_panel) return;
        var tabs = _panel.querySelectorAll('.notif-tab-btn');
        for (var i = 0; i < tabs.length; i++) {
            var tab = tabs[i];
            tab.classList.toggle('active', tab.getAttribute('data-tab') === _activeTab);
        }
    }

    function updateTabCounts() {
        if (!_panel || !window.NotificationBellModule) return;
        var sysCount = _panel.querySelector('#notif-count-system');
        var intCount = _panel.querySelector('#notif-count-interact');
        var unreadSys = window.NotificationBellModule.getUnreadSystem();
        var unreadInt = window.NotificationBellModule.getUnreadInteract();

        if (sysCount) {
            sysCount.textContent = unreadSys > 0 ? unreadSys : '';
            sysCount.setAttribute('data-count', unreadSys);
        }
        if (intCount) {
            intCount.textContent = unreadInt > 0 ? unreadInt : '';
            intCount.setAttribute('data-count', unreadInt);
        }
    }

    function renderList() {
        if (!isNotificationCenterEnabled()) return;
        if (!_panel || !window.NotificationBellModule) return;
        var listEl = _panel.querySelector('#notif-list');
        if (!listEl) return;

        var msgs = [];
        if (_activeTab === 'system') {
            msgs = window.NotificationBellModule.getSystemMessages();
        } else {
            msgs = window.NotificationBellModule.getInteractMessages();
        }

        // 按时间倒序
        msgs = msgs.slice().sort(function (a, b) {
            return (b.timestamp || 0) - (a.timestamp || 0);
        });
        _renderedSystemMessages = _activeTab === 'system' ? msgs : [];

        if (msgs.length === 0) {
            listEl.innerHTML = renderEmpty();
            return;
        }

        var html = [];
        for (var i = 0; i < msgs.length; i++) {
            if (_activeTab === 'system') {
                html.push(renderSystemItem(msgs[i], i));
            } else {
                html.push(renderInteractItem(msgs[i]));
            }
        }
        listEl.innerHTML = html.join('');
    }

    function renderEmpty() {
        var icon = _activeTab === 'system' ? 'ri-megaphone-line' : 'ri-chat-heart-line';
        var text = _activeTab === 'system'
            ? t('notification.empty_system')
            : t('notification.empty_interact');
        return [
            '<div class="notif-empty">',
            '  <div class="notif-empty-icon"><i class="' + icon + '"></i></div>',
            '  <p class="notif-empty-text">' + text + '</p>',
            '</div>'
        ].join('');
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function renderSystemItem(msg, index) {
        var icon = escapeHtml(msg.icon || 'ri-notification-3-line');
        var title = escapeHtml(msg.title || t('notification.system_default_title'));
        var content = escapeHtml(msg.content || '');
        var time = formatRelativeTime(msg.timestamp);
        return [
            '<button type="button" class="notif-item notif-item-clickable notif-system-action" data-message-index="' + index + '" aria-label="' + escapeHtml(t('notification.view_message', { title: msg.title || t('notification.system_default_title') })) + '">',
            '  <div class="notif-item-icon icon-system"><i class="' + icon + '"></i></div>',
            '  <div class="notif-item-body">',
            '    <p class="notif-item-text">' + title + '</p>',
            '    <p class="notif-item-sub">' + content + '</p>',
            '  </div>',
            '  <span class="notif-item-time">' + time + '</span>',
            '</button>'
        ].join('');
    }

    function openAlertMessage(msg, presentation) {
        if (!window.app || typeof window.app.showAlert !== 'function') return;
        var title = presentation.title || msg.title || t('notification.system_default_title');
        var body = presentation.body || msg.content || '';
        window.app.showAlert(String(title), String(body), 'info');
    }

    var MessagePresentationRegistry = {
        none: function () {},
        'alert/default': openAlertMessage,
        'notice/general': function (msg, presentation) {
            if (!window.NoticeModalModule || typeof window.NoticeModalModule.openNoticeDetail !== 'function') {
                openAlertMessage(msg, presentation);
                return;
            }
            var title = presentation.title || msg.title || t('notification.system_default_title');
            var body = presentation.body || msg.content || '';
            window.NoticeModalModule.openNoticeDetail({ type: 'normal', tag: t('notification.notice_tag'), title: String(title), summary: msg.content || '', content: String(body), date: formatNoticeDate(msg.timestamp) });
        },
        'notice/update': function (msg, presentation) {
            if (!window.NoticeModalModule || typeof window.NoticeModalModule.openNoticeDetail !== 'function') {
                openAlertMessage(msg, presentation);
                return;
            }
            var title = presentation.title || msg.title || t('notification.update_default_title');
            var body = presentation.body || msg.content || '';
            window.NoticeModalModule.openNoticeDetail({ type: 'update', tag: t('notification.update_tag'), title: String(title), summary: msg.content || '', content: String(body), date: formatNoticeDate(msg.timestamp) });
        },
        'themed/sponsor_1': function (msg, presentation) {
            if (!window.app || typeof window.app.showThemedMessage !== 'function') {
                openAlertMessage(msg, presentation);
                return;
            }
            window.app.showThemedMessage({ title: presentation.title || msg.title, message: presentation.body || msg.content || '', variant: 'sponsor_1' });
        }
    };

    function formatNoticeDate(timestamp) {
        var date = new Date(Number(timestamp));
        if (!Number.isFinite(date.getTime())) return '';
        return date.toLocaleDateString(document.documentElement.lang || undefined);
    }

    function openSystemMessage(msg) {
        if (!msg || typeof msg !== 'object') return;
        var presentation = msg.presentation && typeof msg.presentation === 'object'
            ? msg.presentation
            : {};
        var renderer = String(presentation.renderer || 'none');
        var variant = String(presentation.variant || '');
        var registryKey = renderer === 'none' ? 'none' : renderer + '/' + variant;
        var handler = MessagePresentationRegistry[registryKey] || openAlertMessage;
        if (window.NotificationBellModule) {
            window.NotificationBellModule.closePanel();
        }
        handler(msg, presentation);
    }

    function renderInteractItem(msg) {
        var action = msg.action || 'like';
        var iconClass = action === 'reply' ? 'icon-reply' : 'icon-like';
        var iconName = action === 'reply' ? 'ri-reply-line' : 'ri-heart-3-fill';
        var actor = escapeHtml(msg.actor || t('notification.anonymous_user'));
        var actionText = action === 'reply' ? t('notification.replied_comment') : t('notification.liked_comment');
        var noticeTitle = escapeHtml(msg.notice_title || '');
        var contentPreview = escapeHtml(msg.content || '');
        var time = formatRelativeTime(msg.timestamp);

        var subText = noticeTitle ? ('"' + noticeTitle + '"') : '';
        if (contentPreview && action === 'reply') {
            subText = contentPreview;
        }

        return [
            '<div class="notif-item">',
            '  <div class="notif-item-icon ' + iconClass + '"><i class="' + iconName + '"></i></div>',
            '  <div class="notif-item-body">',
            '    <p class="notif-item-text"><strong>' + actor + '</strong> ' + actionText + '</p>',
            '    <p class="notif-item-sub">' + subText + '</p>',
            '  </div>',
            '  <span class="notif-item-time">' + time + '</span>',
            '</div>'
        ].join('');
    }

    /* ---- 面板控制 ---- */

    function open() {
        ensurePanel();
        if (!_panel) return;
        _overlay.classList.add('open');
        _panel.classList.add('open');
        if (window.I18N) I18N.applyToDOM(_panel);

        // 同步设置开关状态
        if (window.NotificationBellModule) {
            var settings = window.NotificationBellModule.getSettings();
            var toggleInput = _panel.querySelector('#notif-toggle-interact');
            if (toggleInput) {
                toggleInput.checked = settings.interaction_notify_enabled;
            }
            window.NotificationBellModule.recalcUnread();
        }

        updateTabUI();
        updateTabCounts();
        renderList();
    }

    function close() {
        if (_overlay) _overlay.classList.remove('open');
        if (_panel) _panel.classList.remove('open');
        _settingsOpen = false;
        var settingsPanel = _panel && _panel.querySelector('#notif-settings-panel');
        if (settingsPanel) settingsPanel.classList.remove('open');
    }

    function refresh() {
        if (!_panel || !_panel.classList.contains('open')) return;
        if (window.NotificationBellModule) {
            window.NotificationBellModule.recalcUnread();
        }
        updateTabCounts();
        renderList();
    }

    /* ---- 导出 ---- */

    function getActiveTab() {
        return _activeTab;
    }

    window.NotificationPanelModule = {
        open: open,
        close: close,
        refresh: refresh,
        getActiveTab: getActiveTab
    };
})();
