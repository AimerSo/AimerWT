/**
 * 通知铃铛模块 (Notification Bell Module)
 *
 * 功能定位：
 * - 右下角铃铛按钮的显隐控制（鼠标接近检测）
 * - 新消息到达时铃铛状态管理（晃动、红点）
 * - 通知数据的存储与容量管理（系统与互动消息均≤10条、15天过期）
 * - 用户偏好设置（互动消息提醒开关）
 * - 前景弹窗出现时暂时收起消息中心，关闭后恢复
 * - 本地删除消息，并用 tombstone 避免广播通知再次写入
 * - 对外提供消息推送接口供 Python 桥接层和 WebSocket 调用
 */
(function () {
    var STORAGE_KEY_SYSTEM = 'aimerwt_notification_system_msgs';
    var STORAGE_KEY_INTERACT = 'aimerwt_notification_interact_msgs';
    var STORAGE_KEY_SETTINGS = 'aimerwt_notification_settings';
    var STORAGE_KEY_DELETED = 'aimerwt_notification_deleted_keys';
    var STORAGE_KEY_READ_TS = 'aimerwt_notification_last_read_ts';
    var STORAGE_KEY_READ_TS_SYSTEM = 'aimerwt_notification_system_last_read_ts';
    var STORAGE_KEY_READ_TS_INTERACT = 'aimerwt_notification_interact_last_read_ts';

    var MAX_INTERACT_MSGS = 10;
    var MAX_SYSTEM_MSGS = 10;
    var MAX_DELETED_KEYS = 40;
    var MESSAGE_TTL_DAYS = 15;
    var INTERACTION_RING_MS = 5000;
    var SYSTEM_MESSAGE_ICONS = {
        'ri-notification-3-line': true,
        'ri-information-line': true,
        'ri-megaphone-line': true,
        'ri-gift-line': true,
        'ri-error-warning-line': true,
        'ri-bug-line': true,
        'ri-markdown-line': true
    };
    var SYSTEM_MESSAGE_TYPES = {
        normal: true,
        update: true,
        urgent: true,
        event: true,
        bonus: true
    };
    var PROXIMITY_PAD = 50;
    var _bellBtn = null;
    var _panelOpen = false;
    var _unreadSystem = 0;
    var _unreadInteract = 0;
    var _proximityBound = false;
    var _clickBound = false;
    var _overlayWatcherBound = false;
    var _overlaySyncRaf = 0;
    var _resumePanelAfterOverlay = false;
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

    function getDeletedRecords() {
        var records = loadJSON(STORAGE_KEY_DELETED, []);
        return Array.isArray(records) ? records : [];
    }

    function pruneDeletedRecords() {
        var now = Date.now();
        var cutoff = now - (MESSAGE_TTL_DAYS * 24 * 60 * 60 * 1000);
        var records = getDeletedRecords().filter(function (record) {
            return record && record.key && Number(record.at) > cutoff;
        });
        if (records.length > MAX_DELETED_KEYS) {
            records = records.slice(records.length - MAX_DELETED_KEYS);
        }
        return records;
    }

    function mergeDeletedKeys(keys) {
        var records = pruneDeletedRecords();
        var seen = {};
        records.forEach(function (record) {
            seen[record.key] = true;
        });
        var now = Date.now();
        (keys || []).forEach(function (key) {
            var normalized = String(key || '').trim();
            if (!normalized || seen[normalized]) return;
            seen[normalized] = true;
            records.push({ key: normalized, at: now });
        });
        if (records.length > MAX_DELETED_KEYS) {
            records = records.slice(records.length - MAX_DELETED_KEYS);
        }
        return records;
    }

    function collectSystemTombstoneKeys(msg) {
        var keys = [];
        var dedupeKey = buildSystemMessageKey(msg);
        var contentKey = buildSystemMessageContentKey(msg);
        if (dedupeKey) keys.push(dedupeKey);
        if (contentKey && contentKey !== dedupeKey) keys.push(contentKey);
        if (msg && msg.id) keys.push('local:' + String(msg.id));
        return keys;
    }

    function isTombstonedSystemMessage(msg) {
        var records = pruneDeletedRecords();
        if (!records.length) return false;
        var seen = {};
        records.forEach(function (record) {
            seen[record.key] = true;
        });
        return collectSystemTombstoneKeys(msg).some(function (key) {
            return seen[key];
        });
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
            String(msg.icon || 'ri-notification-3-line'),
            String(msg.type || ''),
            String(msg.tag || ''),
            String(msg.icon_color || ''),
            String(msg.icon_bg || ''),
            String(msg.icon_shape || ''),
            String(msg.tag_color || ''),
            String(msg.tag_bg || '')
        ].join('|');
    }

    function sanitizeCssColor(value) {
        var color = String(value || '').trim();
        if (/^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(color)) return color;
        if (/^rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*(?:,\s*(?:0|1|0?\.\d+)\s*)?\)$/.test(color)) return color;
        return '';
    }

    function normalizeIconShape(value) {
        return String(value || '').trim() === 'circle' ? 'circle' : 'rounded';
    }

    function normalizeSystemMessageType(type, presentation) {
        var normalized = String(type || '').trim().toLowerCase();
        if (SYSTEM_MESSAGE_TYPES[normalized]) return normalized;
        var renderer = String(presentation && presentation.renderer || '');
        var variant = String(presentation && presentation.variant || '');
        return renderer === 'notice' && variant === 'update' ? 'update' : 'normal';
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

    function normalizeStoredReadState(message, lastReadTimestamp, now, notificationSilent) {
        var changed = false;
        if (typeof message.unread !== 'boolean') {
            message.unread = !notificationSilent && Number(message.received_at) > lastReadTimestamp;
            changed = true;
        }
        if (message.unread) {
            if (Number(message.read_at) !== 0) {
                message.read_at = 0;
                changed = true;
            }
        } else if (!Number.isFinite(Number(message.read_at)) || Number(message.read_at) <= 0) {
            message.read_at = Number(message.received_at) || now;
            changed = true;
        }
        return changed;
    }

    function pruneExpiredSystemMessages() {
        var msgs = getSystemMessages();
        var now = Date.now();
        var cutoff = now - (MESSAGE_TTL_DAYS * 24 * 60 * 60 * 1000);
        var lastReadTimestamp = getLastReadTimestamp('system');
        var normalized = false;
        var filtered = msgs.filter(function (m) {
            if (!m || typeof m !== 'object') return false;
            var oldTimestamp = m.timestamp;
            var oldExpiresAt = m.expires_at;
            var oldReceivedAt = m.received_at;
            var timestamp = normalizeStoredTimestamp(m, now);
            if (oldTimestamp !== timestamp || oldExpiresAt !== m.expires_at || oldReceivedAt !== m.received_at) normalized = true;
            if (m.expires_at && Number(m.expires_at) <= now) return false;
            if (normalizeStoredReadState(m, lastReadTimestamp, now, false)) normalized = true;
            var messageType = normalizeSystemMessageType(m.type, m.presentation);
            if (m.type !== messageType) {
                m.type = messageType;
                normalized = true;
            }
            var iconColor = sanitizeCssColor(m.icon_color);
            var iconBg = sanitizeCssColor(m.icon_bg);
            var tagColor = sanitizeCssColor(m.tag_color);
            var tagBg = sanitizeCssColor(m.tag_bg);
            var iconShape = normalizeIconShape(m.icon_shape);
            if (m.icon_color !== iconColor || m.icon_bg !== iconBg || m.tag_color !== tagColor || m.tag_bg !== tagBg || m.icon_shape !== iconShape) {
                m.icon_color = iconColor;
                m.icon_bg = iconBg;
                m.tag_color = tagColor;
                m.tag_bg = tagBg;
                m.icon_shape = iconShape;
                normalized = true;
            }
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
        var lastReadTimestamp = getLastReadTimestamp('interact');
        var normalized = false;
        var filtered = msgs.filter(function (m) {
            if (!m || typeof m !== 'object') return false;
            var oldTimestamp = m.timestamp;
            var oldExpiresAt = m.expires_at;
            var oldReceivedAt = m.received_at;
            var timestamp = normalizeStoredTimestamp(m, now);
            if (oldTimestamp !== timestamp || oldExpiresAt !== m.expires_at || oldReceivedAt !== m.received_at) normalized = true;
            if (normalizeStoredReadState(m, lastReadTimestamp, now, Boolean(m.notification_silent))) normalized = true;
            return Number(m.expires_at) > now && timestamp > cutoff;
        });
        if (normalized || filtered.length !== msgs.length) saveInteractMessages(filtered);
        return filtered;
    }

    /** 计算未读数 */
    function recalcUnread() {
        var sysMsgs = pruneExpiredSystemMessages();
        var intMsgs = pruneExpiredInteractMessages();

        _unreadSystem = 0;
        _unreadInteract = 0;

        sysMsgs.forEach(function (m) {
            if (m && m.unread === true) _unreadSystem++;
        });
        intMsgs.forEach(function (m) {
            if (m && !m.notification_silent && m.unread === true) _unreadInteract++;
        });
    }

    function setInteractionNotifyEnabled(enabled) {
        var settings = getSettings();
        settings.interaction_notify_enabled = Boolean(enabled);
        var values = [{ key: STORAGE_KEY_SETTINGS, data: settings }];
        if (!enabled) {
            var now = Date.now();
            var messages = pruneExpiredInteractMessages();
            messages.forEach(function (message) {
                message.unread = false;
                message.read_at = now;
            });
            values.push({ key: STORAGE_KEY_INTERACT, data: messages });
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
            btn.classList.remove('bell-has-new', 'bell-panel-open', 'bell-ringing', 'bell-ringing-system', 'near');
            return;
        }
        btn.style.display = '';
        var hasNew = getTotalUnread() > 0;
        btn.classList.toggle('bell-has-new', hasNew);
        btn.classList.toggle('bell-panel-open', _panelOpen);
        btn.classList.toggle('bell-ringing-system', _unreadSystem > 0);
        if (_unreadSystem > 0) {
            btn.classList.remove('bell-ringing');
            if (_ringTimer) {
                clearTimeout(_ringTimer);
                _ringTimer = null;
            }
        }
    }

    function triggerRing(kind) {
        if (!isNotificationCenterEnabled()) return;
        var btn = getBellButton();
        if (_unreadSystem > 0 || kind === 'system') {
            updateBellState();
            return;
        }
        if (!btn) return;
        btn.classList.remove('bell-ringing');
        void btn.offsetWidth; // 重置动画
        btn.classList.add('bell-ringing');
        if (_ringTimer) clearTimeout(_ringTimer);
        _ringTimer = setTimeout(function () {
            btn.classList.remove('bell-ringing');
            _ringTimer = null;
        }, INTERACTION_RING_MS);
    }

    function stopRing() {
        var btn = getBellButton();
        if (!btn) return;
        btn.classList.remove('bell-ringing', 'bell-ringing-system');
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

    function isBlockingOverlayNode(node) {
        if (!node || node.nodeType !== 1 || !node.classList) return false;
        if (node.classList.contains('notif-panel-overlay')) return false;
        if (node.classList.contains('modal-overlay')) return true;
        return node.id === 'modal-uid-welcome';
    }

    function hasBlockingOverlay() {
        var overlays = document.querySelectorAll('.modal-overlay.show, #modal-uid-welcome.show');
        for (var i = 0; i < overlays.length; i++) {
            if (overlays[i].classList.contains('notif-panel-overlay')) continue;
            return true;
        }
        return false;
    }

    function dismissForOverlay() {
        if (!_panelOpen) return;
        _resumePanelAfterOverlay = true;
        _panelOpen = false;
        if (window.NotificationPanelModule) window.NotificationPanelModule.close();
        updateBellState();
    }

    function syncPanelWithOverlays() {
        if (hasBlockingOverlay()) {
            dismissForOverlay();
            return;
        }
        if (!_resumePanelAfterOverlay) return;
        _resumePanelAfterOverlay = false;
        openPanel();
    }

    function scheduleOverlaySync() {
        if (_overlaySyncRaf) return;
        _overlaySyncRaf = window.requestAnimationFrame(function () {
            _overlaySyncRaf = 0;
            syncPanelWithOverlays();
        });
    }

    function bindOverlayWatcher() {
        if (_overlayWatcherBound || typeof MutationObserver !== 'function') return;
        _overlayWatcherBound = true;
        var observer = new MutationObserver(function (mutations) {
            for (var i = 0; i < mutations.length; i++) {
                var mutation = mutations[i];
                if (mutation.type === 'attributes') {
                    if (isBlockingOverlayNode(mutation.target)) {
                        scheduleOverlaySync();
                        return;
                    }
                    continue;
                }
                var nodes = [];
                var a;
                for (a = 0; a < mutation.addedNodes.length; a++) nodes.push(mutation.addedNodes[a]);
                for (a = 0; a < mutation.removedNodes.length; a++) nodes.push(mutation.removedNodes[a]);
                for (a = 0; a < nodes.length; a++) {
                    var node = nodes[a];
                    if (isBlockingOverlayNode(node) || (node && node.querySelector && node.querySelector('.modal-overlay, #modal-uid-welcome'))) {
                        scheduleOverlaySync();
                        return;
                    }
                }
            }
        });
        observer.observe(document.body, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['class']
        });
    }

    function openPanel() {
        if (!isNotificationCenterEnabled()) return;
        if (hasBlockingOverlay()) return;
        _panelOpen = true;
        updateBellState();
        if (window.NotificationPanelModule) {
            window.NotificationPanelModule.open();
        }
    }

    function closePanel() {
        _resumePanelAfterOverlay = false;
        _panelOpen = false;
        updateBellState();
        if (window.NotificationPanelModule) {
            window.NotificationPanelModule.close();
        }
        return true;
    }

    function hidePanel() {
        _resumePanelAfterOverlay = false;
        _panelOpen = false;
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
        var receivedAt = Date.now();
        var dedupeKey = buildSystemMessageKey(msg);
        var contentKey = buildSystemMessageContentKey(msg);
        var hasSourceId = msg.notification_id || msg.id != null || msg.source_id;
        var msgs = pruneExpiredSystemMessages();
        if (isTombstonedSystemMessage(msg)) {
            return { success: true, code: 'deleted', message: '消息已被用户删除' };
        }
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
        var messageType = normalizeSystemMessageType(msg.type, normalizedPresentation);
        var message = {
            id: 'sys_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6),
            notification_id: String(msg.notification_id || ''),
            source_id: String(msg.notification_id || msg.source_id || msg.id || ''),
            source_timestamp: msg.created_at || msg.timestamp || '',
            dedupe_key: dedupeKey,
            category: 'system',
            type: messageType,
            tag: String(msg.tag || '').trim().substring(0, 12),
            title: String(msg.title || '系统通知'),
            content: String(msg.summary || msg.content || ''),
            icon: SYSTEM_MESSAGE_ICONS[msg.icon] ? msg.icon : 'ri-notification-3-line',
            icon_color: sanitizeCssColor(msg.icon_color),
            icon_bg: sanitizeCssColor(msg.icon_bg),
            icon_shape: normalizeIconShape(msg.icon_shape),
            tag_color: sanitizeCssColor(msg.tag_color),
            tag_bg: sanitizeCssColor(msg.tag_bg),
            timestamp: msg.created_at || msg.timestamp || Date.now(),
            received_at: receivedAt,
            expires_at: Number(msg.expires_at) || 0,
            unread: true,
            read_at: 0,
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
        if (isNotificationCenterEnabled()) triggerRing('system');
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
        var receivedAt = Date.now();

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
            expires_at: Number(msg.expires_at) || 0,
            unread: !notificationSilent,
            read_at: notificationSilent ? receivedAt : 0
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
        if (!notificationSilent && isNotificationCenterEnabled()) triggerRing('interaction');
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
        var now = Date.now();
        var systemMessages = pruneExpiredSystemMessages();
        var interactMessages = pruneExpiredInteractMessages();
        systemMessages.forEach(function (message) {
            message.unread = false;
            message.read_at = now;
        });
        interactMessages.forEach(function (message) {
            message.unread = false;
            message.read_at = now;
        });
        var saved = saveStorageValues([
            { key: STORAGE_KEY_SYSTEM, data: systemMessages },
            { key: STORAGE_KEY_INTERACT, data: interactMessages }
        ]);
        recalcUnread();
        stopRing();
        updateBellState();
        if (_panelOpen && window.NotificationPanelModule) {
            window.NotificationPanelModule.refresh();
        }
        if (!saved) showStorageFailure('notification.storage_read_failed');
        return saved;
    }

    function markSystemMessageRead(payload) {
        var messageId = payload && typeof payload === 'object'
            ? String(payload.id || payload.notification_id || payload.source_id || '')
            : String(payload || '');
        if (!messageId) return false;
        var messages = pruneExpiredSystemMessages();
        var target = messages.find(function (message) {
            return String(message.id || '') === messageId ||
                String(message.notification_id || message.source_id || '') === messageId;
        });
        if (!target) return false;
        if (target.unread === false) return true;
        target.unread = false;
        target.read_at = Date.now();
        if (!saveSystemMessages(messages)) {
            showStorageFailure('notification.storage_read_failed');
            return false;
        }
        recalcUnread();
        updateBellState();
        if (_panelOpen && window.NotificationPanelModule) window.NotificationPanelModule.refresh();
        return true;
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

    function deleteMessage(payload) {
        var messageId = payload && typeof payload === 'object'
            ? String(payload.id || '')
            : String(payload || '');
        var category = payload && typeof payload === 'object'
            ? String(payload.category || 'system')
            : 'system';
        if (!messageId) {
            return { success: false, code: 'invalid', message: '删除消息标识无效' };
        }

        var storageEntries = [];
        if (category === 'interact') {
            var interactMessages = pruneExpiredInteractMessages();
            var nextInteract = interactMessages.filter(function (message) {
                return String(message.id || '') !== messageId;
            });
            if (nextInteract.length === interactMessages.length) {
                return { success: true, code: 'not_found', message: '消息已不存在' };
            }
            storageEntries.push({ key: STORAGE_KEY_INTERACT, data: nextInteract });
            storageEntries.push({ key: STORAGE_KEY_DELETED, data: mergeDeletedKeys(['interact:' + messageId]) });
        } else {
            var systemMessages = pruneExpiredSystemMessages();
            var target = null;
            var nextSystem = systemMessages.filter(function (message) {
                if (String(message.id || '') !== messageId) return true;
                target = message;
                return false;
            });
            if (!target) {
                return { success: true, code: 'not_found', message: '消息已不存在' };
            }
            storageEntries.push({ key: STORAGE_KEY_SYSTEM, data: nextSystem });
            storageEntries.push({ key: STORAGE_KEY_DELETED, data: mergeDeletedKeys(collectSystemTombstoneKeys(target)) });
        }

        if (!saveStorageValues(storageEntries)) {
            return { success: false, code: 'storage_failed', message: '消息删除保存失败' };
        }
        recalcUnread();
        updateBellState();
        if (_panelOpen && window.NotificationPanelModule) {
            window.NotificationPanelModule.refresh();
        }
        return { success: true, code: 'deleted', message: '消息已删除' };
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
        bindOverlayWatcher();
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
        deleteMessage: deleteMessage,
        dismissForOverlay: dismissForOverlay,
        markAllRead: markAllRead,
        updateProximity: updateProximity,
        openPanel: openPanel,
        closePanel: closePanel,
        togglePanel: togglePanel,
        getSystemMessages: getSystemMessages,
        getInteractMessages: getInteractMessages,
        markSystemMessageRead: markSystemMessageRead,
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
