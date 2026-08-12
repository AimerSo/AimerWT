/**
 * 通知铃铛模块 (Notification Bell Module)
 *
 * 功能定位：
 * - 右下角铃铛按钮的显隐控制（鼠标接近检测）
 * - 新消息到达时铃铛状态管理（晃动、红点）
 * - 通知数据的存储与容量管理（系统与互动消息均≤10条、15天过期）
 * - 用户偏好设置（互动消息提醒开关）
 * - 对外提供消息推送接口供 Python 桥接层和 WebSocket 调用
 */
(function () {
    var STORAGE_KEY_SYSTEM = 'aimerwt_notification_system_msgs';
    var STORAGE_KEY_INTERACT = 'aimerwt_notification_interact_msgs';
    var STORAGE_KEY_SETTINGS = 'aimerwt_notification_settings';
    var STORAGE_KEY_READ_TS = 'aimerwt_notification_last_read_ts';
    var STORAGE_KEY_READ_TS_SYSTEM = 'aimerwt_notification_system_last_read_ts';
    var STORAGE_KEY_READ_TS_INTERACT = 'aimerwt_notification_interact_last_read_ts';

    var MAX_INTERACT_MSGS = 10;
    var MAX_SYSTEM_MSGS = 10;
    var MESSAGE_TTL_DAYS = 15;
    var SYSTEM_MESSAGE_ICONS = {
        'ri-notification-3-line': true,
        'ri-information-line': true,
        'ri-megaphone-line': true,
        'ri-gift-line': true,
        'ri-error-warning-line': true
    };
    var PROXIMITY_PAD = 50;
    var _bellBtn = null;
    var _panelOpen = false;
    var _unreadSystem = 0;
    var _unreadInteract = 0;
    var _proximityBound = false;
    var _clickBound = false;
    var _ringTimer = null;

    function isNotificationCenterEnabled() {
        if (window.app && typeof window.app.getServerUserFeatures === 'function') {
            return window.app.getServerUserFeatures('notification_center_enabled');
        }
        if (window._aimerUserFeatures && window._aimerUserFeatures.notification_center_enabled === false) {
            return false;
        }
        return false;
    }

    /* ---- localStorage 读写 ---- */

    function loadJSON(key, fallback) {
        try {
            var raw = localStorage.getItem(key);
            if (!raw) return fallback;
            return JSON.parse(raw);
        } catch (_e) {
            return fallback;
        }
    }

    function saveJSON(key, data) {
        try {
            localStorage.setItem(key, JSON.stringify(data));
            return true;
        } catch (_e) {
            return false;
        }
    }

    function saveStorageValues(values) {
        var snapshots = [];
        try {
            values.forEach(function (entry) {
                snapshots.push({ key: entry.key, value: localStorage.getItem(entry.key) });
                localStorage.setItem(entry.key, JSON.stringify(entry.data));
            });
            return true;
        } catch (_e) {
            snapshots.forEach(function (snapshot) {
                try {
                    if (snapshot.value === null) localStorage.removeItem(snapshot.key);
                    else localStorage.setItem(snapshot.key, snapshot.value);
                } catch (_rollbackError) {}
            });
            return false;
        }
    }

    function t(key, params) {
        return window.I18N && typeof I18N.t === 'function' ? I18N.t(key, params) : key;
    }

    function showStorageFailure(key) {
        if (window.app && typeof window.app.showAlert === 'function') {
            window.app.showAlert(t('common.error'), t(key), 'error');
        }
    }

    /* ---- 数据管理 ---- */

    function getSettings() {
        var defaults = { interaction_notify_enabled: true };
        var stored = loadJSON(STORAGE_KEY_SETTINGS, {});
        return Object.assign({}, defaults, stored);
    }

    function saveSettings(settings) {
        return saveJSON(STORAGE_KEY_SETTINGS, settings);
    }

    function getSystemMessages() {
        return loadJSON(STORAGE_KEY_SYSTEM, []);
    }

    function getInteractMessages() {
        return loadJSON(STORAGE_KEY_INTERACT, []);
    }

    function saveSystemMessages(msgs) {
        return saveJSON(STORAGE_KEY_SYSTEM, msgs);
    }

    function saveInteractMessages(msgs) {
        return saveJSON(STORAGE_KEY_INTERACT, msgs);
    }

    function buildSystemMessageKey(msg) {
        if (!msg || typeof msg !== 'object') return '';
        if (msg.notification_id) return 'notification:' + String(msg.notification_id);
        if (msg.dedupe_key) return String(msg.dedupe_key);
        if (msg.source_id) return 'id:' + String(msg.source_id);
        if (msg.id != null && !String(msg.id).startsWith('sys_')) return 'id:' + String(msg.id);
        var sourceTimestamp = msg.source_timestamp != null ? msg.source_timestamp : msg.timestamp;
        return [
            'content',
            String(msg.title || '系统通知'),
            String(msg.content || ''),
            String(msg.icon || 'ri-notification-3-line'),
            String(sourceTimestamp || '')
        ].join('|');
    }

    function buildSystemMessageContentKey(msg) {
        if (!msg || typeof msg !== 'object') return '';
        return [
            'content',
            String(msg.title || '系统通知'),
            String(msg.content || ''),
            String(msg.icon || 'ri-notification-3-line')
        ].join('|');
    }

    function getReadStorageKey(tab) {
        return tab === 'interact' ? STORAGE_KEY_READ_TS_INTERACT : STORAGE_KEY_READ_TS_SYSTEM;
    }

    function getLastReadTimestamp(tab) {
        var key = getReadStorageKey(tab);
        try {
            var raw = localStorage.getItem(key);
            if (raw !== null) return Number(JSON.parse(raw)) || 0;
        } catch (_e) {}
        return Number(loadJSON(STORAGE_KEY_READ_TS, 0)) || 0;
    }

    function getLatestReceivedTimestamp(tab) {
        var messages = tab === 'interact' ? getInteractMessages() : getSystemMessages();
        return messages.reduce(function (latest, message) {
            return Math.max(latest, Number(message && message.received_at) || 0);
        }, Date.now());
    }

    function setReadTimestamps(tabs) {
        return saveStorageValues(tabs.map(function (tab) {
            return { key: getReadStorageKey(tab), data: getLatestReceivedTimestamp(tab) };
        }));
    }

    function normalizeStoredTimestamp(message, now) {
        var timestamp = Number(message.timestamp || message.created_at);
        if (!Number.isFinite(timestamp) || timestamp <= 0) timestamp = now;
        message.timestamp = timestamp;
        if (!Number.isFinite(Number(message.received_at)) || Number(message.received_at) <= 0) {
            message.received_at = timestamp;
        }
        if (!Number(message.expires_at)) {
            message.expires_at = timestamp + (MESSAGE_TTL_DAYS * 24 * 60 * 60 * 1000);
        }
        return timestamp;
    }

    function pruneExpiredSystemMessages() {
        var msgs = getSystemMessages();
        var now = Date.now();
        var cutoff = now - (MESSAGE_TTL_DAYS * 24 * 60 * 60 * 1000);
        var normalized = false;
        var filtered = msgs.filter(function (m) {
            if (!m || typeof m !== 'object') return false;
            var oldTimestamp = m.timestamp;
            var oldExpiresAt = m.expires_at;
            var oldReceivedAt = m.received_at;
            var timestamp = normalizeStoredTimestamp(m, now);
            if (oldTimestamp !== timestamp || oldExpiresAt !== m.expires_at || oldReceivedAt !== m.received_at) normalized = true;
            if (m.expires_at && Number(m.expires_at) <= now) return false;
            return timestamp > cutoff;
        });
        if (normalized || filtered.length !== msgs.length) {
            saveSystemMessages(filtered);
        }
        return filtered;
    }

    function pruneExpiredInteractMessages() {
        var msgs = getInteractMessages();
        var now = Date.now();
        var cutoff = now - (MESSAGE_TTL_DAYS * 24 * 60 * 60 * 1000);
        var normalized = false;
        var filtered = msgs.filter(function (m) {
            if (!m || typeof m !== 'object') return false;
            var oldTimestamp = m.timestamp;
            var oldExpiresAt = m.expires_at;
            var oldReceivedAt = m.received_at;
            var timestamp = normalizeStoredTimestamp(m, now);
            if (oldTimestamp !== timestamp || oldExpiresAt !== m.expires_at || oldReceivedAt !== m.received_at) normalized = true;
            return Number(m.expires_at) > now && timestamp > cutoff;
        });
        if (normalized || filtered.length !== msgs.length) saveInteractMessages(filtered);
        return filtered;
    }

    /** 计算未读数 */
    function recalcUnread() {
        var systemLastRead = getLastReadTimestamp('system');
        var interactLastRead = getLastReadTimestamp('interact');
        var sysMsgs = pruneExpiredSystemMessages();
        var intMsgs = pruneExpiredInteractMessages();

        _unreadSystem = 0;
        _unreadInteract = 0;

        sysMsgs.forEach(function (m) {
            if (m && Number(m.received_at) > systemLastRead) _unreadSystem++;
        });
        intMsgs.forEach(function (m) {
            if (m && !m.notification_silent && Number(m.received_at) > interactLastRead) _unreadInteract++;
        });
    }

    function setInteractionNotifyEnabled(enabled) {
        var settings = getSettings();
        settings.interaction_notify_enabled = Boolean(enabled);
        var values = [{ key: STORAGE_KEY_SETTINGS, data: settings }];
        if (!enabled) {
            values.push({ key: STORAGE_KEY_READ_TS_INTERACT, data: getLatestReceivedTimestamp('interact') });
        }
        if (!saveStorageValues(values)) return false;
        recalcUnread();
        updateBellState();
        if (_panelOpen && window.NotificationPanelModule) window.NotificationPanelModule.refresh();
        return true;
    }

    function getTotalUnread() {
        return _unreadSystem + _unreadInteract;
    }

    /* ---- 铃铛 DOM ---- */

    function getBellButton() {
        if (_bellBtn && document.body.contains(_bellBtn)) return _bellBtn;
        _bellBtn = document.getElementById('btn-notification-bell');
        return _bellBtn;
    }

    function updateBellState() {
        var btn = getBellButton();
        if (!btn) return;
        if (!isNotificationCenterEnabled()) {
            btn.style.display = 'none';
            btn.classList.remove('bell-has-new', 'bell-panel-open', 'bell-ringing', 'near');
            return;
        }
        btn.style.display = '';
        var hasNew = getTotalUnread() > 0;
        btn.classList.toggle('bell-has-new', hasNew);
        btn.classList.toggle('bell-panel-open', _panelOpen);
    }

    function triggerRing() {
        if (!isNotificationCenterEnabled()) return;
        var btn = getBellButton();
        if (!btn) return;
        btn.classList.remove('bell-ringing');
        void btn.offsetWidth; // 重置动画
        btn.classList.add('bell-ringing');
        if (_ringTimer) clearTimeout(_ringTimer);
        _ringTimer = setTimeout(function () {
            btn.classList.remove('bell-ringing');
            _ringTimer = null;
        }, 2500);
    }

    function stopRing() {
        var btn = getBellButton();
        if (!btn) return;
        btn.classList.remove('bell-ringing');
        if (_ringTimer) {
            clearTimeout(_ringTimer);
            _ringTimer = null;
        }
    }

    /* ---- 鼠标接近检测 ---- */

    function updateProximity(clientX, clientY) {
        if (!isNotificationCenterEnabled()) return;
        var btn = getBellButton();
        if (!btn) return;
        // 有新消息或面板打开时无需接近检测（按钮已可见）
        if (btn.classList.contains('bell-has-new') || btn.classList.contains('bell-panel-open')) return;
        var rect = btn.getBoundingClientRect();
        var insideExpanded =
            clientX >= rect.left - PROXIMITY_PAD &&
            clientX <= rect.right + PROXIMITY_PAD &&
            clientY >= rect.top - PROXIMITY_PAD &&
            clientY <= rect.bottom + PROXIMITY_PAD;
        btn.classList.toggle('near', insideExpanded);
    }

    function bindProximity() {
        if (_proximityBound) return;
        var btn = getBellButton();
        if (!btn) return;
        _proximityBound = true;
        document.addEventListener('mousemove', function (e) {
            updateProximity(e.clientX, e.clientY);
        });
    }

    /* ---- 面板控制 ---- */

    function openPanel() {
        if (!isNotificationCenterEnabled()) return;
        _panelOpen = true;
        stopRing();
        updateBellState();
        if (window.NotificationPanelModule) {
            window.NotificationPanelModule.open();
        }
    }

    function closePanel(activeTab) {
        _panelOpen = false;
        var tab = activeTab;
        if (!tab && window.NotificationPanelModule && typeof window.NotificationPanelModule.getActiveTab === 'function') {
            tab = window.NotificationPanelModule.getActiveTab();
        }
        var saved = setReadTimestamps([tab === 'interact' ? 'interact' : 'system']);
        recalcUnread();
        updateBellState();
        if (window.NotificationPanelModule) {
            window.NotificationPanelModule.close();
        }
        if (!saved) showStorageFailure('notification.storage_read_failed');
        return saved;
    }

    function hidePanel() {
        _panelOpen = false;
        stopRing();
        if (window.NotificationPanelModule) window.NotificationPanelModule.close();
        updateBellState();
    }

    function togglePanel() {
        if (!isNotificationCenterEnabled()) return;
        if (_panelOpen) {
            closePanel();
        } else {
            openPanel();
        }
    }

    /* ---- 消息推送接口 ---- */

    /**
     * 推送一条系统消息
     * @param {Object} msg - { title, content, icon?, timestamp? }
     */
    function pushSystemMessage(msg) {
        if (!msg || typeof msg !== 'object') return { success: false, code: 'invalid', message: '系统消息格式无效' };
        var receivedAt = Math.max(Date.now(), getLastReadTimestamp('system') + 1);
        var dedupeKey = buildSystemMessageKey(msg);
        var contentKey = buildSystemMessageContentKey(msg);
        var hasSourceId = msg.notification_id || msg.id != null || msg.source_id;
        var msgs = pruneExpiredSystemMessages();
        if (dedupeKey && msgs.some(function (m) {
            return buildSystemMessageKey(m) === dedupeKey ||
                (!hasSourceId && buildSystemMessageContentKey(m) === contentKey);
        })) {
            return { success: true, code: 'duplicate', message: '消息已存在' };
        }
        var presentation = msg.presentation && typeof msg.presentation === 'object'
            ? msg.presentation
            : {};
        var renderer = String(presentation.renderer || 'none');
        var variant = String(presentation.variant || '');
        var validPresentation = (renderer === 'none' && variant === '') ||
            (renderer === 'alert' && (variant === '' || variant === 'default')) ||
            (renderer === 'notice' && (variant === 'general' || variant === 'update')) ||
            (renderer === 'themed' && variant === 'sponsor_1');
        if (!validPresentation) {
            renderer = 'alert';
            variant = 'default';
        }
        if (renderer === 'alert' && !variant) variant = 'default';
        var normalizedPresentation = {
            renderer: renderer,
            variant: variant,
            title: String(presentation.title || msg.title || '系统通知'),
            body: String(presentation.body || msg.summary || msg.content || '')
        };
        var message = {
            id: 'sys_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6),
            notification_id: String(msg.notification_id || ''),
            source_id: String(msg.notification_id || msg.source_id || msg.id || ''),
            source_timestamp: msg.created_at || msg.timestamp || '',
            dedupe_key: dedupeKey,
            type: 'system',
            title: String(msg.title || '系统通知'),
            content: String(msg.summary || msg.content || ''),
            icon: SYSTEM_MESSAGE_ICONS[msg.icon] ? msg.icon : 'ri-notification-3-line',
            timestamp: msg.created_at || msg.timestamp || Date.now(),
            received_at: receivedAt,
            expires_at: Number(msg.expires_at) || 0,
            presentation: normalizedPresentation
        };
        msgs.push(message);
        // 保留最新的 MAX_SYSTEM_MSGS 条
        if (msgs.length > MAX_SYSTEM_MSGS) {
            msgs = msgs.slice(msgs.length - MAX_SYSTEM_MSGS);
        }
        if (!saveSystemMessages(msgs)) {
            return { success: false, code: 'storage_failed', message: '系统消息保存失败' };
        }
        recalcUnread();
        updateBellState();
        if (isNotificationCenterEnabled()) triggerRing();
        if (_panelOpen && window.NotificationPanelModule) {
            window.NotificationPanelModule.refresh();
        }
        return { success: true, code: 'saved', message: '系统消息已保存' };
    }

    /**
     * 批量推送系统消息
     * @param {Array} msgList
     */
    function pushSystemMessages(msgList) {
        if (!isNotificationCenterEnabled()) return;
        if (!Array.isArray(msgList)) return;
        msgList.forEach(function (m) { pushSystemMessage(m); });
    }

    /**
     * 推送一条互动消息（点赞/回复）
     * @param {Object} msg - { action: "like"|"reply", actor, content?, notice_title?, timestamp? }
     */
    function pushInteractionMessage(msg) {
        if (!msg || typeof msg !== 'object') return { success: false, code: 'invalid', message: '互动消息格式无效' };
        var settings = getSettings();
        var notificationSilent = !settings.interaction_notify_enabled;
        var receivedAt = Math.max(Date.now(), getLastReadTimestamp('interact') + 1);

        var message = {
            id: 'int_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6),
            type: 'interaction',
            action: String(msg.action || 'like'),
            actor: String(msg.actor || ''),
            content: String(msg.content || ''),
            notice_title: String(msg.notice_title || ''),
            timestamp: Number(msg.created_at || msg.timestamp) || Date.now(),
            received_at: receivedAt,
            notification_silent: notificationSilent,
            expires_at: Number(msg.expires_at) || 0
        };
        if (!message.expires_at) message.expires_at = message.timestamp + (MESSAGE_TTL_DAYS * 24 * 60 * 60 * 1000);
        var msgs = pruneExpiredInteractMessages();
        msgs.push(message);
        // FIFO: 保留最新的 MAX_INTERACT_MSGS 条
        if (msgs.length > MAX_INTERACT_MSGS) {
            msgs = msgs.slice(msgs.length - MAX_INTERACT_MSGS);
        }
        if (!saveInteractMessages(msgs)) {
            return { success: false, code: 'storage_failed', message: '互动消息保存失败' };
        }
        recalcUnread();
        updateBellState();
        if (!notificationSilent && isNotificationCenterEnabled()) triggerRing();
        if (_panelOpen && window.NotificationPanelModule) {
            window.NotificationPanelModule.refresh();
        }
        return {
            success: true,
            code: notificationSilent ? 'saved_silent' : 'saved',
            message: notificationSilent ? '互动消息已静默保存' : '互动消息已保存'
        };
    }

    /** 标记全部已读 */
    function markAllRead() {
        var saved = setReadTimestamps(['system', 'interact']);
        recalcUnread();
        updateBellState();
        stopRing();
        if (_panelOpen && window.NotificationPanelModule) {
            window.NotificationPanelModule.refresh();
        }
        if (!saved) showStorageFailure('notification.storage_read_failed');
        return saved;
    }

    function revokeSystemNotification(payload) {
        var notificationId = payload && typeof payload === 'object'
            ? String(payload.notification_id || '')
            : String(payload || '');
        if (!notificationId) {
            return { success: false, code: 'invalid', message: '撤回消息标识无效' };
        }
        var msgs = getSystemMessages();
        var filtered = msgs.filter(function (message) {
            return String(message.notification_id || message.source_id || '') !== notificationId;
        });
        if (filtered.length === msgs.length) {
            return { success: true, code: 'not_found', message: '消息已不存在' };
        }
        if (!saveSystemMessages(filtered)) {
            return { success: false, code: 'storage_failed', message: '撤回消息保存失败' };
        }
        recalcUnread();
        updateBellState();
        if (_panelOpen && window.NotificationPanelModule) {
            window.NotificationPanelModule.refresh();
        }
        return { success: true, code: 'revoked', message: '消息已撤回' };
    }

    /* ---- 初始化 ---- */

    function init() {
        var btn = getBellButton();
        if (!isNotificationCenterEnabled()) {
            hidePanel();
            if (btn) btn.style.display = 'none';
            return;
        }
        pruneExpiredSystemMessages();
        pruneExpiredInteractMessages();
        recalcUnread();
        if (btn && !_clickBound) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                togglePanel();
            });
            _clickBound = true;
        }
        bindProximity();
        updateBellState();
    }

    // DOM 就绪后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        // setTimeout 以确保所有脚本加载完毕
        setTimeout(init, 0);
    }

    /* ---- 导出 ---- */

    window.NotificationBellModule = {
        pushSystemMessage: pushSystemMessage,
        pushSystemMessages: pushSystemMessages,
        pushInteractionMessage: pushInteractionMessage,
        revokeSystemNotification: revokeSystemNotification,
        markAllRead: markAllRead,
        updateProximity: updateProximity,
        openPanel: openPanel,
        closePanel: closePanel,
        togglePanel: togglePanel,
        getSystemMessages: getSystemMessages,
        getInteractMessages: getInteractMessages,
        getSettings: getSettings,
        saveSettings: saveSettings,
        setInteractionNotifyEnabled: setInteractionNotifyEnabled,
        getTotalUnread: getTotalUnread,
        getUnreadSystem: function () { return _unreadSystem; },
        getUnreadInteract: function () { return _unreadInteract; },
        isPanelOpen: function () { return _panelOpen; },
        recalcUnread: recalcUnread,
        updateBellState: updateBellState,
        triggerRing: triggerRing,
        init: init
    };
})();
