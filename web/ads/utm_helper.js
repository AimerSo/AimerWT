/**
 * UTM 参数拼接与广告点击上报工具
 *
 * 功能定位:
 * - 为所有外部广告链接自动追加 UTM 查询参数，便于广告商在第三方统计平台识别来源流量
 * - 向遥测服务器异步上报点击事件，供 Dashboard 广告统计页面使用
 *
 * 数据来源:
 * - 遥测服务地址: window._aimerTelemetryBase（由 Python 端注入）
 * - 用户标识: window._aimerMachineId（由 Python 端注入）
 */
(function () {
    'use strict';

    /**
     * 为外部链接拼接 UTM 来源标记
     *
     * 外部链接仅追加 utm_source=AimerWT，保持对广告商的 URL 简洁。
     * 细粒度统计（广告位、素材 ID 等）由 reportClick() 独立上报到遥测服务器。
     *
     * @param {string} url      原始链接
     * @param {string} _medium  （保留）广告位类型，当前未写入 URL
     * @param {string} [_content] （保留）素材标识，当前未写入 URL
     * @param {Object} [options] 扩展选项，预留供未来使用
     * @param {boolean} [options.full_utm] 若为 true 则额外追加 utm_medium 和 utm_content
     * @returns {string} 拼好 UTM 的完整链接
     */
    function appendUtm(url, _medium, _content, options) {
        if (!url || url === '#') return url;
        try {
            var finalUrl = String(url).trim();
            if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(finalUrl)) {
                finalUrl = 'https://' + finalUrl;
            }
            var u = new URL(finalUrl);
            u.searchParams.set('utm_source', 'AimerWT');
            if (options && options.full_utm) {
                if (_medium) u.searchParams.set('utm_medium', _medium);
                if (_content) u.searchParams.set('utm_content', _content);
            }
            return u.toString();
        } catch (e) {
            return url;
        }
    }

    /**
     * 异步上报广告点击事件到遥测服务器
     * @param {string} medium    广告位类型
     * @param {string} adId      广告素材 ID
     * @param {string} targetUrl 目标链接
     */
    function reportClick(medium, adId, targetUrl) {
        var base = window._aimerTelemetryBase || window._telemetryBaseUrl;
        if (!base) return;

        var endpoint = base.replace(/\/+$/, '') + '/telemetry/ad-click';
        var machineId = window._aimerMachineId || window._telemetryHWID || '';

        Promise.resolve().then(async function () {
            try {
                var headers = {
                    'Content-Type': 'application/json',
                    'X-AimerWT-Client': '1'
                };
                if (window.pywebview && window.pywebview.api && window.pywebview.api.get_telemetry_auth_headers) {
                    var authHeaders = await window.pywebview.api.get_telemetry_auth_headers('/telemetry/ad-click', 'POST', machineId || '');
                    if (authHeaders && typeof authHeaders === 'object') {
                        Object.assign(headers, authHeaders);
                    }
                }

                fetch(endpoint, {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({
                        machine_id: machineId,
                        ad_medium: medium || '',
                        ad_id: adId || '',
                        target_url: targetUrl || ''
                    }),
                    keepalive: true
                }).catch(function () { });
            } catch (e) {
                // 上报失败不影响跳转
            }
        });
    }

    window.AimerUtm = {
        appendUtm: appendUtm,
        reportClick: reportClick
    };
})();
