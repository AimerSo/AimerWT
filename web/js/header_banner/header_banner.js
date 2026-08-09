/**
 * Header Banner 信息带模块
 *
 * 功能定位:
 * - 在 Header 空白区域轮播展示更新提示、系统公告、广告标语。
 * - 完全独立，删除此文件夹不影响主程序运行。
 *
 * 优先级: 更新提示 > 系统公告 > 广告标语
 *
 * 数据来源:
 * - 广告标语: 本地默认配置
 * - 更新提示/系统公告: 由外部通过 HeaderBannerModule.pushUpdate / pushAnnouncement 注入
 */
(function () {
    'use strict';

    var ROTATE_INTERVAL = 6000;
    var _container = null;
    var _items = [];
    var _currentIndex = 0;
    var _timer = null;
    var _update_dismissed = false;
    var _currentUpdateKey = null;
    var HEADER_BANNER_EDGE_GAP = 10;
    var _resizeObserver = null;
    var _resizeRaf = null;
    var _paused = false;

    var DEFAULT_SLOGANS = [];

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str || '';
        return div.innerHTML;
    }

    function normalizeBannerColor(value) {
        var color = String(value || '').trim();
        return /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(color) ? color : '';
    }

    function getSortedItems() {
        var priority = { update: 0, announcement: 1, slogan: 2 };
        var sorted = _items.slice();
        sorted.sort(function (a, b) {
            return (priority[a.type] || 9) - (priority[b.type] || 9);
        });
        return sorted;
    }

    function syncContainerState(hasContent) {
        if (!_container) return;
        _container.classList.toggle('has-content', !!hasContent);
    }

    function renderItem(item) {
        if (!_container) return;

        var hasDot = (item.type === 'announcement');

        var html = '<div class="header_banner banner_fade_in" data-type="' + escapeHtml(item.type) + '"'
            + (item.action ? ' data-action-type="' + escapeHtml(item.action.type || '') + '"' : '')
            + '>'
            + (hasDot ? '<span class="header_banner_dot"></span>' : '')
            + '<i class="' + escapeHtml(item.icon || 'ri-information-line') + '"></i>'
            + '<span class="header_banner_text_clip"><span class="header_banner_text">' + escapeHtml(item.text) + '</span></span>'
            + (item.type === 'update' ? '<button class="header_banner_close" title="本次不再提示"><i class="ri-close-line"></i></button>' : '')
            + '</div>';

        _container.innerHTML = html;

        var el = _container.querySelector('.header_banner');
        if (!el) return;

        if (item.action) {
            el.style.cursor = 'pointer';
            el.addEventListener('click', function () {
                handleAction(item.action, item.text);
            });
        }

        var textColor = normalizeBannerColor(item.color);
        var iconColor = normalizeBannerColor(item.icon_color);
        var backgroundColor = normalizeBannerColor(item.background_color);
        if (textColor) el.style.setProperty('--banner_text_color', textColor);
        if (iconColor) el.style.setProperty('--banner_icon_color', iconColor);
        if (backgroundColor) el.style.setProperty('--banner_background_color', backgroundColor);

        var closeBtn = el.querySelector('.header_banner_close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                clearUpdate();
            });
        }

        syncTextScroll(el);

        // Hover tooltip
        el.addEventListener('mouseenter', function () {
            showTooltip(item.text);
        });
        el.addEventListener('mouseleave', function () {
            hideTooltip();
        });
    }

    var _tooltipEl = null;

    function showTooltip(text) {
        if (!_container) return;
        if (!_tooltipEl) {
            _tooltipEl = document.createElement('div');
            _tooltipEl.className = 'header_banner_tooltip';
            document.body.appendChild(_tooltipEl);
        }
        _tooltipEl.textContent = text;
        var bannerEl = _container.querySelector('.header_banner');
        var rect = (bannerEl || _container).getBoundingClientRect();
        _tooltipEl.style.left = (rect.left + rect.width / 2) + 'px';
        _tooltipEl.style.top = (rect.bottom + 6) + 'px';
        requestAnimationFrame(function () {
            if (_tooltipEl) _tooltipEl.classList.add('visible');
        });
    }

    function hideTooltip() {
        if (_tooltipEl) {
            _tooltipEl.classList.remove('visible');
        }
    }

    function getTrackingMedium(tracking) {
        var mediumMap = {
            ad: 'header_banner_ad',
            activity: 'header_banner_activity'
        };
        return tracking ? (mediumMap[tracking.type] || '') : '';
    }

    function getTrackingId(tracking) {
        if (!tracking || tracking.id == null) return '';
        return String(tracking.id).trim().substring(0, 64);
    }

    function appendTrackedUtm(url, tracking) {
        var medium = getTrackingMedium(tracking);
        var adId = getTrackingId(tracking);
        if (!medium || !adId || !window.AimerUtm || !window.AimerUtm.appendUtm) return url;
        return window.AimerUtm.appendUtm(url, medium, adId);
    }

    function reportTrackedClick(action, targetUrl) {
        var medium = getTrackingMedium(action && action.tracking);
        var adId = getTrackingId(action && action.tracking);
        if (!medium || !adId || !window.AimerUtm || !window.AimerUtm.reportClick) return;
        window.AimerUtm.reportClick(medium, adId, targetUrl || '');
    }

    function handleAction(action, bannerText) {
        if (!action) return;

        if (action.type === 'url' && action.url) {
            var tracked = appendTrackedUtm(action.url, action.tracking);
            reportTrackedClick(action, action.url);
            if (window.app && typeof window.app.openExternal === 'function') {
                window.app.openExternal(tracked);
            } else {
                window.open(tracked, '_blank');
            }
        } else if (action.type === 'alert') {
            reportTrackedClick(action, action.url || ('banner-alert:' + getTrackingId(action.tracking)));
            if (window.app && typeof window.app.showAlert === 'function') {
                window.app.showAlert(
                    action.title || '系统通知',
                    action.content || '',
                    action.level || 'info',
                    action.url || ''
                );
            }
        }
    }

    function rotateNext() {
        if (_paused || document.hidden) return;
        var sorted = getSortedItems();
        if (!sorted.length) return;

        var el = _container && _container.querySelector('.header_banner');
        if (el) {
            el.classList.remove('banner_fade_in');
            el.classList.add('banner_fade_out');
        }

        setTimeout(function () {
            _currentIndex = (_currentIndex + 1) % sorted.length;
            renderItem(sorted[_currentIndex]);
        }, 300);
    }

    function startRotation() {
        stopRotation();
        if (_paused || document.hidden) return;
        var sorted = getSortedItems();
        if (sorted.length <= 1) return;

        _timer = setInterval(rotateNext, ROTATE_INTERVAL);
    }

    function stopRotation() {
        if (_timer) {
            clearInterval(_timer);
            _timer = null;
        }
    }

    function refreshDisplay() {
        var sorted = getSortedItems();
        if (!sorted.length) {
            if (_container) _container.innerHTML = '';
            syncContainerState(false);
            return;
        }

        syncContainerState(true);
        _currentIndex = 0;
        renderItem(sorted[0]);
        startRotation();
    }

    function setPaused(paused) {
        _paused = !!paused;
        if (_container) {
            _container.classList.toggle('is-background-paused', _paused);
        }
        hideTooltip();
        if (_paused || document.hidden) {
            stopRotation();
            return;
        }
        calcMaxWidth();
        startRotation();
    }

    function handleVisibilityChange() {
        setPaused(document.hidden || !!window.__aimerwtBackgroundPaused);
    }

    function syncTextScroll(el) {
        if (!el) return;
        // 仅当文字宽度超出容器时才启用滚动动画（所有类型统一逻辑）
        requestAnimationFrame(function () {
            var textEl = el.querySelector('.header_banner_text');
            var clipEl = textEl ? textEl.parentElement : null;
            if (!textEl || !clipEl) return;
            var clipWidth = clipEl.clientWidth;
            var textWidth = textEl.scrollWidth;
            clipEl.classList.remove('is-scrolling');
            textEl.classList.remove('is_scrolling');
            textEl.style.removeProperty('--clip-width');
            textEl.style.removeProperty('--scroll-offset');
            textEl.style.removeProperty('--scroll-duration');
            // 文字能够完全容纳在容器内，则静态显示
            if (textWidth <= clipWidth + 2) return;
            // 文字超出容器，启用滚动
            textEl.style.setProperty('--clip-width', clipWidth + 'px');
            textEl.style.setProperty('--scroll-offset', '-' + textWidth + 'px');
            var totalTravel = clipWidth + textWidth;
            var duration = Math.max(5, totalTravel / 30);
            textEl.style.setProperty('--scroll-duration', duration + 's');
            clipEl.classList.add('is-scrolling');
            textEl.classList.add('is_scrolling');
        });
    }

    function scheduleCalcMaxWidth() {
        if (_resizeRaf) cancelAnimationFrame(_resizeRaf);
        _resizeRaf = requestAnimationFrame(function () {
            _resizeRaf = null;
            calcMaxWidth();
        });
    }

    function calcMaxWidth() {
        if (!_container) return;
        var headerLeft = document.querySelector('.header-left');
        var brandWrapper = document.querySelector('.app-brand-wrapper');
        var headerNav = document.querySelector('.header-nav');
        var headerRight = document.querySelector('.header-right');
        var header = document.querySelector('.app-header');
        if (headerLeft && header && (headerNav || headerRight)) {
            var headerRect = header.getBoundingClientRect();
            var leftTarget = brandWrapper || headerLeft;
            var rightTarget = headerNav || headerRight;
            var leftEnd = leftTarget.getBoundingClientRect().right - headerRect.left;
            var rightStart = rightTarget.getBoundingClientRect().left - headerRect.left;
            var available = rightStart - leftEnd - (HEADER_BANNER_EDGE_GAP * 2);
            _container.style.left = (leftEnd + HEADER_BANNER_EDGE_GAP) + 'px';
            _container.style.width = Math.max(available, 0) + 'px';

            syncTextScroll(_container.querySelector('.header_banner'));
        }
    }

    function bindResizeObserver() {
        if (!window.ResizeObserver) return;
        if (_resizeObserver) _resizeObserver.disconnect();

        var header = document.querySelector('.app-header');
        var brandWrapper = document.querySelector('.app-brand-wrapper');
        var headerNav = document.querySelector('.header-nav');
        var headerRight = document.querySelector('.header-right');
        _resizeObserver = new ResizeObserver(scheduleCalcMaxWidth);
        [header, brandWrapper, headerNav, headerRight].forEach(function (el) {
            if (el) _resizeObserver.observe(el);
        });
    }

    function init() {
        _container = document.getElementById('header_banner_slot');
        if (!_container) return;

        calcMaxWidth();
        bindResizeObserver();
        window.addEventListener('resize', scheduleCalcMaxWidth);
        document.addEventListener('visibilitychange', handleVisibilityChange);

        _items = DEFAULT_SLOGANS.slice();
        refreshDisplay();
        handleVisibilityChange();
    }

    // === 公开 API ===

    function pushUpdate(text, url) {
        var updateKey = (text || '') + '|' + (url || '');
        try {
            if (localStorage.getItem('dismissed_update_key') === updateKey) return;
        } catch (e) {}
        if (_update_dismissed) return;
        _currentUpdateKey = updateKey;
        removeByType('update');
        _items.unshift({
            type: 'update',
            icon: 'ri-error-warning-line',
            text: '有新版本',
            action: {
                type: url ? 'url' : 'alert',
                url: url || '',
                title: '发现新版本',
                content: text || '发现新版本，请前往下载更新。',
                level: 'success'
            }
        });
        _currentIndex = 0;
        refreshDisplay();
    }

    function pushAnnouncement(text, action, append) {
        var appendMode = !!append;
        if (!appendMode) {
            removeByType('announcement');
        }
        var item = {
            type: 'announcement',
            icon: 'ri-megaphone-line',
            text: text || '系统公告'
        };
        if (action) {
            item.action = action;
        } else {
            item.action = {
                type: 'alert',
                title: '系统公告',
                content: text || '',
                level: 'info'
            };
        }
        if (appendMode) {
            _items.push(item);
        } else {
            _items.unshift(item);
        }
        _currentIndex = 0;
        refreshDisplay();
    }

    function normalizeRemoteItem(raw) {
        if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
        var text = String(raw.text || '').trim();
        if (!text) return null;
        var type = String(raw.type || 'announcement').trim().toLowerCase();
        if (type !== 'announcement' && type !== 'slogan') type = 'announcement';
        var icon = String(raw.icon || (type === 'slogan' ? 'ri-sparkling-2-line' : 'ri-megaphone-line')).trim();
        if (!/^[A-Za-z0-9 _-]{1,120}$/.test(icon)) icon = 'ri-megaphone-line';

        var rawAction = raw.action && typeof raw.action === 'object' && !Array.isArray(raw.action) ? raw.action : null;
        var action = null;
        if (rawAction) {
            var actionType = String(rawAction.type || '').trim().toLowerCase();
            var tracking = null;
            if (rawAction.tracking && typeof rawAction.tracking === 'object') {
                var trackingType = String(rawAction.tracking.type || '').trim().toLowerCase();
                var trackingId = String(rawAction.tracking.id || '').trim().substring(0, 64);
                if ((trackingType === 'activity' || trackingType === 'ad') && trackingId) {
                    tracking = { type: trackingType, id: trackingId };
                }
            }
            if (actionType === 'url' && rawAction.url) {
                action = { type: 'url', url: String(rawAction.url) };
            } else if (actionType === 'alert') {
                var level = String(rawAction.level || 'info').trim().toLowerCase();
                if (['info', 'success', 'warning', 'danger'].indexOf(level) < 0) level = 'info';
                action = {
                    type: 'alert',
                    title: String(rawAction.title || '系统公告'),
                    content: String(rawAction.content || text),
                    level: level,
                    url: String(rawAction.url || '')
                };
            }
            if (action && tracking) action.tracking = tracking;
        }

        return {
            type: type,
            icon: icon,
            text: text,
            color: normalizeBannerColor(raw.color),
            icon_color: normalizeBannerColor(raw.icon_color),
            background_color: normalizeBannerColor(raw.background_color),
            action: action
        };
    }

    function applyRemoteItems(items, intervalMs) {
        var incoming = Array.isArray(items) ? items : [];
        _items = _items.filter(function (item) { return item.type === 'update'; });
        incoming.forEach(function (item) {
            var normalized = normalizeRemoteItem(item);
            if (normalized) _items.push(normalized);
        });
        setRotateInterval(intervalMs);
        _currentIndex = 0;
        refreshDisplay();
    }

    function removeByType(type) {
        _items = _items.filter(function (it) { return it.type !== type; });
    }

    function clearUpdate() {
        _update_dismissed = true;
        if (_currentUpdateKey) {
            try { localStorage.setItem('dismissed_update_key', _currentUpdateKey); } catch (e) {}
        }
        removeByType('update');
        refreshDisplay();
    }

    function clearAnnouncement() {
        removeByType('announcement');
        refreshDisplay();
    }

    function setRotateInterval(intervalMs) {
        var nextInterval = Number(intervalMs);
        if (!Number.isFinite(nextInterval) || nextInterval < 3000) {
            nextInterval = 6000;
        }
        ROTATE_INTERVAL = nextInterval;
        startRotation();
    }

    // DOM 就绪后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.HeaderBannerModule = {
        init: init,
        pushUpdate: pushUpdate,
        pushAnnouncement: pushAnnouncement,
        applyRemoteItems: applyRemoteItems,
        clearUpdate: clearUpdate,
        clearAnnouncement: clearAnnouncement,
        setPaused: setPaused,
        _setInterval: setRotateInterval
    };
})();
