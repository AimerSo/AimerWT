/* UID 欢迎弹窗模块（独立文件，自注入样式和 DOM） */
(function () {
    'use strict';

    var UID_SHOWN_KEY = 'aimer_uid_popup_shown';
    var FIRST_SHOW_SETTLED_EVENT = 'aimerwt:uid_first_show_settled';
    var MODAL_ID = 'modal-uid-welcome';
    var _injected = false;
    var _first_show_pending = {};
    var _first_show_handled = {};
    var _first_show_blocking = {};
    var _first_show_visible_seq_id = '';
    var _popup_generation = 0;

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function normalizeSeqId(seqId) {
        var parsed = parseInt(seqId, 10);
        return parsed > 0 ? String(parsed) : '';
    }

    function isGuideActive() {
        return Boolean(
            window.AuthorGuide &&
            typeof window.AuthorGuide.isActive === 'function' &&
            window.AuthorGuide.isActive()
        );
    }

    function isFirstShowBlocking() {
        return Object.keys(_first_show_blocking).some(function (seqId) {
            return _first_show_blocking[seqId] === true;
        });
    }

    function settleFirstShow(seqId) {
        seqId = normalizeSeqId(seqId);
        if (!seqId || !_first_show_blocking[seqId]) return;
        delete _first_show_blocking[seqId];
        window.dispatchEvent(new CustomEvent(FIRST_SHOW_SETTLED_EVENT, {
            detail: { seqId: seqId }
        }));
    }

    /* 将 UID 格式化为 5 位展示编号（如 1 → 00001） */
    function formatUid(seqId) {
        return String(parseInt(seqId, 10) || 0).padStart(5, '0');
    }

    function getLocalFirstShownIds() {
        try {
            var raw = localStorage.getItem(UID_SHOWN_KEY);
            if (!raw) return [];
            try {
                var parsed = JSON.parse(raw);
                if (Array.isArray(parsed)) {
                    return parsed.map(normalizeSeqId).filter(Boolean);
                }
            } catch (e) {
            }
            var legacyId = normalizeSeqId(raw);
            return legacyId ? [legacyId] : [];
        } catch (e) {
            return [];
        }
    }

    function hasLocalFirstShow(seqId) {
        return getLocalFirstShownIds().indexOf(String(seqId)) >= 0;
    }

    function markLocalFirstShow(seqId) {
        try {
            var shownIds = getLocalFirstShownIds();
            if (shownIds.indexOf(String(seqId)) < 0) {
                shownIds.push(String(seqId));
            }
            localStorage.setItem(UID_SHOWN_KEY, JSON.stringify(shownIds));
        } catch (e) {
        }
    }

    async function getBackendFirstShowState(seqId) {
        if (!window.pywebview?.api?.get_uid_popup_state) return null;
        try {
            var res = await pywebview.api.get_uid_popup_state(seqId);
            if (res && res.success) return !!res.shown;
        } catch (e) {
        }
        return null;
    }

    async function markBackendFirstShow(seqId) {
        if (!window.pywebview?.api?.save_uid_popup_state) return false;
        try {
            var res = await pywebview.api.save_uid_popup_state(seqId);
            return !!(res && res.success);
        } catch (e) {
            return false;
        }
    }

    /* ========== 样式注入 ========== */
    function injectStyles() {
        if (_injected) return;
        _injected = true;
        var css = `
/* UID 欢迎弹窗 — 遮罩 */
#${MODAL_ID} {
    position: fixed;
    inset: 0;
    z-index: 2900;
    display: none;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0);
    backdrop-filter: blur(0px);
    -webkit-backdrop-filter: blur(0px);
    transition: background 0.5s ease, backdrop-filter 0.5s ease, -webkit-backdrop-filter 0.5s ease;
}
#${MODAL_ID}.show {
    display: flex;
    background: rgba(0, 0, 0, 0.45);
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
}
#${MODAL_ID}.hiding {
    background: rgba(0, 0, 0, 0);
    backdrop-filter: blur(0px);
    -webkit-backdrop-filter: blur(0px);
    pointer-events: none;
}

/* 面板容器 */
.uid-welcome-panel {
    position: relative;
    width: 340px;
    max-width: 90vw;
    background: var(--bg-card, #fff);
    border: 1px solid var(--border-color, #e5e7eb);
    border-radius: 20px;
    padding: 32px 28px 24px;
    text-align: center;
    box-shadow: 0 24px 64px rgba(0, 0, 0, 0.18), 0 0 0 1px rgba(255, 255, 255, 0.06) inset;
    overflow: hidden;
    transform: scale(0.85) translateY(30px);
    opacity: 0;
    transition: transform 0.55s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.45s ease;
}
#${MODAL_ID}.show .uid-welcome-panel {
    transform: scale(1) translateY(0);
    opacity: 1;
}
#${MODAL_ID}.hiding .uid-welcome-panel {
    transform: scale(0.92) translateY(12px);
    opacity: 0;
    transition: transform 0.3s ease, opacity 0.3s ease;
}

/* 顶部装饰光晕 */
.uid-welcome-glow {
    position: absolute;
    top: -60px;
    left: 50%;
    transform: translateX(-50%);
    width: 200px;
    height: 120px;
    border-radius: 50%;
    background: radial-gradient(ellipse, color-mix(in srgb, var(--primary) 25%, transparent), transparent 70%);
    pointer-events: none;
    animation: uid-glow-pulse 3s ease-in-out infinite;
}
@keyframes uid-glow-pulse {
    0%, 100% { opacity: 0.6; transform: translateX(-50%) scale(1); }
    50% { opacity: 1; transform: translateX(-50%) scale(1.1); }
}

/* 关闭按钮 */
.uid-welcome-close {
    position: absolute;
    top: 12px;
    right: 12px;
    width: 28px;
    height: 28px;
    border: none;
    background: transparent;
    color: var(--text-sec, #9ca3af);
    font-size: 18px;
    cursor: pointer;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.2s ease, color 0.2s ease;
    z-index: 2;
}
.uid-welcome-close:hover {
    background: color-mix(in srgb, var(--text-sec) 12%, transparent);
    color: var(--text-main, #1f2937);
}

/* 图标区 */
.uid-welcome-icon {
    position: relative;
    z-index: 1;
    width: 56px;
    height: 56px;
    margin: 0 auto 16px;
    border-radius: 16px;
    background: linear-gradient(135deg, color-mix(in srgb, var(--primary) 15%, transparent), color-mix(in srgb, var(--primary) 6%, transparent));
    border: 1px solid color-mix(in srgb, var(--primary) 20%, transparent);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 26px;
    color: var(--primary);
    animation: uid-icon-entrance 0.6s 0.2s both cubic-bezier(0.34, 1.56, 0.64, 1);
}
@keyframes uid-icon-entrance {
    0% { transform: scale(0) rotate(-30deg); opacity: 0; }
    100% { transform: scale(1) rotate(0); opacity: 1; }
}

/* 标题 */
.uid-welcome-title {
    position: relative;
    z-index: 1;
    font-size: 17px;
    font-weight: 700;
    color: var(--text-main, #1f2937);
    margin: 0 0 6px;
    animation: uid-fade-up 0.5s 0.3s both ease;
}

.uid-welcome-subtitle-text {
    position: relative;
    z-index: 1;
    font-size: 12px;
    color: var(--text-sec, #9ca3af);
    margin: 0 0 18px;
    animation: uid-fade-up 0.5s 0.35s both ease;
}

@keyframes uid-fade-up {
    0% { opacity: 0; transform: translateY(10px); }
    100% { opacity: 1; transform: translateY(0); }
}

/* UID 徽章区域 */
.uid-badge-area {
    position: relative;
    z-index: 1;
    padding: 20px 0;
    margin: 0 -8px;
    border-radius: 14px;
    background: linear-gradient(135deg, color-mix(in srgb, var(--primary) 8%, transparent), color-mix(in srgb, var(--primary) 3%, transparent));
    border: 1px solid color-mix(in srgb, var(--primary) 12%, transparent);
    animation: uid-fade-up 0.5s 0.4s both ease;
    overflow: hidden;
}

/* 徽章区域内部扫光动画 */
.uid-badge-area::after {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 60%;
    height: 100%;
    background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--primary) 8%, transparent), transparent);
    animation: uid-sweep 4s 1s infinite ease-in-out;
    pointer-events: none;
}
@keyframes uid-sweep {
    0% { left: -60%; }
    50% { left: 100%; }
    100% { left: 100%; }
}

.uid-badge-number {
    display: flex;
    align-items: baseline;
    justify-content: center;
    gap: 2px;
    font-variant-numeric: tabular-nums;
}

.uid-badge-hash {
    font-size: 18px;
    font-weight: 700;
    color: var(--primary);
    opacity: 0.5;
    margin-right: 4px;
    letter-spacing: 0.01em;
}

/* 四位数字中的每一位 */
.uid-digit {
    display: inline-block;
    font-size: 36px;
    font-weight: 800;
    color: var(--primary);
    letter-spacing: 0.02em;
    text-shadow: 0 0 20px color-mix(in srgb, var(--primary) 35%, transparent);
    min-width: 0.65em;
    text-align: center;
    transition: transform 0.15s ease;
}

/* 数字跳动中的抖动效果 */
.uid-digit.rolling {
    animation: uid-digit-jitter 0.08s infinite alternate ease-in-out;
}
@keyframes uid-digit-jitter {
    0% { transform: translateY(-1px); }
    100% { transform: translateY(1px); }
}

/* 数字停稳时的弹跳 */
.uid-digit.landed {
    animation: uid-digit-land 0.35s ease both;
}
@keyframes uid-digit-land {
    0% { transform: scale(1.3) translateY(-3px); }
    50% { transform: scale(0.95) translateY(1px); }
    100% { transform: scale(1) translateY(0); }
}

/* 停稳后的持续发光呼吸 */
.uid-digit.settled {
    animation: uid-number-glow 3s ease-in-out infinite;
}
@keyframes uid-number-glow {
    0%, 100% { text-shadow: 0 0 20px color-mix(in srgb, var(--primary) 35%, transparent); }
    50% { text-shadow: 0 0 32px color-mix(in srgb, var(--primary) 55%, transparent); }
}

.uid-badge-label {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-sec, #9ca3af);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-top: 6px;
}

/* 描述文字（初始隐藏，等数字动画结束后淡入） */
.uid-welcome-desc {
    position: relative;
    z-index: 1;
    font-size: 12px;
    color: var(--text-sec, #9ca3af);
    line-height: 1.6;
    margin: 16px 0 20px;
    opacity: 0;
    transform: translateY(8px);
    transition: opacity 0.5s ease, transform 0.5s ease;
}
.uid-welcome-desc.visible {
    opacity: 1;
    transform: translateY(0);
}
.uid-welcome-desc b {
    color: var(--text-main, #1f2937);
    font-weight: 600;
}

/* 确认按钮（初始隐藏，等数字动画结束后淡入） */
.uid-welcome-btn {
    position: relative;
    z-index: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    height: 38px;
    padding: 0 28px;
    border: none;
    border-radius: 10px;
    background: linear-gradient(135deg, var(--primary), color-mix(in srgb, var(--primary) 80%, #fff));
    color: #fff;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: transform 0.2s ease, box-shadow 0.2s ease, opacity 0.5s ease;
    box-shadow: 0 4px 16px color-mix(in srgb, var(--primary) 30%, transparent);
    opacity: 0;
}
.uid-welcome-btn.visible {
    opacity: 1;
}
.uid-welcome-btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 24px color-mix(in srgb, var(--primary) 45%, transparent);
}
.uid-welcome-btn:active {
    transform: translateY(0) scale(0.97);
}

/* 彩带粒子 */
.uid-confetti {
    position: absolute;
    width: 6px;
    height: 6px;
    border-radius: 2px;
    pointer-events: none;
    z-index: 3;
    opacity: 0;
}
.uid-confetti.active {
    animation: uid-confetti-fall var(--fall-duration, 2.5s) var(--fall-delay, 0s) ease-out forwards;
}
@keyframes uid-confetti-fall {
    0% { opacity: 1; transform: translate(0, 0) rotate(0deg) scale(1); }
    70% { opacity: 0.8; }
    100% { opacity: 0; transform: translate(var(--dx, 30px), var(--dy, 120px)) rotate(var(--rot, 360deg)) scale(0.3); }
}
`;
        var style = document.createElement('style');
        style.setAttribute('data-uid-popup', '1');
        style.textContent = css;
        document.head.appendChild(style);
    }

    /* ========== DOM 构建 ========== */
    function ensureModal() {
        if (document.getElementById(MODAL_ID)) return;
        injectStyles();
        var overlay = document.createElement('div');
        overlay.id = MODAL_ID;
        overlay.className = 'uid-popup-overlay';
        overlay.innerHTML =
            '<div class="uid-welcome-panel">' +
                '<div class="uid-welcome-glow"></div>' +
                '<div class="uid-welcome-icon"><i class="ri-user-star-line"></i></div>' +
                '<div class="uid-welcome-title">欢迎加入 AimerWT 社区</div>' +
                '<div class="uid-welcome-subtitle-text">你的专属用户编号已生成</div>' +
                '<div class="uid-badge-area">' +
                    '<div class="uid-badge-number">' +
                        '<span class="uid-badge-hash">No.</span>' +
                        '<span class="uid-digit" id="uid-d0">0</span>' +
                        '<span class="uid-digit" id="uid-d1">0</span>' +
                        '<span class="uid-digit" id="uid-d2">0</span>' +
                        '<span class="uid-digit" id="uid-d3">0</span>' +
                        '<span class="uid-digit" id="uid-d4">0</span>' +
                    '</div>' +
                    '<div class="uid-badge-label">USER ID</div>' +
                '</div>' +
                '<div class="uid-welcome-desc" id="uid-welcome-desc"></div>' +
                '<button class="uid-welcome-btn" id="uid-welcome-btn"><i class="ri-check-line"></i> 我知道了</button>' +
            '</div>';
        document.body.appendChild(overlay);

        document.getElementById('uid-welcome-btn').addEventListener('click', closeUidPopup);
    }

    /* ========== 彩带粒子 ========== */
    function spawnConfetti(container) {
        var colors = [
            'var(--primary)',
            'color-mix(in srgb, var(--primary) 70%, #fff)',
            'color-mix(in srgb, var(--primary) 50%, gold)',
            '#fbbf24', '#34d399', '#60a5fa', '#f472b6'
        ];
        for (var i = 0; i < 20; i++) {
            var dot = document.createElement('div');
            dot.className = 'uid-confetti';
            var x = 20 + Math.random() * 300;
            var y = 10 + Math.random() * 30;
            dot.style.left = x + 'px';
            dot.style.top = y + 'px';
            dot.style.background = colors[i % colors.length];
            dot.style.width = (4 + Math.random() * 5) + 'px';
            dot.style.height = (4 + Math.random() * 5) + 'px';
            dot.style.borderRadius = Math.random() > 0.5 ? '50%' : '2px';
            dot.style.setProperty('--dx', (Math.random() * 140 - 70) + 'px');
            dot.style.setProperty('--dy', (60 + Math.random() * 120) + 'px');
            dot.style.setProperty('--rot', (Math.random() * 720 - 360) + 'deg');
            dot.style.setProperty('--fall-duration', (1.8 + Math.random() * 1.2) + 's');
            dot.style.setProperty('--fall-delay', (Math.random() * 0.3) + 's');
            container.appendChild(dot);
            requestAnimationFrame(function (el) {
                return function () { el.classList.add('active'); };
            }(dot));
        }
    }

    /* ========== 老虎机式数字滚动 ========== */
    var _rollTimers = [];

    function clearRollTimers() {
        _rollTimers.forEach(function (t) { clearInterval(t); });
        _rollTimers = [];
    }

    /**
     * 五位数字依次快速跳动后逐个停稳。
     * 总时长约 1.5 秒，第 i 位在 baseDelay + i * stagger 时停下。
     */
    function rollDigits(targetStr) {
        clearRollTimers();
        var digits = targetStr.split('');
        var els = [];
        for (var i = 0; i < 5; i++) {
            var el = document.getElementById('uid-d' + i);
            if (!el) return;
            els.push(el);
            el.textContent = String(Math.floor(Math.random() * 10));
            el.className = 'uid-digit rolling';
        }

        var baseDelay = 700;
        var stagger = 180;

        for (var idx = 0; idx < 5; idx++) {
            (function (i) {
                var interval = 50 + Math.random() * 30;
                var timer = setInterval(function () {
                    els[i].textContent = String(Math.floor(Math.random() * 10));
                }, interval);
                _rollTimers.push(timer);

                var stopAt = baseDelay + i * stagger;
                setTimeout(function () {
                    clearInterval(timer);
                    els[i].textContent = digits[i];
                    els[i].className = 'uid-digit landed';
                    setTimeout(function () {
                        els[i].className = 'uid-digit settled';
                    }, 400);
                }, stopAt);
            })(idx);
        }
    }

    /* ========== 弹窗控制 ========== */
    function showUidPopup(seqId) {
        seqId = normalizeSeqId(seqId);
        if (!seqId) return false;
        ensureModal();
        var modal = document.getElementById(MODAL_ID);
        if (!modal) return false;
        _popup_generation += 1;

        var formatted = formatUid(seqId);

        // 填充描述（初始隐藏）
        var descEl = document.getElementById('uid-welcome-desc');
        if (descEl) {
            descEl.innerHTML = '你是第 <b>' + escapeHtml(String(parseInt(seqId, 10))) + '</b> 位注册用户<br>此编号未来将在你的个人资料中展示';
            descEl.classList.remove('visible');
        }

        // 按钮初始隐藏
        var btn = document.getElementById('uid-welcome-btn');
        if (btn) btn.classList.remove('visible');

        // 清除旧彩带
        modal.querySelectorAll('.uid-confetti').forEach(function (el) { el.remove(); });

        // 重置数字
        for (var i = 0; i < 5; i++) {
            var d = document.getElementById('uid-d' + i);
            if (d) { d.textContent = '0'; d.className = 'uid-digit'; }
        }

        // 先设 display:flex（但遮罩透明），下一帧再触发 transition 缓入
        modal.classList.remove('show', 'hiding');
        modal.style.display = 'flex';
        void modal.offsetWidth;

        requestAnimationFrame(function () {
            modal.classList.add('show');
        });

        // 彩带在面板出场动画快结束时释放
        var panel = modal.querySelector('.uid-welcome-panel');
        setTimeout(function () {
            if (panel) spawnConfetti(panel);
        }, 400);

        // 彩带爆完后开始数字滚动
        setTimeout(function () {
            rollDigits(formatted);
        }, 600);

        // 数字动画结束后（约 600 + 700 + 4*180 + 400 ≈ 2.4s），描述和按钮淡入
        var revealDelay = 600 + 700 + 4 * 180 + 400;
        setTimeout(function () {
            if (descEl) descEl.classList.add('visible');
        }, revealDelay);
        setTimeout(function () {
            if (btn) btn.classList.add('visible');
        }, revealDelay + 200);
        return true;
    }

    function showUidFirstPopupWhenReady(seqId) {
        seqId = normalizeSeqId(seqId);
        if (!seqId || !_first_show_blocking[seqId]) return;
        if (isGuideActive()) {
            setTimeout(function () {
                showUidFirstPopupWhenReady(seqId);
            }, 3000);
            return;
        }

        _first_show_visible_seq_id = seqId;
        if (!showUidPopup(seqId)) {
            _first_show_visible_seq_id = '';
            settleFirstShow(seqId);
        }
    }

    function closeUidPopup() {
        clearRollTimers();
        var firstShowSeqId = _first_show_visible_seq_id;
        var closingGeneration = _popup_generation;
        var modal = document.getElementById(MODAL_ID);
        if (!modal) {
            if (_first_show_visible_seq_id === firstShowSeqId) {
                _first_show_visible_seq_id = '';
            }
            settleFirstShow(firstShowSeqId);
            return;
        }
        modal.classList.add('hiding');
        setTimeout(function () {
            if (closingGeneration !== _popup_generation) return;
            modal.classList.remove('show', 'hiding');
            modal.style.display = 'none';
            if (_first_show_visible_seq_id === firstShowSeqId) {
                _first_show_visible_seq_id = '';
            }
            settleFirstShow(firstShowSeqId);
        }, 350);
    }

    /* ========== 首次展示检查 ========== */
    async function checkUidFirstShow(seqId) {
        seqId = normalizeSeqId(seqId);
        if (!seqId || _first_show_handled[seqId] || _first_show_pending[seqId]) return;
        _first_show_blocking[seqId] = true;
        /* 新手引导运行期间不弹，延迟重试 */
        if (isGuideActive()) {
            _first_show_pending[seqId] = true;
            setTimeout(function () {
                _first_show_pending[seqId] = false;
                checkUidFirstShow(seqId);
            }, 3000);
            return;
        }

        _first_show_pending[seqId] = true;
        var keepBlockingUntilClose = false;
        try {
            var backendShown = await getBackendFirstShowState(seqId);
            var localShown = hasLocalFirstShow(seqId);
            if (backendShown === true || localShown) {
                if (backendShown !== true) {
                    await markBackendFirstShow(seqId);
                }
                _first_show_handled[seqId] = true;
                markLocalFirstShow(seqId);
                return;
            }

            await markBackendFirstShow(seqId);
            markLocalFirstShow(seqId);
            _first_show_handled[seqId] = true;
            keepBlockingUntilClose = true;
            setTimeout(function () { showUidFirstPopupWhenReady(seqId); }, 800);
        } finally {
            _first_show_pending[seqId] = false;
            if (!keepBlockingUntilClose) {
                settleFirstShow(seqId);
            }
        }
    }

    /* ========== footer UID 点击委托 ========== */
    document.addEventListener('click', function (e) {
        var label = e.target.closest('.uid-label');
        if (!label) return;
        var uid = label.getAttribute('data-uid');
        if (uid) showUidPopup(uid);
    });

    /* ========== 导出 ========== */
    window.UidPopupModule = {
        showUidPopup: showUidPopup,
        closeUidPopup: closeUidPopup,
        checkUidFirstShow: checkUidFirstShow,
        isFirstShowBlocking: isFirstShowBlocking
    };
})();
