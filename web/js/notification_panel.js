/**
 * 通知面板 UI 模块 (Notification Panel Module)
 *
 * 功能定位：
 * - 通知面板的 DOM 创建与渲染
 * - 系统消息 / 互动消息 的分 Tab 展示
 * - 右键消息条调用共用上下文菜单删除本地消息
 * - 设置面板（互动消息提醒开关）
 * - 时间格式化工具
 */
(function () {
    var _panel = null;
    var _overlay = null;
    var _activeTab = 'system';
    var _settingsOpen = false;
    var _renderedSystemMessages = [];
    var _panelOpenTimer = null;
    var _panelHideTimer = null;
    var _escapeBound = false;
    var PANEL_OPEN_DELAY_MS = 80;
    var PANEL_CLOSE_MS = 280;

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
        _panel.addEventListener('contextmenu', function (e) {
            e.preventDefault();
        });

        bindEvents();
        if (window.I18N) I18N.applyToDOM(_panel);
    }

    function buildPanelHTML() {
        return [
            '<div class="notif-panel-header">',
            '  <h3 class="notif-panel-title"><i class="ri-notification-3-line"></i><span data-i18n="notification.title">消息中心</span></h3>',
            '  <div class="notif-panel-actions">',
            '    <button type="button" class="notif-panel-action-btn" id="notif-btn-settings" aria-pressed="false" title="设置" data-i18n-title="notification.settings"><i class="ri-settings-3-line"></i></button>',
            '    <button type="button" class="notif-panel-action-btn" id="notif-btn-mark-read" title="全部已读" data-i18n-title="notification.mark_all_read"><i class="ri-check-double-line"></i></button>',
            '    <button type="button" class="notif-panel-action-btn" id="notif-btn-close" title="关闭" data-i18n-title="common.close"><i class="ri-close-line"></i></button>',
            '  </div>',
            '</div>',
            '<div class="notif-panel-body" id="notif-panel-body">',
            '  <div class="notif-panel-feed">',
            '    <div class="notif-tab-bar">',
            '      <button type="button" class="notif-tab-btn active" data-tab="system">',
            '        <span class="notif-tab-label"><i class="ri-megaphone-line"></i><span data-i18n="notification.system_tab">系统消息</span><span class="notif-tab-count" id="notif-count-system" data-count="0"></span></span>',
            '      </button>',
            '      <button type="button" class="notif-tab-btn" data-tab="interact">',
            '        <span class="notif-tab-label"><i class="ri-chat-heart-line"></i><span data-i18n="notification.interact_tab">互动消息</span><span class="notif-tab-count" id="notif-count-interact" data-count="0"></span></span>',
            '      </button>',
            '    </div>',
            '    <div class="notif-list-wrap" id="notif-list-wrap">',
            '      <div class="notif-list-pane active" data-pane="system"><div class="notif-list" id="notif-list-system"></div></div>',
            '      <div class="notif-list-pane" data-pane="interact"><div class="notif-list" id="notif-list-interact"></div></div>',
            '    </div>',
            '  </div>',
            '  <div class="notif-settings-page" id="notif-settings-page">',
            '    <p class="notif-settings-kicker" data-i18n="notification.settings">消息设置</p>',
            '    <div class="notif-settings-card">',
            '      <div class="notif-settings-row">',
            '        <span class="notif-settings-label"><i class="ri-hearts-line"></i><span data-i18n="notification.interact_notify">互动消息提醒</span></span>',
            '        <label class="notif-toggle-switch">',
            '          <input type="checkbox" id="notif-toggle-interact" checked>',
            '          <span class="notif-toggle-slider"></span>',
            '        </label>',
            '      </div>',
            '      <p class="notif-settings-hint" data-i18n="notification.interact_notify_hint">关闭后，互动消息仍会保留在消息中心，但不会让铃铛提醒。</p>',
            '    </div>',
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
                updateSettingsUI();
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

        var listWrap = _panel.querySelector('#notif-list-wrap');
        if (listWrap) {
            listWrap.addEventListener('click', function (event) {
                var trigger = event.target.closest('.notif-system-action');
                if (!trigger || !listWrap.contains(trigger)) return;
                var index = Number(trigger.getAttribute('data-message-index'));
                if (!Number.isInteger(index) || !_renderedSystemMessages[index]) return;
                openSystemMessage(_renderedSystemMessages[index]);
            });
            listWrap.addEventListener('contextmenu', function (event) {
                var item = event.target.closest('.notif-item');
                if (!item || !listWrap.contains(item)) return;
                var messageId = String(item.getAttribute('data-message-id') || '');
                var category = String(item.getAttribute('data-message-category') || 'system');
                if (!messageId) return;
                if (!window.app || typeof window.app.showContextMenu !== 'function') return;
                event.preventDefault();
                event.stopPropagation();
                window.app.showContextMenu(event, [{
                    label: t('notification.delete'),
                    icon: 'ri-delete-bin-line',
                    description: t('notification.delete_desc'),
                    danger: true,
                    action: function () {
                        if (!window.NotificationBellModule || typeof window.NotificationBellModule.deleteMessage !== 'function') return;
                        var result = window.NotificationBellModule.deleteMessage({
                            id: messageId,
                            category: category
                        });
                        if (result && result.success) return;
                        if (window.app && typeof window.app.showToast === 'function') {
                            window.app.showToast({
                                type: 'error',
                                title: t('notification.delete_failed')
                            });
                        }
                    }
                }], { compact: true });
            });
        }

        if (!_escapeBound) {
            document.addEventListener('keydown', function (event) {
                if (event.key !== 'Escape') return;
                if (document.querySelector('.modal-overlay.show')) return;
                if (!window.NotificationBellModule || !window.NotificationBellModule.isPanelOpen()) return;
                window.NotificationBellModule.closePanel();
            });
            _escapeBound = true;
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
        var panes = _panel.querySelectorAll('.notif-list-pane');
        for (var j = 0; j < panes.length; j++) {
            var pane = panes[j];
            pane.classList.toggle('active', pane.getAttribute('data-pane') === _activeTab);
        }
    }

    function updateSettingsUI() {
        if (!_panel) return;
        var body = _panel.querySelector('#notif-panel-body');
        var settingsBtn = _panel.querySelector('#notif-btn-settings');
        if (body) {
            body.classList.toggle('settings-open', _settingsOpen);
        }
        if (settingsBtn) {
            settingsBtn.classList.toggle('active', _settingsOpen);
            settingsBtn.setAttribute('aria-pressed', _settingsOpen ? 'true' : 'false');
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

    function renderLists() {
        if (!isNotificationCenterEnabled()) return;
        if (!_panel || !window.NotificationBellModule) return;
        var systemList = _panel.querySelector('#notif-list-system');
        var interactList = _panel.querySelector('#notif-list-interact');
        if (!systemList || !interactList) return;

        var systemMessages = window.NotificationBellModule.getSystemMessages().slice().sort(function (a, b) {
            return (b.timestamp || 0) - (a.timestamp || 0);
        });
        _renderedSystemMessages = systemMessages;

        if (systemMessages.length === 0) {
            systemList.innerHTML = renderEmpty(true);
        } else {
            var html = [];
            for (var i = 0; i < systemMessages.length; i++) {
                html.push(renderSystemItem(systemMessages[i], i));
            }
            systemList.innerHTML = html.join('');
        }

        interactList.innerHTML = renderEmpty(false);
    }

    function renderEmpty(isSystem) {
        var icon = isSystem ? 'ri-megaphone-line' : 'ri-chat-heart-line';
        var text = isSystem
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

    function sanitizeCssColor(value) {
        var color = String(value || '').trim();
        if (/^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(color)) return color;
        if (/^rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*(?:,\s*(?:0|1|0?\.\d+)\s*)?\)$/.test(color)) return color;
        return '';
    }

    function renderSystemItem(msg, index) {
        var visualType = String(msg.type || 'normal');
        var typeMeta = window.NoticeDataModule && typeof window.NoticeDataModule.getNoticeTypeMeta === 'function'
            ? window.NoticeDataModule.getNoticeTypeMeta(visualType)
            : { tagClass: 'notice-tag-normal', iconClass: 'ri-notification-3-line' };
        var icon = escapeHtml(msg.icon || typeMeta.iconClass);
        var tag = escapeHtml(msg.tag || (visualType === 'update' ? t('notification.update_tag') : t('notification.notice_tag')));
        var title = escapeHtml(msg.title || t('notification.system_default_title'));
        var content = escapeHtml(msg.content || '');
        var time = formatRelativeTime(msg.timestamp);
        var timeSizer = escapeHtml(t('notification.time_minutes_ago', { count: 20 }));
        var iconColor = sanitizeCssColor(msg.icon_color);
        var iconBg = sanitizeCssColor(msg.icon_bg);
        var tagColor = sanitizeCssColor(msg.tag_color);
        var tagBg = sanitizeCssColor(msg.tag_bg);
        var iconShape = String(msg.icon_shape || '') === 'circle' ? 'circle' : 'rounded';
        var iconStyle = (iconColor ? 'color:' + iconColor + ';' : '') + (iconBg ? 'background:' + iconBg + ';' : '') + (iconShape === 'circle' ? 'border-radius:999px;' : '');
        var tagStyle = (tagColor ? 'color:' + tagColor + ';' : '') + (tagBg ? 'background:' + tagBg + ';' : '');
        var unreadClass = msg.unread === false ? '' : ' notif-item-unread';
        var shapeClass = iconShape === 'circle' ? ' icon-shape-circle' : '';
        return [
            '<button type="button" class="notif-item notif-item-clickable notif-system-action' + unreadClass + '" data-message-id="' + escapeHtml(String(msg.id || '')) + '" data-message-category="system" data-message-index="' + index + '" aria-label="' + escapeHtml(t('notification.view_message', { title: msg.title || t('notification.system_default_title') })) + '">',
            '  <div class="notif-item-icon icon-system' + shapeClass + '"' + (iconStyle ? ' style="' + iconStyle + '"' : '') + '><i class="' + icon + '"></i></div>',
            '  <div class="notif-item-body">',
            '    <div class="notif-item-title-row"><span class="notice-tag ' + escapeHtml(typeMeta.tagClass) + '"' + (tagStyle ? ' style="' + tagStyle + '"' : '') + '>' + tag + '</span><p class="notif-item-text">' + title + '</p></div>',
            '    <p class="notif-item-sub">' + content + '</p>',
            '  </div>',
            '  <span class="notif-item-time"><span class="notif-item-time-sizer">' + timeSizer + '</span><span class="notif-item-time-text">' + escapeHtml(time) + '</span></span>',
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
        if (window.NotificationBellModule && !window.NotificationBellModule.markSystemMessageRead(msg)) return;
        if (renderer !== 'none' && window.NotificationBellModule && typeof window.NotificationBellModule.dismissForOverlay === 'function') {
            window.NotificationBellModule.dismissForOverlay();
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
        if (_panelOpenTimer) clearTimeout(_panelOpenTimer);
        if (_panelHideTimer) clearTimeout(_panelHideTimer);
        _panel.classList.remove('hiding');
        _overlay.classList.add('open');
        if (window.I18N) I18N.applyToDOM(_panel);

        _panelOpenTimer = setTimeout(function () {
            if (_panel) _panel.classList.add('open');
            _panelOpenTimer = null;
        }, PANEL_OPEN_DELAY_MS);

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
        updateSettingsUI();
        updateTabCounts();
        renderLists();
    }

    function dismissContextMenu() {
        if (window.app && typeof window.app.hideContextMenu === 'function') {
            window.app.hideContextMenu();
            return;
        }
        var existing = document.querySelector('.context-menu');
        if (existing) existing.remove();
    }

    function close() {
        dismissContextMenu();
        if (_panelOpenTimer) {
            clearTimeout(_panelOpenTimer);
            _panelOpenTimer = null;
        }
        if (_panelHideTimer) clearTimeout(_panelHideTimer);
        if (_overlay) _overlay.classList.remove('open');
        if (_panel) {
            _panel.classList.add('hiding');
            _panel.classList.remove('open');
        }
        _settingsOpen = false;
        updateSettingsUI();
        _panelHideTimer = setTimeout(function () {
            if (_panel) _panel.classList.remove('hiding');
            _panelHideTimer = null;
        }, PANEL_CLOSE_MS);
    }

    function refresh() {
        if (!_panel || !_panel.classList.contains('open')) return;
        if (window.NotificationBellModule) {
            window.NotificationBellModule.recalcUnread();
        }
        updateTabCounts();
        renderLists();
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
