/**
 * 通知铃铛模块 (Notification Bell Module)
 *
 * 功能定位：
 * - 右下角铃铛按钮的显隐控制（鼠标接近检测）
 * - 新消息到达时铃铛状态管理（晃动、红点）
 * - 通知数据的存储与容量管理（互动消息≤10条FIFO，系统消息≤20条/30天过期）
 * - 用户偏好设置（互动消息提醒开关）
 * - 对外提供消息推送接口供 Python 桥接层和 WebSocket 调用
 */
(function () {
    var STORAGE_KEY_SYSTEM = 'aimerwt_notification_system_msgs';
    var STORAGE_KEY_INTERACT = 'aimerwt_notification_interact_msgs';
    var STORAGE_KEY_SETTINGS = 'aimerwt_notification_settings';
    var STORAGE_KEY_READ_TS = 'aimerwt_notification_last_read_ts';

    var MAX_INTERACT_MSGS = 10;
    var MAX_SYSTEM_MSGS = 20;
    var SYSTEM_MSG_TTL_DAYS = 30;
    var PROXIMITY_PAD = 50;

    var _bellBtn = null;
    var _panelOpen = false;
    var _unreadSystem = 0;
    var _unreadInteract = 0;
    var _proximityBound = false;
    var _ringTimer = null;

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
        } catch (_e) { /* ignore */ }
    }

    /* ---- 数据管理 ---- */

    function getSettings() {
        var defaults = { interaction_notify_enabled: true };
        var stored = loadJSON(STORAGE_KEY_SETTINGS, {});
        return Object.assign({}, defaults, stored);
    }

    function saveSettings(settings) {
        saveJSON(STORAGE_KEY_SETTINGS, settings);
    }

    function getSystemMessages() {
        return loadJSON(STORAGE_KEY_SYSTEM, []);
    }

    function getInteractMessages() {
        return loadJSON(STORAGE_KEY_INTERACT, []);
    }

    function saveSystemMessages(msgs) {
        saveJSON(STORAGE_KEY_SYSTEM, msgs);
    }

    function saveInteractMessages(msgs) {
        saveJSON(STORAGE_KEY_INTERACT, msgs);
    }

    function buildSystemMessageKey(msg) {
        if (!msg || typeof msg !== 'object') return '';
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

    function getLastReadTimestamp() {
        return Number(loadJSON(STORAGE_KEY_READ_TS, 0)) || 0;
    }

    function setLastReadTimestamp() {
        saveJSON(STORAGE_KEY_READ_TS, Date.now());
    }

    /** 清理超过30天的系统消息 */
    function pruneExpiredSystemMessages() {
        var msgs = getSystemMessages();
        var cutoff = Date.now() - (SYSTEM_MSG_TTL_DAYS * 24 * 60 * 60 * 1000);
        var filtered = msgs.filter(function (m) {
            return (m && m.timestamp && m.timestamp > cutoff);
        });
        if (filtered.length !== msgs.length) {
            saveSystemMessages(filtered);
        }
        return filtered;
    }

    /** 计算未读数 */
    function recalcUnread() {
        var lastRead = getLastReadTimestamp();
        var sysMsgs = getSystemMessages();
        var intMsgs = getInteractMessages();

        _unreadSystem = 0;
        _unreadInteract = 0;

        sysMsgs.forEach(function (m) {
            if (m && m.timestamp && m.timestamp > lastRead) _unreadSystem++;
        });
        intMsgs.forEach(function (m) {
            if (m && m.timestamp && m.timestamp > lastRead) _unreadInteract++;
        });
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
        var hasNew = getTotalUnread() > 0;
        btn.classList.toggle('bell-has-new', hasNew);
        btn.classList.toggle('bell-panel-open', _panelOpen);
    }

    function triggerRing() {
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
        // 监听由 guide.js 传递的接近事件（避免重复绑定 mousemove）
    }

    /* ---- 面板控制 ---- */

    function openPanel() {
        _panelOpen = true;
        stopRing();
        updateBellState();
        if (window.NotificationPanelModule) {
            window.NotificationPanelModule.open();
        }
    }

    function closePanel() {
        _panelOpen = false;
        // 标记已读
        setLastReadTimestamp();
        recalcUnread();
        updateBellState();
        if (window.NotificationPanelModule) {
            window.NotificationPanelModule.close();
        }
    }

    function togglePanel() {
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
        if (!msg || typeof msg !== 'object') return;
        var dedupeKey = buildSystemMessageKey(msg);
        var contentKey = buildSystemMessageContentKey(msg);
        var hasSourceId = msg.id != null || msg.source_id;
        var msgs = pruneExpiredSystemMessages();
        if (dedupeKey && msgs.some(function (m) {
            return buildSystemMessageKey(m) === dedupeKey ||
                (!hasSourceId && buildSystemMessageContentKey(m) === contentKey);
        })) {
            return;
        }
        var message = {
            id: 'sys_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6),
            source_id: msg.id != null ? String(msg.id) : '',
            source_timestamp: msg.timestamp || '',
            dedupe_key: dedupeKey,
            type: 'system',
            title: String(msg.title || '系统通知'),
            content: String(msg.content || ''),
            icon: String(msg.icon || 'ri-notification-3-line'),
            timestamp: msg.timestamp || Date.now()
        };
        msgs.push(message);
        // 保留最新的 MAX_SYSTEM_MSGS 条
        if (msgs.length > MAX_SYSTEM_MSGS) {
            msgs = msgs.slice(msgs.length - MAX_SYSTEM_MSGS);
        }
        saveSystemMessages(msgs);
        recalcUnread();
        updateBellState();
        triggerRing();
        if (_panelOpen && window.NotificationPanelModule) {
            window.NotificationPanelModule.refresh();
        }
    }

    /**
     * 批量推送系统消息
     * @param {Array} msgList
     */
    function pushSystemMessages(msgList) {
        if (!Array.isArray(msgList)) return;
        msgList.forEach(function (m) { pushSystemMessage(m); });
    }

    /**
     * 推送一条互动消息（点赞/回复）
     * @param {Object} msg - { action: "like"|"reply", actor, content?, notice_title?, timestamp? }
     */
    function pushInteractionMessage(msg) {
        if (!msg || typeof msg !== 'object') return;
        var settings = getSettings();
        if (!settings.interaction_notify_enabled) return;

        var message = {
            id: 'int_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6),
            type: 'interaction',
            action: String(msg.action || 'like'),
            actor: String(msg.actor || ''),
            content: String(msg.content || ''),
            notice_title: String(msg.notice_title || ''),
            timestamp: msg.timestamp || Date.now()
        };
        var msgs = getInteractMessages();
        msgs.push(message);
        // FIFO: 保留最新的 MAX_INTERACT_MSGS 条
        if (msgs.length > MAX_INTERACT_MSGS) {
            msgs = msgs.slice(msgs.length - MAX_INTERACT_MSGS);
        }
        saveInteractMessages(msgs);
        recalcUnread();
        updateBellState();
        triggerRing();
        if (_panelOpen && window.NotificationPanelModule) {
            window.NotificationPanelModule.refresh();
        }
    }

    /** 标记全部已读 */
    function markAllRead() {
        setLastReadTimestamp();
        recalcUnread();
        updateBellState();
        stopRing();
        if (_panelOpen && window.NotificationPanelModule) {
            window.NotificationPanelModule.refresh();
        }
    }

    /* ---- 初始化 ---- */

    function init() {
        pruneExpiredSystemMessages();
        recalcUnread();
        var btn = getBellButton();
        if (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                togglePanel();
            });
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
        markAllRead: markAllRead,
        updateProximity: updateProximity,
        openPanel: openPanel,
        closePanel: closePanel,
        togglePanel: togglePanel,
        getSystemMessages: getSystemMessages,
        getInteractMessages: getInteractMessages,
        getSettings: getSettings,
        saveSettings: saveSettings,
        getTotalUnread: getTotalUnread,
        getUnreadSystem: function () { return _unreadSystem; },
        getUnreadInteract: function () { return _unreadInteract; },
        isPanelOpen: function () { return _panelOpen; },
        recalcUnread: recalcUnread,
        updateBellState: updateBellState,
        triggerRing: triggerRing
    };
})();
