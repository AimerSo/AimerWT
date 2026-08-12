/**
 * 信息库广告位渲染模块
 *
 * 功能定位: 读取 AIMER_KNOWLEDGE_ADS_CONFIG，在 #knowledge-ads-grid 容器中渲染广告位卡片
 * 输入: window.AIMER_KNOWLEDGE_ADS_CONFIG.items[]
 * 输出: DOM 元素插入 #knowledge-ads-grid
 * 业务关联: 点击时调用 AimerUtm 进行 UTM 拼接和广告点击上报
 */
(function () {
    'use strict';

    function openAdLink(item) {
        if (!item.url) return;
        var tracked = (window.AimerUtm && window.AimerUtm.appendUtm)
            ? window.AimerUtm.appendUtm(item.url, 'knowledge_link', item.id)
            : item.url;
        if (window.AimerUtm && window.AimerUtm.reportClick) {
            window.AimerUtm.reportClick('knowledge_link', item.id || '', item.url);
        }
        if (window.app && typeof window.app.openExternal === 'function') {
            window.app.openExternal(tracked);
            return;
        }
        window.open(tracked, '_blank');
    }

    function showAdPopup(item) {
        if (window.AimerUtm && window.AimerUtm.reportClick) {
            window.AimerUtm.reportClick('knowledge_link', item.id || '', 'popup');
        }
        var overlay = document.createElement('div');
        overlay.className = 'modal-overlay show';
        overlay.style.zIndex = '10001';
        var box = document.createElement('div');
        box.className = 'modal-content';
        box.style.maxWidth = '520px';
        box.style.textAlign = 'left';
        box.innerHTML =
            '<h3 style="margin:0 0 12px;font-size:18px;font-weight:700;color:var(--text-main);">' +
            escapeHtml(item.title || '广告') +
            '</h3>' +
            '<div style="font-size:14px;color:var(--text-sec);line-height:1.7;white-space:pre-wrap;">' +
            escapeHtml(item.popup_content || item.subtitle || '') +
            '</div>' +
            '<div style="margin-top:20px;text-align:right;">' +
            '<button class="btn" style="padding:8px 20px;" onclick="this.closest(\'.modal-overlay\').remove()">关闭</button>' +
            '</div>';
        overlay.appendChild(box);
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) overlay.remove();
        });
        document.body.appendChild(overlay);
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function sanitize_image_url(value) {
        var raw = String(value || '').trim();
        if (/^data:image\/(?:webp|png|jpe?g|gif|bmp);base64,/i.test(raw)) {
            return raw;
        }
        if (!window.MarkdownRenderer || typeof window.MarkdownRenderer.sanitizeUrl !== 'function') {
            return '';
        }
        var sanitized = window.MarkdownRenderer.sanitizeUrl(raw);
        return /^https:\/\//i.test(sanitized) ? sanitized : '';
    }

    function renderKnowledgeAds() {
        var grid = document.getElementById('knowledge-ads-grid');
        if (!grid) return;
        grid.innerHTML = '';
        var cfg = window.AIMER_KNOWLEDGE_ADS_CONFIG || {};
        var items = Array.isArray(cfg.items) ? cfg.items : [];
        var hasVisible = false;

        items.forEach(function (item) {
            if (!item || !item.enabled) return;
            hasVisible = true;

            var card = document.createElement('div');
            card.className = 'link-card-ad';
            var background_url = sanitize_image_url(item.background);
            if (background_url) {
                card.classList.add('has-bg');
                var background = document.createElement('div');
                background.className = 'link-card-bg-img';
                background.style.backgroundImage = 'url(' + JSON.stringify(background_url) + ')';
                card.appendChild(background);
            }

            var content = document.createElement('div');
            content.className = 'link-card-content';

            var icon = document.createElement('div');
            icon.className = 'link-icon';
            var avatar_url = sanitize_image_url(item.avatar);
            if (avatar_url) {
                var avatar = document.createElement('img');
                avatar.src = avatar_url;
                avatar.alt = String(item.title || '');
                icon.appendChild(avatar);
            } else {
                var fallback_icon = document.createElement('i');
                fallback_icon.className = 'ri-megaphone-line';
                icon.appendChild(fallback_icon);
            }
            content.appendChild(icon);

            var info = document.createElement('div');
            info.className = 'link-info';
            var title = document.createElement('div');
            title.className = 'link-title';
            title.textContent = item.title || '广告位';
            info.appendChild(title);
            if (item.subtitle) {
                var subtitle = document.createElement('div');
                subtitle.className = 'link-desc';
                subtitle.textContent = item.subtitle;
                info.appendChild(subtitle);
            }
            content.appendChild(info);

            var arrow = document.createElement('div');
            arrow.className = 'link-arrow';
            var arrow_icon = document.createElement('i');
            arrow_icon.className = 'ri-arrow-right-line';
            arrow.appendChild(arrow_icon);
            content.appendChild(arrow);
            card.appendChild(content);

            card.addEventListener('click', function () {
                if (item.action === 'popup') {
                    showAdPopup(item);
                } else {
                    openAdLink(item);
                }
            });
            grid.appendChild(card);
        });
    }

    function refreshKnowledgeAds() {
        renderKnowledgeAds();
    }

    window.KnowledgeAdsModule = {
        render: renderKnowledgeAds,
        refresh: refreshKnowledgeAds
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', renderKnowledgeAds);
    } else {
        renderKnowledgeAds();
    }
})();
