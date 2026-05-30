const DEFAULT_THEME = {
    "--primary": "#FF9900",
    "--primary-hover": "#e68a00",
    "--bg-body": "#F5F7FA",
    "--bg-card": "#FFFFFF",
    "--text-main": "#2C3E50",
    "--text-sec": "#7F8C8D",
    "--border-color": "#E2E8F0",
    "--nav-bg": "#FFFFFF",
    "--nav-item-text": "#7F8C8D",
    "--nav-item-hover-bg": "rgba(0, 0, 0, 0.05)",
    "--nav-item-active": "#FF9900",
    "--nav-item-active-bg": "rgba(255, 153, 0, 0.1)",
    "--nav-btn-active-shadow": "rgba(255, 153, 0, 0.15)",
    "--nav-btn-active-icon-shadow": "rgba(255, 153, 0, 0.3)",
    "--nav-btn-after-bg": "rgba(255, 153, 0, 0.3)",
    "--brand-text-color": "#2C3E50",
    "--brand-text-gradient": "linear-gradient(135deg, #2C3E50 0%, #7F8C8D 100%)",
    "--brand-text-fill": "transparent",
    "--status-waiting": "#F59E0B",
    "--status-success": "#10B981",
    "--status-error": "#EF4444",
    "--status-icon-def": "#E2E8F0",
    "--mod-card-title": "#2C3E50",
    "--mod-ver-bg": "rgba(255,153,0,0.1)",
    "--mod-ver-text": "#FF9900",
    "--mod-author-text": "#7F8C8D",
    "--action-trash": "#2C3E50",
    "--action-trash-hover": "#EF4444",
    "--action-refresh": "#2C3E50",
    "--action-refresh-bg": "#FF9900",
    "--link-bili-normal": "#23ade5",
    "--link-bili-hover": "#23ade5",
    "--link-wt-normal": "#2C3E50",
    "--link-wt-hover": "#2C3E50",
    "--link-vid-normal": "#EF4444",
    "--link-vid-hover": "#EF4444",
    "--tag-tank-bg": "#DCFCE7",
    "--tag-tank-text": "#16A34A",
    "--tag-air-bg": "#F3F4F6",
    "--tag-air-text": "#4B5563",
    "--tag-naval-bg": "#E0F2FE",
    "--tag-naval-text": "#0284C7",
    "--tag-radio-bg": "#FEF9C3",
    "--tag-radio-text": "#CA8A04",
    "--tag-missile-bg": "#FFE4E8",
    "--tag-missile-text": "#DC2626",
    "--tag-music-bg": "#F3E8FF",
    "--tag-music-text": "#9333EA",

    // 默认主题变量（与样式表中使用的 CSS 变量保持一致）
    "--bg-log": "#FFFFFF",
    "--text-log": "#374151",
    "--border-log": "#f0f0f0",
    "--log-info": "#0EA5E9",
    "--log-success": "#10B981",
    "--log-error": "#EF4444",
    "--log-warn": "#F59E0B",
    "--log-sys": "#9CA3AF",
    "--log-scan": "#FF9900",
    "--bili-color-1": "#00aeec",
    "--bili-color-2": "#fb7299",
    "--win-close-hover-bg": "#EF4444",
    "--win-close-hover-text": "#FFFFFF",
    "--scrollbar-track-hover": "#ccc",
    "--notice-hero-bg-start": "#FFFFFF",
    "--notice-hero-bg-end": "#F8FAFC",
    "--notice-hero-title": "#1E293B",
    "--notice-hero-text": "#64748B",
    "--notice-hero-subtext": "#64748B",
    "--notice-hero-tag-bg": "rgba(239, 68, 68, 0.95)",
    "--notice-hero-tag-text": "#ffffff",
    "--notice-hero-shadow": "0 4px 12px rgba(15, 23, 42, 0.06)",
    "--notice-hero-deco": "rgba(100, 116, 139, 0.12)",
    "--notice-section-text": "#9CA3AF",
    "--notice-section-line": "#E5E7EB",
    "--notice-item-hover-bg": "rgba(0, 0, 0, 0.03)",
    "--notice-item-hover-text": "#FF9900",
    "--notice-arrow": "#D1D5DB",
    "--notice-footer-text": "#D1D5DB",
    "--notice-urgent-bg": "rgba(239, 68, 68, 0.12)",
    "--notice-urgent-text": "#EF4444",
    "--notice-update-bg": "rgba(59, 130, 246, 0.12)",
    "--notice-update-text": "#3B82F6",
    "--notice-event-bg": "rgba(249, 115, 22, 0.12)",
    "--notice-event-text": "#F97316",
    "--notice-bonus-bg": "rgba(16, 185, 129, 0.12)",
    "--notice-bonus-text": "#059669",
    "--notice-normal-bg": "rgba(148, 163, 184, 0.2)",
    "--notice-normal-text": "#64748B",
    "--shadow-card": "0 4px 12px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.06)",
    "--shadow-btn-primary": "0 4px 12px rgba(255,153,0,0.25)",
    "--primary-shadow": "rgba(255,153,0,0.25)",
    "--primary-shadow-hover": "rgba(255,153,0,0.35)",
    "--card-shadow-rgb": "0,0,0",
    "--card-shadow-opacity": "0.12"
};

/**
 * 前端主控制对象。
 *
 * 功能定位:
 * - 维护页面状态（当前路径/主题/已加载数据等），并提供 UI 交互与后端 API 调用的统一入口。
 *
 * 输入输出:
 * - 输入:
 *   - 用户交互（点击/输入/拖拽等）
 *   - 后端返回的数据（pywebview.api.*）
 * - 输出:
 *   - DOM 更新（列表渲染、弹窗、提示、日志面板）
 *   - 调用后端接口（安装/还原/导入/扫描/配置保存）
 * - 外部资源/依赖:
 *   - pywebview.api（后端桥接 API）
 *   - 页面 DOM（按 id/class 组织）
 *   - MinimalistLoading（加载组件）
 *
 * 实现逻辑:
 * - 按“初始化 → 页面切换 → 数据加载/刷新 → 用户操作回调”的流程组织方法。
 *
 * 业务关联:
 * - 上游: index.html 的按钮/输入与浏览器事件。
 * - 下游: main.py 的 AppApi 接口，负责实际文件系统读写与业务执行。
 */
const app = {
    currentGamePath: "",
    currentLaunchMode: "launcher",
    currentModId: null, // 当前正在操作的 mod
    currentTheme: null, // 当前主题对象
    currentThemeData: null, // 当前主题原始数据
    serverUserFeatures: null,
    _appliedThemeKeys: [],
    _libraryLoaded: false,
    _libraryRefreshing: false,
    _skinsLoaded: false,
    _skinsItems: [],
    _skinsSearchQuery: "",
    _skinsSortKey: "update_time",
    _skinsRenderSeq: 0,
    _sightsLoaded: false,
    _sightsItems: [],
    _sightsSearchQuery: "",
    _sightsSortKey: "update_time",
    _guideReady: false,
    telemetryConnected: false,
    userSeqId: 0,
    currentUiLanguage: null,
    currentPathValid: false,
    _pathUiReady: false,
    _telemetryStatusTimer: 0,
    _lastLogHtml: "",
    _lastLogAt: 0,

    // 应用主题的函数
    applyTheme(themeObj) {
        const root = document.documentElement;
        this._appliedThemeKeys.forEach(key => {
            root.style.removeProperty(key);
        });

        const appliedKeys = [];
        for (const [key, value] of Object.entries(themeObj)) {
            if (key.startsWith('--')) {
                root.style.setProperty(key, value);
                appliedKeys.push(key);
            }
        }
        this._appliedThemeKeys = appliedKeys;
        this.currentTheme = { ...themeObj };
    },

    resolveThemeColors(themeData) {
        const mode = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
        const base = themeData?.colors || {};
        const overrides = mode === 'dark' ? themeData?.dark : themeData?.light;
        return { ...base, ...(overrides || {}) };
    },

    applyThemeData(themeData) {
        if (!themeData) return;
        const themeColors = this.resolveThemeColors(themeData);
        this.applyTheme({ ...DEFAULT_THEME, ...themeColors });
        this.currentThemeData = themeData;
    },

    // 恢复默认主题（清除内联样式，交给 CSS 处理）
    resetTheme() {
        const root = document.documentElement;
        this._appliedThemeKeys.forEach(key => {
            root.style.removeProperty(key);
        });
        this._appliedThemeKeys = [];
        this.currentTheme = { ...DEFAULT_THEME };
        this.currentThemeData = null;
    },

    getDefaultUserFeatures() {
        return {
            badge_system_enabled: false,
            nickname_change_enabled: false,
            avatar_upload_enabled: false,
            notice_comment_enabled: false,
            notice_reaction_enabled: false,
            redeem_code_enabled: true,
            feedback_enabled: true,
            user_profile_enabled: false,
            ai_assistant_enabled: false,
            notification_center_enabled: false,
        };
    },

    getBasicServerReleaseFeatureLocks() {
        return {
            badge_system_enabled: false,
            nickname_change_enabled: false,
            avatar_upload_enabled: false,
            notice_comment_enabled: false,
            notice_reaction_enabled: false,
            user_profile_enabled: false,
            ai_assistant_enabled: false,
            notification_center_enabled: false,
        };
    },

    normalizeServerUserFeatures(raw = {}) {
        return {
            ...this.getDefaultUserFeatures(),
            ...(raw || {}),
            ...this.getBasicServerReleaseFeatureLocks(),
        };
    },

    getServerUserFeatures(key) {
        const features = this.normalizeServerUserFeatures(this.serverUserFeatures || window._aimerUserFeatures || {});
        if (!this.serverUserFeatures) {
            this.serverUserFeatures = features;
        }
        return key ? features[key] !== false : features;
    },

    t(key, params) {
        return window.I18N ? I18N.t(key, params) : key;
    },

    detectPreferredUiLanguage() {
        const languages = [];
        if (Array.isArray(navigator.languages)) languages.push(...navigator.languages);
        if (navigator.language) languages.push(navigator.language);
        if (navigator.userLanguage) languages.push(navigator.userLanguage);

        for (const lang of languages) {
            const normalized = String(lang || "").toLowerCase().replace("_", "-");
            if (!normalized) continue;
            if (
                normalized === "zh-tw" ||
                normalized === "zh-hk" ||
                normalized === "zh-mo" ||
                normalized.includes("hant")
            ) {
                return "zh_tw";
            }
            if (normalized.startsWith("en")) return "en_us";
            if (normalized.startsWith("ru")) return "ru_ru";
            if (normalized.startsWith("de")) return "de_de";
            if (normalized.startsWith("zh")) return "zh_cn";
        }
        return "zh_cn";
    },

    applyUiLanguage(locale) {
        if (!window.I18N) return "zh_cn";
        const applied = I18N.setLocale(locale || "zh_cn");
        this.currentUiLanguage = applied;
        this.updateLanguageSelect(applied);
        this.applyDisclaimerI18n();
        if (typeof this.refreshResourceDropdownI18n === 'function') {
            this.refreshResourceDropdownI18n();
        }
        if (typeof this.refreshResourceStatusBadgeI18n === 'function') {
            this.refreshResourceStatusBadgeI18n();
        }
        if (typeof this.updateAllResourceSelectionSummaries === 'function') {
            this.updateAllResourceSelectionSummaries();
        }
        if (this.sightsUidDropdown && typeof this.refreshSightsUidList === 'function') {
            this.refreshSightsUidList();
        }
        if (this._pathUiReady) {
            this.updatePathUI(this.currentGamePath || "", this.currentPathValid, { skipInstalledRefresh: true });
        }
        if (typeof this.refreshDynamicI18n === 'function') {
            this.refreshDynamicI18n();
        }
        return applied;
    },

    updateLanguageSelect(locale) {
        const current = locale || this.currentUiLanguage || "zh_cn";
        const textEl = document.getElementById('language-select-text');
        if (textEl && window.I18N) textEl.textContent = I18N.getLocaleName(current);
        document.querySelectorAll('#language-select-dropdown .custom-select-option').forEach(opt => {
            opt.classList.toggle('selected', opt.dataset.value === current);
        });
    },

    toggleLanguageDropdown() {
        const wrapper = document.getElementById('language-select-wrapper');
        if (!wrapper) return;
        const isActive = wrapper.classList.contains('active');
        document.querySelectorAll('.custom-select-wrapper').forEach(el => {
            el.classList.remove('active');
        });
        if (!isActive) wrapper.classList.add('active');
    },

    async selectLanguage(locale) {
        const applied = this.applyUiLanguage(locale);
        document.getElementById('language-select-wrapper')?.classList.remove('active');
        this.applyOnlineFeatureVisibility();
        if (this.isOnlineFeatureAvailable()) {
            this.renderNoticeBoard();
        }
        if (window.pywebview?.api?.set_ui_language) {
            try {
                await pywebview.api.set_ui_language(applied);
            } catch (e) {
                console.warn('set_ui_language failed:', e);
            }
        }
    },

    applyDisclaimerI18n() {
        if (!window.I18N) return;
        const modal = document.getElementById('modal-disclaimer');
        if (modal) I18N.applyToDOM(modal);
    },

    isOnlineFeatureAvailable() {
        if (!window.I18N) return true;
        if (!this.currentUiLanguage) return false;
        return I18N.isOnlineFeatureAvailable();
    },

    applyOnlineFeatureVisibility() {
        const online = this.isOnlineFeatureAvailable();
        const features = this.normalizeServerUserFeatures(this.serverUserFeatures || window._aimerUserFeatures || {});
        const visibility = {
            'cdk-redeem-card': online && features.redeem_code_enabled !== false,
            'feedback-card': online && features.feedback_enabled !== false,
            'user-profile-card': online && features.user_profile_enabled !== false,
            'btn-notification-bell': online && features.notification_center_enabled !== false,
        };
        Object.entries(visibility).forEach(([id, visible]) => {
            const el = document.getElementById(id);
            if (el) el.style.display = visible ? '' : 'none';
        });
        const noticeBoard = document.getElementById('notice-board') || document.querySelector('.notice-content');
        if (noticeBoard && !online) {
            noticeBoard.innerHTML = `
                <div class="empty-state" style="padding: 22px 12px;">
                    <i class="ri-global-line"></i>
                    <h3>${this.t('online.unavailable_title')}</h3>
                    <p>${this.t('online.unavailable_desc')}</p>
                </div>`;
        }
        const profileEnabled = online && features.user_profile_enabled !== false;
        if (!profileEnabled && window.userProfile && typeof window.userProfile.stopForCurrentLanguage === 'function') {
            window.userProfile.stopForCurrentLanguage();
        } else if (profileEnabled && window._telemetryHWID && window.userProfile && typeof window.userProfile.loadProfile === 'function') {
            window.userProfile.loadProfile();
        }
    },

    applyServerUserFeatures(raw = {}) {
        const features = this.normalizeServerUserFeatures(raw);
        this.serverUserFeatures = features;
        window._aimerUserFeatures = { ...features };

        const cdkCard = document.getElementById('cdk-redeem-card');
        if (cdkCard) cdkCard.style.display = features.redeem_code_enabled ? '' : 'none';

        const feedbackCard = document.getElementById('feedback-card');
        if (feedbackCard) feedbackCard.style.display = features.feedback_enabled ? '' : 'none';

        const openNoticeShell = document.getElementById('notice-detail-shell');
        if (openNoticeShell) {
            if (!features.notice_comment_enabled) {
                openNoticeShell.querySelectorAll('.nc-panel').forEach(el => el.remove());
                openNoticeShell.querySelectorAll('.nc-split-layout').forEach(el => el.classList.remove('nc-split-layout'));
            }
            if (!features.notice_reaction_enabled) {
                openNoticeShell.querySelectorAll('.notice-reaction-inline').forEach(el => el.remove());
            }
        }

        if (window.userProfile && typeof window.userProfile.applyFeatureSettings === 'function') {
            window.userProfile.applyFeatureSettings(features);
        }

        this.applyOnlineFeatureVisibility();
        return features;
    },

    // --- Theme Logic ---
    themeListData: [],

    async loadThemeList() {
        const dropdown = document.getElementById('theme-select-dropdown');
        const textEl = document.getElementById('theme-select-text');
        if (!dropdown) return;

        this.themeListData = [{ filename: 'default.json', name: '默认主题', version: '', author: 'System' }];

        try {
            const themes = await pywebview.api.get_theme_list();
            themes.forEach(t => {
                if (t.filename !== 'default.json') {
                    this.themeListData.push(t);
                }
            });
            this.renderThemeDropdown();
        } catch (e) {
            console.error("Failed to load themes", e);
        }
    },

    renderThemeDropdown() {
        const dropdown = document.getElementById('theme-select-dropdown');
        const textEl = document.getElementById('theme-select-text');
        if (!dropdown) return;

        dropdown.innerHTML = '';
        this.themeListData.forEach(theme => {
            const option = document.createElement('div');
            option.className = 'custom-select-option';
            option.dataset.value = theme.filename;
            const hasAuthor = theme.author && theme.author !== 'System';
            const themeLabel = hasAuthor
                ? (theme.version ? `${theme.name} (v${theme.version}) - by ${theme.author}` : `${theme.name} - by ${theme.author}`)
                : theme.name;
            option.textContent = theme.filename === 'default.json'
                ? this.t('theme.default')
                : themeLabel;
            option.onclick = () => this.selectTheme(theme.filename);
            dropdown.appendChild(option);
        });
    },

    toggleThemeDropdown() {
        const wrapper = document.getElementById('theme-select-wrapper');
        if (!wrapper) return;

        const isActive = wrapper.classList.contains('active');

        document.querySelectorAll('.custom-select-wrapper').forEach(el => {
            el.classList.remove('active');
        });

        if (!isActive) {
            wrapper.classList.add('active');
        }
    },

    selectTheme(filename) {
        const textEl = document.getElementById('theme-select-text');
        const theme = this.themeListData.find(t => t.filename === filename);
        if (textEl && theme) {
            const hasAuthor = theme.author && theme.author !== 'System';
            const themeLabel = hasAuthor
                ? (theme.version ? `${theme.name} (v${theme.version}) - by ${theme.author}` : `${theme.name} - by ${theme.author}`)
                : theme.name;
            textEl.textContent = filename === 'default.json'
                ? this.t('theme.default')
                : themeLabel;
        }

        document.querySelectorAll('#theme-select-dropdown .custom-select-option').forEach(opt => {
            opt.classList.toggle('selected', opt.dataset.value === filename);
        });

        document.getElementById('theme-select-wrapper')?.classList.remove('active');

        this.onThemeChange(filename);
    },

    async onThemeChange(filename) {
        const themeData = await pywebview.api.load_theme_content(filename);
        if (themeData && (themeData.colors || themeData.light || themeData.dark)) {
            this.applyThemeData(themeData);
            pywebview.api.save_theme_selection(filename);
        } else {
            app.showAlert(this.t('common.error'), this.t('theme.invalid'));
            this.selectTheme("default.json");
            // 尝试载入预设主题
            const defaultTheme = await pywebview.api.load_theme_content("default.json");
            if (defaultTheme) {
                this.applyThemeData(defaultTheme);
            } else {
                this.resetTheme();
            }
        }
    },

    // 初始化 - 此函数会被下方的 app.init 复盖，保留此处仅为结构完整性
    // 实际初始化逻辑请见文件末尾的 app.init = async function() {...}
    async init() {
        // 此方法将被复盖，不需要实现
    },

    initGuideSystem() {
        if (this._guideReady) return;
        if (!window.AuthorGuide || typeof window.AuthorGuide.init !== "function") return;
        window.AuthorGuide.init(this, { autoStart: true });
        this._guideReady = true;
    },

    startGuide(force = false) {
        this.initGuideSystem();
        if (!window.AuthorGuide || typeof window.AuthorGuide.start !== "function") return;
        window.AuthorGuide.start({ force: Boolean(force) });
    },

    // --- 页面切换 ---
    switchTab(tabId) {
        const current = document.querySelector('.page.active');
        if (current && current.id === `page-${tabId}`) {
            if (tabId === 'camo') this.ensureCamoResourceLoaded();
            return;
        }

        const now = (window.performance && performance.now) ? performance.now() : Date.now();
        if (this._lastTabSwitchAt && (now - this._lastTabSwitchAt) < 120) return;
        this._lastTabSwitchAt = now;

        // 更新按钮状态
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.getElementById(`btn-${tabId}`).classList.add('active');

        // 更新页面显隐
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        document.getElementById(`page-${tabId}`).classList.add('active');

        if (tabId === 'camo') {
            setTimeout(() => {
                this.ensureCamoResourceLoaded();
            }, 80);
        } else if (tabId === 'lib') {
            if (!this._libraryLoaded) this.refreshLibrary();
        }
    },

    ensureCamoResourceLoaded() {
        const camoPage = document.getElementById('page-camo');
        const skinsView = document.getElementById('view-skins');
        const sightsView = document.getElementById('view-sights');
        if (!camoPage || !skinsView) return;
        if (!camoPage.classList.contains('active')) return;

        if (skinsView.classList.contains('active')) {
            this.updateResourceStorage('skins');
            if (!this._skinsLoaded && !this._skinsRefreshing) this.refreshSkins();
            return;
        }

        if (sightsView && sightsView.classList.contains('active')) {
            this.updateResourceStorage('sights');
            if (!this._sightsLoaded) this.loadSightsView();
        }
    },

    async refreshSkins(opts) {
        const listEl = document.getElementById('skins-list');
        const countEl = document.getElementById('skins-count');
        if (!listEl || !countEl || !window.pywebview?.api?.get_skins_list) return;

        const refreshBtn = document.getElementById('btn-refresh-skins');
        if (this._skinsRefreshing) return;
        this._skinsRefreshing = true;
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.classList.add('is-loading');
        }
        countEl.textContent = this.t('tools.count_refreshing');
        await new Promise(requestAnimationFrame);

        const camoPage = document.getElementById('page-camo');
        const skinsView = document.getElementById('view-skins');
        if (!camoPage || !skinsView) {
            this._skinsRefreshing = false;
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.classList.remove('is-loading');
            }
            return;
        }
        if (!camoPage.classList.contains('active') || !skinsView.classList.contains('active')) {
            this._skinsRefreshing = false;
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.classList.remove('is-loading');
            }
            return;
        }

        this._skinsRefreshSeq = (this._skinsRefreshSeq || 0) + 1;
        const seq = this._skinsRefreshSeq;

        try {
            const forceRefresh = !!(opts && opts.manual);
            if (this._skinsFallbackTimer) {
                clearTimeout(this._skinsFallbackTimer);
                this._skinsFallbackTimer = null;
            }

            const loadBySyncApi = async () => {
                if (seq !== this._skinsRefreshSeq) return;
                try {
                    const res = await pywebview.api.get_skins_list({ force_refresh: forceRefresh });
                    if (seq !== this._skinsRefreshSeq) return;
                    this.onSkinsListReady(res);
                } catch (err) {
                    console.error(err);
                    this._skinsRefreshing = false;
                    if (refreshBtn) {
                        refreshBtn.disabled = false;
                        refreshBtn.classList.remove('is-loading');
                    }
                    countEl.textContent = this.t('resource.count_zero');
                }
            };

            if (typeof pywebview.api.refresh_skins_async === 'function') {
                const started = await pywebview.api.refresh_skins_async({ force_refresh: forceRefresh });
                if (!started) {
                    await loadBySyncApi();
                    return;
                }
                this._skinsFallbackTimer = setTimeout(loadBySyncApi, 2500);
            } else {
                await loadBySyncApi();
            }
        } catch (e) {
            console.error(e);
            this._skinsRefreshing = false;
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.classList.remove('is-loading');
            }
        }
    },

    // 接收后端异步推送的基本列表数据
    onSkinsListReady(res) {
        const listEl = document.getElementById('skins-list');
        const countEl = document.getElementById('skins-count');
        const refreshBtn = document.getElementById('btn-refresh-skins');

        if (this._skinsFallbackTimer) {
            clearTimeout(this._skinsFallbackTimer);
            this._skinsFallbackTimer = null;
        }

        if (!listEl || !countEl || !res || !res.valid) {
            this._skinsRefreshing = false;
            if (refreshBtn) refreshBtn.classList.remove('is-loading');
            return;
        }

        this._skinsItems = Array.isArray(res.items) ? res.items : [];
        this._skinsLoaded = true;

        const searchInput = document.getElementById('skins-search-input');
        const sortSelect = document.getElementById('skins-sort-select');
        if (searchInput) this._skinsSearchQuery = searchInput.value || "";
        if (sortSelect) this._skinsSortKey = sortSelect.value || "update_time";

        this._renderSkinsView();
        this.updateResourceStorage('skins');
    },

    filterSkinsNew(query) {
        this._skinsSearchQuery = String(query || "");
        if (this._skinsRefreshing && !this._skinsLoaded) return;
        this._renderSkinsView();
    },

    sortSkinsNew(sortKey) {
        this._skinsSortKey = sortKey || "update_time";
        if (this._skinsRefreshing && !this._skinsLoaded) return;
        this._renderSkinsView();
    },

    filterSkinsStatus(value) {
        this._skinsFilterStatus = value || 'all';
        if (this._skinsRefreshing && !this._skinsLoaded) return;
        this._renderSkinsView();
    },

    toggleSkinsSortOrder() {
        this._skinsSortAsc = !this._skinsSortAsc;
        const btn = document.getElementById('skins-sort-order-btn');
        if (btn) btn.classList.toggle('is-asc', this._skinsSortAsc);
        this._renderSkinsView();
    },

    _getFilteredSkins() {
        const query = String(this._skinsSearchQuery || "").trim().toLowerCase();
        let items = Array.isArray(this._skinsItems) ? this._skinsItems.slice() : [];

        /* 状态筛选 */
        const filterStatus = this._skinsFilterStatus || 'all';
        if (filterStatus !== 'all') {
            items = items.filter(it => {
                const name = String(it.name || '');
                const isDisabled = !!it.disabled || name.endsWith('.AimerWT_BAN');
                return filterStatus === 'disabled' ? isDisabled : !isDisabled;
            });
        }

        if (query) {
            items = items.filter(it => {
                const searchText = [
                    it.display_name,
                    it.folder_name || it.name,
                    it.path,
                    it.preview_path,
                    it.file_count,
                    it.size_bytes
                ].filter(v => v !== null && v !== undefined).join(" ").toLowerCase();
                return searchText.includes(query);
            });
        }

        const sortKey = this._skinsSortKey || "update_time";
        const asc = !!this._skinsSortAsc;
        items.sort((a, b) => {
            let cmp = 0;
            if (sortKey === "name") {
                const aName = String(a.display_name || a.name || "");
                const bName = String(b.display_name || b.name || "");
                cmp = aName.localeCompare(bName, "zh-CN", { numeric: true });
            } else if (sortKey === "size") {
                cmp = Number(b.size_bytes || 0) - Number(a.size_bytes || 0);
            } else {
                const bTime = Number(b.mtime || b.update_time || 0);
                const aTime = Number(a.mtime || a.update_time || 0);
                cmp = bTime - aTime;
            }
            return asc ? -cmp : cmp;
        });

        return items;
    },

    _renderSkinsView() {
        const listEl = document.getElementById('skins-list');
        const countEl = document.getElementById('skins-count');
        if (!listEl || !countEl) return;

        this._skinsRenderSeq = (this._skinsRenderSeq || 0) + 1;
        const seq = this._skinsRenderSeq;
        const items = this._getFilteredSkins();
        this.updateResourceSelectionSummary('skins', items.length);

        const selectAll = document.getElementById('skins-select-all');
        if (selectAll) {
            selectAll.checked = false;
            selectAll.indeterminate = false;
        }

        if (items.length === 0) {
            const hasQuery = String(this._skinsSearchQuery || "").trim().length > 0;
            listEl.innerHTML = `
                <div class="res-empty-state">
                    <i class="ri-brush-3-line"></i>
                    <h3>${hasQuery ? this.t('resource.no_matching_skins') : this.t('tools.empty_skins')}</h3>
                    <p>${hasQuery ? this.t('resource.try_another_keyword') : this.t('tools.empty_skins_desc')}</p>
                </div>
            `;
            this.updateResourceSelectionSummary('skins', 0);
            this._finishSkinsRender();
            return;
        }

        listEl.innerHTML = '';
        const CHUNK_SIZE = 24;
        let currentIndex = 0;
        const placeholder = 'assets/card_image_small.png';

        const renderChunk = () => {
            if (seq !== this._skinsRenderSeq) return;

            const chunk = items.slice(currentIndex, currentIndex + CHUNK_SIZE);
            const html = chunk.map(it => {
                const folderName = String(it.name || "");
                const isDisabled = folderName.endsWith(".AimerWT_BAN");
                const enabledName = isDisabled ? folderName.replace(/\.AimerWT_BAN$/, "") : folderName;
                const displayName = String(it.display_name || enabledName);
                const cover = it.cover_url || placeholder;
                const isDefaultCover = !!it.cover_is_default || !it.cover_url || !it.preview_path;
                const sizeText = app._formatBytes(it.size_bytes || 0);
                const safeName = app._escapeHtml(folderName);
                const safeDisplayName = app._escapeHtml(displayName);
                const encodedName = encodeURIComponent(folderName);
                const disabledLabel = app._escapeHtml(app.t('resource.status_disabled'));
                const cardTitle = app._escapeHtml(
                    displayName === folderName
                        ? String(it.path || '')
                        : `${displayName}\n${app.t('resource.original_folder_title', { name: folderName })}\n${it.path || ''}`
                );

                return `
                    <div class="small-card animate-in${isDisabled ? ' is-disabled-resource' : ''}" title="${cardTitle}" data-skin-name="${safeName}" data-resource-name-encoded="${encodedName}" data-disabled="${isDisabled ? '1' : '0'}">
                        <div class="small-card-img-wrapper" style="position:relative;">
                             <img class="small-card-img${isDefaultCover ? ' is-default-cover' : ''} skin-img-node"
                                  src="${cover}" loading="lazy" alt="">
                             ${isDisabled ? `<div class="resource-status-badge is-disabled">${disabledLabel}</div>` : ''}
                             <div class="skin-edit-overlay">
                                 <button class="btn-v2 icon-only small secondary skin-edit-btn"
                                         data-skin-name-encoded="${encodedName}"
                                         onclick="app.openEditSkinModal(decodeURIComponent(this.dataset.skinNameEncoded || ''), this.closest('.small-card').querySelector('.skin-img-node').src)">
                                     <i class="ri-edit-line"></i>
                                 </button>
                             </div>
                        </div>
                        <div class="small-card-body">
                            <div class="skin-card-footer">
                                <div class="skin-card-name" title="${safeDisplayName}">${safeDisplayName || app._escapeHtml(enabledName)}</div>
                                <div class="skin-card-size">${sizeText}</div>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');

            listEl.insertAdjacentHTML('beforeend', html);
            currentIndex += CHUNK_SIZE;

            if (currentIndex < items.length) {
                requestAnimationFrame(renderChunk);
            } else {
                this.updateResourceSelectionSummary('skins', items.length);
                this._finishSkinsRender();
            }
        };

        renderChunk();
    },

    _finishSkinsRender() {
        const refreshBtn = document.getElementById('btn-refresh-skins');
        this._skinsRefreshing = false;
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.classList.remove('is-loading');
        }
    },

    // 接收后端异步推送的封面数据
    onSkinCoverReady(skinName, coverUrl, coverIsDefault) {
        const item = (this._skinsItems || []).find(it => it && it.name === skinName);
        const isDefaultCover = coverIsDefault !== undefined ? !!coverIsDefault : (item ? !item.preview_path : false);
        if (item) {
            item.cover_url = coverUrl;
            item.cover_is_default = isDefaultCover;
        }
        const card = document.querySelector(`.small-card[data-skin-name="${CSS.escape(skinName)}"]`);
        if (card) {
            const img = card.querySelector('.skin-img-node');
            if (img && img.src.includes('card_image_small.png')) {
                img.src = coverUrl;
                img.classList.toggle('is-default-cover', isDefaultCover);
            }
        }
    },


    // --- Skin Editing Logic (New) ---
    currentEditSkin: null,
    currentEditSight: null,
    _cropCoverTarget: "skin",

    _updateSkinDisplayNameCount() {
        const input = document.getElementById('edit-skin-display-name');
        const counter = document.getElementById('edit-skin-display-count');
        if (!input || !counter) return;
        counter.textContent = `${String(input.value || '').length}/32`;
    },

    _updateSightDisplayNameCount() {
        const input = document.getElementById('edit-sight-display-name');
        const counter = document.getElementById('edit-sight-display-count');
        if (!input || !counter) return;
        counter.textContent = `${String(input.value || '').length}/32`;
    },

    openEditSkinModal(skinName, coverUrl) {
        this.currentEditSkin = skinName;
        this._cropCoverTarget = "skin";
        const modal = document.getElementById('modal-edit-skin');
        const displayInput = document.getElementById('edit-skin-display-name');
        const nameInput = document.getElementById('edit-skin-name');
        const coverImg = document.getElementById('edit-skin-cover');

        if (!modal || !displayInput || !nameInput || !coverImg) return;

        const item = (this._skinsItems || []).find(it => it && it.name === skinName);
        displayInput.value = item?.display_name || skinName;
        nameInput.value = item?.folder_name || skinName;
        coverImg.src = coverUrl || 'assets/coming_soon_img.png';
        this._updateSkinDisplayNameCount();

        if (displayInput.dataset.countBound !== '1') {
            displayInput.dataset.countBound = '1';
            displayInput.addEventListener('input', () => this._updateSkinDisplayNameCount());
        }

        modal.classList.remove('hiding');
        modal.classList.add('show');
    },

    async saveSkinEdit() {
        if (!this.currentEditSkin) return;

        const displayInput = document.getElementById('edit-skin-display-name');
        const folderInput = document.getElementById('edit-skin-name');
        const displayName = String(displayInput?.value || '').trim();
        const newName = String(folderInput?.value || '').trim();

        if (!displayName) {
            app.showAlert(app.t("common.error"), app.t("resource.display_name_required"), "error");
            return;
        }

        if (displayName.length > 32) {
            app.showAlert(app.t("common.error"), app.t("resource.display_name_too_long"), "error");
            return;
        }

        if (!newName) {
            app.showAlert(app.t("common.error"), app.t("tools.name_empty"), "error");
            return;
        }

        if (newName !== this.currentEditSkin) {
            try {
                const res = await pywebview.api.rename_skin(this.currentEditSkin, newName);
                if (res.success) {
                    this.currentEditSkin = newName;
                } else {
                    app.showAlert(app.t("common.failure"), app.t("tools.rename_failed", { message: res.msg }), "error");
                    return;
                }
            } catch (e) {
                app.showAlert(app.t("common.error"), app.t("common.operation_failed", { message: e }), "error");
                return;
            }
        }

        try {
            const res = await pywebview.api.set_resource_display_name('skins', this.currentEditSkin, displayName);
            if (!res || !res.success) {
                app.showAlert(app.t("common.failure"), (res && res.msg) ? res.msg : app.t("resource.display_name_save_failed"), "error");
                return;
            }
        } catch (e) {
            app.showAlert(app.t("common.error"), app.t("common.operation_failed", { message: e }), "error");
            return;
        }

        app.showAlert(app.t("common.success"), app.t("resource.skin_info_saved"), "success");
        app.closeModal('modal-edit-skin');
        this.refreshSkins();
    },

    async requestUpdateSkinCover() {
        if (!this.currentEditSkin) return;
        this._cropCoverTarget = "skin";

        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*';
        input.onchange = async () => {
            const file = input.files && input.files[0];
            if (!file) return;
            try {
                const dataUrl = await new Promise((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onerror = () => reject(new Error(app.t("common.read_image_failed")));
                    reader.onload = () => resolve(String(reader.result || ''));
                    reader.readAsDataURL(file);
                });
                this.openCropCoverModal(dataUrl);
            } catch (e) {
                console.error(e);
                this.showAlert(this.t("common.error"), this.t("common.read_image_failed"), "error");
            }
        };
        input.click();
    },

    _cropCoverState: null,

    openEditSightModal(sightName, coverUrl) {
        this.currentEditSight = sightName;
        this._cropCoverTarget = "sight";
        const modal = document.getElementById('modal-edit-sight');
        const displayInput = document.getElementById('edit-sight-display-name');
        const nameInput = document.getElementById('edit-sight-name');
        const coverImg = document.getElementById('edit-sight-cover');

        if (!modal || !displayInput || !nameInput || !coverImg) return;

        const item = (this._sightsItems || []).find(it => it && it.name === sightName);
        displayInput.value = item?.display_name || sightName;
        nameInput.value = item?.folder_name || sightName;
        coverImg.src = coverUrl || 'assets/coming_soon_img.png';
        this._updateSightDisplayNameCount();

        if (displayInput.dataset.countBound !== '1') {
            displayInput.dataset.countBound = '1';
            displayInput.addEventListener('input', () => this._updateSightDisplayNameCount());
        }

        modal.classList.remove('hiding');
        modal.classList.add('show');
    },

    async saveSightEdit() {
        if (!this.currentEditSight) return;

        const displayInput = document.getElementById('edit-sight-display-name');
        const displayName = String(displayInput?.value || '').trim();
        const newName = document.getElementById('edit-sight-name').value.trim();
        if (!displayName) {
            app.showAlert(app.t("common.error"), app.t("resource.display_name_required"), "error");
            return;
        }
        if (displayName.length > 32) {
            app.showAlert(app.t("common.error"), app.t("resource.display_name_too_long"), "error");
            return;
        }
        if (!newName) {
            app.showAlert(app.t("common.error"), app.t("tools.name_empty"), "error");
            return;
        }

        if (newName !== this.currentEditSight) {
            try {
                const res = await pywebview.api.rename_sight(this.currentEditSight, newName);
                if (res.success) {
                    this.currentEditSight = newName;
                } else {
                    app.showAlert(app.t("common.failure"), app.t("tools.rename_failed", { message: res.msg }), "error");
                    return;
                }
            } catch (e) {
                app.showAlert(app.t("common.error"), app.t("common.operation_failed", { message: e }), "error");
                return;
            }
        }

        try {
            const res = await pywebview.api.set_resource_display_name('sights', this.currentEditSight, displayName);
            if (!res || !res.success) {
                app.showAlert(app.t("common.failure"), (res && res.msg) ? res.msg : app.t("resource.display_name_save_failed"), "error");
                return;
            }
        } catch (e) {
            app.showAlert(app.t("common.error"), app.t("common.operation_failed", { message: e }), "error");
            return;
        }

        app.showAlert(app.t("common.success"), app.t("resource.sight_info_saved"), "success");
        app.closeModal('modal-edit-sight');
        this.refreshSights({ manual: true });
    },

    async requestUpdateSightCover() {
        if (!this.currentEditSight) return;
        this._cropCoverTarget = "sight";

        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*';
        input.onchange = async () => {
            const file = input.files && input.files[0];
            if (!file) return;
            try {
                const dataUrl = await new Promise((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onerror = () => reject(new Error(app.t("common.read_image_failed")));
                    reader.onload = () => resolve(String(reader.result || ''));
                    reader.readAsDataURL(file);
                });
                this.openCropCoverModal(dataUrl);
            } catch (e) {
                console.error(e);
                this.showAlert(this.t("common.error"), this.t("common.read_image_failed"), "error");
            }
        };
        input.click();
    },

    openCropCoverModal(dataUrl) {
        const modal = document.getElementById('modal-crop-cover');
        const canvas = document.getElementById('crop-canvas');
        const zoomEl = document.getElementById('crop-zoom');
        if (!modal || !canvas || !zoomEl) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const img = new Image();
        img.onload = () => {
            const cw = canvas.width;
            const ch = canvas.height;

            const scaleX = cw / img.width;
            const scaleY = ch / img.height;
            const baseScale = Math.max(scaleX, scaleY);

            const state = {
                img,
                baseScale,
                scale: 1,
                offsetX: (cw - img.width * baseScale) / 2,
                offsetY: (ch - img.height * baseScale) / 2,
                dragging: false,
                lastX: 0,
                lastY: 0,
                cw,
                ch,
            };

            this._cropCoverState = state;
            zoomEl.value = '1';

            const draw = () => {
                const s = this._cropCoverState;
                if (!s) return;
                ctx.clearRect(0, 0, cw, ch);
                const drawScale = s.baseScale * s.scale;
                const dw = s.img.width * drawScale;
                const dh = s.img.height * drawScale;
                ctx.drawImage(s.img, s.offsetX, s.offsetY, dw, dh);
            };

            const clamp = () => {
                const s = this._cropCoverState;
                if (!s) return;
                const drawScale = s.baseScale * s.scale;
                const dw = s.img.width * drawScale;
                const dh = s.img.height * drawScale;

                const minX = Math.min(0, s.cw - dw);
                const maxX = Math.max(0, s.cw - dw);
                const minY = Math.min(0, s.ch - dh);
                const maxY = Math.max(0, s.ch - dh);

                s.offsetX = Math.min(Math.max(s.offsetX, minX), maxX);
                s.offsetY = Math.min(Math.max(s.offsetY, minY), maxY);
            };

            const onPointerDown = (e) => {
                const s = this._cropCoverState;
                if (!s) return;
                s.dragging = true;
                s.lastX = e.clientX;
                s.lastY = e.clientY;
                canvas.setPointerCapture(e.pointerId);
            };
            const onPointerMove = (e) => {
                const s = this._cropCoverState;
                if (!s || !s.dragging) return;
                const dx = e.clientX - s.lastX;
                const dy = e.clientY - s.lastY;
                s.lastX = e.clientX;
                s.lastY = e.clientY;
                s.offsetX += dx;
                s.offsetY += dy;
                clamp();
                draw();
            };
            const onPointerUp = (e) => {
                const s = this._cropCoverState;
                if (!s) return;
                s.dragging = false;
                try { canvas.releasePointerCapture(e.pointerId); } catch { }
            };

            canvas.onpointerdown = onPointerDown;
            canvas.onpointermove = onPointerMove;
            canvas.onpointerup = onPointerUp;
            canvas.onpointercancel = onPointerUp;

            canvas.onwheel = (e) => {
                e.preventDefault();
                const s = this._cropCoverState;
                if (!s) return;
                const delta = e.deltaY > 0 ? -0.06 : 0.06;
                s.scale = Math.min(3, Math.max(0.2, s.scale + delta));
                zoomEl.value = String(s.scale);
                clamp();
                draw();
            };

            zoomEl.oninput = () => {
                const s = this._cropCoverState;
                if (!s) return;
                s.scale = Math.min(3, Math.max(0.2, Number(zoomEl.value || 1)));
                clamp();
                draw();
            };

            draw();
            modal.classList.remove('hiding');
            modal.classList.add('show');
        };
        img.src = dataUrl;
    },

    async applyCroppedCover() {
        const target = this._cropCoverTarget;
        // 扩展支持: skin / sight / task / model / hangar
        const has_edit_target = this.currentEditSkin || this.currentEditSight
            || (typeof TaskLibrary !== 'undefined' && TaskLibrary._current_edit_name)
            || (typeof ModelLibrary !== 'undefined' && ModelLibrary._current_edit_name)
            || (typeof Hangar !== 'undefined' && Hangar._current_edit_name);
        if (!has_edit_target) return;

        const canvas = document.getElementById('crop-canvas');
        const state = this._cropCoverState;
        if (!canvas || !state) return;

        const out = document.createElement('canvas');
        out.width = 1280;
        out.height = 720;
        const octx = out.getContext('2d');
        if (!octx) return;

        const drawScale = state.baseScale * state.scale;
        const srcScale = drawScale * (out.width / state.cw);

        const sx = (-state.offsetX) / drawScale;
        const sy = (-state.offsetY) / drawScale;
        const sw = state.cw / drawScale;
        const sh = state.ch / drawScale;

        octx.clearRect(0, 0, out.width, out.height);
        octx.drawImage(state.img, sx, sy, sw, sh, 0, 0, out.width, out.height);

        const dataUrl = out.toDataURL('image/png');
        try {
            // --- 炮镜 ---
            if (target === "sight") {
                if (!window.pywebview?.api?.update_sight_cover_data) {
                    this.showAlert(this.t("common.error"), this.t("common.feature_not_ready"), "error");
                    return;
                }
                const res = await pywebview.api.update_sight_cover_data(this.currentEditSight, dataUrl);
                if (res && res.success) {
                    const coverImg = document.getElementById('edit-sight-cover');
                    if (coverImg) coverImg.src = dataUrl;
                    this.showAlert(this.t("common.success"), this.t("tools.cover_updated"), "success");
                    this.refreshSights({ manual: true });
                    this.closeModal('modal-crop-cover');
                } else {
                    this.showAlert(this.t("common.error"), (res && res.msg) ? res.msg : this.t("tools.cover_update_failed"), "error");
                }
                return;
            }

            // --- 任务库 ---
            if (target === "task") {
                if (!window.pywebview?.api?.update_task_cover_data || typeof TaskLibrary === 'undefined') {
                    this.showAlert(this.t("common.error"), this.t("common.feature_not_ready"), "error");
                    return;
                }
                const res = await pywebview.api.update_task_cover_data(TaskLibrary._current_edit_name, dataUrl);
                if (res && res.success) {
                    const coverImg = document.getElementById('edit-task-cover');
                    if (coverImg) coverImg.src = dataUrl;
                    this.showAlert(this.t("common.success"), this.t("tools.cover_updated"), "success");
                    TaskLibrary.refresh_list();
                    this.closeModal('modal-crop-cover');
                } else {
                    this.showAlert(this.t("common.error"), (res && res.msg) ? res.msg : this.t("tools.cover_update_failed"), "error");
                }
                return;
            }

            // --- 模型库 ---
            if (target === "model") {
                if (!window.pywebview?.api?.update_model_cover_data || typeof ModelLibrary === 'undefined') {
                    this.showAlert(this.t("common.error"), this.t("common.feature_not_ready"), "error");
                    return;
                }
                const res = await pywebview.api.update_model_cover_data(ModelLibrary._current_edit_name, dataUrl);
                if (res && res.success) {
                    const coverImg = document.getElementById('edit-model-cover');
                    if (coverImg) coverImg.src = dataUrl;
                    this.showAlert(this.t("common.success"), this.t("tools.cover_updated"), "success");
                    ModelLibrary.refresh_list();
                    this.closeModal('modal-crop-cover');
                } else {
                    this.showAlert(this.t("common.error"), (res && res.msg) ? res.msg : this.t("tools.cover_update_failed"), "error");
                }
                return;
            }

            // --- 机库 ---
            if (target === "hangar") {
                if (!window.pywebview?.api?.update_hangar_cover_data || typeof Hangar === 'undefined') {
                    this.showAlert(this.t("common.error"), this.t("common.feature_not_ready"), "error");
                    return;
                }
                const res = await pywebview.api.update_hangar_cover_data(Hangar._current_edit_name, dataUrl);
                if (res && res.success) {
                    const coverImg = document.getElementById('edit-hangar-cover');
                    if (coverImg) coverImg.src = dataUrl;
                    this.showAlert(this.t("common.success"), this.t("tools.cover_updated"), "success");
                    Hangar.refresh_list();
                    this.closeModal('modal-crop-cover');
                } else {
                    this.showAlert(this.t("common.error"), (res && res.msg) ? res.msg : this.t("tools.cover_update_failed"), "error");
                }
                return;
            }

            // --- 涂装（默认） ---
            if (!window.pywebview?.api?.update_skin_cover_data) {
                this.showAlert(this.t("common.error"), this.t("common.feature_not_ready"), "error");
                return;
            }

            const res = await pywebview.api.update_skin_cover_data(this.currentEditSkin, dataUrl);
            if (res && res.success) {
                const coverImg = document.getElementById('edit-skin-cover');
                if (coverImg) coverImg.src = dataUrl;
                this.showAlert(this.t("common.success"), this.t("tools.cover_updated"), "success");
                this.refreshSkins({ manual: true });
                this.closeModal('modal-crop-cover');
            } else {
                this.showAlert(this.t("common.error"), (res && res.msg) ? res.msg : this.t("tools.cover_update_failed"), "error");
            }
        } catch (e) {
            console.error(e);
            this.showAlert(this.t("common.error"), this.t("tools.cover_update_failed"), "error");
        }
    },


    importSkinZipDialog() {
        if (!this.currentGamePath) {
            app.showAlert(app.t("common.info"), app.t("home.path_required"));
            this.switchTab('home');
            return;
        }
        if (!window.pywebview?.api?.import_skin_zip_dialog) return;
        pywebview.api.import_skin_zip_dialog();
    },

    openUserskinsResidueModal() {
        this.userskinsResidueData = null;
        this.userskinsResidueTargetPath = "";
        const modal = document.getElementById('modal-userskins-residue');
        const resultEl = document.getElementById('userskins-residue-result');
        const currentOption = document.getElementById('userskins-residue-current-option');
        const migrateBtn = document.getElementById('btn-userskins-residue-migrate');
        const scanBtn = document.getElementById('btn-userskins-residue-scan');
        if (!modal || !resultEl) return;
        resultEl.innerHTML = `<div class="userskins-residue-empty">${this._escapeHtml(this.t('userskins_residue.initial_hint'))}</div>`;
        if (currentOption) currentOption.hidden = true;
        if (migrateBtn) migrateBtn.hidden = true;
        if (scanBtn) {
            scanBtn.disabled = false;
            scanBtn.innerHTML = `<i class="ri-search-line"></i> <span>${this.t('userskins_residue.scan')}</span>`;
        }
        this._setUserskinsResidueProgress(0, this.t('userskins_residue.ready'), true);
        if (window.I18N) I18N.applyToDOM(modal);
        this.openModal('modal-userskins-residue');
    },

    _setUserskinsResidueProgress(progress, text, hidden = false) {
        const wrap = document.getElementById('userskins-residue-progress');
        const fill = document.getElementById('userskins-residue-progress-fill');
        const percentEl = document.getElementById('userskins-residue-progress-percent');
        const textEl = document.getElementById('userskins-residue-progress-text');
        const safeProgress = Math.max(0, Math.min(100, Number(progress || 0)));
        if (wrap) wrap.hidden = !!hidden;
        if (fill) fill.style.width = `${safeProgress}%`;
        if (percentEl) percentEl.textContent = `${Math.round(safeProgress)}%`;
        if (textEl) textEl.textContent = text || '';
    },

    _setUserskinsResidueBusy(isBusy, mode = 'scan') {
        const scanBtn = document.getElementById('btn-userskins-residue-scan');
        const migrateBtn = document.getElementById('btn-userskins-residue-migrate');
        if (scanBtn) {
            scanBtn.disabled = !!isBusy;
            scanBtn.innerHTML = isBusy && mode === 'scan'
                ? `<i class="ri-loader-4-line"></i> <span>${this.t('userskins_residue.scanning')}</span>`
                : `<i class="ri-search-line"></i> <span>${this.t('userskins_residue.scan')}</span>`;
        }
        if (migrateBtn) {
            migrateBtn.disabled = !!isBusy;
            if (isBusy && mode === 'migrate') {
                migrateBtn.innerHTML = `<i class="ri-loader-4-line"></i> <span>${this.t('userskins_residue.migrating')}</span>`;
            } else {
                migrateBtn.innerHTML = `<i class="ri-file-copy-2-line"></i> <span>${this.t('userskins_residue.copy_migrate')}</span>`;
            }
        }
    },

    async scanUserskinsResidue() {
        const api = window.pywebview?.api;
        if (!api?.discover_userskins_residue) {
            this.showAlert(this.t('common.error'), this.t('common.feature_not_ready'), 'error');
            return;
        }

        const resultEl = document.getElementById('userskins-residue-result');
        if (resultEl) {
            resultEl.innerHTML = `<div class="userskins-residue-empty">${this._escapeHtml(this.t('userskins_residue.scanning_hint'))}</div>`;
        }
        this._setUserskinsResidueBusy(true, 'scan');
        this._setUserskinsResidueProgress(0, this.t('userskins_residue.ready'), false);

        // 1. 开启 API 异步查询
        const apiPromise = api.discover_userskins_residue();

        // 2. 开启 1.5 - 2 秒的随机线性进度步进
        const duration = 1500 + Math.random() * 500;
        const stepTime = 30;
        const totalSteps = duration / stepTime;

        const progressPromise = new Promise((resolve) => {
            let step = 0;
            const interval = setInterval(() => {
                step += 1;
                const currentProgress = Math.min(100, (step / totalSteps) * 100);

                let text = this.t('userskins_residue.progress_current');
                if (currentProgress > 45) {
                    text = this.t('userskins_residue.progress_scan');
                }

                this._setUserskinsResidueProgress(currentProgress, text, false);

                if (step >= totalSteps) {
                    clearInterval(interval);
                    resolve();
                }
            }, stepTime);
        });

        try {
            // 3. 并行等待 API 返回以及进度条平滑走到 100%
            const [data] = await Promise.all([apiPromise, progressPromise]);

            if (!data || !data.success) {
                this._setUserskinsResidueProgress(100, this.t('userskins_residue.scan_failed'));
                this.showAlert(this.t('common.error'), data?.msg || this.t('userskins_residue.scan_failed'), 'error');
                return;
            }

            this.userskinsResidueData = data;
            this._setUserskinsResidueProgress(100, this.t('userskins_residue.scan_done'), false);

            // 给 100% 极光进度条 180ms 优雅定格，再淡出结果，提供踏实平滑的视觉质感
            await new Promise(resolve => setTimeout(resolve, 180));
            this._setUserskinsResidueProgress(100, this.t('userskins_residue.scan_done'), true);
            this._renderUserskinsResidueResult(data);
        } catch (e) {
            console.error('scanUserskinsResidue failed:', e);
            this._setUserskinsResidueProgress(100, this.t('userskins_residue.scan_failed'));
            this.showAlert(this.t('common.error'), this.t('common.call_failed', { message: e?.message || e }), 'error');
        } finally {
            this._setUserskinsResidueBusy(false, 'scan');
        }
    },

    _renderUserskinsResidueResult(data) {
        const resultEl = document.getElementById('userskins-residue-result');
        const currentOption = document.getElementById('userskins-residue-current-option');
        if (!resultEl) return;
        const folders = Array.isArray(data?.folders) ? data.folders : [];
        const visibleFolders = folders.filter(item => item && (item.exists || item.valid_game || Number(item.item_count || 0) > 0));
        if (visibleFolders.length === 0) {
            resultEl.innerHTML = `<div class="userskins-residue-empty">${this._escapeHtml(this.t('userskins_residue.not_found'))}</div>`;
            if (currentOption) currentOption.hidden = true;
            this._updateUserskinsResiduePlan();
            return;
        }

        const preferred = visibleFolders.find(item => item.is_current && item.valid_game)
            || visibleFolders.find(item => item.valid_game);
        this.userskinsResidueTargetPath = preferred?.userskins_path || "";

        const locationHtml = visibleFolders.map((item) => {
            const userskinsPath = String(item.userskins_path || '');
            const checked = userskinsPath === this.userskinsResidueTargetPath ? ' checked' : '';
            const disabled = item.valid_game ? '' : ' disabled';
            const disabledClass = item.valid_game ? '' : ' is-disabled';
            const itemCount = Number(item.item_count || 0);
            const sizeText = this._formatStorageBytes(item.total_size_bytes || 0);
            const statusText = this._userskinsResidueStatusText(item);

            // 智能选择平台图标
            const iconClass = item.install_type === 'steam' ? 'ri-steam-fill' : 'ri-computer-line';

            // 胶囊 Badge 颜色映射
            let badgeClass = 'badge-source';
            if (item.is_current) badgeClass = 'badge-current';
            else if (!item.valid_game && item.exists) badgeClass = 'badge-residue';
            else if (itemCount <= 0) badgeClass = 'badge-empty';

            return `
                <label class="userskins-residue-location${checked ? ' selected' : ''}${disabledClass}">
                    <input type="radio" name="userskins-residue-target" value="${this._escapeHtml(userskinsPath)}"${checked}${disabled}>
                    <div class="userskins-residue-location-main">
                        <div class="userskins-residue-location-title">
                            <div class="title-text">
                                <i class="${iconClass}"></i>
                                <span>${this._escapeHtml(item.install_label || this._userskinsResidueVersionText(item))}</span>
                            </div>
                            <em class="${badgeClass}">${this._escapeHtml(statusText)}</em>
                        </div>
                        <div class="userskins-residue-location-meta">
                            <span><i class="ri-folder-image-line"></i> ${this.t('userskins_residue.skin_count', { count: itemCount })}</span>
                            <span><i class="ri-database-2-line"></i> ${this._escapeHtml(sizeText)}</span>
                        </div>
                        <div class="userskins-residue-path" title="${this._escapeHtml(userskinsPath)}">${this._escapeHtml(userskinsPath)}</div>
                    </div>
                </label>
            `;
        }).join('');

        resultEl.innerHTML = `
            <div class="userskins-residue-summary">
                <strong>${this.t('userskins_residue.found_count', { count: visibleFolders.length })}</strong>
                <span>${this.t('userskins_residue.choose_main')}</span>
            </div>
            <div class="userskins-residue-list">${locationHtml}</div>
            <div class="userskins-residue-plan" id="userskins-residue-plan"></div>
        `;

        resultEl.querySelectorAll('input[name="userskins-residue-target"]').forEach((input) => {
            input.addEventListener('change', () => this.selectUserskinsResidueTarget(input.value));
        });
        this._updateUserskinsResiduePlan();
    },

    _userskinsResidueVersionText(item) {
        if (item?.install_type === 'steam') return this.t('userskins_residue.type_steam');
        if (item?.install_type === 'official') return this.t('userskins_residue.type_official');
        return this.t('userskins_residue.type_unknown');
    },

    _userskinsResidueStatusText(item) {
        if (item?.is_current) return this.t('userskins_residue.status_current');
        if (!item?.valid_game && item?.exists) return this.t('userskins_residue.status_residue');
        if (Number(item?.item_count || 0) <= 0) return this.t('userskins_residue.status_empty');
        return this.t('userskins_residue.status_source');
    },

    selectUserskinsResidueTarget(userskinsPath) {
        this.userskinsResidueTargetPath = String(userskinsPath || '');
        document.querySelectorAll('.userskins-residue-location').forEach((label) => {
            const input = label.querySelector('input[name="userskins-residue-target"]');
            label.classList.toggle('selected', input?.value === this.userskinsResidueTargetPath);
        });
        this._updateUserskinsResiduePlan();
    },

    _getUserskinsResidueSelection() {
        const folders = Array.isArray(this.userskinsResidueData?.folders) ? this.userskinsResidueData.folders : [];
        const target = folders.find(item => String(item.userskins_path || '') === String(this.userskinsResidueTargetPath || ''));
        const sources = target
            ? folders.filter(item => String(item.userskins_path || '') !== String(target.userskins_path || '') && Number(item.item_count || 0) > 0)
            : [];
        return { target, sources };
    },

    _updateUserskinsResiduePlan() {
        const planEl = document.getElementById('userskins-residue-plan');
        const migrateBtn = document.getElementById('btn-userskins-residue-migrate');
        const currentOption = document.getElementById('userskins-residue-current-option');
        const setCurrent = document.getElementById('userskins-residue-set-current');
        const { target, sources } = this._getUserskinsResidueSelection();

        if (!target) {
            if (planEl) planEl.innerHTML = `<i class="ri-error-warning-line warn"></i> <span class="warn">${this.t('userskins_residue.no_target')}</span>`;
            if (migrateBtn) migrateBtn.hidden = true;
            if (currentOption) currentOption.hidden = true;
            return;
        }

        if (currentOption) currentOption.hidden = !target.valid_game;
        if (setCurrent) {
            setCurrent.checked = true;
            setCurrent.disabled = !!target.is_current;
        }

        const totalSkins = sources.reduce((sum, item) => sum + Number(item.item_count || 0), 0);
        if (planEl) {
            planEl.innerHTML = sources.length > 0
                ? `<i class="ri-shuffle-line"></i> <span>${this.t('userskins_residue.plan_copy', { sources: sources.length, count: totalSkins })}</span>`
                : `<i class="ri-checkbox-circle-line"></i> <span>${this.t('userskins_residue.no_other_source')}</span>`;
        }
        if (migrateBtn) migrateBtn.hidden = sources.length === 0 || !target.valid_game;
    },

    async migrateUserskinsResidue() {
        const api = window.pywebview?.api;
        if (!api?.migrate_userskins_residue) {
            this.showAlert(this.t('common.error'), this.t('common.feature_not_ready'), 'error');
            return;
        }
        const { target, sources } = this._getUserskinsResidueSelection();
        if (!target || sources.length === 0) {
            this.showAlert(this.t('common.info'), this.t('userskins_residue.no_other_source'), 'warn');
            return;
        }

        const confirmHtml = `
            <div style="text-align:left;line-height:1.7;">
                <div>${this._escapeHtml(this.t('userskins_residue.confirm_copy', { sources: sources.length, target: target.install_label || target.userskins_path }))}</div>
                <div style="color:var(--text-sec);font-size:12px;margin-top:8px;">${this._escapeHtml(this.t('userskins_residue.copy_rule'))}</div>
            </div>
        `;
        const confirmed = await this.confirm(
            this.t('userskins_residue.copy_confirm_title'),
            confirmHtml,
            false,
            this.t('userskins_residue.copy_migrate')
        );
        if (!confirmed) return;

        this._setUserskinsResidueBusy(true, 'migrate');
        let copiedCount = 0;
        let skippedCount = 0;
        let failedCount = 0;

        try {
            for (let i = 0; i < sources.length; i += 1) {
                const source = sources[i];
                const progress = 10 + Math.round((i / Math.max(1, sources.length)) * 75);
                this._setUserskinsResidueProgress(progress, this.t('userskins_residue.progress_copying', { current: i + 1, total: sources.length }));
                const result = await api.migrate_userskins_residue(source.userskins_path, target.userskins_path);
                copiedCount += Number(result?.copied_count || 0);
                skippedCount += Number(result?.skipped_count || 0);
                failedCount += Number(result?.failed_count || 0);
            }

            const setCurrent = document.getElementById('userskins-residue-set-current');
            if (setCurrent?.checked && target.valid_game && !target.is_current && api?.set_userskins_residue_game_path) {
                const setResult = await api.set_userskins_residue_game_path(target.game_path);
                if (setResult?.success) {
                    await this.updatePathUI(setResult.path, true);
                }
            }

            this._setUserskinsResidueProgress(100, this.t('userskins_residue.copy_done'));
            const resultEl = document.getElementById('userskins-residue-result');
            if (resultEl) {
                resultEl.innerHTML = `
                    <div class="userskins-residue-finish">
                        <strong><i class="ri-checkbox-circle-fill"></i> ${this.t('userskins_residue.copy_done')}</strong>
                        <span>${this.t('userskins_residue.copy_summary', { copied: copiedCount, skipped: skippedCount, failed: failedCount })}</span>
                    </div>
                `;
            }
            const currentOption = document.getElementById('userskins-residue-current-option');
            const migrateBtn = document.getElementById('btn-userskins-residue-migrate');
            if (currentOption) currentOption.hidden = true;
            if (migrateBtn) migrateBtn.hidden = true;
            this.refreshSkins({ manual: true });
            this.showAlert(
                failedCount > 0 ? this.t('common.warn') : this.t('common.success'),
                this.t('userskins_residue.copy_summary', { copied: copiedCount, skipped: skippedCount, failed: failedCount }),
                failedCount > 0 ? 'warn' : 'success'
            );
        } catch (e) {
            console.error('migrateUserskinsResidue failed:', e);
            this._setUserskinsResidueProgress(100, this.t('userskins_residue.copy_failed'));
            this.showAlert(this.t('common.error'), this.t('common.call_failed', { message: e?.message || e }), 'error');
        } finally {
            this._setUserskinsResidueBusy(false, 'migrate');
        }
    },

    async importSightsFileDialog() {
        if (!this.sightsPath) {
            app.showAlert(app.t("common.info"), app.t("tools.set_sights_path"));
            return;
        }
        const api = window.pywebview?.api;
        if (!api?.select_sight_import_file || !api?.import_sight_file_from_path) {
            this.showAlert(this.t("common.error"), this.t("common.feature_not_ready"), "error");
            return;
        }
        try {
            const selected = await api.select_sight_import_file();
            if (!selected || selected.cancelled) return;
            if (!selected.success || !selected.path) {
                this.showAlert(this.t("common.error"), selected?.msg || this.t("common.select_path_failed", { message: this.t("resource.import_sight_file") }), "error");
                return;
            }
            const options = await this.buildSightImportOptions(selected.path);
            if (!options) return;
            const started = await api.import_sight_file_from_path(selected.path, options);
            if (!started) {
                this.showAlert(this.t("common.error"), this.t("common.operation_failed", { message: this.t("resource.import_sight_file") }), "error");
            }
        } catch (error) {
            this.showAlert(this.t("common.error"), error?.message || this.t("common.operation_failed", { message: this.t("resource.import_sight_file") }), "error");
        }
    },

    importSightsZipDialog() {
        return this.importSightsFileDialog();
    },

    async buildSightImportOptions(fileNameOrPath) {
        const text = String(fileNameOrPath || "");
        const lower = text.toLowerCase();
        const options = { conflict_strategy: "backup" };
        const needsTargetDialog = [".blk", ".zip", ".rar", ".7z"].some(ext => lower.endsWith(ext));
        if (!needsTargetDialog) return options;
        return this.showSightImportTargetDialog(fileNameOrPath);
    },

    showSightImportTargetDialog(fileNameOrPath) {
        return new Promise((resolve) => {
            const modalId = "modal-sight-import-target";
            let modal = document.getElementById(modalId);
            if (!modal) {
                modal = document.createElement("div");
                modal.id = modalId;
                modal.className = "modal-overlay";
                modal.innerHTML = `
                    <div class="modal-content sight-import-target-modal">
                        <h2>${this.t("sight_import.title")}</h2>
                        <p class="subtitle" id="sight-import-file-name"></p>
                        <div class="sight-import-target-options">
                            <label class="sight-import-target-option">
                                <input type="radio" name="sight-import-target-mode" value="all" checked>
                                <span>
                                    <strong>${this.t("sight_import.apply_all")}</strong>
                                    <small>${this.t("sight_import.apply_all_desc")}</small>
                                </span>
                            </label>
                            <label class="sight-import-target-option">
                                <input type="radio" name="sight-import-target-mode" value="vehicle">
                                <span>
                                    <strong>${this.t("sight_import.apply_vehicle")}</strong>
                                    <small>${this.t("sight_import.apply_vehicle_desc")}</small>
                                </span>
                            </label>
                        </div>
                        <input id="sight-import-target-input" class="input-v2 sight-import-target-input" placeholder="${this.t("sight_import.vehicle_placeholder")}">
                        <div class="modal-actions">
                            <button class="btn secondary" id="sight-import-target-cancel">${this.t("common.cancel")}</button>
                            <button class="btn primary" id="sight-import-target-ok">
                                <i class="ri-upload-cloud-2-line"></i> ${this.t("sight_import.start")}
                            </button>
                        </div>
                    </div>
                `;
                document.body.appendChild(modal);
            }

            const fileNameEl = modal.querySelector("#sight-import-file-name");
            const inputEl = modal.querySelector("#sight-import-target-input");
            const okBtn = modal.querySelector("#sight-import-target-ok");
            const cancelBtn = modal.querySelector("#sight-import-target-cancel");
            const modeInputs = Array.from(modal.querySelectorAll('input[name="sight-import-target-mode"]'));
            let done = false;

            const updateInputState = () => {
                const mode = modeInputs.find(item => item.checked)?.value || "all";
                inputEl.disabled = mode !== "vehicle";
                if (mode !== "vehicle") inputEl.value = "";
                if (mode === "vehicle") inputEl.focus();
            };
            const cleanup = () => {
                okBtn.removeEventListener("click", onOk);
                cancelBtn.removeEventListener("click", onCancel);
                modal.removeEventListener("click", onOverlay);
                modeInputs.forEach(input => input.removeEventListener("change", updateInputState));
                this.closeModal(modalId);
            };
            const finish = (value) => {
                if (done) return;
                done = true;
                cleanup();
                resolve(value);
            };
            const onOk = () => {
                const mode = modeInputs.find(item => item.checked)?.value || "all";
                const targetDir = mode === "vehicle" ? String(inputEl.value || "").trim() : "all_tanks";
                if (mode === "vehicle" && !targetDir) {
                    this.showAlert(this.t("common.info"), this.t("sight_import.vehicle_required"), "warn");
                    inputEl.focus();
                    return;
                }
                finish({ conflict_strategy: "backup", target_dir: targetDir || "all_tanks" });
            };
            const onCancel = () => finish(null);
            const onOverlay = (event) => {
                if (event.target === modal) finish(null);
            };

            if (fileNameEl) fileNameEl.textContent = this.t("sight_import.file_label", { name: String(fileNameOrPath || "").split(/[\\/]/).pop() });
            modeInputs.forEach(input => {
                input.checked = input.value === "all";
                input.addEventListener("change", updateInputState);
            });
            if (inputEl) inputEl.value = "";
            updateInputState();

            okBtn.addEventListener("click", onOk);
            cancelBtn.addEventListener("click", onCancel);
            modal.addEventListener("click", onOverlay);
            this.openModal(modalId);
        });
    },

    async uploadArchiveFileForImport(file, targetType, importOptions) {
        const api = window.pywebview?.api;
        if (!api?.begin_browser_archive_import || !api?.append_browser_archive_chunk || !api?.finish_browser_archive_import) {
                this.showAlert(this.t("common.error"), this.t("drop.drag_api_not_ready"), "error");
            return false;
        }

        const fileName = String(file?.name || "archive.zip");
        const fileSize = Number(file?.size || 0);
        const chunkSize = 256 * 1024;
        let sessionId = "";

        const readChunkAsBase64 = (blob) => new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onerror = () => reject(new Error(this.t("drop.write_drag_file_failed")));
            reader.onload = () => {
                const text = String(reader.result || "");
                const commaIndex = text.indexOf(",");
                resolve(commaIndex >= 0 ? text.slice(commaIndex + 1) : text);
            };
            reader.readAsDataURL(blob);
        });

        try {
            if (window.MinimalistLoading) {
                MinimalistLoading.show(false, this.t("drop.receive_file", { name: fileName }));
                MinimalistLoading.update(1, this.t("drop.prepare_drag_file"));
            }

            const beginRes = await api.begin_browser_archive_import(targetType, fileName, fileSize, importOptions || {});
            if (!beginRes || !beginRes.success || !beginRes.session_id) {
                this.showAlert(this.t("common.error"), beginRes?.msg || this.t("drop.create_drag_task_failed"), "error");
                if (window.MinimalistLoading) MinimalistLoading.hide();
                return false;
            }
            sessionId = beginRes.session_id;

            let offset = 0;
            let chunkIndex = 0;
            while (offset < fileSize) {
                const blob = file.slice(offset, Math.min(offset + chunkSize, fileSize));
                const chunkBase64 = await readChunkAsBase64(blob);
                const appendRes = await api.append_browser_archive_chunk(sessionId, chunkBase64);
                if (!appendRes || !appendRes.success) {
                    throw new Error(appendRes?.msg || this.t("drop.write_drag_file_failed"));
                }
                offset += blob.size;
                chunkIndex += 1;
                if (window.MinimalistLoading) {
                    const percent = Math.max(1, Math.min(95, Math.round((offset / Math.max(fileSize, 1)) * 95)));
                    MinimalistLoading.update(percent, this.t("drop.receive_file", { name: fileName }));
                }
                if (chunkIndex % 8 === 0) {
                    await new Promise(resolve => setTimeout(resolve, 0));
                }
            }

            const finishRes = await api.finish_browser_archive_import(sessionId);
            if (!finishRes || !finishRes.success) {
                this.showAlert(this.t("common.error"), finishRes?.msg || this.t("drop.drag_import_failed"), "error");
                if (window.MinimalistLoading) MinimalistLoading.hide();
                return false;
            }
            return true;
        } catch (error) {
            console.error("uploadArchiveFileForImport failed", error);
            if (sessionId && api?.cancel_browser_archive_import) {
                try {
                    await api.cancel_browser_archive_import(sessionId);
                } catch (_) { }
            }
            if (window.MinimalistLoading) MinimalistLoading.hide();
            this.showAlert(this.t("common.error"), error?.message || this.t("drop.drag_import_failed"), "error");
            return false;
        }
    },

    setupSkinsDropZone() {
        if (!window.ResourceDragOverlay) return;
        ResourceDragOverlay.register({
            resource_type: 'skins',
            target_selector: '#view-skins .res-main',
            icon: 'ri-upload-cloud-2-line',
            title: this.t('drop.skin_drag_title'),
            subtitle: this.t('drop.skin_drag_subtitle'),
            allowed_exts: ['.zip', '.rar', '.7z'],
            invalid_message: this.t('drop.skin_invalid_file'),
            missing_path_message: this.t('drop.skin_missing_path'),
            backend_drop_fallback: false,
            active_check: () => {
                const activeId = (document.querySelector('.page.active') || {}).id || '';
                const skinsView = document.getElementById('view-skins');
                return activeId === 'page-camo' && !!(skinsView && skinsView.classList.contains('active'));
            },
            on_missing_path: async () => {
                if (!this.currentGamePath) {
                    this.showAlert(this.t("common.info"), this.t("home.path_required"), "warn");
                    this.switchTab('home');
                    return true;
                }
                return false;
            },
            on_file_drop: async (file) => {
                if (!this.currentGamePath) {
                    this.showAlert(this.t("common.info"), this.t("home.path_required"), "warn");
                    this.switchTab('home');
                    return;
                }
                await this.uploadArchiveFileForImport(file, 'skins');
            },
            on_drop: async (zipPath) => {
                if (!this.currentGamePath) {
                    this.showAlert(this.t("common.info"), this.t("home.path_required"), "warn");
                    this.switchTab('home');
                    return;
                }
                if (!window.pywebview?.api?.import_skin_zip_from_path) {
                    this.showAlert(this.t("common.error"), this.t("common.feature_not_ready"), "error");
                    return;
                }
                pywebview.api.import_skin_zip_from_path(zipPath);
            }
        });
        ResourceDragOverlay.bind('skins');
    },

    setupVoiceLibraryDropZone() {
        if (!window.ResourceDragOverlay) return;
        ResourceDragOverlay.register({
            resource_type: 'voice_library',
            target_selector: '#page-lib .lib-scroll-area',
            icon: 'ri-file-zip-line',
            title: this.t('drop.voice_drag_title'),
            subtitle: this.t('drop.voice_drag_subtitle'),
            allowed_exts: ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.tgz', '.tbz2', '.bank'],
            invalid_message: this.t('drop.voice_invalid_archive'),
            missing_path_message: this.t('drop.voice_missing_path'),
            backend_drop_fallback: true,
            active_check: () => {
                const activeId = (document.querySelector('.page.active') || {}).id || '';
                return activeId === 'page-lib';
            },
            on_file_drop: async (file) => {
                await this.uploadArchiveFileForImport(file, 'voice');
            },
            on_drop: async (archivePath) => {
                if (!window.pywebview?.api?.import_voice_zip_from_path) {
                    this.showAlert(this.t('common.error'), this.t('drop.voice_api_not_ready'), 'error');
                    return;
                }
                const started = await pywebview.api.import_voice_zip_from_path(archivePath);
                if (started === false) {
                    this.showAlert(this.t('common.error'), this.t('drop.voice_import_start_failed'), 'error');
                }
            }
        });
        ResourceDragOverlay.bind('voice_library');
    },

    setupSightsDropZone() {
        if (!window.ResourceDragOverlay) return;
        ResourceDragOverlay.register({
            resource_type: 'sights',
            target_selector: '#view-sights .res-main',
            icon: 'ri-crosshair-2-line',
            title: this.t('drop.sight_drag_title'),
            subtitle: this.t('drop.sight_drag_subtitle'),
            allowed_exts: ['.blk', '.zip', '.rar', '.7z'],
            invalid_message: this.t('drop.sight_invalid_file'),
            missing_path_message: this.t('drop.sight_missing_path'),
            backend_drop_fallback: true,
            active_check: () => {
                const activeId = (document.querySelector('.page.active') || {}).id || '';
                const sightsView = document.getElementById('view-sights');
                return activeId === 'page-camo' && !!(sightsView && sightsView.classList.contains('active'));
            },
            on_missing_path: async () => {
                if (!this.sightsPath) {
                    this.showAlert(this.t("common.info"), this.t("tools.set_sights_path"), "warn");
                    return true;
                }
                return false;
            },
            on_file_drop: async (file) => {
                if (!this.sightsPath) {
                    this.showAlert(this.t("common.info"), this.t("tools.set_sights_path"), "warn");
                    return;
                }
                const options = await this.buildSightImportOptions(file?.name || "");
                if (!options) return;
                await this.uploadArchiveFileForImport(file, 'sights', options);
            },
            on_drop: async (zipPath) => {
                if (!this.sightsPath) {
                    this.showAlert(this.t("common.info"), this.t("tools.set_sights_path"), "warn");
                    return;
                }
                if (!window.pywebview?.api?.import_sight_file_from_path) {
                    this.showAlert(this.t("common.error"), this.t("common.feature_not_ready"), "error");
                    return;
                }
                const options = await this.buildSightImportOptions(zipPath);
                if (!options) return;
                pywebview.api.import_sight_file_from_path(zipPath, options);
            }
        });
        ResourceDragOverlay.bind('sights');
    },

    _formatBytes(bytes) {
        const b = Number(bytes || 0);
        if (!Number.isFinite(b) || b <= 0) return '0 MB';
        const mb = b / (1024 * 1024);
        if (mb < 1) return '<1 MB';
        if (mb < 1024) return `${mb.toFixed(0)} MB`;
        return `${(mb / 1024).toFixed(1)} GB`;
    },

    _formatStorageBytes(bytes) {
        const b = Number(bytes || 0);
        if (!Number.isFinite(b) || b <= 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        const index = Math.min(Math.floor(Math.log(b) / Math.log(1024)), units.length - 1);
        const value = b / Math.pow(1024, index);
        const digits = index <= 1 ? 0 : 1;
        return `${value.toFixed(digits)} ${units[index]}`;
    },

    _setResourceStorageState(resourceType, state, data) {
        const prefix = String(resourceType || '');
        const totalEl = document.getElementById(`${prefix}-storage-total`);
        const usedEl = document.getElementById(`${prefix}-storage-used`);
        const folderEl = document.getElementById(`${prefix}-storage-folder`);
        const barEl = document.getElementById(`${prefix}-storage-bar`);
        if (!totalEl || !usedEl || !folderEl || !barEl) return;
        const setTranslatedValue = (el, key) => {
            el.setAttribute('data-i18n', key);
            el.textContent = this.t(key);
        };
        const setStorageValue = (el, text) => {
            el.removeAttribute('data-i18n');
            el.textContent = text;
        };

        if (state === 'loading') {
            setTranslatedValue(totalEl, 'resource.loading');
            setTranslatedValue(usedEl, 'resource.loading');
            setTranslatedValue(folderEl, 'resource.loading');
            barEl.style.width = '0%';
            return;
        }

        if (state !== 'ready' || !data || !data.success) {
            setTranslatedValue(totalEl, 'resource.not_loaded');
            setTranslatedValue(usedEl, 'resource.not_loaded');
            setTranslatedValue(folderEl, data && data.reason === 'path_not_found'
                ? 'resource.path_not_set'
                : 'resource.not_loaded');
            barEl.style.width = '0%';
            return;
        }

        const totalBytes = Number(data.total_bytes || 0);
        const usedBytes = Number(data.used_bytes || 0);
        const folderBytes = Number(data.folder_size_bytes || 0);
        const usedPercent = totalBytes > 0 ? Math.max(0, Math.min(100, usedBytes / totalBytes * 100)) : 0;
        const remainingBytes = totalBytes > 0 ? Math.max(0, totalBytes - usedBytes) : 0;

        setStorageValue(totalEl, this._formatStorageBytes(totalBytes));
        setStorageValue(usedEl, this._formatStorageBytes(remainingBytes));
        setStorageValue(folderEl, this._formatStorageBytes(folderBytes));
        barEl.style.width = `${usedPercent.toFixed(1)}%`;
    },

    async updateResourceStorage(resourceType) {
        const type = String(resourceType || '').trim();
        if (!type) return;

        /* 如果当前已有有效数据，跳过 loading 状态，静默刷新 */
        const totalEl = document.getElementById(`${type}-storage-total`);
        const cur = totalEl ? totalEl.textContent.trim() : '';
        const isFirstLoad = !cur
            || cur === '未获取'
            || cur === '读取中...'
            || cur === this.t('resource.not_loaded')
            || cur === this.t('resource.loading');
        if (isFirstLoad) {
            this._setResourceStorageState(type, 'loading');
        }

        try {
            if (!window.pywebview?.api?.get_resource_storage_info) {
                this._setResourceStorageState(type, 'unavailable', { reason: 'api_unavailable' });
                return;
            }

            const result = await pywebview.api.get_resource_storage_info(type);
            this._setResourceStorageState(type, 'ready', result);
        } catch (error) {
            console.warn(`[Storage] ${type} 存储信息读取失败:`, error);
            this._setResourceStorageState(type, 'error', { reason: 'read_failed' });
        }
    },

    _escapeHtml(str) {
        return String(str || '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    },

    async copyText(text) {
        const value = String(text || '');
        if (!value) return false;
        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            try {
                await navigator.clipboard.writeText(value);
                return true;
            } catch (e) {
            }
        }
        const textarea = document.createElement('textarea');
        textarea.value = value;
        textarea.setAttribute('readonly', 'true');
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        textarea.style.pointerEvents = 'none';
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        let ok = false;
        try {
            ok = document.execCommand('copy');
        } catch (e) {
            ok = false;
        }
        document.body.removeChild(textarea);
        return ok;
    },

    openModal(modalId) {
        const el = document.getElementById(modalId);
        if (!el) return;
        if (el.classList.contains('show')) return;
        el.classList.remove('hiding');
        el.classList.add('show');
        void el.offsetWidth; // 强制触发重排，确保渐入过渡动画完美执行
    },

    closeModal(modalId) {
        const el = document.getElementById(modalId);
        if (!el) return;
        if (!el.classList.contains('show')) return;

        el.classList.add('hiding');

        const finalize = () => {
            if (!el.classList.contains('hiding')) return;
            el.classList.remove('show');
            el.classList.remove('hiding');
        };

        el.addEventListener('animationend', finalize, { once: true });
        setTimeout(finalize, 250);
    },

    openRedeemCodeModal() {
        const modal = document.getElementById('modal-redeem-code');
        const input = document.getElementById('redeem-code-input');
        if (!modal) return;

        modal.classList.remove('hiding');
        modal.classList.add('show');
        void modal.offsetWidth; // 强制触发重排，确保兑换码模态框渐入与缩放动画完美播放

        if (input) {
            window.setTimeout(() => {
                try {
                    input.focus();
                    input.select();
                } catch (_e) {
                }
            }, 50);
        }
    },

    _lastUpdateCheckTime: 0,

    async checkForUpdate() {
        const now = Date.now();
        const cooldown = 5 * 60 * 1000;
        if (now - this._lastUpdateCheckTime < cooldown) {
            const remaining = Math.ceil((cooldown - (now - this._lastUpdateCheckTime)) / 1000);
            const min = Math.floor(remaining / 60);
            const sec = remaining % 60;
            this.showAlert(this.t('common.info'), this.t('update.wait_retry', { min, sec }), 'warn');
            return;
        }

        const btn = document.getElementById('btn-check-update');
        const badge = document.getElementById('update-status-badge');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<i class="ri-loader-4-line"></i> ${this.t('update.checking')}`;
        }

        try {
            const result = await pywebview.api.check_for_update();
            this._lastUpdateCheckTime = Date.now();

            if (!result?.success) {
                this.showAlert(this.t('update.title'), result?.message || this.t('update.failed'), 'error');
                if (badge) badge.style.display = 'none';
                return;
            }

            if (result.has_update) {
                if (badge) {
                    badge.style.display = '';
                    badge.textContent = this.t('update.badge_new_version', { version: result.latest });
                    badge.style.background = 'var(--primary)';
                    badge.style.color = '#fff';
                }
                this.showAlert(this.t('update.available_title'), this.t('update.latest_version', { version: result.latest, changelog: result.changelog || '' }), 'success');
            } else {
                if (badge) {
                    badge.style.display = '';
                    badge.textContent = this.t('update.badge_latest');
                    badge.style.background = 'var(--bg-body)';
                    badge.style.color = 'var(--text-sec)';
                }
                this.showAlert(this.t('update.title'), result.message || this.t('update.current_latest'), 'success');
            }
        } catch (e) {
            console.error('checkForUpdate failed:', e);
            this.showAlert(this.t('update.title'), this.t('update.failed_retry'), 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<i class="ri-refresh-line"></i> ${this.t('settings.check_update')}`;
            }
        }
    },

    openFeedbackModal() {
        const modal = document.getElementById('modal-feedback');
        if (!modal) return;
        modal.classList.remove('hiding');
        modal.classList.add('show');
        const contact = document.getElementById('feedback-contact');
        const content = document.getElementById('feedback-content');
        if (contact) contact.value = '';
        if (content) content.value = '';
        this.updateFeedbackCount();

        // 重置分类选择器为默认值 (bug)
        const options = modal.querySelectorAll('.feedback-type-option');
        options.forEach(opt => {
            const radio = opt.querySelector('input[type="radio"]');
            if (opt.dataset.value === 'bug') {
                opt.classList.add('selected');
                if (radio) radio.checked = true;
            } else {
                opt.classList.remove('selected');
                if (radio) radio.checked = false;
            }
        });

        // 绑定分类点击事件（仅绑定一次）
        if (!this._feedbackTypesBound) {
            this._feedbackTypesBound = true;
            document.querySelectorAll('.feedback-type-option').forEach(opt => {
                opt.addEventListener('click', () => {
                    document.querySelectorAll('.feedback-type-option').forEach(o => o.classList.remove('selected'));
                    opt.classList.add('selected');
                    const radio = opt.querySelector('input[type="radio"]');
                    if (radio) radio.checked = true;
                });
            });
        }

        // 恢复提交按钮状态
        const btn = document.getElementById('btn-submit-feedback');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="ri-send-plane-line"></i> ${this.t('feedback.submit')}`;
        }
    },

    updateFeedbackCount() {
        const contact = document.getElementById('feedback-contact');
        const content = document.getElementById('feedback-content');
        const contactCount = document.getElementById('feedback-contact-count');
        const contentCount = document.getElementById('feedback-content-count');
        if (contact && contactCount) {
            contactCount.textContent = `${contact.value.length}/40`;
        }
        if (content && contentCount) {
            contentCount.textContent = `${content.value.length}/200`;
        }
    },

    async submitFeedback() {
        const contact = (document.getElementById('feedback-contact')?.value || '').trim();
        const content = (document.getElementById('feedback-content')?.value || '').trim();
        const checkedRadio = document.querySelector('input[name="feedback-category"]:checked');
        const category = checkedRadio ? checkedRadio.value : 'other';

        if (!content) {
            this.showAlert(this.t('common.info'), this.t('feedback.content_required'), 'warn');
            return;
        }

        if (!window.pywebview?.api?.submit_feedback) {
            this.showAlert(this.t('common.info'), this.t('common.feature_not_ready'), 'error');
            return;
        }

        // 禁用按钮防止重复提交
        const btn = document.getElementById('btn-submit-feedback');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<i class="ri-loader-4-line"></i> ${this.t('feedback.submitting')}`;
        }

        try {
            const res = await pywebview.api.submit_feedback(contact, content, category);
            if (res && res.submitted) {
                this.closeModal('modal-feedback');
            } else {
                this.showAlert(this.t('common.info'), (res && res.message) || this.t('feedback.submit_failed'), 'warn');
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = `<i class="ri-send-plane-line"></i> ${this.t('feedback.submit')}`;
                }
            }
        } catch (e) {
            console.error('反馈提交异常:', e);
            this.showAlert(this.t('common.error'), this.t('feedback.submit_exception'), 'error');
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<i class="ri-send-plane-line"></i> ${this.t('feedback.submit')}`;
            }
        }
    },

    _setupModalDragLock() {
        // 缓存弹窗打开状态，避免每次 pywebview 回调都做 DOM 查询
        let _anyModalOpen = false;
        const WATCHED_OVERLAY_SELECTOR = '.modal-overlay, .ai-disclaimer-modal, .ai-chat-overlay, .loading-overlay, .drop-overlay, .import-result-overlay';
        const DRAG_LOCK_OPEN_SELECTOR = '.modal-overlay.show, .ai-disclaimer-modal.show, .ai-chat-overlay.show, .loading-overlay:not(.hidden), .drop-overlay.active, .import-result-overlay';
        const PERFORMANCE_LOCK_OPEN_SELECTOR = '.modal-overlay.show, .loading-overlay:not(.hidden), .import-result-overlay';

        const patchPywebviewMoveWindow = () => {
            if (this._pywebviewMoveWindowPatched) return;
            if (!window.pywebview || typeof window.pywebview._jsApiCallback !== 'function') return;

            const original = window.pywebview._jsApiCallback.bind(window.pywebview);
            window.pywebview._jsApiCallback = (funcName, params, id) => {
                if (_anyModalOpen && funcName === 'pywebviewMoveWindow') return;
                return original(funcName, params, id);
            };
            this._pywebviewMoveWindowPatched = true;
        };

        const updateState = () => {
            _anyModalOpen = !!document.querySelector(DRAG_LOCK_OPEN_SELECTOR);
            document.body.classList.toggle('overlay-performance-lock', !!document.querySelector(PERFORMANCE_LOCK_OPEN_SELECTOR));
        };

        patchPywebviewMoveWindow();

        const classObserver = new MutationObserver(updateState);
        const watchedModals = new WeakSet();

        const watchModal = (modal) => {
            if (!(modal instanceof Element) || watchedModals.has(modal)) return;
            watchedModals.add(modal);
            classObserver.observe(modal, { attributes: true, attributeFilter: ['class'] });
        };

        const syncWatchedModals = () => {
            document.querySelectorAll(WATCHED_OVERLAY_SELECTOR).forEach(watchModal);
            updateState();
        };

        const treeObserver = new MutationObserver(syncWatchedModals);
        treeObserver.observe(document.body, { childList: true, subtree: true });

        syncWatchedModals();
    },

    _setupModalOverlayClose() {
        if (this._modalOverlayCloseBound) return;
        this._modalOverlayCloseBound = true;

        document.addEventListener('click', (e) => {
            const target = e.target;
            if (!(target instanceof Element)) return;
            if (!target.classList.contains('modal-overlay')) return;
            if (!target.classList.contains('show')) return;
            const modalId = target.id;
            if (!modalId) return;
            // 免责声明弹窗只能通过按钮关闭
            if (modalId === 'modal-disclaimer') return;

            e.stopPropagation();

            if (modalId === 'modal-confirm' && typeof this._confirmCleanup === 'function') {
                try {
                    this._confirmCleanup(false);
                } catch (err) {
                    this.closeModal(modalId);
                }
                return;
            }

            if (modalId === 'modal-archive-password') {
                this.cancelArchivePassword();
                return;
            }

            if (modalId === 'modal-mod-preview' && typeof this.closeModPreview === 'function') {
                this.closeModPreview();
                return;
            }

            this.closeModal(modalId);
        }, true);
    },

    confirm(title, messageHtml, isDanger = false, okText = null) {
        const modal = document.getElementById('modal-confirm');
        const titleEl = document.getElementById('confirm-title');
        const msgEl = document.getElementById('confirm-message');
        const okBtn = document.getElementById('btn-confirm-ok');
        const cancelBtn = document.getElementById('btn-confirm-cancel');

        if (!modal || !titleEl || !msgEl || !okBtn || !cancelBtn) {
            return Promise.resolve(false);
        }

        if (typeof this._confirmCleanup === 'function') {
            try { this._confirmCleanup(false); } catch (e) { }
        }

        titleEl.textContent = title || this.t('modal.confirm_title');
        msgEl.innerHTML = messageHtml || '';

        let finalOkText = okText;
        let iconClass = 'ri-check-line';
        const t = String(title || '');
        if (!finalOkText) {
            if (t.includes('删除') || t.toLowerCase().includes('delete')) {
                finalOkText = this.t('modal.confirm_delete');
                iconClass = 'ri-delete-bin-line';
            } else if (t.includes('还原') || t.toLowerCase().includes('restore')) {
                finalOkText = this.t('modal.confirm_restore');
                iconClass = 'ri-refresh-line';
            } else if (t.includes('冲突') || t.includes('安装') || t.toLowerCase().includes('conflict') || t.toLowerCase().includes('install')) {
                finalOkText = this.t('modal.confirm_continue');
                iconClass = 'ri-rocket-line';
            } else {
                finalOkText = isDanger ? this.t('modal.confirm_danger') : this.t('modal.confirm_ok');
                iconClass = isDanger ? 'ri-alert-line' : 'ri-check-line';
            }
        }

        okBtn.innerHTML = `<i class="${iconClass}"></i> ${finalOkText}`;
        cancelBtn.textContent = this.t('common.cancel');
        okBtn.classList.remove('primary', 'secondary', 'danger');
        okBtn.classList.add(isDanger ? 'danger' : 'primary');

        modal.classList.remove('hiding');
        modal.classList.add('show');

        return new Promise((resolve) => {
            let done = false;

            const cleanup = () => {
                okBtn.removeEventListener('click', onOk);
                cancelBtn.removeEventListener('click', onCancel);
                modal.removeEventListener('click', onOverlay);
                document.removeEventListener('keydown', onKeydown, true);
                this._confirmCleanup = null;
            };

            const finish = (result) => {
                if (done) return;
                done = true;
                cleanup();
                this.closeModal('modal-confirm');
                resolve(!!result);
            };

            const onOk = () => finish(true);
            const onCancel = () => finish(false);
            const onOverlay = (e) => {
                if (e.target === modal) finish(false);
            };
            const onKeydown = (e) => {
                if (e.key === 'Escape') finish(false);
            };

            this._confirmCleanup = finish;

            okBtn.addEventListener('click', onOk);
            cancelBtn.addEventListener('click', onCancel);
            modal.addEventListener('click', onOverlay);
            document.addEventListener('keydown', onKeydown, true);
        });
    },

    openArchivePasswordModal(archiveName, errorHint = '') {
        const modal = document.getElementById('modal-archive-password');
        const titleEl = document.getElementById('archive-password-title');
        const fileEl = document.getElementById('archive-password-file');
        const hintEl = document.getElementById('archive-password-hint');
        const input = document.getElementById('archive-password-input');
        if (!modal || !input) return;

        if (typeof this._archivePasswordCleanup === 'function') {
            try { this._archivePasswordCleanup(); } catch (e) { }
        }

        if (titleEl) titleEl.textContent = this.t('modal.archive_password_title');
        if (fileEl) fileEl.textContent = archiveName ? this.t('modal.archive_file', { name: archiveName }) : '';
        if (hintEl) {
            const hintPayload = errorHint && typeof errorHint === 'object' ? errorHint : null;
            hintEl.textContent = hintPayload?.key
                ? this.t(hintPayload.key, hintPayload.params || {})
                : (errorHint || '');
        }
        input.value = '';

        modal.classList.remove('hiding');
        modal.classList.add('show');

        const onOverlay = (e) => {
            if (e.target === modal) this.cancelArchivePassword();
        };
        const onKeydown = (e) => {
            if (e.key === 'Escape') this.cancelArchivePassword();
        };
        modal.addEventListener('click', onOverlay);
        document.addEventListener('keydown', onKeydown, true);

        this._archivePasswordCleanup = () => {
            modal.removeEventListener('click', onOverlay);
            document.removeEventListener('keydown', onKeydown, true);
            this._archivePasswordCleanup = null;
        };

        setTimeout(() => {
            try { input.focus(); } catch (e) { }
        }, 0);
    },

    onArchivePasswordKeydown(e) {
        if (!e) return;
        if (e.key === 'Enter') {
            e.preventDefault();
            this.submitArchivePassword();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            this.cancelArchivePassword();
        }
    },

    submitArchivePassword() {
        const input = document.getElementById('archive-password-input');
        const value = String(input?.value || '');
        if (!value) {
            this.showAlert(this.t('common.info'), this.t('modal.archive_password_required'), 'warn');
            return;
        }
        if (typeof this._archivePasswordCleanup === 'function') {
            try { this._archivePasswordCleanup(); } catch (e) { }
        }
        this.closeModal('modal-archive-password');
        pywebview.api.submit_archive_password(value);
    },

    cancelArchivePassword() {
        if (typeof this._archivePasswordCleanup === 'function') {
            try { this._archivePasswordCleanup(); } catch (e) { }
        }
        this.closeModal('modal-archive-password');
        pywebview.api.cancel_archive_password();
    },

    forceHideAllModals() {
        document.querySelectorAll('.modal-overlay').forEach(el => {
            el.classList.remove('show');
            el.classList.remove('hiding');
        });
    },

    initToasts() {
        if (this._toastInited) return;
        this._toastInited = true;

        const errorClose = document.getElementById('toast-error-close');
        if (errorClose) errorClose.addEventListener('click', () => this.hideErrorToast());

        const warnClose = document.getElementById('toast-warn-close');
        if (warnClose) warnClose.addEventListener('click', () => this.hideWarnToast());

        const infoClose = document.getElementById('toast-info-close');
        if (infoClose) infoClose.addEventListener('click', () => this.hideInfoToast());
    },

    formatToastMessage(message) {
        const text = String(message || '')
            .replace(/<br\s*\/?>/gi, ' ')
            .replace(/\s+/g, ' ')
            .trim();
        return text
            .replace(/^\[[^\]]+\]\s*\[[A-Z]+\]\s*/i, '')
            .replace(/^\[(SUCCESS|WARN|ERROR|INFO|SYS)\]\s*/i, '');
    },

    notifyToast(level, message) {
        const content = this.formatToastMessage(message);
        if (!content) return;
        if (level === 'ERROR') {
            this.showErrorToast(this.t('common.error'), content);
            return;
        }
        if (level === 'WARN') {
            this.showWarnToast(this.t('common.warn'), content);
            return;
        }
        if (level === 'SUCCESS') {
            this.showInfoToast(this.t('common.success'), content);
            return;
        }
        this.showInfoToast(this.t('common.info'), content);
    },

    notifyToastI18n(level, key, params = {}) {
        this.notifyToast(level, this.t(key, params || {}));
    },

    showErrorToast(title, message, duration = 5000) {
        const toast = document.getElementById('toast-error');
        if (!toast) {
            this.showAlert(title || this.t('common.error'), message, 'error');
            return;
        }

        const titleEl = toast.querySelector('.toast-error-title');
        const messageEl = toast.querySelector('.toast-error-message');

        if (titleEl) titleEl.textContent = title || this.t('common.error');
        if (messageEl) messageEl.textContent = message || '';

        toast.classList.remove('hiding');
        toast.classList.add('show');

        if (this._errorToastTimeout) {
            clearTimeout(this._errorToastTimeout);
        }

        this._errorToastTimeout = setTimeout(() => {
            this.hideErrorToast();
        }, duration);
    },

    hideErrorToast() {
        const toast = document.getElementById('toast-error');
        if (!toast) return;

        toast.classList.add('hiding');

        setTimeout(() => {
            toast.classList.remove('hiding', 'show');
        }, 300);

        if (this._errorToastTimeout) {
            clearTimeout(this._errorToastTimeout);
            this._errorToastTimeout = null;
        }
    },

    showWarnToast(title, message, duration = 5000) {
        const toast = document.getElementById('toast-warn');
        if (!toast) {
            this.showAlert(title || this.t('common.warn'), message, 'warn');
            return;
        }

        const titleEl = toast.querySelector('.toast-warn-title');
        const messageEl = toast.querySelector('.toast-warn-message');

        if (titleEl) titleEl.textContent = title || this.t('common.warn');
        if (messageEl) messageEl.textContent = message || '';

        toast.classList.remove('hiding');
        toast.classList.add('show');

        if (this._warnToastTimeout) {
            clearTimeout(this._warnToastTimeout);
        }

        this._warnToastTimeout = setTimeout(() => {
            this.hideWarnToast();
        }, duration);
    },

    hideWarnToast() {
        const toast = document.getElementById('toast-warn');
        if (!toast) return;

        toast.classList.add('hiding');

        setTimeout(() => {
            toast.classList.remove('hiding', 'show');
        }, 300);

        if (this._warnToastTimeout) {
            clearTimeout(this._warnToastTimeout);
            this._warnToastTimeout = null;
        }
    },

    showInfoToast(title, message, duration = 5000) {
        const toast = document.getElementById('toast-info');
        if (!toast) {
            this.showAlert(title || this.t('common.info'), message, 'info');
            return;
        }

        const titleEl = toast.querySelector('.toast-info-title');
        const messageEl = toast.querySelector('.toast-info-message');

        if (titleEl) titleEl.textContent = title || this.t('modal.alert_default_title');
        if (messageEl) messageEl.textContent = message || '';

        toast.classList.remove('hiding');
        toast.classList.add('show');

        if (this._infoToastTimeout) {
            clearTimeout(this._infoToastTimeout);
        }

        this._infoToastTimeout = setTimeout(() => {
            this.hideInfoToast();
        }, duration);
    },

    hideInfoToast() {
        const toast = document.getElementById('toast-info');
        if (!toast) return;

        toast.classList.add('hiding');

        setTimeout(() => {
            toast.classList.remove('hiding', 'show');
        }, 300);

        if (this._infoToastTimeout) {
            clearTimeout(this._infoToastTimeout);
            this._infoToastTimeout = null;
        }
    },

    // 自定义提示弹窗（替代原生 alert）
    showAlert(title, message, iconType = 'info', linkUrl = null, options = null) {
        const modal = document.getElementById('modal-alert');
        if (!modal) {
            console.error('modal-alert not found, falling back to native alert');
            alert(message);
            return;
        }

        const titleEl = document.getElementById('alert-title');
        const msgEl = document.getElementById('alert-message');
        const iconEl = document.getElementById('alert-icon');
        const linkBtn = document.getElementById('alert-link-btn');
        const allowHtml = !!(options && options.allowHtml);

        if (titleEl) titleEl.textContent = title || this.t('modal.alert_default_title');
        if (msgEl) {
            if (allowHtml) msgEl.innerHTML = message || '';
            else msgEl.textContent = message || '';
        }

        // 处理跳转链接按钮
        if (linkBtn) {
            if (linkUrl) {
                linkBtn.style.display = 'flex';
                linkBtn.dataset.url = linkUrl;
            } else {
                linkBtn.style.display = 'none';
                linkBtn.dataset.url = '';
            }
        }

        // 根据类型设置图标
        if (iconEl) {
            let iconClass = 'ri-information-line';
            let iconColor = 'var(--primary)';
            if (iconType === 'error') {
                iconClass = 'ri-error-warning-line';
                iconColor = 'var(--status-error)';
            } else if (iconType === 'success') {
                iconClass = 'ri-checkbox-circle-line';
                iconColor = 'var(--status-success)';
            } else if (iconType === 'warn') {
                iconClass = 'ri-alert-line';
                iconColor = 'var(--status-waiting)';
            }
            iconEl.innerHTML = `<i class="${iconClass}" style="font-size: 48px; color: ${iconColor};"></i>`;
        }

        modal.classList.remove('hiding');
        modal.classList.add('show');
    },

    // 动态更新首页公告栏文字
    updateNoticeBar(contentHtml) {
        if (!this.isOnlineFeatureAvailable()) {
            this.applyOnlineFeatureVisibility();
            return;
        }
        if (window.NoticeBoardModule && typeof window.NoticeBoardModule.updateNoticeBar === 'function') {
            window.NoticeBoardModule.updateNoticeBar(contentHtml);
            return;
        }
        const container = document.querySelector('.notice-content');
        if (container && contentHtml) {
            container.innerHTML = contentHtml;
        }
    },

    async refreshTelemetryConnectionStatus() {
        if (!window.pywebview?.api?.get_telemetry_connection_status) return;
        try {
            const connected = await pywebview.api.get_telemetry_connection_status();
            var wasDisconnected = !this.telemetryConnected;
            this.telemetryConnected = !!connected;
            if (window.pywebview?.api?.init_app_state && connected) {
                const st = await pywebview.api.init_app_state();
                if (st && st.user_seq_id) { this.userSeqId = st.user_seq_id; window._userSeqId = st.user_seq_id; }
                if (st && st.telemetry_base_url) window._telemetryBaseUrl = st.telemetry_base_url;
                if (st && st.hwid) window._telemetryHWID = st.hwid;
            }
            if (connected && wasDisconnected && this.getServerUserFeatures('user_profile_enabled') &&
                window.userProfile && typeof window.userProfile.loadProfile === 'function') {
                window.userProfile.loadProfile();
            }
            if (window.NoticeBoardModule && typeof window.NoticeBoardModule.updateServerStatusFooter === 'function') {
                window.NoticeBoardModule.updateServerStatusFooter(this.telemetryConnected, this.userSeqId);
            }
        } catch (_e) {
        }
    },

    startTelemetryStatusPolling() {
        if (this._telemetryStatusTimer) {
            clearInterval(this._telemetryStatusTimer);
            this._telemetryStatusTimer = 0;
        }
        this.refreshTelemetryConnectionStatus();
        this._telemetryStatusTimer = window.setInterval(() => {
            this.refreshTelemetryConnectionStatus();
        }, 10000);
    },

    noticeData: (window.NoticeDataModule && typeof window.NoticeDataModule.getDefaultNoticeData === 'function')
        ? window.NoticeDataModule.getDefaultNoticeData()
        : [
            {
                id: 1,
                type: 'urgent',
                tag: '维护',
                title: '服务器临时维护与线路升级公告',
                date: '今天 14:00',
                content: '为了优化联机节点性能，我们将于今晚 24:00 进行临时停机维护，预计耗时 2 小时。维护期间将无法获取云端语音包。',
                isPinned: true
            },
            {
                id: 2,
                type: 'update',
                tag: '更新',
                title: 'v3.1.0 版本更新：云端工坊上线',
                date: '昨天 09:30',
                content: '1. 新增在线语音包工坊功能；2. 优化解压引擎；3. 修复了部分系统图标丢失的BUG。',
                isPinned: false
            },
            {
                id: 3,
                type: 'event',
                tag: '活动',
                title: '周末创作者激励计划开启',
                date: '02-25',
                content: '本周末上传自制语音包至云端工坊，审核通过即可获得双倍社区积分。',
                isPinned: false
            },
            {
                id: 4,
                type: 'normal',
                tag: '日常',
                title: '关于部分杀毒软件误报的说明',
                date: '02-20',
                content: '由于更新了底层注入逻辑，部分杀软可能误报拦截，请手动添加至白名单。',
                isPinned: false
            }
        ],

    getNoticeTypeMeta(type) {
        if (window.NoticeDataModule && typeof window.NoticeDataModule.getNoticeTypeMeta === 'function') {
            return window.NoticeDataModule.getNoticeTypeMeta(type);
        }
        switch (type) {
            case 'urgent':
                return { tagClass: 'notice-tag-urgent', iconClass: 'ri-tools-line' };
            case 'update':
                return { tagClass: 'notice-tag-update', iconClass: 'ri-flashlight-line' };
            case 'event':
                return { tagClass: 'notice-tag-event', iconClass: 'ri-sparkling-2-line' };
            case 'bonus':
                return { tagClass: 'notice-tag-bonus', iconClass: 'ri-gift-line' };
            default:
                return { tagClass: 'notice-tag-normal', iconClass: 'ri-notification-3-line' };
        }
    },

    renderNoticeBoard() {
        if (!this.isOnlineFeatureAvailable()) {
            this.applyOnlineFeatureVisibility();
            return;
        }
        if (window.NoticeBoardModule && typeof window.NoticeBoardModule.renderNoticeBoard === 'function') {
            window.NoticeBoardModule.renderNoticeBoard(this);
            return;
        }
        const container = document.getElementById('notice-board') || document.querySelector('.notice-content');
        if (!container) return;
        container.innerHTML = '';
    },

    recoverToSafeState(reason) {
        try {
            const disclaimer = document.getElementById('modal-disclaimer');
            if (reason === 'backend_start' && disclaimer && disclaimer.classList.contains('show')) {
                return;
            }
            this.forceHideAllModals();
            this.switchTab('home');
        } catch (e) {
        }
    },

    // --- 主题与置顶 ---
    toggleTheme() {
        const root = document.documentElement;
        const btn = document.getElementById('btn-theme');

        if (root.getAttribute('data-theme') === 'light') {
            // 切换到深色
            root.setAttribute('data-theme', 'dark');
            // 换成太阳图标
            btn.innerHTML = '<i class="ri-sun-line"></i>';
            pywebview.api.set_theme('Dark');
        } else {
            // 切换到浅色
            root.setAttribute('data-theme', 'light');
            // 换成月亮图标
            btn.innerHTML = '<i class="ri-moon-line"></i>';
            pywebview.api.set_theme('Light');
        }
        if (this.currentThemeData) {
            this.applyThemeData(this.currentThemeData);
        }
    },

    togglePin() {
        const btn = document.getElementById('btn-pin-title');
        if (!btn) return;

        btn.classList.toggle('active');
        const isTop = btn.classList.contains('active');

        if (isTop) {
            btn.innerHTML = '<i class="ri-pushpin-fill"></i>';
        } else {
            btn.innerHTML = '<i class="ri-pushpin-line"></i>';
        }

        pywebview.api.toggle_topmost(isTop);
    },

    // --- 窗口控制 ---
    minimizeApp() {
        pywebview.api.minimize_window();
    },

    closeApp() {
        this.handleWindowClose();
    },

    // --- 路径搜索逻辑 ---
    async updatePathUI(path, valid, options = {}) {
        const input = document.getElementById('input-game-path');
        const statusIcon = document.getElementById('status-icon');
        const statusText = document.getElementById('status-text');
        const gameStatusText = document.getElementById('game-status-text');
        const gameStatusIcon = document.getElementById('game-status-icon');

        input.value = path || "";
        this.currentGamePath = path;
        this.currentPathValid = !!valid;
        this._pathUiReady = true;

        const modeText = this.currentLaunchMode === 'steam'
            ? this.t('home.launch_mode.steam')
            : this.t('home.launch_mode.launcher');
        if (valid) {
            statusIcon.innerHTML = '<i class="ri-link"></i>';
            statusIcon.className = 'status-icon active';
            statusText.textContent = this.t('home.ready.connected');
            statusText.className = 'status-text success';
            if (gameStatusIcon) {
                gameStatusIcon.innerHTML = '<i class="ri-link"></i>';
                gameStatusIcon.className = 'game-status-icon active';
            }
            if (gameStatusText) {
                gameStatusText.innerHTML = `<span style="color: var(--status-success)">${this.t('home.ready.connected')}</span><span style="color: var(--text-sec)">${this.t('home.ready.can_start', { mode: modeText })}</span>`;
                gameStatusText.className = 'game-status-text ready';
            }

            try {
                if (!options.skipInstalledRefresh && window.pywebview && pywebview.api && pywebview.api.get_installed_mods) {
                    this.installedModIds = await pywebview.api.get_installed_mods() || [];
                }
            } catch (e) {
                console.error("Failed to update installed mods:", e);
                this.installedModIds = [];
            }
        } else if (!path) {
            statusIcon.innerHTML = '<i class="ri-wifi-off-line"></i>';
            statusIcon.className = 'status-icon';
            statusText.textContent = this.t('home.status.path_unset');
            statusText.className = 'status-text waiting';
            if (gameStatusIcon) {
                gameStatusIcon.innerHTML = '<i class="ri-wifi-off-line"></i>';
                gameStatusIcon.className = 'game-status-icon';
            }
            if (gameStatusText) {
                gameStatusText.textContent = this.t('home.ready.not_ready');
                gameStatusText.className = 'game-status-text waiting';
            }
            this.installedModIds = [];
        } else {
            statusIcon.innerHTML = '<i class="ri-error-warning-line"></i>';
            statusIcon.className = 'status-icon';
            statusText.textContent = this.t('home.status.invalid_path');
            statusText.className = 'status-text error';
            if (gameStatusIcon) {
                gameStatusIcon.innerHTML = '<i class="ri-error-warning-line"></i>';
                gameStatusIcon.className = 'game-status-icon error';
            }
            if (gameStatusText) {
                gameStatusText.textContent = this.t('home.ready.invalid_path');
                gameStatusText.className = 'game-status-text error';
            }
            this.installedModIds = [];
        }

        if (this.modCache && this.modCache.length > 0) {
            this.renderList(this.modCache);
        }
    },

    startGame() {
        if (!this.currentGamePath) {
            this.showAlert(this.t('common.info'), this.t('home.path_required'));
            return;
        }
        if (window.AuthorGuide?.isActive?.()) {
            this.showAlert(this.t('modal.guide_running'), this.t('modal.launch_demo'), 'info');
            return;
        }
        if (!window.pywebview?.api?.start_game) {
            this.showAlert(this.t('common.error'), this.t('common.not_ready_backend'), 'error');
            return;
        }
        pywebview.api.start_game().then((result) => {
            const success = typeof result === 'object' ? Boolean(result?.success) : Boolean(result);
            if (success) {
                this.notifyToast('SUCCESS', this.t('home.start_game_sent'));
                return;
            }

            const message = typeof result === 'object' && result?.message_key
                ? this.t(result.message_key, result.message_params || {})
                : (typeof result === 'object' && result?.message
                    ? result.message
                    : this.t('home.start_game_failed'));
            this.showAlert(this.t('common.error'), message, 'error');
        }).catch((e) => {
            const message = e && e.message ? e.message : String(e || '');
            this.showAlert(this.t('common.error'), this.t('home.start_game_failed_with_message', { message }), 'error');
        });
    },

    openLaunchSettings() {
        const modal = document.getElementById('modal-launch-settings');
        if (!modal) return;

        const launcherCard = document.getElementById('option-launch-launcher');
        const steamCard = document.getElementById('option-launch-steam');
        const setActive = (card, active) => {
            if (!card) return;
            card.classList.toggle('active', active);
            const check = card.querySelector('.option-card-check i');
            if (check) check.style.display = active ? 'block' : 'none';
        };

        const mode = this.currentLaunchMode || 'launcher';
        setActive(launcherCard, mode === 'launcher');
        setActive(steamCard, mode === 'steam');

        modal.classList.remove('hiding');
        modal.classList.add('show');
        void modal.offsetWidth; // 强制触发重排，确保启动设置模态框缓入过渡和面板轻微升起完美渲染
    },

    async saveLaunchSettings(mode) {
        if (!mode) return;
        this.currentLaunchMode = mode;

        const launcherCard = document.getElementById('option-launch-launcher');
        const steamCard = document.getElementById('option-launch-steam');
        const setActive = (card, active) => {
            if (!card) return;
            card.classList.toggle('active', active);
            const check = card.querySelector('.option-card-check i');
            if (check) check.style.display = active ? 'block' : 'none';
        };

        setActive(launcherCard, mode === 'launcher');
        setActive(steamCard, mode === 'steam');

        if (window.pywebview?.api?.set_launch_mode) {
            try {
                await pywebview.api.set_launch_mode(mode);
            } catch (e) {
                const message = e && e.message ? e.message : String(e || '');
                this.showAlert(this.t('common.error'), this.t('home.save_launch_failed', { message }), 'error');
            }
        }
        this.closeModal('modal-launch-settings');
        const gameStatusText = document.getElementById('game-status-text');
        if (gameStatusText && gameStatusText.classList.contains('ready')) {
            const modeText = mode === 'steam' ? this.t('home.launch_mode.steam') : this.t('home.launch_mode.launcher');
            gameStatusText.innerHTML = `<span style="color: var(--status-success)">${this.t('home.ready.connected')}</span><span style="color: var(--text-sec)">${this.t('home.ready.can_start', { mode: modeText })}</span>`;
        }
    },

    async browsePath() {
        if (!window.pywebview?.api?.browse_folder) {
            console.error('API not ready: browse_folder');
            this.showAlert(this.t('common.error'), this.t('common.not_ready_backend'), 'error');
            return;
        }
        try {
            const res = await pywebview.api.browse_folder();
            if (res) {
                this.updatePathUI(res.path, res.valid);
            }
        } catch (e) {
            console.error('browsePath failed:', e);
            this.showAlert(this.t('common.error'), this.t('common.select_path_failed', { message: e.message }), 'error');
        }
    },

    async toggleTelemetry(checked) {
        const toggle = document.getElementById('telemetry-switch');
        // 先还原 UI 状态，等待确认
        toggle.checked = !checked;
        const action = checked ? this.t('settings.telemetry_enable_action') : this.t('settings.telemetry_disable_action');
        const message = checked
            ? this.t('settings.telemetry_enable_message')
            : this.t('settings.telemetry_disable_message');
        // 关闭时显示红色确认按钮，开启时显示普通按钮
        const isDanger = !checked;
        const yes = await app.confirm(app.t('settings.telemetry_confirm_title', { action }), message, isDanger);
        if (yes) {
            toggle.checked = checked; // 用户确认，应用新状态
            await pywebview.api.set_telemetry_status(checked);
            await this.refreshTelemetryConnectionStatus();
        }
    },

    async toggleAutostart(checked) {
        const toggle = document.getElementById('autostart-switch');
        if (!window.pywebview?.api?.set_autostart_status) {
            toggle.checked = !checked;
            this.showAlert(this.t('common.error'), this.t('common.backend_not_ready_short'), 'error');
            return;
        }
        try {
            const success = await pywebview.api.set_autostart_status(checked);
            if (!success) {
                toggle.checked = !checked;
                this.showAlert(this.t('common.error'), this.t('settings.autostart_failed'), 'error');
            }
        } catch (e) {
            toggle.checked = !checked;
            console.error('toggleAutostart failed:', e);
            this.showAlert(this.t('common.error'), this.t('settings.set_failed', { message: e.message }), 'error');
        }
    },

    async toggleTrayMode(checked) {
        const toggle = document.getElementById('tray-mode-switch');
        if (!window.pywebview?.api?.set_tray_mode_status) {
            toggle.checked = !checked;
            this.showAlert(this.t('common.error'), this.t('common.backend_not_ready_short'), 'error');
            return;
        }
        try {
            await pywebview.api.set_tray_mode_status(checked);
            // 更新本地状态
            this._trayMode = checked;
        } catch (e) {
            toggle.checked = !checked;
            console.error('toggleTrayMode failed:', e);
            this.showAlert(this.t('common.error'), this.t('settings.set_failed', { message: e.message }), 'error');
        }
    },

    async toggleCloseConfirm(checked) {
        const toggle = document.getElementById('close-confirm-switch');
        if (!window.pywebview?.api?.set_close_confirm_status) {
            toggle.checked = !checked;
            this.showAlert(this.t('common.error'), this.t('common.backend_not_ready_short'), 'error');
            return;
        }
        try {
            await pywebview.api.set_close_confirm_status(checked);
            // 更新本地状态
            this._closeConfirm = checked;
        } catch (e) {
            toggle.checked = !checked;
            console.error('toggleCloseConfirm failed:', e);
            this.showAlert(this.t('common.error'), this.t('settings.set_failed', { message: e.message }), 'error');
        }
    },

    /**
     * 处理窗口关闭事件
     * 根据配置决定是直接关闭、最小化到托盘，还是显示确认弹窗
     */
    handleWindowClose() {
        // 如果托盘模式已开启，直接最小化到托盘
        if (this._trayMode) {
            this.minimizeToTray();
            return;
        }

        // 如果关闭确认已禁用，直接退出
        if (!this._closeConfirm) {
            this.exitApp();
            return;
        }

        // 显示关闭确认弹窗
        this.showCloseConfirmModal();
    },

    /**
     * 显示关闭确认弹窗
     */
    showCloseConfirmModal() {
        // 重置复选框
        const rememberCheckbox = document.getElementById('close-confirm-remember');
        if (rememberCheckbox) {
            rememberCheckbox.checked = false;
        }
        this.openModal('modal-close-confirm');
    },

    /**
     * 处理关闭确认弹窗的按钮点击
     * @param {string} action - 'cancel' | 'tray' | 'exit'
     */
    async handleCloseAction(action) {
        if (action === 'cancel') {
            this.closeModal('modal-close-confirm');
            return;
        }

        // 检查是否勾选了"不再提示"
        const rememberCheckbox = document.getElementById('close-confirm-remember');
        const remember = rememberCheckbox && rememberCheckbox.checked;

        if (remember) {
            // 用户选择了记住选择
            if (action === 'tray') {
                // 记住选择：开启托盘模式，关闭确认提示
                await this.toggleTrayMode(true);
                await this.toggleCloseConfirm(false);
                // 更新UI开关状态
                const traySwitch = document.getElementById('tray-mode-switch');
                const confirmSwitch = document.getElementById('close-confirm-switch');
                if (traySwitch) traySwitch.checked = true;
                if (confirmSwitch) confirmSwitch.checked = false;
            } else if (action === 'exit') {
                // 记住选择：关闭托盘模式，关闭确认提示
                await this.toggleTrayMode(false);
                await this.toggleCloseConfirm(false);
                // 更新UI开关状态
                const traySwitch = document.getElementById('tray-mode-switch');
                const confirmSwitch = document.getElementById('close-confirm-switch');
                if (traySwitch) traySwitch.checked = false;
                if (confirmSwitch) confirmSwitch.checked = false;
            }
        }

        this.closeModal('modal-close-confirm');

        if (action === 'tray') {
            this.minimizeToTray();
        } else if (action === 'exit') {
            this.exitApp();
        }
    },

    /**
     * 最小化到托盘
     */
    minimizeToTray() {
        if (window.pywebview?.api?.minimize_to_tray) {
            pywebview.api.minimize_to_tray();
        } else {
            // 降级处理：直接隐藏窗口
            console.log('[App] 最小化到托盘（降级处理）');
        }
    },

    /**
     * 退出程序
     */
    exitApp() {
        console.log('[App] 用户选择退出程序');
        if (window.pywebview?.api?.exit_app) {
            pywebview.api.exit_app();
        } else {
            // 降级处理
            window.close();
        }
    },

    autoSearch() {
        if (!window.pywebview?.api?.start_auto_search) {
            console.error('API not ready: start_auto_search');
            this.showAlert(this.t('common.error'), this.t('common.not_ready_backend'), 'error');
            return;
        }
        document.getElementById('btn-auto-search').disabled = true;
        document.getElementById('status-text').textContent = this.t('home.status.searching');
        document.getElementById('status-icon').innerHTML = '<i class="ri-loader-4-line"></i>';
        const gameStatusIcon = document.getElementById('game-status-icon');
        if (gameStatusIcon) {
            gameStatusIcon.innerHTML = '<i class="ri-loader-4-line"></i>';
            gameStatusIcon.className = 'game-status-icon searching';
        }
        try {
            pywebview.api.start_auto_search();
        } catch (e) {
            console.error('autoSearch failed:', e);
            document.getElementById('btn-auto-search').disabled = false;
            this.showAlert(this.t('common.error'), this.t('home.auto_search_failed', { message: e.message }), 'error');
        }
    },

    // 被 Python 调用的回调
    onSearchSuccess(path) {
        this.updatePathUI(path, true);
        document.getElementById('btn-auto-search').disabled = false;
    },

    onSearchFail() {
        this.updatePathUI("", false);
        document.getElementById('btn-auto-search').disabled = false;
    },

    // --- 日志系统 ---
    getLogClass(level, message) {
        const normalizedLevel = String(level || '').toUpperCase();
        const text = String(message || '');
        if (normalizedLevel === 'ERROR' || text.includes('ERROR') || text.includes('错误')) return 'error';
        if (normalizedLevel === 'SUCCESS' || text.includes('SUCCESS') || text.includes('成功')) return 'success';
        if (normalizedLevel === 'WARN' || normalizedLevel === 'WARNING' || text.includes('WARN')) return 'warn';
        if (normalizedLevel === 'SYS' || text.includes('SYS')) return 'sys';
        return 'info';
    },

    appendLogMessage(message, forcedClass = null, allowHtml = false) {
        const container = document.getElementById('log-container');
        if (!container) return;

        const normalizedMsg = String(message || '').trim();
        const now = Date.now();

        // 避免极短时间内同一条日志被重复追加到运行日志面板。
        if (normalizedMsg && normalizedMsg === this._lastLogHtml && (now - this._lastLogAt) < 500) {
            return;
        }
        if (normalizedMsg) {
            const recent = this._recentLogFingerprints || (this._recentLogFingerprints = new Map());
            for (const [msg, ts] of recent) {
                if ((now - ts) > 5000) recent.delete(msg);
            }
            if (recent.has(normalizedMsg)) {
                return;
            }
            recent.set(normalizedMsg, now);
            if (recent.size > 80) {
                const oldestKey = recent.keys().next().value;
                recent.delete(oldestKey);
            }
        }

        this._lastLogHtml = normalizedMsg;
        this._lastLogAt = now;

        const div = document.createElement('div');
        const cls = forcedClass || this.getLogClass('', message);
        div.className = `log-line ${cls}`;
        if (allowHtml) {
            div.innerHTML = message; // 兼容旧日志中的 <br>
        } else {
            div.textContent = message;
        }
        container.appendChild(div);
        container.scrollTop = container.scrollHeight; // 自动滚动到底部
    },

    appendLog(htmlMsg) {
        this.appendLogMessage(htmlMsg, null, true);
    },

    appendI18nLog(level, key, params = {}, prefix = '') {
        const content = this.t(key, params || {});
        const text = `${prefix || ''}${content}`;
        this.appendLogMessage(text, this.getLogClass(level, text), false);
    },

    updateSearchLog(msg) {
        // 更新最后一行而不是追加
        const container = document.getElementById('log-container');
        if (container.lastElementChild && container.lastElementChild.classList.contains('scan')) {
            container.lastElementChild.textContent = msg;
        } else {
            const div = document.createElement('div');
            div.className = 'log-line scan';
            div.textContent = msg;
            container.appendChild(div);
        }
        container.scrollTop = container.scrollHeight;
    },

    updateSearchLogI18n(key, params = {}) {
        this.updateSearchLog(this.t(key, params || {}));
    },

    clearLogs() {
        document.getElementById('log-container').innerHTML = '';
        this._lastLogHtml = "";
        this._lastLogAt = 0;
        if (this._recentLogFingerprints) this._recentLogFingerprints.clear();
        if (window.pywebview?.api?.clear_logs) {
            pywebview.api.clear_logs();
        }
    },

    // --- 语音包库逻辑 ---
    async refreshLibrary(opts) {
        const listContainer = document.getElementById('lib-list');
        if (!listContainer) {
            return;
        }
        if (this._libraryRefreshing) {
            return;
        }
        const isManual = !!(opts && opts.manual);
        if (!isManual && this._libraryLoaded) {
            return;
        }

        // 检查 API 是否就绪
        if (!window.pywebview?.api?.get_library_list) {
            console.warn('refreshLibrary: API not ready, will retry later');
            // 短暂延迟后重试
            setTimeout(() => {
                this._libraryRefreshing = false;
                this.refreshLibrary(opts);
            }, 1000);
            return;
        }

        this._libraryRefreshing = true;

        listContainer.classList.add('fade-out');
        await new Promise(r => setTimeout(r, 200));

        try {
            const mods = await pywebview.api.get_library_list({ force_refresh: isManual });
            app.modCache = mods;
            this.renderList(mods);
        } catch (e) {
            console.error('refreshLibrary failed:', e);
            listContainer.innerHTML = `
                <div class="empty-state">
                    <i class="ri-error-warning-line"></i>
                    <h3>${this.t('lib.load_failed')}</h3>
                    <p>${this.t('lib.backend_status_check', { message: e.message })}</p>
                </div>
            `;
        } finally {
            requestAnimationFrame(() => {
                listContainer.classList.remove('fade-out');
            });

            this._libraryLoaded = true;
            this._libraryRefreshing = false;
        }
    },

    renderList(modsToRender) {
        const listContainer = document.getElementById('lib-list');
        listContainer.innerHTML = '';
        this.bindModNoteTooltip();

        if (modsToRender.length === 0) {
            listContainer.innerHTML = `
                <div class="empty-state" style="grid-column: 1 / span 2; animation: cardEntrance 0.5s ease both;">
                    <i class="ri-search-line"></i>
                    <h3>${this.t('lib.no_search_result')}</h3>
                    <p>${this.t('lib.try_other_keyword_or_import')}</p>
                </div>`;
            return;
        }

        modsToRender.forEach((mod, index) => {
            const card = this.createModCard(mod);
            // 卡片入场动画延迟：按索引递增并限制最大延迟
            const delay = Math.min(index * 0.05, 0.5);
            card.style.animationDelay = `${delay}s`;
            listContainer.appendChild(card);
        });
    },

    filterTimeout: null,
    filterLibrary(keyword) {
        if (!app.modCache) return;

        // 防抖处理，避免输入太快导致动画混乱
        if (this.filterTimeout) clearTimeout(this.filterTimeout);

        this.filterTimeout = setTimeout(async () => {
            const listContainer = document.getElementById('lib-list');
            const term = keyword.toLowerCase().trim();

            const filtered = app.modCache.filter(mod => {
                const title = (mod.title || "").toLowerCase();
                const author = (mod.author || "").toLowerCase();
                return title.includes(term) || author.includes(term);
            });

            // 先让旧列表淡出
            listContainer.classList.add('fade-out');
            await new Promise(r => setTimeout(r, 200));

            this.renderList(filtered);

            // 再让新列表淡入
            requestAnimationFrame(() => {
                listContainer.classList.remove('fade-out');
            });
        }, 150);
    },

    createModCard(mod) {
        const div = document.createElement('div');
        div.className = 'card mod-card';
        const safeModId = String(mod?.id || '');
        div.dataset.id = safeModId; // 添加 ID 标识，方便动画定位

        const escapeHtml = (value) => app._escapeHtml(String(value == null ? '' : value));
        const safeClass = (value, fallback = '') => {
            const cls = String(value || '').trim();
            return /^[a-zA-Z0-9_-]+$/.test(cls) ? cls : fallback;
        };
        const translate_or = (key, params = {}, fallback = '') => {
            const text = this.t(key, params);
            return text === key ? (fallback || key) : text;
        };
        const localize_lang = (lang) => {
            const key_map = {
                '多语言': 'mod.lang_multi',
                '中': 'mod.lang_cn',
                '美': 'mod.lang_us',
                '英': 'mod.lang_uk',
                '俄': 'mod.lang_ru',
                '德': 'mod.lang_de',
                '日': 'mod.lang_jp',
                '法': 'mod.lang_fr',
                '未识别': 'mod.lang_unknown',
                '其他': 'mod.lang_other',
            };
            return translate_or(key_map[String(lang || '').trim()] || '', {}, lang);
        };
        const capability_label = (key, fallback) => translate_or(`mod.capability_${key}`, {}, fallback);
        const sanitizeCardUrl = (value) => {
            const raw = String(value || '').trim();
            if (!raw) return '';
            if (/^(https?:\/\/|mailto:)/i.test(raw)) return raw;
            if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(raw)) return `https://${raw}`;
            return '';
        };
        const sanitizeImageUrl = (value) => {
            const raw = String(value || '').trim();
            if (!raw) return '';
            if (/^data:image\/(?:png|jpe?g|webp|gif|bmp);base64,/i.test(raw)) return raw;
            if (/^(https?:\/\/|\.{0,2}\/|assets\/)/i.test(raw)) return raw;
            return '';
        };

        const titleText = String(mod?.title || translate_or('mod.untitled_voice_pack', {}, '未命名语音包'));
        const authorText = String(mod?.author || translate_or('mod.unknown_author', {}, '未知作者'));
        const sizeText = String(mod?.size_str || '0 MB');
        const capabilities = (mod?.capabilities && typeof mod.capabilities === 'object') ? mod.capabilities : {};
        const imgUrl = sanitizeImageUrl(mod?.cover_url);
        let tagsHtml = '';

        // 标签映射优先使用 UI_CONFIG；当 UI_CONFIG 不存在时使用内置映射
        if (typeof UI_CONFIG !== 'undefined' && UI_CONFIG.tagMap) {
            for (const [key, conf] of Object.entries(UI_CONFIG.tagMap)) {
                if (capabilities[key]) {
                    const tagConf = conf || {};
                    tagsHtml += `<span class="tag ${safeClass(tagConf.cls, 'default')}">${escapeHtml(capability_label(key, tagConf.text || key))}</span>`;
                }
            }
        } else {
            if (capabilities.tank) tagsHtml += `<span class="tag tank">${escapeHtml(capability_label('tank', '陆战'))}</span>`;
            if (capabilities.air) tagsHtml += `<span class="tag air">${escapeHtml(capability_label('air', '空战'))}</span>`;
            if (capabilities.naval) tagsHtml += `<span class="tag naval">${escapeHtml(capability_label('naval', '海战'))}</span>`;
            if (capabilities.radio) tagsHtml += `<span class="tag radio">${escapeHtml(capability_label('radio', '无线电/局势'))}</span>`;
            if (capabilities.missile) tagsHtml += `<span class="tag missile">${escapeHtml(capability_label('missile', '导弹音效'))}</span>`;
            if (capabilities.music) tagsHtml += `<span class="tag music">${escapeHtml(capability_label('music', '音乐包'))}</span>`;
            if (capabilities.noise) tagsHtml += `<span class="tag noise">${escapeHtml(capability_label('noise', '降噪包'))}</span>`;
            if (capabilities.pilot) tagsHtml += `<span class="tag pilot">${escapeHtml(capability_label('pilot', '飞行员语音'))}</span>`;
        }

        let fullLangList = [];
        if (mod?.language && Array.isArray(mod.language) && mod.language.length > 0) {
            fullLangList = mod.language.map(lang => String(lang || '').trim()).filter(Boolean);
        } else if (mod?.language && typeof mod.language === 'string') {
            fullLangList = [mod.language.trim()].filter(Boolean);
        } else {
            fullLangList = (titleText.includes("Aimer") || safeModId === "Aimer") ? ["中", "美", "俄"] : ["未识别"];
        }

        // 过滤出主要展示语言 (中/美/英)
        let displayLangs = fullLangList.filter(lang => ["中", "美", "英"].includes(lang));
        if (displayLangs.length === 0) {
            displayLangs = fullLangList.includes("未识别") ? ["未识别"] : ["其他"];
        }

        const langHtml = displayLangs.map(lang => {
            let cls = "";
            if (typeof UI_CONFIG !== 'undefined' && UI_CONFIG.langMap && UI_CONFIG.langMap[lang]) {
                cls = safeClass(UI_CONFIG.langMap[lang]);
            }
            return `<span class="lang-text ${cls}">${escapeHtml(localize_lang(lang))}</span>`;
        }).join('<span style="margin:0 2px">/</span>');

        // 拼接悬停显示的完整列表
        const localizedFullLangList = fullLangList.map(localize_lang);
        const langTooltip = fullLangList.length > 0
            ? translate_or('mod.supported_languages', { languages: localizedFullLangList.join(', ') }, `支持语言: ${localizedFullLangList.join(', ')}`)
            : translate_or('mod.unknown_language', {}, '未识别语言');

        const updateDate = String(mod?.date || translate_or('mod.unknown_date', {}, '未知日期'));

        const videoUrl = sanitizeCardUrl(mod?.link_video);
        const wtLiveUrl = sanitizeCardUrl(mod?.link_wtlive);
        const biliUrl = sanitizeCardUrl(mod?.link_bilibili);

        const clsVideo = videoUrl ? 'video' : 'disabled';
        const clsWt = wtLiveUrl ? 'wt' : 'disabled';
        const clsBili = biliUrl ? 'bili' : 'disabled';

        const noteText = String(mod?.note || translate_or('mod.no_message', {}, '暂无留言'));

        // 判断该语音包是否为当前已生效项
        const isInstalled = Array.isArray(app.installedModIds) && app.installedModIds.includes(safeModId);

        // 根据状态决定按钮样式和图标
        // 已安装: active 样式, check 图标, title="当前已加载"
        // 未安装: 普通样式, play-circle 图标, title="加载此语音包"
        const loadBtnClass = isInstalled ? 'action-btn-load active' : 'action-btn-load';
        const loadBtnIcon = isInstalled ? 'ri-check-line' : 'ri-play-circle-line';
        const loadBtnTitle = isInstalled ? this.t('lib.current_loaded') : this.t('lib.load_voice_pack');

        // 处理版本号显示，避免出现 vv2.53 的情况
        let displayVersion = String(mod?.version || "1.0");
        if (displayVersion.toLowerCase().startsWith('v')) {
            displayVersion = displayVersion.substring(1);
        }

        const filesHtml = Array.isArray(mod?.files) && mod.files.length > 0 ?
            mod.files.map(f => {
                const fileCls = safeClass(f?.cls || 'default', 'default');
                const fileType = String(f?.type || '');
                return `<span class="tag ${fileCls}" title="${escapeHtml(translate_or('mod.contains_module', { module: fileType }, `包含模块: ${fileType}`))}">${escapeHtml(fileType)}</span>`;
            }).join('')
            : tagsHtml;

        div.innerHTML = `
            <div class="mod-img-area">
                <img src="${escapeHtml(imgUrl)}" alt="${escapeHtml(titleText)}" class="mod-img" onerror="this.style.display='none'">
            </div>

            <div class="mod-info-area">
                <div class="mod-ver">v${escapeHtml(displayVersion)}</div>

                <div class="mod-title-row">
                    <div class="mod-title" title="${escapeHtml(titleText)}">${escapeHtml(titleText)}</div>
                </div>

                <div class="mod-author-row">
                    <i class="ri-user-3-line"></i> <span>${escapeHtml(authorText)}</span>
                    <span style="margin: 0 5px; color:#ddd">|</span>
                    <i class="ri-hard-drive-2-line"></i> <span>${escapeHtml(sizeText)}</span>
                    <span style="margin: 0 5px; color:#ddd">|</span>

                    <div class="mod-lang-wrap" title="${escapeHtml(langTooltip)}" style="display:inline-flex; align-items:center; cursor:help;">
                        <i class="ri-translate"></i>
                        <span style="margin-left:2px">${langHtml || escapeHtml(localize_lang('未识别'))}</span>
                    </div>
                </div>

                <div class="mod-meta-row" style="margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; min-height: 20px;">
                    ${filesHtml}
                </div>

                <div style="font-size:11px; color:var(--text-log); opacity:0.6; margin: 6px 0 8px; display:flex; align-items:center; gap:4px;">
                    <i class="ri-time-line"></i> ${escapeHtml(translate_or('mod.updated_at', { date: updateDate }, `更新于: ${updateDate}`))}
                </div>

                <div class="mod-note">
                    <i class="ri-chat-1-line" style="vertical-align:middle; margin-right:4px; opacity:0.7"></i>
                    ${escapeHtml(noteText)}
                </div>
            </div>

            <button class="mod-copy-action" title="${escapeHtml(translate_or('mod.copy_country_title', {}, '复制国籍文件'))}">
                <i class="ri-file-copy-line"></i>
            </button>

            <div class="mod-actions-col">
                <div class="action-icon action-btn-del-dropdown" data-action="delete-menu" title="${escapeHtml(translate_or('mod.delete_options', {}, '删除选项'))}">
                    <i class="ri-delete-bin-line"></i>
                    <i class="ri-arrow-down-s-line" style="font-size: 12px; margin-left: -2px;"></i>
                </div>

                <div style="flex:1"></div>

                <div class="action-icon ${clsVideo}" data-action="open-link" data-url="${escapeHtml(videoUrl)}" title="${escapeHtml(translate_or('mod.watch_video', {}, '观看介绍视频'))}">
                    <i class="ri-play-circle-line"></i>
                </div>

                <div class="action-icon ${clsWt}" data-action="open-link" data-url="${escapeHtml(wtLiveUrl)}" title="${escapeHtml(translate_or('mod.visit_wt_live', {}, '访问 WT Live 页面'))}">
                    <i class="ri-global-line"></i>
                </div>

                <div class="action-icon ${clsBili}" data-action="open-link" data-url="${escapeHtml(biliUrl)}" title="${escapeHtml(translate_or('mod.visit_bilibili', {}, '访问 Bilibili'))}">
                    <i class="ri-bilibili-line"></i>
                </div>

                <button class="${loadBtnClass}" data-action="load" title="${escapeHtml(loadBtnTitle)}">
                    <i class="${loadBtnIcon}" style="font-size: 24px;"></i>
                </button>
            </div>
        `;

        div.dataset.caps = JSON.stringify(capabilities);
        const copyBtn = div.querySelector('.mod-copy-action');
        if (copyBtn) {
            copyBtn.dataset.modId = safeModId;
            copyBtn.dataset.modTitle = titleText;
            copyBtn.addEventListener('click', () => {
                app.openCopyCountryModal(copyBtn.dataset.modId, copyBtn.dataset.modTitle);
            });
        }
        const deleteBtn = div.querySelector('[data-action="delete-menu"]');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', (event) => {
                app.showDeleteMenu(event, safeModId);
            });
        }
        div.querySelectorAll('[data-action="open-link"]').forEach((btn) => {
            const url = btn.dataset.url || '';
            if (!url) {
                btn.setAttribute('aria-disabled', 'true');
                return;
            }
            btn.addEventListener('click', () => {
                app.openExternal(url);
            });
        });
        const loadBtn = div.querySelector('[data-action="load"]');
        if (loadBtn) {
            loadBtn.addEventListener('click', () => {
                app.openInstallModal(safeModId);
            });
        }
        const noteEl = div.querySelector('.mod-note');
        if (noteEl) noteEl.dataset.note = noteText;
        return div;
    },

    bindModNoteTooltip() {
        const listContainer = document.getElementById('lib-list');
        if (!listContainer || this._modNoteTooltipBound) return;
        this._modNoteTooltipBound = true;

        listContainer.addEventListener('mouseover', (e) => {
            const noteEl = e.target.closest('.mod-note');
            if (!noteEl || !listContainer.contains(noteEl)) return;
            if (noteEl.contains(e.relatedTarget)) return;
            const text = noteEl.dataset.note || '';
            if (!text) return;
            app.showTooltip(noteEl, text);
            this._tooltipTarget = noteEl;
        });

        listContainer.addEventListener('mouseout', (e) => {
            const noteEl = e.target.closest('.mod-note');
            if (!noteEl || !listContainer.contains(noteEl)) return;
            if (noteEl.contains(e.relatedTarget)) return;
            if (this._tooltipTarget === noteEl) {
                app.hideTooltip();
                this._tooltipTarget = null;
            }
        });

        listContainer.addEventListener('click', async (e) => {
            if (e.button !== 0) return;
            const noteEl = e.target.closest('.mod-note');
            if (!noteEl || !listContainer.contains(noteEl)) return;
            const text = noteEl.dataset.note || '';
            if (!text) return;
            e.stopPropagation();
            await app.copyText(text);
        });
    },

    currentCopyModId: null,
    openCopyCountryModal(modId, modTitle) {
        this.currentCopyModId = modId || null;
        const modal = document.getElementById('modal-copy-country');
        const titleEl = document.getElementById('copy-country-title');
        const input = document.getElementById('copy-country-code');
        if (!modal || !input) return;
        if (titleEl) {
            titleEl.textContent = modTitle
                ? this.t('copy_country.title_with_mod', { title: modTitle })
                : this.t('copy_country.title');
        }
        input.value = '';
        modal.classList.remove('hiding');
        modal.classList.add('show');
    },
    async confirmCopyCountryFiles(mode) {
        const modal = document.getElementById('modal-copy-country');
        const input = document.getElementById('copy-country-code');
        const code = String(input?.value || '').trim().toLowerCase();
        if (!this.currentCopyModId) {
            this.showAlert(this.t('common.error'), this.t('copy_country.no_mod'), 'error');
            return;
        }
        if (!code) {
            this.showAlert(this.t('common.error'), this.t('copy_country.code_required'), 'error');
            return;
        }
        if (!/^[a-z]{2,10}$/.test(code)) {
            this.showAlert(this.t('common.error'), this.t('copy_country.code_invalid'), 'error');
            return;
        }
        const includeGround = mode ? mode === 'ground' : true;
        const includeRadio = mode ? mode === 'radio' : true;
        if (!includeGround && !includeRadio) {
            this.showAlert(this.t('common.error'), this.t('copy_country.type_required'), 'error');
            return;
        }
        try {
            const res = await pywebview.api.copy_country_files(
                this.currentCopyModId,
                code,
                includeGround,
                includeRadio
            );
            if (res && res.success) {
                const created = (res.created || []).length;
                const skipped = (res.skipped || []).length;
                const missing = (res.missing || []).length;
                this.showAlert(this.t('common.success'), this.t('copy_country.copied', {
                    created,
                    skipped: skipped ? this.t('copy_country.skipped', { count: skipped }) : '',
                    missing: missing ? this.t('copy_country.missing', { count: missing }) : ''
                }), 'success');
                if (modal) this.closeModal('modal-copy-country');
            } else {
                this.showAlert(this.t('common.failure'), res?.msg || this.t('copy_country.copy_failed'), 'error');
            }
        } catch (e) {
            this.showAlert(this.t('common.error'), this.t('copy_country.call_failed', { message: e }), 'error');
        }
    },

    // --- 导入功能新逻辑 ---
    openImportModal() {
        const el = document.getElementById('modal-import');
        el.classList.remove('hiding');
        el.classList.add('show');
    },

    importSelectedZip() {
        app.closeModal('modal-import');
        // 调用后端选择文件接口
        pywebview.api.import_selected_zip();
    },

    importPendingZips() {
        app.closeModal('modal-import');
        // 调用后端批量导入接口 (原 import_zips)
        pywebview.api.import_zips();
    },

    openFolder(type) {
        if (type === 'game' || type === 'userskins' || type === 'user_missions') {
            if (!this.currentGamePath) {
                app.showAlert(this.t("common.info"), this.t("home.path_required"));
                this.switchTab('home');
                return;
            }
        }
        pywebview.api.open_folder(type);
    },

    refreshHangar(opts) {
        if (typeof Hangar !== 'undefined') {
            Hangar.refresh_list(opts);
        }
    },

    refreshModels(opts) {
        if (typeof ModelLibrary !== 'undefined') {
            ModelLibrary.refresh_list(opts);
        }
    },

    openBiliSpace() {
        window.open('https://space.bilibili.com/1379084732?spm_id_from=333.1007.0.0');
    },

    openGitHubRepo() {
        window.open('https://github.com/AimerSo/Aimer_WT');
    },

    openExternal(url) {
        const u = String(url || '').trim();
        if (!u) return;
        let finalUrl = u;
        if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(finalUrl)) {
            finalUrl = 'https://' + finalUrl;
        }
        const scheme = (finalUrl.match(/^([a-zA-Z][a-zA-Z0-9+.-]*):/) || [])[1]?.toLowerCase();
        if (!['http', 'https', 'mailto'].includes(scheme)) {
            if (typeof app.showToast === 'function') app.showToast(this.t('common.unsupported_link_protocol'), 'warning');
            return;
        }
        try {
            const parsedUrl = new URL(finalUrl);
            if ((scheme === 'http' || scheme === 'https') && !parsedUrl.host) return;
            if (scheme === 'mailto' && !parsedUrl.pathname) return;
        } catch (_) {
            return;
        }

        // 优先使用后端 API 以在外部浏览器打开，并处理协议头
        if (window.pywebview?.api?.open_external) {
            pywebview.api.open_external(finalUrl);
        } else {
            // 降级方案
            window.open(finalUrl, '_blank', 'noopener');
        }
    },

    openSupportMe() {
        const modal = document.getElementById('modal-support-me');
        if (!modal) return;
        modal.classList.remove('hiding');
        modal.classList.add('show');
    },

    openImagePreview(src, title) {
        const modal = document.getElementById('modal-image-preview');
        const img = document.getElementById('image-preview-img');
        const titleEl = document.getElementById('image-preview-title');
        if (!modal || !img) return;

        img.src = src;
        if (titleEl) titleEl.textContent = title || this.t('modal.image_preview');

        modal.classList.remove('hiding');
        modal.classList.add('show');
    },

    openWorkshopChooser() {
        const el = document.getElementById('modal-workshop');
        if (!el) return;
        el.classList.remove('hiding');
        el.classList.add('show');
    },

    openWorkshop(site) {
        const key = String(site || '').toLowerCase();
        const url = key === 'liker'
            ? 'https://wtliker.com/'
            : 'https://live.warthunder.com/feed/all/';

        this.closeModal('modal-workshop');
        window.open(url);
    },

    async deleteMod(modId) {
        const yes = await app.confirm(
            this.t('lib.delete_confirm_title'),
            this.t('lib.delete_confirm_message', { id: modId }),
            true
        );
        if (yes) {
            // 找到对应的卡片并添加离场动画
            const card = document.querySelector(`.mod-card[data-id="${modId}"]`);
            if (card) {
                card.classList.add('leaving');
                // 等待动画结束 (300ms)
                await new Promise(r => setTimeout(r, 300));
            }

            const result = await pywebview.api.delete_mod(modId);
            if (result && result.success) {
                app.showToast(result.msg || this.t('lib.delete_from_library'), 'success');

                // 更新已安装列表
                try {
                    if (window.pywebview && pywebview.api && pywebview.api.get_installed_mods) {
                        this.installedModIds = await pywebview.api.get_installed_mods() || [];
                    }
                } catch (e) {
                    console.error("Failed to update installed mods:", e);
                }

                // 强制刷新库列表以更新卡片状态
                this.refreshLibrary({ manual: true });
            } else {
                app.showToast(result?.msg || this.t('lib.delete_failed'), 'error');
            }
        }
    },

    showDeleteMenu(event, modId) {
        event.stopPropagation();

        // 检查是否已安装
        pywebview.api.get_installed_mods_info().then(result => {
            const isInstalled = result.success && result.mods && result.mods[modId];

            const menuItems = [
                {
                    label: this.t('lib.delete_library'),
                    icon: 'ri-folder-reduce-line',
                    description: this.t('lib.delete_library_desc'),
                    action: () => this.deleteModLibraryOnly(modId)
                }
            ];

            if (isInstalled) {
                menuItems.push({
                    label: this.t('lib.uninstall_game'),
                    icon: 'ri-uninstall-line',
                    description: this.t('lib.uninstall_game_desc'),
                    action: () => this.uninstallModFromGame(modId)
                });
                menuItems.push({
                    label: this.t('lib.uninstall_modules'),
                    icon: 'ri-list-check',
                    description: this.t('lib.uninstall_modules_desc'),
                    action: () => this.showUninstallModulesDialog(modId)
                });
            }

            menuItems.push({
                label: this.t('lib.delete_complete'),
                icon: 'ri-delete-bin-line',
                description: this.t('lib.delete_complete_desc'),
                action: () => this.deleteModCompletely(modId),
                danger: true
            });

            app.showContextMenu(event, menuItems);
        }).catch(err => {
            console.error('获取安装信息失败:', err);
            app.showToast(app.t('lib.install_info_failed'), 'error');
        });
    },

    async deleteModLibraryOnly(modId) {
        const yes = await app.confirm(
            this.t('lib.delete_library_title'),
            this.t('lib.delete_library_message', { id: modId }),
            true
        );
        if (yes) {
            const card = document.querySelector(`.mod-card[data-id="${modId}"]`);
            if (card) {
                card.classList.add('leaving');
                await new Promise(r => setTimeout(r, 300));
            }

            const result = await pywebview.api.delete_mod(modId);
            if (result && result.success) {
                app.showToast(this.t('lib.delete_from_library'), 'success');

                // 更新已安装列表
                try {
                    if (window.pywebview && pywebview.api && pywebview.api.get_installed_mods) {
                        this.installedModIds = await pywebview.api.get_installed_mods() || [];
                    }
                } catch (e) {
                    console.error("Failed to update installed mods:", e);
                }

                // 强制刷新库列表以更新卡片状态
                this.refreshLibrary({ manual: true });
            } else {
                app.showToast(result?.msg || this.t('lib.delete_failed'), 'error');
            }
        }
    },

    async uninstallModFromGame(modId) {
        const yes = await app.confirm(
            this.t('lib.uninstall_game_title'),
            this.t('lib.uninstall_game_message', { id: modId }),
            true
        );
        if (yes) {
            const card = document.querySelector(`.mod-card[data-id="${modId}"]`);
            if (card) {
                card.style.transition = 'all 0.3s ease';
                card.style.opacity = '0.5';
                card.style.transform = 'scale(0.95)';
            }

            const result = await pywebview.api.uninstall_mod(modId);
            if (result && result.success) {
                app.showToast(this.t('lib.uninstall_success', { count: result.removed || 0 }), 'success');
                if (card) {
                    card.style.opacity = '1';
                    card.style.transform = 'scale(1)';
                }

                // 更新已安装列表
                try {
                    if (window.pywebview && pywebview.api && pywebview.api.get_installed_mods) {
                        this.installedModIds = await pywebview.api.get_installed_mods() || [];
                    }
                } catch (e) {
                    console.error("Failed to update installed mods:", e);
                }

                // 强制刷新库列表
                this.refreshLibrary({ manual: true });
            } else {
                app.showToast(result?.msg || this.t('lib.uninstall_failed'), 'error');
                if (card) {
                    card.style.opacity = '1';
                    card.style.transform = 'scale(1)';
                }
            }
        }
    },

    async deleteModCompletely(modId) {
        const yes = await app.confirm(
            this.t('lib.delete_complete_title'),
            this.t('lib.delete_complete_message', { id: modId }),
            true
        );
        if (yes) {
            const card = document.querySelector(`.mod-card[data-id="${modId}"]`);
            if (card) {
                card.classList.add('leaving');
                await new Promise(r => setTimeout(r, 300));
            }

            const result = await pywebview.api.delete_mod_completely(modId);
            if (result && result.success) {
                app.showToast(this.t('lib.delete_complete_success'), 'success');

                // 更新已安装列表
                try {
                    if (window.pywebview && pywebview.api && pywebview.api.get_installed_mods) {
                        this.installedModIds = await pywebview.api.get_installed_mods() || [];
                    }
                } catch (e) {
                    console.error("Failed to update installed mods:", e);
                }

                // 强制刷新库列表
                this.refreshLibrary({ manual: true });
            } else {
                app.showToast(result?.msg || this.t('lib.delete_failed'), 'error');
            }
        }
    },

    async showUninstallModulesDialog(modId) {
        // 获取语音包详情和已安装信息
        const [mods, installedInfo] = await Promise.all([
            pywebview.api.get_library_list(),
            pywebview.api.get_installed_mods_info()
        ]);

        const mod = mods.find(m => m.id === modId);
        if (!mod || !mod.files || mod.files.length === 0) {
            app.showToast(this.t('lib.module_info_unavailable'), 'error');
            return;
        }

        // 获取已安装的文件列表
        const installedFiles = installedInfo.success && installedInfo.mods && installedInfo.mods[modId]
            ? installedInfo.mods[modId].files || []
            : [];

        if (installedFiles.length === 0) {
            app.showToast(this.t('lib.no_installed_files'), 'warning');
            return;
        }

        // 只显示已安装的模块
        const moduleOptions = mod.files.filter(f => {
            const moduleCode = f.code.toLowerCase();
            return installedFiles.some(file => file.toLowerCase().includes(moduleCode));
        }).map(f => ({
            value: f.code,
            label: f.type,
            cls: f.cls || 'default'
        }));

        if (moduleOptions.length === 0) {
            app.showToast(this.t('lib.no_uninstallable_modules'), 'warning');
            return;
        }

        // 创建模态框
        const modalId = 'modal-uninstall-modules';
        let existingModal = document.getElementById(modalId);
        if (existingModal) {
            existingModal.remove();
        }

        const modalHtml = `
            <div id="${modalId}" class="modal-overlay">
                <div class="modal-content" style="max-width: 480px; text-align: left;">
                    <h2 style="margin: 0 0 8px 0; font-size: 22px; font-weight: 600; color: var(--text-main);">${this.t('lib.uninstall_modules_title')}</h2>
                    <p style="margin: 0 0 24px 0; color: var(--text-sec); font-size: 14px;">
                        ${this.t('lib.voice_pack_label')}: <strong style="color: var(--primary);">${mod.title || modId}</strong>
                    </p>

                    <div class="toggle-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 12px; margin-bottom: 30px;">
                        ${moduleOptions.map(opt => `
                            <div class="toggle-btn available module-toggle" data-module="${opt.value}" style="height: 90px; opacity: 1; pointer-events: all;">
                                <span class="tag ${opt.cls}" style="font-size: 28px; margin-bottom: 8px;">${this.getModuleIcon(opt.cls)}</span>
                                <span style="font-size: 13px; font-weight: 500; text-align: center; line-height: 1.3;">${opt.label}</span>
                            </div>
                        `).join('')}
                    </div>

                    <div style="display: flex; gap: 12px; justify-content: flex-end; align-items: center;">
                        <button class="btn secondary modal-cancel-btn" style="height: 40px; padding: 0 20px; display: flex; align-items: center; justify-content: center;">${this.t('common.cancel')}</button>
                        <button class="btn primary modal-confirm-btn" style="height: 40px; padding: 0 20px; display: flex; align-items: center; justify-content: center; gap: 6px;">
                            <i class="ri-uninstall-line"></i>
                            <span>${this.t('lib.uninstall_selected')}</span>
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);
        const modal = document.getElementById(modalId);

        // 绑定事件
        const cancelBtn = modal.querySelector('.modal-cancel-btn');
        const confirmBtn = modal.querySelector('.modal-confirm-btn');
        const toggleBtns = modal.querySelectorAll('.module-toggle');

        const closeModal = () => {
            modal.classList.add('hiding');
            setTimeout(() => modal.remove(), 200);
        };

        cancelBtn.addEventListener('click', closeModal);

        // 切换选中状态
        toggleBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                btn.classList.toggle('selected');
            });
        });

        confirmBtn.addEventListener('click', () => {
            const selectedModules = Array.from(modal.querySelectorAll('.module-toggle.selected'))
                .map(btn => btn.dataset.module);

            if (selectedModules.length === 0) {
                app.showToast(app.t('lib.select_module_required'), 'warning');
                return;
            }

            closeModal();
            app.confirmUninstallModules(modId, selectedModules);
        });

        // 显示动画
        modal.classList.add('show');
    },

    getModuleIcon(cls) {
        const icons = {
            '陆战语音': '🎖️',
            '无线电': '📻',
            '陆战音效': '💥',
            '空战音效': '✈️',
            '海战音效': '⚓',
            '降噪包': '🔇',
            '步兵': '🪖',
            'default': '📦'
        };
        return icons[cls] || icons['default'];
    },

    async confirmUninstallModules(modId, selectedModules) {
        try {
            const result = await pywebview.api.uninstall_mod_modules(modId, selectedModules || []);

            if (result && result.success) {
                const msg = result.remaining
                    ? this.t('lib.uninstall_success_remaining', { count: result.removed || 0, remaining: result.remaining })
                    : this.t('lib.uninstall_success', { count: result.removed || 0 });

                // 使用 app 引用而不是 this
                const appRef = window.app || this;
                if (appRef.showToast) {
                    appRef.showToast(msg, 'success');
                }

                // 更新已安装列表
                try {
                    if (window.pywebview && pywebview.api && pywebview.api.get_installed_mods) {
                        appRef.installedModIds = await pywebview.api.get_installed_mods() || [];
                    }
                } catch (e) {
                    console.error("Failed to update installed mods:", e);
                }

                // 强制刷新库列表
                if (appRef.refreshLibrary) {
                    appRef.refreshLibrary({ manual: true });
                }
            } else {
                const appRef = window.app || this;
                if (appRef.showToast) {
                    appRef.showToast(result?.msg || appRef.t('lib.uninstall_modules_failed'), 'error');
                }
            }
        } catch (error) {
            console.error("confirmUninstallModules error:", error);
            const appRef = window.app || this;
            if (appRef.showToast) {
                appRef.showToast(appRef.t('lib.uninstall_error'), 'error');
            }
        }
    },

    // --- 安装模态框 ---
    // openInstallModal 的实现在文件末尾，使用 modCache

    // 安装/还原成功回调
    onInstallSuccess(modName) {
        console.log("Install Success:", modName);
        if (!this.installedModIds) {
            this.installedModIds = [];
        }
        if (!this.installedModIds.includes(modName)) {
            this.installedModIds.push(modName);
        }
        if (this.modCache) this.renderList(this.modCache);
    },

    onRestoreSuccess() {
        console.log("Restore Success");
        this.installedModIds = [];
        if (this.modCache) this.renderList(this.modCache);
    }
};

// 补充 modCache 逻辑
app.modCache = [];

// 真正的打开模态框
app.openInstallModal = async function (modId) {
    if (!app.currentGamePath) {
        app.showAlert(app.t("common.info"), app.t("home.path_required"));
        app.switchTab('home');
        return;
    }
    app.currentModId = modId;
    const mod = app.modCache.find(m => m.id === modId);
    if (!mod) return;

    const modal = document.getElementById('modal-install');
    const container = document.getElementById('install-toggles');
    container.innerHTML = '';

    const fileGroups = mod.files || [];
    const moduleLabel = (group) => {
        const code = String(group?.code || '').toLowerCase();
        const type = String(group?.type || '');
        if (code.includes('ground') || code.includes('tank') || type.includes('陆战语音')) return app.t('install.module_ground_voice');
        if (code.includes('common') || code.includes('dialogs_chat') || type.includes('无线电')) return app.t('install.module_radio');
        if (code.includes('aircraft') || type.includes('空战音效')) return app.t('install.module_air_sfx');
        if (code.includes('ships') || code.includes('naval') || type.includes('海战音效')) return app.t('install.module_naval_sfx');
        if (code.includes('infantry') || type.includes('步兵')) return app.t('install.module_infantry');
        if (code.includes('masterbank') || type.includes('降噪包')) return app.t('install.module_noise');
        if (code.includes('preview') || type.includes('试听')) return app.t('install.module_preview');
        if (type.includes('陆战音效')) return app.t('install.module_ground_sfx');
        return type;
    };

    if (fileGroups.length === 0) {
        container.innerHTML = `<div class="no-folders" style="padding:20px;text-align:center;color:#888;">⚠️ ${app._escapeHtml(app.t('install.no_valid_audio_files'))}</div>`;
    } else {
        fileGroups.forEach(group => {
            const div = document.createElement('div');

            // 检查是否为试听语音包
            const isPreview = group.code.includes('preview') || group.type.includes('试听');

            if (isPreview) {
                // 试听语音包：禁用状态
                div.className = 'toggle-btn';
                div.style.opacity = '0.4';
                div.style.cursor = 'not-allowed';
                div.style.pointerEvents = 'none';
            } else {
                // 普通模块：默认不选中，可用
                div.className = 'toggle-btn available';
            }

            div.dataset.key = group.code; // 使用 code 作为标识
            div.dataset.files = JSON.stringify(group.files); // 存储文件列表

            // 显示名称和文件数量
            const displayName = moduleLabel(group);
            const fileCount = group.count;

            // 根据类型选择图标
            let iconClass = "ri-file-music-line"; // 默认音频图标

            if (group.code.includes('ground') || group.code.includes('tank')) {
                iconClass = "ri-car-line";
            }
            // 无线电/通用语音
            else if (group.code.includes('common') || group.code.includes('dialogs_chat')) {
                iconClass = "ri-radio-2-line";
            }
            // 空战相关
            else if (group.code.includes('aircraft')) {
                iconClass = "ri-plane-line";
            }
            // 海战相关
            else if (group.code.includes('ships') || group.code.includes('naval')) {
                iconClass = "ri-ship-line";
            }
            // 步兵相关
            else if (group.code.includes('infantry')) {
                iconClass = "ri-user-line";
            }
            // 降噪包
            else if (group.code.includes('masterbank')) {
                iconClass = "ri-volume-mute-line";
            }
            // 试听语音
            else if (isPreview) {
                iconClass = "ri-headphone-line";
            }

            div.innerHTML = `<i class="${iconClass}"></i><div class="label">${app._escapeHtml(displayName)}${isPreview ? ` <span style="color:var(--text-sec);font-size:10px;">(${app._escapeHtml(app.t('install.disabled'))})</span>` : ''} <span style="opacity:0.6;font-size:11px;">(${fileCount})</span></div>`;

            if (!isPreview) {
                div.onclick = () => {
                    div.classList.toggle('selected');
                };

                // Tooltip 交互
                const tooltipText = app.t('install.contains_files', { name: displayName, count: fileCount });
                div.onmouseenter = (e) => app.showTooltip(div, tooltipText);
                div.onmouseleave = () => app.hideTooltip();
            } else {
                // 试听语音包的提示
                const tooltipText = app.t('install.preview_not_installable');
                div.onmouseenter = (e) => app.showTooltip(div, tooltipText);
                div.onmouseleave = () => app.hideTooltip();
            }

            container.appendChild(div);
        });
    }

    modal.classList.add('show');
};

document.getElementById('btn-confirm-install').onclick = async function () {
    const toggles = document.querySelectorAll('#install-toggles .toggle-btn.selected');

    // 收集所有选中类型的文件列表
    let allFiles = [];
    toggles.forEach(el => {
        try {
            const files = JSON.parse(el.dataset.files || '[]');
            allFiles = allFiles.concat(files);
        } catch (e) {
            console.error('解析文件列表失败:', e);
        }
    });

    // 如果列表为空（说明可能是全量安装模式，或者用户没选）
    // 但如果有 toggle 存在却没选，那就是用户取消了所有
    const hasToggles = document.querySelectorAll('#install-toggles .toggle-btn').length > 0;

    if (hasToggles && allFiles.length === 0) {
        app.showAlert(app.t("common.info"), app.t("lib.select_module_required"));
        return;
    }

    // 安装前执行冲突检查
    const conflictBtn = document.getElementById('btn-confirm-install');
    const originalText = conflictBtn.innerHTML;
    conflictBtn.disabled = true;
    conflictBtn.innerHTML = `<i class="ri-loader-4-line ri-spin"></i> ${app.t("lib.checking")}`;

    try {
        // 将文件列表序列化为 JSON 字符串传递给后端
        const conflicts = await pywebview.api.check_install_conflicts(app.currentModId, JSON.stringify(allFiles));

        if (conflicts && conflicts.length > 0) {
            // 构建冲突提示信息
            const conflictCount = conflicts.length;
            let msg = app.t("lib.conflict_message", { count: conflictCount });
            msg += `<div style="max-height:100px;overflow-y:auto;background:rgba(0,0,0,0.05);padding:8px;border-radius:4px;font-size:12px;">`;

            // 只显示前 5 个
            conflicts.slice(0, 5).forEach(c => {
                msg += `<div style="margin-bottom:2px;">• ${c.file} <span style="color:#aaa;">(${app.t("lib.conflict_from", { name: c.existing_mod })})</span></div>`;
            });

            if (conflictCount > 5) {
                msg += `<div>${app.t("lib.conflict_more", { count: conflictCount - 5 })}</div>`;
            }
            msg += `</div><br>${app.t("lib.conflict_continue")}`;

            const proceed = await app.confirm(app.t("lib.conflict_title"), msg, true); // 使用危险样式提醒
            if (!proceed) {
                conflictBtn.disabled = false;
                conflictBtn.innerHTML = originalText;
                return;
            }
        }
    } catch (e) {
        console.error("Conflict check failed", e);
    }

    // 恢复按钮状态
    conflictBtn.disabled = false;
    conflictBtn.innerHTML = originalText;

    // 显示极简加载动画 (关闭模拟模式，等待后端真实进度)
    if (typeof MinimalistLoading !== 'undefined') {
        MinimalistLoading.show(false, app.t("loading.preparing_install"));
    }

    // 将文件列表序列化为 JSON 字符串传递给后端
    pywebview.api.install_mod(app.currentModId, JSON.stringify(allFiles));
    app.closeModal('modal-install');
};

app.restoreGame = async function () {
    const yes = await app.confirm(
        app.t("settings.restore_confirm_title"),
        app.t("settings.restore_confirm_message"),
        true
    );
    if (yes) {
        // 显示加载组件，等待后端推送进度
        if (typeof MinimalistLoading !== 'undefined') {
            MinimalistLoading.show();
        }
        pywebview.api.restore_game();
        app.switchTab('home');
    }
};

// --- 免责声明逻辑 ---
app.checkDisclaimer = async function () {
    if (app._disclaimerPromise) return app._disclaimerPromise;
    try {
        const result = await pywebview.api.check_first_run();
        // check_first_run 返回 { status: bool, version: str }
        // 如果 status 为 true，说明需要显示

        if (result && result.status) {
            // 保存版本号到临时变量，等用户同意后再写回
            app._pendingAgreementVer = result.version;

            const modal = document.getElementById('modal-disclaimer');
            app.applyDisclaimerI18n();
            modal.classList.add('show');

            // 倒计时逻辑
            const btn = document.getElementById('btn-disclaimer-agree');
            const hint = document.getElementById('disclaimer-timer-hint');
            let timeLeft = 5;
            const updateTimerHint = () => {
                if (hint) hint.textContent = app.t('disclaimer.timer', { seconds: timeLeft });
            };

            btn.disabled = true;
            updateTimerHint();

            const timer = setInterval(() => {
                timeLeft--;
                if (timeLeft <= 0) {
                    clearInterval(timer);
                    btn.disabled = false;
                    if (hint) hint.textContent = "";
                } else {
                    updateTimerHint();
                }
            }, 1000);

            app._disclaimerPromise = new Promise((resolve) => {
                app._disclaimerResolve = resolve;
            });
            return app._disclaimerPromise;
        }
        return true;
    } catch (e) {
        console.error("Disclaimer check failed", e);
        return true;
    }
};

app.disclaimerAgree = async function () {
    if (!app._pendingAgreementVer) return;

    // 关闭弹窗
    const modal = document.getElementById('modal-disclaimer');
    modal.classList.remove('show');

    // 调用 API 保存状态
    await pywebview.api.agree_to_terms(app._pendingAgreementVer);
    app._pendingAgreementVer = null;
    if (typeof app._disclaimerResolve === 'function') app._disclaimerResolve(true);
    app._disclaimerResolve = null;
    app._disclaimerPromise = null;
};

app.disclaimerReject = function () {
    if (typeof app._disclaimerResolve === 'function') app._disclaimerResolve(false);
    app._disclaimerResolve = null;
    app._disclaimerPromise = null;
    // 拒绝则退出程序
    pywebview.api.close_window();
};

// --- Tooltip 智能定位 ---
app.showTooltip = function (el, text) {
    const tip = document.getElementById('tooltip');
    if (!tip) return;

    tip.textContent = text || '';
    tip.style.display = 'block';

    const rect = el.getBoundingClientRect();
    const tipRect = tip.getBoundingClientRect();
    const viewportHeight = window.innerHeight;
    const viewportWindow = window.innerWidth;

    let top = rect.bottom + 10;

    if (top + tipRect.height > viewportHeight) {
        top = rect.top - tipRect.height - 10;
    }
    // 防止顶部溢出
    if (top < 10) top = 10;

    let left = rect.left;

    if (left + tipRect.width > viewportWindow) {
        left = viewportWindow - tipRect.width - 20;
    }
    // 防止左侧溢出
    if (left < 10) left = 10;

    tip.style.top = top + 'px';
    tip.style.left = left + 'px';
};
app.hideTooltip = function () {
    const tip = document.getElementById('tooltip');
    if (!tip) return;
    tip.style.display = 'none';
};

// --- Shortcuts ---
app.handleShortcuts = function (e) {
    // 如果有模态框打开（比如首次运行协议），禁止常用快捷键
    const openModals = document.querySelectorAll('.modal-overlay.show');
    if (openModals.length > 0) return;

    if (e.ctrlKey) {
        switch (e.key) {
            case '1': this.switchTab('home'); break;
            case '2': this.switchTab('lib'); break;
            case '3': this.switchTab('camo'); break;
            case '4': this.switchTab('sight'); break;
            case '5': this.switchTab('settings'); break;
            case 't': case 'T': this.toggleTheme(); break;
            case 'p': case 'P': this.togglePin(); break;
            case 'r': case 'R': this.refreshLibrary(); break;
            case 'l': case 'L': this.clearLogs(); break;
        }
    }
};

// 启动 (稍作修改: init 里面调用 checkDisclaimer)
app.init = async function () {
    // 防止重複初始化
    if (this._initStarted) {
        console.log("App init already started, skipping...");
        return;
    }
    this._initStarted = true;

    console.log("App initializing...");
    this.recoverToSafeState('init');
    this.initToasts();
    // 公告渲染等配置语言恢复后再执行，避免英文界面初始化阶段触发联网公告。

    if (!this._safetyHandlersInstalled) {
        this._safetyHandlersInstalled = true;

        window.addEventListener('error', () => this.recoverToSafeState('error'));
        window.addEventListener('unhandledrejection', () => this.recoverToSafeState('unhandledrejection'));
        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return;
            const openModal = document.querySelector('.modal-overlay.show');
            // 免责声明不允许 Esc 关闭
            if (openModal && openModal.id && openModal.id !== 'modal-disclaimer') {
                app.closeModal(openModal.id);
            }
        });
    }

    const feedbackContact = document.getElementById('feedback-contact');
    const feedbackContent = document.getElementById('feedback-content');
    if (feedbackContact) {
        feedbackContact.addEventListener('input', () => this.updateFeedbackCount());
    }
    if (feedbackContent) {
        feedbackContent.addEventListener('input', () => this.updateFeedbackCount());
    }

    // 核心初始化逻辑，抽取为独立函数以便重用
    const doInit = async () => {
        // 防止重複执行核心初始化
        if (this._coreInitDone) {
            console.log("Core init already done, skipping...");
            return;
        }
        this._coreInitDone = true;
        console.log("PyWebview ready, starting core init...");

        this._setupModalDragLock();
        this._setupModalOverlayClose();

        // 1. 获取初始状态并先恢复界面语言，免责声明随后按当前语言展示。
        const state = await pywebview.api.init_app_state() || {
            game_path: "",
            path_valid: false,
            active_theme: "default.json",
            theme: "Light",
            installed_mods: [],
            ui_language: "",
        };
        this.applyUiLanguage(state.ui_language || this.detectPreferredUiLanguage());

        // 1.1 检查免责声明
        const disclaimerAccepted = await app.checkDisclaimer();
        if (disclaimerAccepted === false) return;

        // 1.2 资源库拖放提示由 ResourceDragOverlay 负责。
        this.telemetryConnected = !!state.telemetry_connected;
        // AI 代理模式使用的遥测服务器基地址
        if (state.telemetry_base_url) window._telemetryBaseUrl = state.telemetry_base_url;
        if (state.hwid) {
            window._telemetryHWID = state.hwid;
            if (window.userProfile && typeof window.userProfile.init === 'function') {
                window.userProfile.init(state.hwid, state.telemetry_base_url || '');
            }
        }
        this.userSeqId = state.user_seq_id || 0;
        window._userSeqId = this.userSeqId;
        this.applyServerUserFeatures(state.server_user_features || {});
        this.currentLaunchMode = state.launch_mode || 'launcher';
        this.updatePathUI(state.game_path, state.path_valid);

        if (state.installed_mods && Array.isArray(state.installed_mods)) {
            this.installedModIds = state.installed_mods;
        } else {
            this.installedModIds = [];
        }
        this.sightsPath = state.sights_path || null;
        this._sightsLoaded = false;
        this.loadSightsView();
        if (typeof this.setupVoiceLibraryDropZone === 'function') {
            this.setupVoiceLibraryDropZone();
        }
        if (typeof this.setupSkinsDropZone === 'function') {
            this.setupSkinsDropZone();
        }
        if (typeof this.setupSightsDropZone === 'function') {
            this.setupSightsDropZone();
        }

        const themeBtn = document.getElementById('btn-theme');
        if (state.theme === 'Light') {
            document.documentElement.setAttribute('data-theme', 'light');
            themeBtn.innerHTML = '<i class="ri-moon-line"></i>';
        } else {
            document.documentElement.setAttribute('data-theme', 'dark');
            themeBtn.innerHTML = '<i class="ri-sun-line"></i>';
        }

        // 加载主题列表并应用上次的选择
        await this.loadThemeList();
        const activeTheme = state.active_theme || 'default.json';
        this.selectTheme(activeTheme);

        // 加载主题内容（包括 default.json）
        const themeData = await pywebview.api.load_theme_content(activeTheme);
        if (themeData && (themeData.colors || themeData.light || themeData.dark)) {
            this.applyThemeData(themeData);
        }
        this.renderNoticeBoard();
        this.startTelemetryStatusPolling();

        // 加载语音包库路径信息（设置页显示用）
        try {
            await this.loadLibraryPathInfo();
        } catch (e) {
            console.error('loadLibraryPathInfo failed:', e);
        }

        // 加载版本号到更新检测卡片
        try {
            const verInfo = await pywebview.api.get_app_version();
            if (verInfo?.version) {
                const el = document.getElementById('current-version-display');
                if (el) el.textContent = 'v' + verInfo.version;
            }
        } catch (e) {
            console.error('get_app_version failed:', e);
        }

        // 绑定快捷键
        document.addEventListener('keydown', this.handleShortcuts.bind(this));

        // 初始刷新库
        this.refreshLibrary();

        // 设置页面防止拖拽干扰
        document.querySelectorAll('#page-settings .card').forEach(card => {
            card.addEventListener('mouseenter', () => {
                document.body.classList.add('drag-disabled');
            });
            card.addEventListener('mouseleave', () => {
                document.body.classList.remove('drag-disabled');
            });
        });

        const telSwitch = document.getElementById('telemetry-switch');
        if (telSwitch) {
            telSwitch.checked = !!state.telemetry_enabled;
        }

        // 设置开机自启动开关状态
        const autostartSwitch = document.getElementById('autostart-switch');
        if (autostartSwitch) {
            autostartSwitch.checked = !!state.autostart_enabled;
        }

        // 设置托盘模式开关状态
        const trayModeSwitch = document.getElementById('tray-mode-switch');
        if (trayModeSwitch) {
            trayModeSwitch.checked = !!state.tray_mode;
        }

        // 设置关闭确认开关状态
        const closeConfirmSwitch = document.getElementById('close-confirm-switch');
        if (closeConfirmSwitch) {
            closeConfirmSwitch.checked = state.close_confirm !== false; // 默认开启
        }

        // 保存状态到本地变量供关闭逻辑使用
        this._trayMode = !!state.tray_mode;
        this._closeConfirm = state.close_confirm !== false; // 默认开启

        // 可选引导系统初始化（模块不存在时会自动跳过）
        this.initGuideSystem();
    };

    // 防止重複註册 pywebviewready 监听器
    if (!this._pywebviewReadyListenerAdded) {
        this._pywebviewReadyListenerAdded = true;
        window.addEventListener('pywebviewready', doInit);
    }

    // 备用机制：如果 pywebview 已经就绪但事件没有触发（例如快取问题）
    // 则在短暂延迟后手动检查并初始化
    setTimeout(() => {
        if (window.pywebview && window.pywebview.api && !this._coreInitDone) {
            console.log("PyWebview API detected but event not fired, triggering manual init...");
            doInit();
        }
    }, 500);

    // 额外的备用机制：更长的超时确保初始化
    setTimeout(() => {
        if (window.pywebview && window.pywebview.api && !this._coreInitDone) {
            console.log("PyWebview API detected (late check), triggering manual init...");
            doInit();
        } else if (!this._coreInitDone) {
            console.warn("PyWebview API still not available after timeout, UI may not be fully functional.");
        }
    }, 2000);
};

// 添加上下文菜单功能
app.showContextMenu = function (event, menuItems) {
    event.preventDefault();
    event.stopPropagation();

    // 移除已存在的菜单
    const existingMenu = document.querySelector('.context-menu');
    if (existingMenu) {
        existingMenu.remove();
    }

    // 创建菜单容器
    const menu = document.createElement('div');
    menu.className = 'context-menu';
    menu.style.cssText = `
        position: fixed;
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        z-index: 10000;
        min-width: 220px;
        padding: 8px 0;
    `;

    // 添加菜单项
    menuItems.forEach(item => {
        const menuItem = document.createElement('div');
        menuItem.className = 'context-menu-item' + (item.danger ? ' danger' : '');
        menuItem.style.cssText = `
            padding: 10px 16px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 12px;
            transition: background 0.2s;
        `;

        menuItem.innerHTML = `
            <i class="${item.icon}" style="font-size: 18px; ${item.danger ? 'color: var(--danger);' : ''}"></i>
            <div style="flex: 1;">
                <div style="font-weight: 500; ${item.danger ? 'color: var(--danger);' : ''}">${item.label}</div>
                ${item.description ? `<div style="font-size: 12px; color: var(--text-secondary); margin-top: 2px;">${item.description}</div>` : ''}
            </div>
        `;

        menuItem.addEventListener('mouseenter', () => {
            if (item.danger) {
                menuItem.style.background = 'rgba(239, 68, 68, 0.1)';
            } else {
                menuItem.style.background = 'rgba(100, 100, 100, 0.15)';
            }
        });
        menuItem.addEventListener('mouseleave', () => {
            menuItem.style.background = 'transparent';
        });

        menuItem.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            menu.remove();
            if (item.action) {
                const handleActionError = (error) => {
                    console.error('context menu action failed:', error);
                    if (app && typeof app.showToast === 'function') {
                        app.showToast(app.t('common.operation_failed', { message: error?.message || error || '' }), 'error');
                    }
                };
                try {
                    Promise.resolve(item.action()).catch(handleActionError);
                } catch (error) {
                    handleActionError(error);
                }
            }
        });

        menu.appendChild(menuItem);
    });

    // 添加到页面
    document.body.appendChild(menu);

    // 定位菜单
    const x = event.clientX;
    const y = event.clientY;
    const menuRect = menu.getBoundingClientRect();
    const windowWidth = window.innerWidth;
    const windowHeight = window.innerHeight;

    // 调整位置避免超出屏幕
    let left = x;
    let top = y;

    if (x + menuRect.width > windowWidth) {
        left = windowWidth - menuRect.width - 10;
    }
    if (y + menuRect.height > windowHeight) {
        top = windowHeight - menuRect.height - 10;
    }

    menu.style.left = left + 'px';
    menu.style.top = top + 'px';

    // 点击其他地方关闭菜单
    const closeMenu = (e) => {
        if (!menu.contains(e.target)) {
            menu.remove();
            document.removeEventListener('click', closeMenu);
        }
    };
    setTimeout(() => {
        document.addEventListener('click', closeMenu);
    }, 0);
};

app.init();
// 显式挂载到 window，供后端通过 evaluate_js 访问
window.app = app;

// ===========================
// 资源库 Master-Detail 导航
// ===========================

// ===========================
// 资源页面注册系统
// ===========================
app.resourcePages = {};
app.currentResourcePage = null;

/**
 * 注册资源页面
 * @param {string} name - 页面标识名
 * @param {Object} pageModule - 页面对象，需包含 init/show/hide/destroy 方法
 */
app.registerResourcePage = function (name, pageModule) {
    this.resourcePages[name] = pageModule;
    console.log(`[App] 注册资源页面: ${name}`);
};

app.switchResourceView = function (target) {
    // 更新导航按钮状态
    document.querySelectorAll('.resource-nav-item').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.target === target);
    });

    // 检查是否是新模块系统注册的页面
    const registeredPage = this.resourcePages[target];
    if (registeredPage) {
        const wasInitialized = !!registeredPage._initialized;
        // 无论当前是否已有注册页，都先隐藏原生视图，避免与注册页叠层显示
        document.querySelectorAll('.resource-view').forEach(view => {
            view.classList.remove('active');
        });

        // 隐藏当前页面
        if (this.currentResourcePage && this.currentResourcePage !== registeredPage) {
            if (this.currentResourcePage.hide) {
                this.currentResourcePage.hide();
            }
        }

        // 初始化并显示新页面（如果未初始化）
        if (!wasInitialized) {
            registeredPage.init();
            registeredPage._initialized = true;
        }
        registeredPage.show();
        if (wasInitialized && typeof this.refreshResourcePageI18n === 'function') {
            this.refreshResourcePageI18n(registeredPage);
        }
        this.currentResourcePage = registeredPage;
        return;
    }

    // 原有逻辑：隐藏当前注册的页面（如果有）
    if (this.currentResourcePage) {
        if (this.currentResourcePage.hide) {
            this.currentResourcePage.hide();
        }
        this.currentResourcePage = null;
    }

    // 切换原生视图
    document.querySelectorAll('.resource-view').forEach(view => {
        view.classList.toggle('active', view.id === `view-${target}`);
    });

    // 刷新对应内容
    if (typeof this.updateResourceStorage === 'function') {
        this.updateResourceStorage(target);
    }

    if (target === 'skins') {
        this.ensureCamoResourceLoaded();
    } else if (target === 'sights') {
        if (!this._sightsLoaded) this.loadSightsView();
    } else if (target === 'tasks') {
        if (typeof TaskLibrary !== 'undefined' && !TaskLibrary._loaded) TaskLibrary.refresh_list();
    } else if (target === 'models') {
        if (typeof ModelLibrary !== 'undefined' && !ModelLibrary._loaded) ModelLibrary.refresh_list();
    } else if (target === 'hangar') {
        if (typeof Hangar !== 'undefined' && !Hangar._loaded) Hangar.refresh_list();
    }
};

app.get_resource_select_options = function (select_el) {
    if (!select_el) return [];
    return Array.from(select_el.options).map((option) => ({
        value: option.value,
        label: option.textContent.trim()
    }));
};

app.update_resource_dropdown_language = function (configs, dropdowns, placeholder_key) {
    if (!configs || !dropdowns) return;
    const placeholder = this.t(placeholder_key).replace(/:$/, '');
    configs.forEach((config) => {
        const select_el = document.getElementById(config.select_id);
        const dropdown = dropdowns[config.type];
        if (!select_el || !dropdown) return;
        const options = this.get_resource_select_options(select_el);
        dropdown.placeholder = placeholder;
        dropdown.setOptions(options, true);
        dropdown.setValue(select_el.value || options[0]?.value || '', false);
    });
};

app.get_resource_sort_dropdown_configs = function () {
    return [
        { type: 'skins', select_id: 'skins-sort-select', dropdown_id: 'skins-sort-dropdown' },
        { type: 'sights', select_id: 'sights-sort-select', dropdown_id: 'sights-sort-dropdown' },
        { type: 'tasks', select_id: 'tasks-sort-select', dropdown_id: 'tasks-sort-dropdown' },
        { type: 'models', select_id: 'models-sort-select', dropdown_id: 'models-sort-dropdown' },
        { type: 'hangar', select_id: 'hangar-sort-select', dropdown_id: 'hangar-sort-dropdown' }
    ];
};

app.get_resource_filter_dropdown_configs = function () {
    return [
        { type: 'skins', select_id: 'skins-filter-select', dropdown_id: 'skins-filter-dropdown' },
        { type: 'sights', select_id: 'sights-filter-select', dropdown_id: 'sights-filter-dropdown' },
        { type: 'tasks', select_id: 'tasks-filter-select', dropdown_id: 'tasks-filter-dropdown' },
        { type: 'models', select_id: 'models-filter-select', dropdown_id: 'models-filter-dropdown' },
        { type: 'hangar', select_id: 'hangar-filter-select', dropdown_id: 'hangar-filter-dropdown' }
    ];
};

app.refreshResourceDropdownI18n = function () {
    this.update_resource_dropdown_language(
        this.get_resource_sort_dropdown_configs(),
        this.resource_sort_dropdowns,
        'resource.sort_label'
    );
    this.update_resource_dropdown_language(
        this.get_resource_filter_dropdown_configs(),
        this.resource_filter_dropdowns,
        'resource.filter_label'
    );
};

app.refreshResourceStatusBadgeI18n = function () {
    document.querySelectorAll('.resource-status-badge.is-disabled').forEach((badge) => {
        badge.textContent = this.t('resource.status_disabled');
    });
};

app.updateAllResourceSelectionSummaries = function () {
    ['skins', 'sights', 'tasks', 'models', 'hangar'].forEach((resource_type) => {
        this.updateResourceSelectionSummary(resource_type);
    });
};

app.refreshResourcePageI18n = function (page_module) {
    if (!page_module) return;
    if (page_module._refreshing && !page_module._loaded) return;
    if (typeof page_module.refresh_i18n === 'function') {
        page_module.refresh_i18n();
        return;
    }
    if (typeof page_module._render_filtered_list === 'function') {
        page_module._render_filtered_list();
    }
};

app.refreshDynamicI18n = function () {
    const lib_page = document.getElementById('page-lib');
    if (lib_page?.classList.contains('active') && this._libraryLoaded && Array.isArray(this.modCache) && typeof this.renderList === 'function') {
        const search_input = document.querySelector('#page-lib [data-i18n-placeholder="lib.search_placeholder"]');
        const term = String(search_input?.value || '').toLowerCase().trim();
        const mods = term
            ? this.modCache.filter(mod => {
                const title = String(mod?.title || '').toLowerCase();
                const author = String(mod?.author || '').toLowerCase();
                return title.includes(term) || author.includes(term);
            })
            : this.modCache;
        this.renderList(mods);
    }

    const camo_page_active = document.getElementById('page-camo')?.classList.contains('active');
    if (camo_page_active && document.getElementById('view-skins')?.classList.contains('active') && typeof this._renderSkinsView === 'function' && !(this._skinsRefreshing && !this._skinsLoaded)) {
        this._renderSkinsView();
    }
    if (camo_page_active && document.getElementById('view-sights')?.classList.contains('active') && typeof this._renderSightsView === 'function' && !(this._sightsRefreshing && !this._sightsLoaded)) {
        this._renderSightsView();
    }

    this.refreshResourcePageI18n(this.currentResourcePage);
};

app.initResourceSortDropdowns = function () {
    if (!window.AppDropdownMenu) return;

    const sort_configs = this.get_resource_sort_dropdown_configs();

    this.resource_sort_dropdowns = this.resource_sort_dropdowns || {};

    sort_configs.forEach((config) => {
        const select_el = document.getElementById(config.select_id);
        const dropdown_el = document.getElementById(config.dropdown_id);
        if (!select_el || !dropdown_el) return;

        const options = this.get_resource_select_options(select_el);

        const dropdown = new AppDropdownMenu({
            id: `${config.type}-resource-sort`,
            containerId: config.dropdown_id,
            options,
            placeholder: this.t('resource.sort_label').replace(/:$/, ''),
            size: 'sm',
            width: '108px',
            onChange: (value) => {
                select_el.value = value;
                select_el.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });

        dropdown.setValue(select_el.value || options[0]?.value || '', false);
        this.resource_sort_dropdowns[config.type] = dropdown;
    });

    /* 筛选下拉菜单初始化 */
    const filter_configs = this.get_resource_filter_dropdown_configs();

    this.resource_filter_dropdowns = this.resource_filter_dropdowns || {};

    filter_configs.forEach((config) => {
        const select_el = document.getElementById(config.select_id);
        const dropdown_el = document.getElementById(config.dropdown_id);
        if (!select_el || !dropdown_el) return;

        const options = this.get_resource_select_options(select_el);

        const dropdown = new AppDropdownMenu({
            id: `${config.type}-resource-filter`,
            containerId: config.dropdown_id,
            options,
            placeholder: this.t('resource.filter_label').replace(/:$/, ''),
            size: 'sm',
            width: '90px',
            onChange: (value) => {
                select_el.value = value;
                select_el.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });

        dropdown.setValue(select_el.value || options[0]?.value || '', false);
        this.resource_filter_dropdowns[config.type] = dropdown;
    });
};

app.switchResourceViewMode = function (resource_type, mode) {
    const type = String(resource_type || '').trim();
    const view_mode = mode === 'list' ? 'list' : 'card';
    if (!type) return;

    const toggle_el = document.querySelector(`.res-view-toggle[data-resource-type="${type}"]`);
    const list_el = document.getElementById(`${type}-list`);

    if (toggle_el) {
        toggle_el.classList.toggle('is-card-mode', view_mode === 'card');
        toggle_el.classList.toggle('is-list-mode', view_mode === 'list');
        toggle_el.querySelectorAll('button').forEach((button, index) => {
            const button_mode = index === 0 ? 'card' : 'list';
            button.classList.toggle('active', button_mode === view_mode);
            button.setAttribute('aria-pressed', button_mode === view_mode ? 'true' : 'false');
        });
    }

    if (list_el) {
        list_el.classList.toggle('is-card-view', view_mode === 'card');
        list_el.classList.toggle('is-list-view', view_mode === 'list');
    }
};

app.resource_ops_config = {
    skins: {
        label: '涂装',
        label_key: 'resource.label_skins',
        open_api: 'open_skin_folder_by_name',
        enable_api: 'enable_skin',
        disable_api: 'disable_skin',
        delete_api: 'delete_skin',
        refresh: () => app.refreshSkins({ manual: true })
    },
    sights: {
        label: '炮镜',
        label_key: 'resource.label_sights',
        open_api: 'open_sight_folder_by_name',
        enable_api: 'enable_sight',
        disable_api: 'disable_sight',
        delete_api: 'delete_sight',
        refresh: () => app.refreshSights({ manual: true })
    },
    tasks: {
        label: '任务',
        label_key: 'resource.label_tasks',
        open_api: 'open_task_folder_by_name',
        enable_api: 'enable_task',
        disable_api: 'disable_task',
        delete_api: 'delete_task',
        refresh: () => {
            if (typeof TaskLibrary !== 'undefined') return TaskLibrary.refresh_list({ manual: true });
        }
    },
    models: {
        label: '模型',
        label_key: 'resource.label_models',
        open_api: 'open_model_folder_by_name',
        enable_api: 'enable_model',
        disable_api: 'disable_model',
        delete_api: 'delete_model',
        refresh: () => {
            if (typeof ModelLibrary !== 'undefined') return ModelLibrary.refresh_list({ manual: true });
        }
    },
    hangar: {
        label: '机库',
        label_key: 'resource.label_hangar',
        open_api: 'open_hangar_folder_by_name',
        enable_api: 'enable_hangar',
        disable_api: 'disable_hangar',
        delete_api: 'delete_hangar',
        refresh: () => {
            if (typeof Hangar !== 'undefined') return Hangar.refresh_list({ manual: true });
        }
    }
};

app.get_resource_label = function (config) {
    if (!config) return '';
    return config.label_key ? this.t(config.label_key) : String(config.label || '');
};

app.updateResourceSelectionSummary = function (resource_type, total_count) {
    const type = String(resource_type || '').trim();
    if (!type) return;

    const count_el = document.getElementById(`${type}-count`);
    const hint_el = document.getElementById(`${type}-selected-hint`);
    const select_all_el = document.getElementById(`${type}-select-all`);
    const list_el = document.getElementById(`${type}-list`);
    const cards = list_el ? Array.from(list_el.querySelectorAll('.small-card, .res-card')) : [];
    const selected_count = cards.filter((card) => card.classList.contains('is-selected')).length;
    const visible_count = Number.isFinite(Number(total_count)) ? Number(total_count) : cards.length;

    if (count_el) {
        const count_key = visible_count === 1 ? 'resource.count_item' : 'resource.count_items';
        count_el.textContent = this.t(count_key, { count: visible_count });
    }
    if (hint_el) {
        const selected_key = selected_count === 1 ? 'resource.selected_item' : 'resource.selected_items';
        hint_el.textContent = selected_count > 0
            ? this.t(selected_key, { count: selected_count })
            : this.t('resource.min_select_one');
    }

    if (select_all_el) {
        select_all_el.checked = visible_count > 0 && selected_count === visible_count;
        select_all_el.indeterminate = selected_count > 0 && selected_count < visible_count;
    }

    if (typeof this.update_resource_ops_buttons === 'function') {
        this.update_resource_ops_buttons(type);
    }
};

app.get_selected_resource_cards = function (resource_type) {
    const type = String(resource_type || '').trim();
    const list_el = document.getElementById(`${type}-list`);
    if (!list_el) return [];
    return Array.from(list_el.querySelectorAll('.small-card.is-selected, .res-card.is-selected'));
};

app.get_selected_resource_items = function (resource_type) {
    return this.get_selected_resource_cards(resource_type).map(card => {
        const encoded_name = card.dataset.resourceNameEncoded
            || card.dataset.sightNameEncoded
            || card.dataset.skinNameEncoded
            || '';
        const name = encoded_name
            ? decodeURIComponent(encoded_name)
            : String(card.dataset.itemName || card.dataset.skinName || '').trim();
        return {
            name,
            disabled: card.dataset.disabled === '1' || name.endsWith('.AimerWT_BAN'),
        };
    }).filter(item => item.name);
};

app.update_resource_ops_buttons = function (resource_type) {
    const type = String(resource_type || '').trim();
    const selected = this.get_selected_resource_items(type);
    const has_selection = selected.length > 0;
    const all_disabled = has_selection && selected.every(item => item.disabled);
    const all_enabled = has_selection && selected.every(item => !item.disabled);
    const open_btn = document.getElementById(`${type}-op-open`);
    const enable_btn = document.getElementById(`${type}-op-enable`);
    const disable_btn = document.getElementById(`${type}-op-disable`);
    const delete_btn = document.getElementById(`${type}-op-delete`);
    if (open_btn) open_btn.disabled = selected.length !== 1;
    if (enable_btn) enable_btn.disabled = !all_disabled;
    if (disable_btn) disable_btn.disabled = !all_enabled;
    if (delete_btn) delete_btn.disabled = !has_selection;
};

app.open_selected_resource_folder = async function (resource_type) {
    const type = String(resource_type || '').trim();
    const config = this.resource_ops_config[type];
    const selected = this.get_selected_resource_items(type);
    if (selected.length !== 1) return;
    const api_fn = config && window.pywebview?.api?.[config.open_api];
    if (!api_fn) {
        this.showAlert(this.t('common.error'), this.t('common.feature_not_ready'), 'error');
        return;
    }
    const result = await window.pywebview.api[config.open_api](selected[0].name);
    if (!result || !result.success) {
        this.showAlert(this.t('common.error'), result?.msg || this.t('resource.open_failed', { label: this.get_resource_label(config) }), 'error');
    }
};

app.enable_selected_resources = async function (resource_type) {
    const type = String(resource_type || '').trim();
    const config = this.resource_ops_config[type];
    const selected = this.get_selected_resource_items(type).filter(item => item.disabled);
    if (!selected.length) return;
    const api_fn = config && window.pywebview?.api?.[config.enable_api];
    if (!api_fn) {
        this.showAlert(this.t('common.error'), this.t('common.feature_not_ready'), 'error');
        return;
    }
    for (const item of selected) {
        const result = await window.pywebview.api[config.enable_api](item.name);
        if (!result || !result.success) {
            this.showAlert(this.t('common.error'), result?.msg || this.t('resource.enable_failed', { name: item.name }), 'error');
            return;
        }
    }
    await config.refresh();
};

app.disable_selected_resources = async function (resource_type) {
    const type = String(resource_type || '').trim();
    const config = this.resource_ops_config[type];
    const selected = this.get_selected_resource_items(type).filter(item => !item.disabled);
    if (!selected.length) return;
    const api_fn = config && window.pywebview?.api?.[config.disable_api];
    if (!api_fn) {
        this.showAlert(this.t('common.error'), this.t('common.feature_not_ready'), 'error');
        return;
    }
    for (const item of selected) {
        const result = await window.pywebview.api[config.disable_api](item.name);
        if (!result || !result.success) {
            this.showAlert(this.t('common.error'), result?.msg || this.t('resource.disable_failed', { name: item.name }), 'error');
            return;
        }
    }
    await config.refresh();
};

app.delete_selected_resources = async function (resource_type) {
    const type = String(resource_type || '').trim();
    const config = this.resource_ops_config[type];
    const selected = this.get_selected_resource_items(type);
    if (!selected.length) return;
    const api_fn = config && window.pywebview?.api?.[config.delete_api];
    if (!api_fn) {
        this.showAlert(this.t('common.error'), this.t('common.feature_not_ready'), 'error');
        return;
    }
    const names = selected.map(item => app._escapeHtml(item.name)).join('<br>');
    const label = this.get_resource_label(config);
    const yes = await this.confirm(
        this.t('resource.delete_title', { label }),
        this.t('resource.delete_message', { count: selected.length, label, names }),
        true,
        this.t('resource.confirm_delete')
    );
    if (!yes) return;
    for (const item of selected) {
        const result = await window.pywebview.api[config.delete_api](item.name);
        if (!result || !result.success) {
            this.showAlert(this.t('common.error'), result?.msg || this.t('resource.delete_failed', { name: item.name }), 'error');
            return;
        }
    }
    await config.refresh();
};

app.getSelectedSightCards = function () {
    return this.get_selected_resource_cards('sights');
};

app.getSelectedSightItems = function () {
    return this.get_selected_resource_items('sights');
};

app.updateSightsOpsButtons = function () {
    this.update_resource_ops_buttons('sights');
};

app.openSelectedSightFolder = function () {
    return this.open_selected_resource_folder('sights');
};

app.enableSelectedSights = function () {
    return this.enable_selected_resources('sights');
};

app.disableSelectedSights = function () {
    return this.disable_selected_resources('sights');
};

app.deleteSelectedSights = function () {
    return this.delete_selected_resources('sights');
};

app.setResourceSelection = function (resource_type, selected) {
    const type = String(resource_type || '').trim();
    const list_el = document.getElementById(`${type}-list`);
    if (!list_el) return;

    list_el.querySelectorAll('.small-card, .res-card').forEach((card) => {
        card.classList.toggle('is-selected', !!selected);
    });
    this.updateResourceSelectionSummary(type);
};

app.initResourceSelectionControls = function () {
    ['skins', 'sights', 'tasks', 'models', 'hangar'].forEach((resource_type) => {
        const select_all_el = document.getElementById(`${resource_type}-select-all`);
        const list_el = document.getElementById(`${resource_type}-list`);

        if (select_all_el && select_all_el.dataset.selectionBound !== '1') {
            select_all_el.dataset.selectionBound = '1';
            select_all_el.addEventListener('change', () => {
                this.setResourceSelection(resource_type, select_all_el.checked);
            });
        }

        if (list_el && list_el.dataset.selectionBound !== '1') {
            list_el.dataset.selectionBound = '1';
            list_el.addEventListener('click', (event) => {
                if (event.target.closest('button, a, input, select, textarea, [role="button"]')) return;
                const card = event.target.closest('.small-card, .res-card');
                if (!card || !list_el.contains(card)) return;
                card.classList.toggle('is-selected');
                this.updateResourceSelectionSummary(resource_type);
            });
        }
        this.update_resource_ops_buttons(resource_type);
    });
};

app.initResourceViewModeControls = function () {
    ['skins', 'sights', 'tasks', 'models', 'hangar'].forEach((resource_type) => {
        this.switchResourceViewMode(resource_type, 'card');
    });
};

app.initResourcePageControls = function () {
    this.initResourceSortDropdowns();
    this.initResourceViewModeControls();
    this.initResourceSelectionControls();
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => app.initResourcePageControls(), { once: true });
} else {
    app.initResourcePageControls();
}

// ===========================
// 炮镜管理功能
// ===========================

app.sightsPath = null;
app._sightsUidList = [];

app.loadSightsView = function () {
    const primaryBtn = document.getElementById('btn-sights-primary');
    const primaryText = primaryBtn ? primaryBtn.querySelector('span') : null;
    const primaryIcon = primaryBtn ? primaryBtn.querySelector('i') : null;
    const secondaryBtn = document.getElementById('btn-sights-secondary');
    const secondaryText = secondaryBtn ? secondaryBtn.querySelector('span') : null;

    // 自动搜索 UID 列表
    this.refreshSightsUidList();
    this.updateResourceStorage('sights');

    if (this.sightsPath) {
        if (primaryBtn) primaryBtn.onclick = () => app.selectSightsPath();
        if (primaryText) primaryText.textContent = this.t('tools.manual_select_path');
        if (primaryIcon) primaryIcon.className = 'ri-folder-open-line';

        if (secondaryBtn) secondaryBtn.disabled = false;
        if (secondaryText) secondaryText.textContent = this.t('resource.open_usersights_folder');

        setTimeout(() => {
            const camoPage = document.getElementById('page-camo');
            const sightsView = document.getElementById('view-sights');
            if (!camoPage || !sightsView) return;
            if (!camoPage.classList.contains('active')) return;
            if (!sightsView.classList.contains('active')) return;
            if (!this._sightsLoaded) this.refreshSights();
        }, 80);
        return;
    }

    this._sightsLoaded = false;
    if (primaryBtn) primaryBtn.onclick = () => app.selectSightsPath();
    if (primaryText) primaryText.textContent = this.t('tools.manual_select_path');
    if (primaryIcon) primaryIcon.className = 'ri-folder-open-line';

    if (secondaryBtn) secondaryBtn.disabled = true;
    if (secondaryText) secondaryText.textContent = this.t('resource.open_usersights_folder');
};

// 刷新 UID 列表
app.refreshSightsUidList = async function () {
    const wrapper = document.getElementById('sights-uid-select-wrapper');
    if (!wrapper) return;

    if (!window.pywebview?.api?.discover_usersights_paths) {
        if (this.sightsUidDropdown) {
            this.sightsUidDropdown.setOptions([{ value: '', label: this.t('resource.uid_api_not_ready') }]);
        }
        return;
    }

    try {
        // 初始化或更新下拉菜单
        if (!this.sightsUidDropdown) {
            this.sightsUidDropdown = new AppDropdownMenu({
                id: 'sights-uid-select',
                containerId: 'sights-uid-select-wrapper',
                placeholder: this.t('resource.uid_searching'),
                options: [{ value: '', label: this.t('resource.uid_searching') }],
                size: 'sm',
                onChange: (value) => this.onSightsUidChange(value)
            });
        } else {
            this.sightsUidDropdown.placeholder = this.t('resource.uid_searching');
            this.sightsUidDropdown.setOptions([{ value: '', label: this.t('resource.uid_searching') }]);
        }

        const paths = await pywebview.api.discover_usersights_paths();
        this._sightsUidList = paths || [];

        if (this._sightsUidList.length === 0) {
            this.sightsUidDropdown.setOptions([{ value: '', label: this.t('resource.uid_not_found') }]);
            return;
        }

        // 构建选项
        const options = [{ value: '', label: this.t('resource.uid_select_placeholder') }];
        let currentValue = '';
        for (const item of this._sightsUidList) {
            const status = item.exists ? '✓' : this.t('resource.uid_new');
            const label = `${item.uid} ${status}`;
            options.push({ value: item.uid, label: label });
            if (this.sightsPath && this.sightsPath.includes(item.uid)) {
                currentValue = item.uid;
            }
        }

        this.sightsUidDropdown.setOptions(options);
        if (currentValue) {
            this.sightsUidDropdown.setValue(currentValue, false);
        }
    } catch (e) {
        console.error('刷新 UID 列表失败:', e);
        if (this.sightsUidDropdown) {
            this.sightsUidDropdown.setOptions([{ value: '', label: this.t('resource.uid_search_failed') }]);
        }
    }
};

// UID 选择变更事件
app.onSightsUidChange = async function (uid) {
    if (!uid) return;

    if (!window.pywebview?.api?.select_uid_sights_path) {
        this.showAlert(this.t('common.error'), this.t('common.feature_not_ready'), 'error');
        return;
    }

    try {
        const result = await pywebview.api.select_uid_sights_path(uid);
        if (result && result.success) {
            this.sightsPath = result.path;
            this._sightsLoaded = false;
            this.loadSightsView();
            this.showInfoToast(this.t('settings.saved'), this.t('resource.uid_path_set', { uid }));
        } else {
            this.showAlert(this.t('common.error'), result?.error || this.t('common.save_failed'), 'error');
        }
    } catch (e) {
        console.error(e);
        this.showAlert(this.t('common.error'), this.t('resource.uid_select_failed', { message: e.message }), 'error');
    }
};

app.selectSightsPath = async function () {
    if (!window.pywebview?.api?.select_sights_path) {
        this.showAlert(this.t('common.error'), this.t('common.feature_not_ready'), 'error');
        return;
    }

    try {
        const result = await pywebview.api.select_sights_path();
        if (result && result.success) {
            this.sightsPath = result.path;
            this._sightsLoaded = false;
            this.loadSightsView();
            this.showAlert(this.t('common.success'), this.t('tools.sights_path_success'), 'success');
        }
    } catch (e) {
        console.error(e);
        this.showAlert(this.t('common.error'), this.t('common.select_path_failed', { message: e.message }), 'error');
    }
};

app.changeSightsPath = function () {
    this.sightsPath = null;
    this._sightsLoaded = false;
    this.loadSightsView();
};

app.openSightsFolder = async function () {
    if (!this.sightsPath) {
        this.showAlert(this.t('common.info'), this.t('tools.select_sights_path'), 'warn');
        return;
    }

    try {
        await pywebview.api.open_sights_folder();
    } catch (e) {
        console.error(e);
    }
};

app.refreshSights = async function (opts) {
    if (!this.sightsPath || !window.pywebview?.api) return;
    const canAsyncRefresh = typeof pywebview.api.refresh_sights_async === 'function';
    if (!canAsyncRefresh && typeof pywebview.api.get_sights_list !== 'function') return;

    const camoPage = document.getElementById('page-camo');
    const sightsView = document.getElementById('view-sights');
    if (!camoPage || !sightsView) return;
    if (!camoPage.classList.contains('active')) return;
    if (!sightsView.classList.contains('active')) return;

    const refreshBtn = document.getElementById('btn-refresh-sights');
    const isManual = !!(opts && opts.manual);
    const now = (window.performance && performance.now) ? performance.now() : Date.now();
    if (this._sightsRefreshing) return;
    if (!isManual && this._lastSightsRefreshAt && (now - this._lastSightsRefreshAt) < 800) return;
    this._lastSightsRefreshAt = now;
    this._sightsRefreshing = true;
    this._sightsRefreshSeq = (this._sightsRefreshSeq || 0) + 1;
    const seq = this._sightsRefreshSeq;

    const listEl = document.getElementById('sights-list');
    const countEl = document.getElementById('sights-count');
    let waitingForAsyncPush = false;

    try {
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.classList.add('is-loading');
        }
        if (countEl) countEl.textContent = this.t('tools.count_refreshing');
        await new Promise(requestAnimationFrame);

        const forceRefresh = !!(opts && opts.manual);
        if (canAsyncRefresh) {
            waitingForAsyncPush = true;
            pywebview.api.refresh_sights_async({ force_refresh: forceRefresh });
            return;
        }

        const result = await pywebview.api.get_sights_list({ force_refresh: forceRefresh });
        if (seq !== this._sightsRefreshSeq) return;
        if (!camoPage.classList.contains('active')) return;
        if (!sightsView.classList.contains('active')) return;

        this._sightsItems = Array.isArray(result.items) ? result.items : [];
        const searchInput = document.getElementById('sights-search-input');
        const sortSelect = document.getElementById('sights-sort-select');
        if (searchInput) this._sightsSearchQuery = searchInput.value || "";
        if (sortSelect) this._sightsSortKey = sortSelect.value || "update_time";
        this._renderSightsView();
        this.updateResourceStorage('sights');
        this._sightsLoaded = true;
    } catch (e) {
        console.error(e);
        waitingForAsyncPush = false;
    } finally {
        if (!waitingForAsyncPush && seq === this._sightsRefreshSeq) this._sightsRefreshing = false;
        if (!waitingForAsyncPush && refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.classList.remove('is-loading');
        }
    }
};

app.onSightsListReady = function (result) {
    const refreshBtn = document.getElementById('btn-refresh-sights');
    const camoPage = document.getElementById('page-camo');
    const sightsView = document.getElementById('view-sights');

    try {
        if (!camoPage || !sightsView) return;
        if (!camoPage.classList.contains('active')) return;
        if (!sightsView.classList.contains('active')) return;

        this._sightsItems = Array.isArray(result?.items) ? result.items : [];
        const searchInput = document.getElementById('sights-search-input');
        const sortSelect = document.getElementById('sights-sort-select');
        if (searchInput) this._sightsSearchQuery = searchInput.value || "";
        if (sortSelect) this._sightsSortKey = sortSelect.value || "update_time";
        this._renderSightsView();
        this.updateResourceStorage('sights');
        this._sightsLoaded = true;
    } finally {
        this._sightsRefreshing = false;
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.classList.remove('is-loading');
        }
    }
};

app.filterSightsNew = function (query) {
    this._sightsSearchQuery = String(query || "");
    this._renderSightsView();
};

app.sortSightsNew = function (sortKey) {
    this._sightsSortKey = sortKey || "update_time";
    this._renderSightsView();
};

app.filterSightsStatus = function (value) {
    this._sightsFilterStatus = value || 'all';
    this._renderSightsView();
};

app.toggleSightsSortOrder = function () {
    this._sightsSortAsc = !this._sightsSortAsc;
    const btn = document.getElementById('sights-sort-order-btn');
    if (btn) btn.classList.toggle('is-asc', this._sightsSortAsc);
    this._renderSightsView();
};

app._getFilteredSights = function () {
    const query = String(this._sightsSearchQuery || "").trim().toLowerCase();
    let items = Array.isArray(this._sightsItems) ? this._sightsItems.slice() : [];

    /* 状态筛选 */
    const filterStatus = this._sightsFilterStatus || 'all';
    if (filterStatus !== 'all') {
        items = items.filter(item => {
            const name = String(item.name || '');
            const isDisabled = !!item.disabled || name.endsWith('.AimerWT_BAN');
            return filterStatus === 'disabled' ? isDisabled : !isDisabled;
        });
    }

    if (query) {
        items = items.filter(item => {
            const searchText = [
                item.display_name,
                item.folder_name || item.name,
                item.name,
                item.path,
                item.preview_path,
                item.file_count,
                item.size_bytes
            ].filter(v => v !== null && v !== undefined).join(" ").toLowerCase();
            return searchText.includes(query);
        });
    }

    const sortKey = this._sightsSortKey || "update_time";
    const asc = !!this._sightsSortAsc;
    items.sort((a, b) => {
        let cmp = 0;
        if (sortKey === "name") {
            const aName = String(a.display_name || a.name || "");
            const bName = String(b.display_name || b.name || "");
            cmp = aName.localeCompare(bName, "zh-CN", { numeric: true });
        } else if (sortKey === "size") {
            cmp = Number(b.size_bytes || 0) - Number(a.size_bytes || 0);
        } else {
            const bTime = Number(b.mtime || b.update_time || 0);
            const aTime = Number(a.mtime || a.update_time || 0);
            cmp = bTime - aTime;
        }
        return asc ? -cmp : cmp;
    });

    return items;
};

app._renderSightsView = function () {
    const listEl = document.getElementById('sights-list');
    const countEl = document.getElementById('sights-count');
    if (!listEl || !countEl) return;

    const items = this._getFilteredSights();
    this.updateResourceSelectionSummary('sights', items.length);

    const selectAll = document.getElementById('sights-select-all');
    if (selectAll) {
        selectAll.checked = false;
        selectAll.indeterminate = false;
    }

    if (items.length === 0) {
        const hasQuery = String(this._sightsSearchQuery || "").trim().length > 0;
        listEl.innerHTML = `
            <div class="res-empty-state">
                <i class="ri-crosshair-line"></i>
                <h3>${hasQuery ? this.t('resource.no_matching_sights') : this.t('tools.empty_sights')}</h3>
                <p>${hasQuery ? this.t('resource.try_another_keyword') : this.t('tools.empty_sights_desc')}</p>
            </div>
        `;
        this.updateResourceSelectionSummary('sights', 0);
        return;
    }

    const placeholder = 'assets/card_image_small.png';
    listEl.innerHTML = items.map(item => {
        const folderName = String(item.name || "");
        const isDisabled = !!item.disabled || folderName.endsWith(".AimerWT_BAN");
        const enabledName = String(item.enabled_name || (isDisabled ? folderName.replace(/\.AimerWT_BAN$/, "") : folderName));
        const displayName = String(item.display_name || enabledName);
        const cover = item.cover_url || placeholder;
        const isDefaultCover = !!item.cover_is_default;
        const safeDisplayName = app._escapeHtml(displayName);
        const disabledLabel = app._escapeHtml(app.t('resource.status_disabled'));
        const cardTitle = app._escapeHtml(displayName === folderName
            ? String(item.path || "")
            : `${displayName}\n${app.t('resource.original_folder_title', { name: folderName })}\n${item.path || ""}`);
        const encodedName = encodeURIComponent(folderName);
        return `
            <div class="small-card${isDisabled ? ' is-disabled-resource' : ''}" title="${cardTitle}" data-sight-name-encoded="${encodedName}" data-disabled="${isDisabled ? '1' : '0'}">
                <div class="small-card-img-wrapper" style="position:relative;">
                    <img class="small-card-img${isDefaultCover ? ' is-default-cover' : ''}" src="${cover}" alt="">
                    ${isDisabled ? `<div class="resource-status-badge is-disabled">${disabledLabel}</div>` : ''}
                    <div class="skin-edit-overlay">
                        <button class="btn-v2 icon-only small secondary skin-edit-btn"
                                data-sight-name-encoded="${encodedName}"
                                onclick="app.openEditSightModal(decodeURIComponent(this.dataset.sightNameEncoded || ''), '${cover.replace(/'/g, "\\'")}')">
                            <i class="ri-edit-line"></i>
                        </button>
                    </div>
                </div>
                <div class="small-card-body">
                    <div class="small-card-title" title="${safeDisplayName}">${safeDisplayName}</div>
                    <div class="small-card-meta">
                        <span><i class="ri-file-list-3-line"></i> ${app._escapeHtml(app.t('resource.file_count', { count: item.file_count }))}</span>
                    </div>
                </div>
            </div>
        `;
    }).join('');
    this.updateResourceSelectionSummary('sights', items.length);
};

// --- 语音包库路径管理 ---
app.loadLibraryPathInfo = async function () {
    const pendingInput = document.getElementById('pending-dir-input');
    const libraryInput = document.getElementById('library-dir-input');

    // 检查 API 是否可用
    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_library_path_info !== 'function') {
        console.warn('loadLibraryPathInfo: API not ready');
        if (pendingInput) pendingInput.placeholder = this.t('settings.backend_waiting');
        if (libraryInput) libraryInput.placeholder = this.t('settings.backend_waiting');
        return;
    }

    try {
        console.log('loadLibraryPathInfo: calling API...');
        const info = await pywebview.api.get_library_path_info();
        console.log('loadLibraryPathInfo: got info', info);

        if (pendingInput && info) {
            if (info.custom_pending_dir) {
                pendingInput.value = info.custom_pending_dir;
                pendingInput.title = info.custom_pending_dir;
            } else {
                pendingInput.value = '';
                pendingInput.placeholder = info.default_pending_dir || this.t('settings.use_default_path');
                pendingInput.title = info.default_pending_dir || '';
            }
        }
        if (libraryInput && info) {
            if (info.custom_library_dir) {
                libraryInput.value = info.custom_library_dir;
                libraryInput.title = info.custom_library_dir;
            } else {
                libraryInput.value = '';
                libraryInput.placeholder = info.default_library_dir || this.t('settings.use_default_path');
                libraryInput.title = info.default_library_dir || '';
            }
        }
    } catch (e) {
        console.error('加载语音包库路径信息失败:', e);
        if (pendingInput) pendingInput.placeholder = this.t('settings.load_failed');
        if (libraryInput) libraryInput.placeholder = this.t('settings.load_failed');
    }
};

app.browsePendingDir = async function () {
    if (!window.pywebview?.api?.select_pending_dir) {
        this.showAlert(this.t('common.error'), this.t('common.feature_not_ready'), 'error');
        return;
    }

    try {
        const result = await pywebview.api.select_pending_dir();
        if (result && result.success && result.path) {
            const input = document.getElementById('pending-dir-input');
            if (input) {
                input.value = result.path;
                input.title = result.path;
            }
            await this.saveLibraryPaths();
        }
    } catch (e) {
        console.error(e);
        this.showAlert(this.t('common.error'), this.t('common.select_path_failed', { message: e.message }), 'error');
    }
};

app.browseLibraryDir = async function () {
    if (!window.pywebview?.api?.select_library_dir) {
        this.showAlert(this.t('common.error'), this.t('common.feature_not_ready'), 'error');
        return;
    }

    try {
        const result = await pywebview.api.select_library_dir();
        if (result && result.success && result.path) {
            const input = document.getElementById('library-dir-input');
            if (input) {
                input.value = result.path;
                input.title = result.path;
            }
            await this.saveLibraryPaths();
        }
    } catch (e) {
        console.error(e);
        this.showAlert(this.t('common.error'), this.t('common.select_path_failed', { message: e.message }), 'error');
    }
};

app.openPendingFolder = async function () {
    if (!window.pywebview?.api?.open_pending_folder) {
        this.showAlert(this.t('common.error'), this.t('common.feature_not_ready'), 'error');
        return;
    }

    try {
        await pywebview.api.open_pending_folder();
    } catch (e) {
        console.error(e);
        this.showAlert(this.t('common.error'), this.t('common.open_folder_failed', { message: e.message }), 'error');
    }
};

app.openLibraryFolder = async function () {
    if (!window.pywebview?.api?.open_library_folder) {
        this.showAlert(this.t('common.error'), this.t('common.feature_not_ready'), 'error');
        return;
    }

    try {
        await pywebview.api.open_library_folder();
    } catch (e) {
        console.error(e);
        this.showAlert(this.t('common.error'), this.t('common.open_folder_failed', { message: e.message }), 'error');
    }
};

app.saveLibraryPaths = async function () {
    if (!window.pywebview?.api?.save_pending_dir || !window.pywebview?.api?.save_library_dir) {
        this.showAlert(this.t('common.error'), this.t('common.feature_not_ready'), 'error');
        return;
    }

    const pendingInput = document.getElementById('pending-dir-input');
    const libraryInput = document.getElementById('library-dir-input');
    const pendingDir = pendingInput ? pendingInput.value.trim() : null;
    const libraryDir = libraryInput ? libraryInput.value.trim() : null;

    try {
        const pendingRes = await pywebview.api.save_pending_dir(pendingDir);
        if (!pendingRes || !pendingRes.success) {
            this.showErrorToast(this.t('common.save_failed'), pendingRes?.msg || this.t('common.save_failed'));
            return;
        }

        const libraryRes = await pywebview.api.save_library_dir(libraryDir);
        if (!libraryRes || !libraryRes.success) {
            this.showErrorToast(this.t('common.save_failed'), libraryRes?.msg || this.t('common.save_failed'));
            return;
        }

        this.showInfoToast(this.t('settings.saved'), this.t('settings.path_saved'));
        // 重新加载路径信息以更新 placeholder
        await this.loadLibraryPathInfo();
        // 刷新语音包库列表
        if (typeof this.refreshLibrary === 'function') {
            this.refreshLibrary();
        }
    } catch (e) {
        console.error(e);
        this.showErrorToast(this.t('common.save_failed'), this.t('common.operation_failed', { message: e.message }));
    }
};

app.resetLibraryPaths = async function () {
    if (!window.pywebview?.api?.save_pending_dir || !window.pywebview?.api?.save_library_dir) {
        this.showAlert(this.t('common.error'), this.t('common.feature_not_ready'), 'error');
        return;
    }

    // 确认重置
    const confirmed = await this.showConfirmDialog(
        this.t('settings.reset_paths_title'),
        this.t('settings.reset_paths_message')
    );
    if (!confirmed) return;

    try {
        const pendingRes = await pywebview.api.save_pending_dir('');
        if (!pendingRes || !pendingRes.success) {
            this.showErrorToast(this.t('common.reset_failed'), pendingRes?.msg || this.t('common.reset_failed'));
            return;
        }

        const libraryRes = await pywebview.api.save_library_dir('');
        if (!libraryRes || !libraryRes.success) {
            this.showErrorToast(this.t('common.reset_failed'), libraryRes?.msg || this.t('common.reset_failed'));
            return;
        }

        // 清空输入框
        const pendingInput = document.getElementById('pending-dir-input');
        const libraryInput = document.getElementById('library-dir-input');
        if (pendingInput) pendingInput.value = '';
        if (libraryInput) libraryInput.value = '';

        this.showInfoToast(this.t('settings.reset_done'), this.t('settings.path_reset'));
        // 重新加载以更新 placeholder
        await this.loadLibraryPathInfo();
        // 刷新语音包库列表
        if (typeof this.refreshLibrary === 'function') {
            this.refreshLibrary();
        }
    } catch (e) {
        console.error(e);
        this.showErrorToast(this.t('common.reset_failed'), this.t('common.operation_failed', { message: e.message }));
    }
};

// 複製路径到剪贴板
app.copyPathToClipboard = async function (inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;

    const path = input.value || input.placeholder;
    if (!path || path === this.t('settings.use_default_path') || path === this.t('settings.backend_waiting')) {
        this.showInfoToast(this.t('common.info'), this.t('settings.copy_no_path'));
        return;
    }

    try {
        await navigator.clipboard.writeText(path);

        // 显示複製成功的视觉反馈
        const btn = input.parentElement.querySelector('.path-copy-btn');
        if (btn) {
            btn.classList.add('copied');
            setTimeout(() => btn.classList.remove('copied'), 1500);
        }

        this.showInfoToast(this.t('settings.saved'), this.t('settings.copy_success'));
    } catch (e) {
        console.error('复制失败:', e);
        this.showErrorToast(this.t('settings.copy_failed'), this.t('settings.copy_failed'));
    }
};

// 单独重置待解压区路径
app.resetPendingDir = async function () {
    if (!window.pywebview?.api?.save_pending_dir) {
        this.showAlert(this.t('common.error'), this.t('common.feature_not_ready'), 'error');
        return;
    }

    try {
        // 将待解压区路径设为空（重置为预设）
        const result = await pywebview.api.save_pending_dir('');
        if (result && result.success) {
            const pendingInput = document.getElementById('pending-dir-input');
            if (pendingInput) {
                pendingInput.value = '';
            }
            this.showInfoToast(this.t('settings.reset_done'), this.t('settings.pending_path_reset'));
            await this.loadLibraryPathInfo();
            if (typeof this.refreshLibrary === 'function') {
                this.refreshLibrary();
            }
        } else {
            this.showErrorToast(this.t('common.reset_failed'), result.msg || this.t('common.reset_failed'));
        }
    } catch (e) {
        console.error(e);
        this.showErrorToast(this.t('common.reset_failed'), this.t('common.operation_failed', { message: e.message }));
    }
};

// 单独重置语音包库路径
app.resetLibraryDir = async function () {
    if (!window.pywebview?.api?.save_library_dir) {
        this.showAlert(this.t('common.error'), this.t('common.feature_not_ready'), 'error');
        return;
    }

    try {
        // 将语音包库路径设为空（重置为预设）
        const result = await pywebview.api.save_library_dir('');
        if (result && result.success) {
            const libraryInput = document.getElementById('library-dir-input');
            if (libraryInput) {
                libraryInput.value = '';
            }
            this.showInfoToast(this.t('settings.reset_done'), this.t('settings.library_path_reset'));
            await this.loadLibraryPathInfo();
            if (typeof this.refreshLibrary === 'function') {
                this.refreshLibrary();
            }
        } else {
            this.showErrorToast(this.t('common.reset_failed'), result.msg || this.t('common.reset_failed'));
        }
    } catch (e) {
        console.error(e);
        this.showErrorToast(this.t('common.reset_failed'), this.t('common.operation_failed', { message: e.message }));
    }
};

// 辅助方法：显示确认对话框
app.showConfirmDialog = function (title, message) {
    return new Promise((resolve) => {
        const modal = document.getElementById('modal-confirm');
        const titleEl = document.getElementById('confirm-title');
        const msgEl = document.getElementById('confirm-message');
        const cancelBtn = document.getElementById('btn-confirm-cancel');
        const okBtn = document.getElementById('btn-confirm-ok');

        if (!modal || !titleEl || !msgEl) {
            resolve(false);
            return;
        }

        titleEl.textContent = title;
        msgEl.innerHTML = message;
        okBtn.innerHTML = `<i class="ri-check-line"></i> ${this.t('common.confirm')}`;
        okBtn.className = 'btn primary';

        const cleanup = () => {
            modal.classList.remove('show');
            cancelBtn.onclick = null;
            okBtn.onclick = null;
        };

        cancelBtn.onclick = () => {
            cleanup();
            resolve(false);
        };

        okBtn.onclick = () => {
            cleanup();
            resolve(true);
        };

        modal.classList.add('show');
    });
};

/**
 * 全局拖放识别逻辑 (Global Drag & Drop Setup)
 * 功能：在特定页面监听文件拖入，并显示高级视觉反馈。
 */
app._dragCounter = 0;
app.hideDropOverlay = function () {
    const overlay = document.getElementById('drop-overlay');
    if (overlay) overlay.classList.remove('active');
    app._dragCounter = 0;
};

app.setupGlobalDragDrop = function () {
    const overlay = document.getElementById('drop-overlay');
    if (!overlay) return;

    // 定义允许显示拖放层的页面 (包括首页)
    const allowedPages = ['page-home', 'page-camo', 'page-sight'];

    const canShow = () => {
        const activePageEl = document.querySelector('.page.active');
        if (!activePageEl) return false;
        const activePageId = activePageEl.id;

        // 额外的逻辑判断：如果在炮镜库则也允许
        if (activePageId === 'page-camo') {
            const sightsView = document.getElementById('view-sights');
            if (sightsView && sightsView.classList.contains('active')) return true;
        }

        return allowedPages.includes(activePageId);
    };

    window.addEventListener('dragenter', (e) => {
        if (!canShow()) return;
        e.preventDefault();
        app._dragCounter++;
        if (app._dragCounter === 1) {
            // --- 动态更新提示文本 ---
            const activePageEl = document.querySelector('.page.active');
            const textEl = overlay.querySelector('.drop-overlay-text');
            if (activePageEl && textEl) {
                const id = activePageEl.id;
                if (id === 'page-home') {
                    textEl.innerText = app.t('drop.import_voice_pack');
                } else if (id === 'page-camo') {
                    const sightsView = document.getElementById('view-sights');
                    if (sightsView && sightsView.classList.contains('active')) {
                        textEl.innerText = app.t('drop.import_sight');
                    } else {
                        textEl.innerText = app.t('drop.import_skin');
                    }
                } else if (id === 'page-sight') {
                    textEl.innerText = app.t('drop.import_info_sight');
                }
            }
            overlay.classList.add('active');
        }
    });

    window.addEventListener('dragover', (e) => {
        if (!canShow()) return;
        e.preventDefault();
        if (!overlay.classList.contains('active')) {
            overlay.classList.add('active');
        }
    });

    window.addEventListener('dragleave', (e) => {
        if (!canShow()) return;
        e.preventDefault();
        app._dragCounter--;
        if (app._dragCounter <= 0) {
            app.hideDropOverlay();
        }
    });

    window.addEventListener('drop', (e) => {
        e.preventDefault();
        app.hideDropOverlay();
    });
};

(function () {
    const MODAL_ID = 'modal-mod-preview';
    const AUTHOR_WORKS_MODAL_ID = 'modal-author-works';
    const LIST_ID = 'lib-list';
    const FALLBACK_AVATAR = 'assets/card_image_small.png';
    const QQ_GROUP_URL = 'https://qun.qq.com/universal-share/share?ac=1&authKey=%2FDJOR1E72xAQKvLD%2BNQmaZmD7py%2F5PUY7xHORJX4kmmKdabaRF4%2BwIJkp6s8I10U&busi_data=eyJncm91cENvZGUiOiIxMDc4MzQzNjI5IiwidG9rZW4iOiJmSUNpVXErcnNMMVhlemRNR25EbVF5TWJrbmc5bm02UmRIS0c0WHFxemdWQkRzUlVmSkVZQW11NXFkRXZkMXBDIiwidWluIjoiMTA3OTY0OTM2OSJ9&data=4qfEzEByH95wqWw0I5ButymAfP5Aj5bjksqrXyh3uAoIWg5ChDGQ3w6cocqmRaRaGbDRpFunhEYQYBHwC46GHg&svctype=4&tempid=h5_group_info';
    const WTLIKER_URL = 'https://wtliker.com/';
    const WT_LIVE_URL = 'https://live.warthunder.com/';

    function getApp() {
        return window.app || null;
    }

    function tr(key, params = {}, fallback = '') {
        const app = getApp();
        if (app && typeof app.t === 'function') {
            const text = app.t(key, params);
            if (text !== key) return text;
        }
        if (window.I18N && typeof I18N.t === 'function') {
            const text = I18N.t(key, params);
            if (text !== key) return text;
        }
        return fallback || key;
    }

    function escapeHtml(value) {
        const app = getApp();
        if (app && typeof app._escapeHtml === 'function') return app._escapeHtml(value);
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function normalizeVersion(value) {
        let version = String(value || '1.0').trim();
        if (version.toLowerCase().startsWith('v')) version = version.slice(1);
        return version || '1.0';
    }

    function normalizeLanguages(mod) {
        if (Array.isArray(mod?.language) && mod.language.length > 0) return mod.language.map(String);
        if (typeof mod?.language === 'string' && mod.language.trim()) return [mod.language.trim()];
        return ['多语言'];
    }

    function localizeLanguageLabel(lang) {
        const keyMap = {
            '多语言': 'mod.lang_multi',
            '中': 'mod.lang_cn',
            '美': 'mod.lang_us',
            '英': 'mod.lang_uk',
            '俄': 'mod.lang_ru',
            '德': 'mod.lang_de',
            '日': 'mod.lang_jp',
            '法': 'mod.lang_fr',
            '未识别': 'mod.lang_unknown',
            '其他': 'mod.lang_other',
        };
        return tr(keyMap[String(lang || '').trim()] || '', {}, lang);
    }

    function capabilityLabel(capKey, fallback) {
        return tr(`mod.capability_${capKey}`, {}, fallback);
    }

    function buildLangHtml(mod) {
        return normalizeLanguages(mod).map((lang) => {
            let cls = '';
            if (typeof window.UI_CONFIG !== 'undefined' && window.UI_CONFIG?.langMap?.[lang]) {
                cls = window.UI_CONFIG.langMap[lang];
            }
            return `<span class="lang-text ${cls}">${escapeHtml(localizeLanguageLabel(lang))}</span>`;
        }).join('<span class="mod-preview-lang-sep">/</span>');
    }

    function normalizeUserTags(mod) {
        if (!Array.isArray(mod?.tags)) return [];
        return mod.tags
            .map((t) => typeof t === 'string' ? t.trim() : String(t || '').trim())
            .filter(Boolean);
    }

    function buildCapabilityTags(mod) {
        const caps = mod?.capabilities || {};
        const tags = [];

        if (typeof UI_CONFIG !== 'undefined' && UI_CONFIG?.tagMap) {
            Object.entries(UI_CONFIG.tagMap).forEach(([key, conf]) => {
                if (!caps[key]) return;
                tags.push({
                    text: capabilityLabel(key, conf?.text || key),
                    cls: conf?.cls || '',
                });
            });
            return tags;
        }

        const fallback = [
            ['tank', 'tank', capabilityLabel('tank', '陆战')],
            ['air', 'air', capabilityLabel('air', '空战')],
            ['naval', 'naval', capabilityLabel('naval', '海战')],
            ['radio', 'radio', capabilityLabel('radio', '无线电/队友')],
            ['missile', 'missile', capabilityLabel('missile', '导弹音效')],
            ['music', 'music', capabilityLabel('music', '音乐包')],
            ['noise', 'noise', capabilityLabel('noise', '降噪包')],
            ['pilot', 'pilot', capabilityLabel('pilot', '飞行员语音')],
        ];
        fallback.forEach(([capKey, cls, text]) => {
            if (caps[capKey]) tags.push({ text, cls });
        });
        return tags;
    }

    function buildTagHtml(mod) {
        const fromInfo = normalizeUserTags(mod);
        const normalizeTagText = (value) => String(value || '')
            .replace(/\s+/g, '')
            .replace(/[／]/g, '/')
            .toLowerCase();
        const resolveTagClass = (text) => {
            const keyText = normalizeTagText(text);
            if (typeof UI_CONFIG !== 'undefined' && UI_CONFIG?.tagMap) {
                const entry = Object.values(UI_CONFIG.tagMap).find((conf) => (
                    normalizeTagText(conf?.text) === keyText || normalizeTagText(conf?.cls) === keyText
                ));
                if (entry?.cls) return entry.cls;
            }
            const alias = [
                { cls: 'tank', words: ['陆战', '坦克'] },
                { cls: 'air', words: ['空战', '空军'] },
                { cls: 'naval', words: ['海战', '海军'] },
                { cls: 'radio', words: ['无线电', '局势'] },
                { cls: 'missile', words: ['导弹'] },
                { cls: 'music', words: ['音乐'] },
                { cls: 'noise', words: ['降噪'] },
                { cls: 'pilot', words: ['飞行员'] }
            ];
            for (const item of alias) {
                if (item.words.some((word) => keyText.includes(normalizeTagText(word)))) {
                    return item.cls;
                }
            }
            return '';
        };
        if (fromInfo.length > 0) {
            return fromInfo
                .map((text) => {
                    const cls = resolveTagClass(text);
                    return `<span class="tag ${escapeHtml(cls)}">${escapeHtml(text)}</span>`;
                })
                .join('');
        }
        return buildCapabilityTags(mod)
            .map((item) => `<span class="tag ${escapeHtml(item.cls)}">${escapeHtml(item.text)}</span>`)
            .join('');
    }

    function resolveDescription(mod) {
        return String(mod?.full_desc || mod?.description || mod?.note || tr('mod.no_description', {}, '暂无详细介绍')).trim();
    }

    function splitVersionNoteText(raw) {
        return String(raw || '')
            .split(/\n{2,}/)
            .map((block) => block.trim())
            .filter(Boolean)
            .map((block) => {
                const lines = block.split('\n');
                const firstLine = String(lines[0] || '').trim();
                const isPureVersion = /^v?\d+(?:\.\d+)*$/i.test(firstLine);
                if (isPureVersion) {
                    const version = `v${normalizeVersion(firstLine)}`;
                    const note = lines.slice(1).join('\n').trim();
                    return { version, note };
                }
                return { version: '', note: block };
            })
            .filter((item) => item.version || item.note);
    }

    function resolveVersionNoteEntries(mod) {
        if (Array.isArray(mod?.version_note)) {
            const entries = mod.version_note
                .map((item) => {
                    const rawVersion = String(item?.version || '').trim();
                    const version = rawVersion ? `v${normalizeVersion(rawVersion)}` : '';
                    const note = String(item?.note || '').trim();
                    if (!version && !note) return null;
                    return { version, note };
                })
                .filter(Boolean);
            if (entries.length) return entries;
        }

        const raw = String(mod?.version_note || mod?.changelog || '').trim();
        if (raw) return splitVersionNoteText(raw);

        const version = `v${normalizeVersion(mod?.version)}`;
        return [{ version, note: tr('mod.no_version_notes', {}, '暂无详细更新日志。') }];
    }

    function normalizeRelatedVoicepacks(raw) {
        if (!Array.isArray(raw)) return [];
        return raw
            .map((item) => ({
                name: String(item?.name || '').trim(),
                description: String(item?.description || '').trim(),
                link: String(item?.link || '').trim(),
                avatar_url: String(item?.avatar_url || '').trim(),
                preview_audio_files: Array.isArray(item?.preview_audio_files) ? item.preview_audio_files : []
            }))
            .filter((item) => item.name || item.description || item.link || item.avatar_url);
    }

    function normalizePreviewAudioItems(raw) {
        if (!Array.isArray(raw)) return [];
        return raw
            .map((item, idx) => ({
                preview_index: idx,
                display_name: String(item?.display_name || tr('mod.default_audio_name', { index: idx + 1 }, `试听音频${idx + 1}`)).trim() || tr('mod.default_audio_name', { index: idx + 1 }, `试听音频${idx + 1}`),
                source_name: String(item?.source_name || item?.source_file || '').trim(),
                source_file: String(item?.source_file || '').trim(),
                ext: String(item?.ext || '').trim().toLowerCase(),
            }))
            .filter((item) => item.source_name || item.source_file);
    }

    function buildVersionNoteHtml(mod) {
        const entries = resolveVersionNoteEntries(mod);
        if (!entries.length) {
            return `<span class="mod-preview-empty">${escapeHtml(tr('mod.no_version_notes', {}, '暂无详细更新日志。'))}</span>`;
        }
        return entries.map((item) => {
            const versionText = String(item?.version || '').trim();
            const noteText = String(item?.note || '').trim();
            const versionHtml = versionText ? `<div class="mod-preview-note-version">${escapeHtml(versionText)}</div>` : '';
            const noteHtml = noteText ? `<div class="mod-preview-note-text">${escapeHtml(noteText)}</div>` : '';
            const content = (versionHtml || noteHtml)
                ? `${versionHtml}${noteHtml}`
                : `<div class="mod-preview-note-text">${escapeHtml(tr('mod.no_version_notes', {}, '暂无详细更新日志。'))}</div>`;
            return `<div class="mod-preview-note-item">${content}</div>`;
        }).join('');
    }

    function findModById(modId) {
        const app = getApp();
        const list = Array.isArray(app?.modCache) ? app.modCache : [];
        const key = String(modId ?? '');
        return list.find((item) => String(item?.id ?? '') === key) || null;
    }

    function ensureModal() {
        let overlay = document.getElementById(MODAL_ID);
        if (overlay) return overlay;

        overlay = document.createElement('div');
        overlay.id = MODAL_ID;
        overlay.className = 'modal-overlay mod-preview-overlay';
        overlay.innerHTML = `
            <div class="modal-content mod-preview-modal-v2">
                <div class="mod-preview-topbar">
                    <div class="mod-preview-head-main">
                            <img class="mod-preview-author-avatar" id="mod-preview-author-avatar" src="${FALLBACK_AVATAR}" alt="author avatar">
                        <div class="mod-preview-head-text">
                            <div class="mod-preview-title-wrap">
                                <div class="mod-preview-title" id="mod-preview-title"></div>
                                <span class="mod-preview-version" id="mod-preview-version"></span>
                            </div>
                            <div class="mod-preview-subline">
                                <span class="meta-item"><i class="ri-user-3-line"></i> <span id="mod-preview-author"></span></span>
                                <span class="dot"></span>
                                <span class="meta-item"><i class="ri-time-line"></i> <span id="mod-preview-date"></span></span>
                            </div>
                        </div>
                    </div>
                    <button class="mod-preview-close-btn" type="button" title="${escapeHtml(tr('common.close', {}, '关闭'))}">
                        <i class="ri-close-line"></i>
                    </button>
                </div>

                <div class="mod-preview-body">
                    <div class="mod-preview-left">
                        <div class="mod-preview-cover-box">
                            <img class="mod-preview-cover" id="mod-preview-cover" src="" alt="${escapeHtml(tr('lib.voice_pack_label', {}, '语音包'))}">
                        </div>
                        <div class="mod-preview-attrs">
                            <h4>${escapeHtml(tr('mod.file_attrs', {}, '文件属性'))}</h4>
                            <div class="row"><span><i class="ri-hard-drive-2-line"></i> ${escapeHtml(tr('mod.file_size', {}, '文件大小'))}</span><b id="mod-preview-size"></b></div>
                            <div class="row"><span><i class="ri-translate"></i> ${escapeHtml(tr('mod.language_support', {}, '语言支持'))}</span><b id="mod-preview-lang"></b></div>
                            <div class="row"><span><i class="ri-price-tag-3-line"></i> ${escapeHtml(tr('mod.tag_count', {}, '标签数量'))}</span><b id="mod-preview-tag-count"></b></div>
                        </div>
                        <div class="mod-preview-compat">
                            <i class="ri-checkbox-circle-line"></i>
                            <div>
                                <strong>${escapeHtml(tr('mod.compatibility_good', {}, '兼容性良好'))}</strong>
                                <p>${escapeHtml(tr('mod.compatibility_desc', {}, '适配当前版本 War Thunder'))}</p>
                            </div>
                        </div>
                    </div>

                    <div class="mod-preview-right">
                        <div class="mod-preview-top-stack">
                            <section class="mod-preview-card mod-preview-tags-card">
                                <h4><i class="ri-price-tag-3-line"></i> ${escapeHtml(tr('mod.included_content', {}, '包含内容'))}</h4>
                                <div class="mod-preview-tags-scroll" id="mod-preview-tags"></div>
                            </section>

                            <section class="mod-preview-card mod-preview-desc-card">
                                <h4><i class="ri-information-line"></i> ${escapeHtml(tr('mod.detail_intro', {}, '详细介绍'))}</h4>
                                <div class="mod-preview-desc" id="mod-preview-desc"></div>
                            </section>
                        </div>
                        <div class="mod-preview-bottom-grid">
                            <section class="mod-preview-card">
                                <h4><i class="ri-refresh-line"></i> ${escapeHtml(tr('mod.version_notes', {}, '版本说明'))}</h4>
                                <div class="mod-preview-note-log" id="mod-preview-version-note"></div>
                            </section>

                            <section class="mod-preview-card mod-preview-links-card">
                                <h4><i class="ri-links-line"></i> ${escapeHtml(tr('mod.follow_feedback', {}, '关注与反馈'))}</h4>
                                <div class="mod-preview-link-grid">
                                    <button class="mod-preview-link-btn bili" type="button" data-link-action="bili"><i class="ri-bilibili-line"></i> ${escapeHtml(tr('mod.bili_home', {}, 'Bilibili 主页'))}</button>
                                    <button class="mod-preview-link-btn qq" type="button" data-link-action="qq"><i class="ri-qq-line"></i> ${escapeHtml(tr('mod.join_fan_group', {}, '加入粉丝群'))}</button>
                                    <button class="mod-preview-link-btn wt" type="button" data-link-action="wtlive"><i class="ri-global-line"></i> WT Live</button>
                                    <button class="mod-preview-link-btn liker" type="button" data-link-action="liker"><i class="ri-heart-3-line"></i> WT Liker</button>
                                    <button class="mod-preview-link-btn other-works" type="button" data-link-action="otherworks"><i class="ri-apps-2-line"></i> ${escapeHtml(tr('mod.author_other_packs', {}, '作者其他语音包'))}</button>
                                    <button class="mod-preview-link-btn feedback" type="button" data-link-action="feedback"><i class="ri-mail-send-line"></i> ${escapeHtml(tr('mod.contact_author', {}, '联系作者反馈'))}</button>
                                </div>
                            </section>
                        </div>
                    </div>
                </div>

                <div class="mod-preview-footer">
                    <div class="mod-preview-footer-actions">
                        <button class="btn secondary" type="button" data-action="delete"><i class="ri-delete-bin-line"></i> ${escapeHtml(tr('mod.delete', {}, '删除'))}</button>
                        <button class="btn secondary" type="button" data-action="open-folder"><i class="ri-folder-open-line"></i> ${escapeHtml(tr('mod.open', {}, '打开'))}</button>
                        <button class="btn secondary" type="button" data-action="audition"><i class="ri-play-circle-line"></i> ${escapeHtml(tr('mod.audition', {}, '试听语音'))}</button>
                        <button class="btn primary" type="button" data-action="apply"><i class="ri-check-line"></i> ${escapeHtml(tr('mod.apply', {}, '应用语音包'))}</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closePreview();
        });
        const closeBtn = overlay.querySelector('.mod-preview-close-btn');
        if (closeBtn) closeBtn.addEventListener('click', closePreview);
        if (!overlay.dataset.alignResizeBound) {
            const onResize = () => {
                if (overlay.classList.contains('show')) {
                    schedulePreviewHeaderAlign(overlay);
                }
            };
            window.addEventListener('resize', onResize);
            overlay.dataset.alignResizeBound = '1';
        }

        return overlay;
    }

    function openExternal(url) {
        const safeUrl = String(url || '').trim();
        if (!safeUrl) return;
        const app = getApp();
        if (app && typeof app.openExternal === 'function') {
            app.openExternal(safeUrl);
            return;
        }
        let finalUrl = safeUrl;
        if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(finalUrl)) {
            finalUrl = 'https://' + finalUrl;
        }
        const scheme = (finalUrl.match(/^([a-zA-Z][a-zA-Z0-9+.-]*):/) || [])[1]?.toLowerCase();
        if (!['http', 'https', 'mailto'].includes(scheme)) return;
        try {
            const parsedUrl = new URL(finalUrl);
            if ((scheme === 'http' || scheme === 'https') && !parsedUrl.host) return;
            if (scheme === 'mailto' && !parsedUrl.pathname) return;
        } catch (_) {
            return;
        }
        try {
            window.open(finalUrl, '_blank', 'noopener');
        } catch (e) {
            if (app && typeof app.showAlert === 'function') {
                app.showAlert(tr('common.error', {}, '错误'), tr('common.open_link_failed', {}, '打开链接失败'), 'error');
            }
        }
    }

    function bindFooterActions(overlay, mod) {
        const app = getApp();
        const applyBtn = overlay.querySelector('[data-action="apply"]');
        const deleteBtn = overlay.querySelector('[data-action="delete"]');
        const openFolderBtn = overlay.querySelector('[data-action="open-folder"]');
        const auditionBtn = overlay.querySelector('[data-action="audition"]');

        if (applyBtn) {
            applyBtn.onclick = () => {
                closePreview();
                if (app && typeof app.openInstallModal === 'function') {
                    app.openInstallModal(mod.id);
                }
            };
        }
        if (deleteBtn) {
            deleteBtn.onclick = () => {
                closePreview();
                if (app && typeof app.deleteMod === 'function') {
                    app.deleteMod(mod.id);
                }
            };
        }
        if (openFolderBtn) {
            openFolderBtn.onclick = async () => {
                const modId = String(mod?.id || '').trim();
                if (!modId) {
                    if (app && typeof app.showAlert === 'function') {
                        app.showAlert(tr('common.info', {}, '提示'), tr('mod.id_empty_open_folder', {}, '语音包标识为空，无法打开目录'), 'warn');
                    }
                    return;
                }
                try {
                    if (window.pywebview?.api?.open_mod_folder) {
                        const res = await pywebview.api.open_mod_folder(modId);
                        if (!res?.success) {
                            if (app && typeof app.showAlert === 'function') {
                                app.showAlert(tr('common.error', {}, '错误'), res?.msg || tr('common.open_directory_failed', {}, '打开目录失败'), 'error');
                            }
                        }
                        return;
                    }
                    if (window.pywebview?.api?.open_folder) {
                        await pywebview.api.open_folder('library');
                        return;
                    }
                    if (app && typeof app.showAlert === 'function') {
                        app.showAlert(tr('common.error', {}, '错误'), tr('common.open_directory_unavailable', {}, '打开目录接口不可用'), 'error');
                    }
                } catch (e) {
                    if (app && typeof app.showAlert === 'function') {
                        app.showAlert(tr('common.error', {}, '错误'), tr('common.operation_failed', { message: e.message || e }, `打开目录失败: ${e.message || e}`), 'error');
                    }
                }
            };
        }
        if (auditionBtn) {
            auditionBtn.onclick = async () => {
                try {
                    const manualPreviewItems = normalizePreviewAudioItems(mod?.preview_audio_files || []);
                    const useRandomPreview = mod?.preview_use_random_bank !== false || !manualPreviewItems.length;
                    if (mod?.preview_use_random_bank === false && !manualPreviewItems.length) {
                        if (app && typeof app.showInfoToast === 'function') {
                            app.showInfoToast(tr('common.info', {}, '提示'), tr('mod.audition_fallback_random', {}, '未配置作者试听文件，已回退到随机试听'));
                        }
                    }
                    if (!useRandomPreview) {
                        openAuthorPreviewAudioPicker(mod, manualPreviewItems);
                        return;
                    }

                    if (!window.pywebview?.api?.start_mod_audition_scan || !window.pywebview?.api?.get_mod_audition_categories_snapshot) {
                        if (app && typeof app.showAlert === 'function') {
                            app.showAlert(tr('common.error', {}, '错误'), tr('audition.backend_unavailable', {}, '后端试听接口不可用'), 'error');
                        }
                        return;
                    }

                    auditionBtn.disabled = true;
                    const oldHtml = auditionBtn.innerHTML;
                    auditionBtn.innerHTML = `<i class="ri-loader-2-line"></i> ${escapeHtml(tr('audition.preparing', {}, '初始化试听...'))}`;
                    const currentState = window.__auditionPickerState;
                    const currentModId = String(mod.id || '');
                    if (currentState && currentState.modId === currentModId) {
                        // 同一语音包重复点击：不重复开窗和重复初始化
                        auditionBtn.innerHTML = oldHtml;
                        auditionBtn.disabled = false;
                        if (app && typeof app.showInfoToast === 'function') {
                            app.showInfoToast(tr('common.info', {}, '提示'), tr('mod.audition_window_open', {}, '该语音包试听窗口已打开'));
                        }
                        return;
                    }
                    if (currentState && typeof currentState.close === 'function') {
                        currentState.close(true);
                    }
                    openAuditionPicker(mod, []);
                    await pywebview.api.start_mod_audition_scan(mod.id);
                    const snap = await pywebview.api.get_mod_audition_categories_snapshot(mod.id);
                    auditionBtn.innerHTML = oldHtml;
                    auditionBtn.disabled = false;

                    if (!snap || !snap.success) {
                        const msg = (snap && snap.msg) ? snap.msg : tr('mod.audition_init_failed', {}, '试听初始化失败');
                        if (app && typeof app.showAlert === 'function') {
                            app.showAlert(tr('common.error', {}, '错误'), msg, 'error');
                        }
                        return;
                    }
                    if (window.__auditionPickerState && typeof window.__auditionPickerState.update === 'function') {
                        window.__auditionPickerState.update(snap);
                    }
                } catch (e) {
                    if (auditionBtn) {
                        auditionBtn.disabled = false;
                        auditionBtn.innerHTML = `<i class="ri-play-circle-line"></i> ${escapeHtml(tr('mod.audition', {}, '试听语音'))}`;
                    }
                    if (app && typeof app.showAlert === 'function') {
                        app.showAlert(tr('common.error', {}, '错误'), tr('mod.audition_failed_with_message', { message: e.message || e }, `试听失败: ${e.message || e}`), 'error');
                    }
                }
            };
        }
    }

    function formatDuration(sec) {
        const n = Number(sec || 0);
        if (!Number.isFinite(n) || n <= 0) return '0:00';
        const m = Math.floor(n / 60);
        const s = Math.floor(n % 60);
        return `${m}:${String(s).padStart(2, '0')}`;
    }

    function openAuditionPicker(mod, categories) {
        const app = getApp();
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay show';
        overlay.style.zIndex = '10002';
        let categoriesData = Array.isArray(categories) ? [...categories] : [];

        overlay.innerHTML = `
            <div class="modal-content" style="max-width:980px;width:min(94vw,980px);padding:20px;max-height:86vh;display:flex;flex-direction:column;">
                <h3 style="margin:0 0 12px 0;">${escapeHtml(tr('audition.choose_category', {}, '选择试听分类'))}</h3>
                <div style="display:flex;gap:8px;margin-bottom:10px;">
                    <input id="audition-search" type="text" placeholder="${escapeHtml(tr('audition.search_category_placeholder', {}, '搜索分类名 / code'))}" style="flex:1;padding:10px;border:1px solid var(--border-color);border-radius:10px;">
                    <span id="audition-count" style="align-self:center;color:var(--text-secondary);font-size:13px;line-height:1;padding:8px 10px;border:1px solid var(--border-color);border-radius:8px;white-space:nowrap;">${escapeHtml(tr('audition.waiting_parse', {}, '等待解析...'))}</span>
                </div>
                <div style="margin-bottom:10px;">
                    <div id="audition-progress-text" style="font-size:13px;color:var(--text-secondary);margin-bottom:6px;">${escapeHtml(tr('audition.preparing', {}, '准备中...'))}</div>
                    <div style="height:8px;background:var(--bg-card-soft, rgba(127,127,127,0.2));border-radius:999px;overflow:hidden;border:1px solid var(--border-color);">
                        <div id="audition-progress-bar" style="height:100%;width:0%;background:linear-gradient(90deg,var(--primary),#ffb347);transition:width .2s ease;"></div>
                    </div>
                </div>
                <select id="audition-select" size="22" style="width:100%;flex:1;min-height:320px;font-family:Consolas, monospace;padding:10px;border:1px solid var(--border-color);border-radius:10px;"></select>
                <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:12px;">
                    <button class="btn secondary" type="button" id="audition-pause-btn">${escapeHtml(tr('audition.pause_parse', {}, '暂停解析'))}</button>
                    <button class="btn secondary" type="button" id="audition-close-btn">${escapeHtml(tr('common.close', {}, '关闭'))}</button>
                    <button class="btn primary" type="button" id="audition-play-btn"><i class="ri-play-circle-line"></i> ${escapeHtml(tr('audition.random_play_category', {}, '随机试听该分类'))}</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        const selectEl = overlay.querySelector('#audition-select');
        const searchEl = overlay.querySelector('#audition-search');
        const countEl = overlay.querySelector('#audition-count');
        const progressTextEl = overlay.querySelector('#audition-progress-text');
        const progressBarEl = overlay.querySelector('#audition-progress-bar');
        const playBtn = overlay.querySelector('#audition-play-btn');
        const closeBtn = overlay.querySelector('#audition-close-btn');
        const pauseBtn = overlay.querySelector('#audition-pause-btn');
        let snapshotStatusText = tr('audition.preparing', {}, '准备中...');

        const close = (switching = false) => {
            if (window.__aimerAuditionAudio) {
                try {
                    window.__aimerAuditionAudio.pause();
                    window.__aimerAuditionAudio.currentTime = 0;
                    window.__aimerAuditionAudio.src = '';
                } catch (e) {
                }
            }
            if (window.pywebview?.api?.stop_mod_audition_scan) {
                pywebview.api.stop_mod_audition_scan(mod.id).catch(() => { });
            }
            if (window.pywebview?.api?.clear_audition_cache) {
                pywebview.api.clear_audition_cache(mod.id).catch(() => { });
            }
            if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
            if (window.__auditionPickerState && window.__auditionPickerState.modId === String(mod.id || '')) {
                window.__auditionPickerState = null;
            }
            if (!switching && app && typeof app.showInfoToast === 'function') {
                app.showInfoToast(tr('common.info', {}, '提示'), tr('audition.closed', {}, '已关闭试听窗口'));
            }
        };

        const rebuildOptions = (keyword) => {
            const q = String(keyword || '').trim().toLowerCase();
            let visible = 0;
            const html = categoriesData.map((it, idx) => {
                const name = String(it.name || '');
                const code = String(it.code || '');
                const hit = !q || name.toLowerCase().includes(q) || code.toLowerCase().includes(q);
                if (!hit) return '';
                visible += 1;
                const label = `${escapeHtml(name)} (${escapeHtml(tr('audition.item_count', { count: Number(it.count || 0) }, `${Number(it.count || 0)} 条`))}) [${escapeHtml(code)}]`;
                return `<option value="${idx}">${label}</option>`;
            }).join('');
            selectEl.innerHTML = html;
            if (progressTextEl) {
                const base = snapshotStatusText || tr('audition.parse_in_progress', {}, '解析中...');
                if (visible !== categoriesData.length) {
                    progressTextEl.textContent = tr('audition.filtered_categories', { base, visible, total: categoriesData.length }, `${base} · 当前筛选 ${visible}/${categoriesData.length} 类`);
                } else {
                    progressTextEl.textContent = base;
                }
            }
        };

        const updateFromSnapshot = (snap) => {
            if (!snap) return;
            if (Array.isArray(snap.categories)) categoriesData = snap.categories;
            if (countEl) {
                const p = Number(snap.progress || 0);
                const msg = String(snap.message || '');
                countEl.textContent = tr('audition.count_summary', { categories: categoriesData.length, items: Number(snap.count || 0) }, `${categoriesData.length} 类 / ${Number(snap.count || 0)} 条`);
                if (progressTextEl) {
                    snapshotStatusText = `${msg || tr('audition.parse_in_progress', {}, '解析中')} (${p}%)`;
                    progressTextEl.textContent = snapshotStatusText;
                }
                if (progressBarEl) {
                    progressBarEl.style.width = `${Math.max(0, Math.min(100, p))}%`;
                }
                if (snap.done) {
                    if (snap.error) {
                        snapshotStatusText = tr('audition.parse_finished_error', { message: snap.error }, `解析结束：${snap.error}`);
                        if (progressTextEl) progressTextEl.textContent = snapshotStatusText;
                    } else {
                        snapshotStatusText = tr('audition.parse_completed', { categories: categoriesData.length, items: Number(snap.count || 0) }, `解析完成：${categoriesData.length} 类，${Number(snap.count || 0)} 条语音`);
                        if (progressTextEl) progressTextEl.textContent = snapshotStatusText;
                    }
                }
            }
            rebuildOptions(searchEl ? searchEl.value : '');
            if (pauseBtn) {
                if (snap.done) {
                    pauseBtn.disabled = true;
                    pauseBtn.textContent = tr('audition.parse_done_button', {}, '解析已完成');
                } else {
                    pauseBtn.disabled = false;
                    pauseBtn.textContent = snap.paused ? tr('audition.resume_parse', {}, '继续解析') : tr('audition.pause_parse', {}, '暂停解析');
                }
            }
        };

        if (searchEl) {
            searchEl.addEventListener('input', (e) => {
                rebuildOptions(e.target.value);
            });
        }

        const playSelected = async () => {
            try {
                if (!selectEl || !selectEl.value) {
                    if (app && typeof app.showAlert === 'function') {
                        app.showAlert(tr('common.info', {}, '提示'), tr('audition.select_category_required', {}, '请先选择一个分类'), 'warn');
                    }
                    return;
                }
                if (!window.pywebview?.api?.audition_mod_random_by_type) {
                    if (app && typeof app.showAlert === 'function') {
                        app.showAlert(tr('common.error', {}, '错误'), tr('audition.backend_unavailable', {}, '后端试听接口不可用'), 'error');
                    }
                    return;
                }

                const selected = categoriesData[Number(selectEl.value)];
                if (!selected) return;

                const selectedCode = String(selected.code || '').toLowerCase();
                if (selectedCode === 'preview') {
                    if (!window.pywebview?.api?.list_mod_audition_items_by_type) {
                        if (app && typeof app.showAlert === 'function') {
                            app.showAlert(tr('common.error', {}, '错误'), tr('audition.backend_manual_unavailable', {}, '后端手动试听接口不可用'), 'error');
                        }
                        return;
                    }
                    playBtn.disabled = true;
                    const oldHtml = playBtn.innerHTML;
                    playBtn.innerHTML = `<i class="ri-loader-2-line"></i> ${escapeHtml(tr('audition.loading_items', {}, '加载试听条目...'))}`;
                    const listRes = await pywebview.api.list_mod_audition_items_by_type(mod.id, selected.code);
                    playBtn.disabled = false;
                    playBtn.innerHTML = oldHtml;
                    if (!listRes || !listRes.success || !Array.isArray(listRes.items) || listRes.items.length === 0) {
                        const msg = (listRes && listRes.msg) ? listRes.msg : tr('audition.no_items', {}, '未获取到可试听条目');
                        if (app && typeof app.showAlert === 'function') {
                            app.showAlert(tr('common.error', {}, '错误'), msg, 'error');
                        }
                        return;
                    }
                    openManualPreviewPicker(mod, selected, listRes.items);
                    return;
                }

                playBtn.disabled = true;
                const oldHtml = playBtn.innerHTML;
                playBtn.innerHTML = `<i class="ri-loader-2-line"></i> ${escapeHtml(tr('audition.random_picking', {}, '随机抽取中...'))}`;
                const res = await pywebview.api.audition_mod_random_by_type(
                    mod.id,
                    selected.code,
                    12
                );
                playBtn.disabled = false;
                playBtn.innerHTML = oldHtml;

                if (!res || !res.success || !res.audio_url) {
                    const msg = (res && res.msg) ? res.msg : tr('mod.audition_failed', {}, '试听失败');
                    if (app && typeof app.showAlert === 'function') {
                        app.showAlert(tr('common.error', {}, '错误'), msg, 'error');
                    }
                    return;
                }

                if (!window.__aimerAuditionAudio) {
                    window.__aimerAuditionAudio = new Audio();
                }
                const player = window.__aimerAuditionAudio;
                player.pause();
                player.currentTime = 0;
                player.src = res.audio_url;
                await player.play();
                if (app && typeof app.showInfoToast === 'function') {
                    const picked = String(res.picked_name || tr('audition.random_voice', {}, '随机语音'));
                    const typeName = String(res.voice_type_name || selected.name || selected.code);
                    app.showInfoToast(tr('audition.playing_title', {}, '试听中'), tr('audition.playing_random', { type: typeName, name: picked }, `分类[${typeName}] 随机播放：${picked}`));
                }
            } catch (e) {
                playBtn.disabled = false;
                playBtn.innerHTML = `<i class="ri-play-circle-line"></i> ${escapeHtml(tr('audition.random_play_category', {}, '随机试听该分类'))}`;
                if (app && typeof app.showAlert === 'function') {
                    app.showAlert(tr('common.error', {}, '错误'), tr('mod.audition_failed_with_message', { message: e.message || e }, `试听失败: ${e.message || e}`), 'error');
                }
            }
        };

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) close();
        });
        if (closeBtn) closeBtn.addEventListener('click', close);
        if (pauseBtn) {
            pauseBtn.addEventListener('click', async () => {
                try {
                    if (!window.pywebview?.api?.set_mod_audition_scan_paused) {
                        if (app && typeof app.showAlert === 'function') {
                            app.showAlert(tr('common.error', {}, '错误'), tr('audition.backend_pause_unavailable', {}, '后端暂停接口不可用'), 'error');
                        }
                        return;
                    }
                    const willPause = pauseBtn.textContent.includes(tr('audition.pause_parse', {}, '暂停解析')) || pauseBtn.textContent.includes('暂停');
                    pauseBtn.disabled = true;
                    const res = await pywebview.api.set_mod_audition_scan_paused(mod.id, willPause);
                    if (!res || !res.success) {
                        if (app && typeof app.showAlert === 'function') {
                            app.showAlert(tr('common.error', {}, '错误'), (res && res.msg) ? res.msg : tr('common.failure', {}, '操作失败'), 'error');
                        }
                        pauseBtn.disabled = false;
                        return;
                    }
                    pauseBtn.textContent = res.paused ? tr('audition.resume_parse', {}, '继续解析') : tr('audition.pause_parse', {}, '暂停解析');
                    pauseBtn.disabled = false;
                } catch (e) {
                    pauseBtn.disabled = false;
                    if (app && typeof app.showAlert === 'function') {
                        app.showAlert(tr('common.error', {}, '错误'), tr('common.operation_failed', { message: e.message || e }, `操作失败: ${e.message || e}`), 'error');
                    }
                }
            });
        }
        if (playBtn) playBtn.addEventListener('click', playSelected);
        if (selectEl) {
            selectEl.addEventListener('dblclick', playSelected);
        }

        window.__auditionPickerState = {
            modId: String(mod.id || ''),
            update: updateFromSnapshot,
            close,
        };
        updateFromSnapshot({ categories: categoriesData, progress: 0, message: tr('audition.waiting_parse_message', {}, '等待解析'), done: false, count: 0 });
    }

    function openManualPreviewPicker(mod, category, items) {
        const app = getApp();
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay show';
        overlay.style.zIndex = '10003';

        const optionsHtml = items.map((it, idx) => {
            const nm = escapeHtml(String(it.name || `stream_${it.stream_index}`));
            const bk = escapeHtml(String(it.bank_file || 'unknown.bank'));
            const d = formatDuration(it.duration_sec);
            return `<option value="${idx}">#${idx + 1} ${nm} (${d}) [${bk}]</option>`;
        }).join('');

        overlay.innerHTML = `
            <div class="modal-content" style="max-width:980px;width:min(94vw,980px);padding:20px;max-height:86vh;display:flex;flex-direction:column;">
                <h3 style="margin:0 0 12px 0;">${escapeHtml(tr('audition.manual_title', { name: String(category?.name || tr('audition.manual_fallback_title', {}, '试听')) }, `手动选择试听语音 - ${String(category?.name || '试听')}`))}</h3>
                <div style="display:flex;gap:8px;margin-bottom:10px;">
                    <input id="manual-preview-search" type="text" placeholder="${escapeHtml(tr('audition.search_voice_placeholder', {}, '搜索语音名 / bank 文件名'))}" style="flex:1;padding:10px;border:1px solid var(--border-color);border-radius:10px;">
                    <span id="manual-preview-count" style="align-self:center;color:var(--text-secondary);font-size:13px;line-height:1;padding:8px 10px;border:1px solid var(--border-color);border-radius:8px;white-space:nowrap;">${escapeHtml(tr('audition.total_items', { count: items.length }, `共 ${items.length} 条`))}</span>
                </div>
                <select id="manual-preview-select" size="22" style="width:100%;flex:1;min-height:320px;font-family:Consolas, monospace;padding:10px;border:1px solid var(--border-color);border-radius:10px;">${optionsHtml}</select>
                <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:12px;">
                    <button class="btn secondary" type="button" id="manual-preview-close-btn">${escapeHtml(tr('common.close', {}, '关闭'))}</button>
                    <button class="btn primary" type="button" id="manual-preview-play-btn"><i class="ri-play-circle-line"></i> ${escapeHtml(tr('audition.play_selected_voice', {}, '播放选中语音'))}</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        const selectEl = overlay.querySelector('#manual-preview-select');
        const searchEl = overlay.querySelector('#manual-preview-search');
        const countEl = overlay.querySelector('#manual-preview-count');
        const playBtn = overlay.querySelector('#manual-preview-play-btn');
        const closeBtn = overlay.querySelector('#manual-preview-close-btn');
        let viewItems = [...items];

        const close = () => {
            if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
        };

        const rebuild = (keyword) => {
            const q = String(keyword || '').trim().toLowerCase();
            const filtered = items.filter((it) => {
                const n = String(it.name || '').toLowerCase();
                const b = String(it.bank_file || '').toLowerCase();
                return !q || n.includes(q) || b.includes(q);
            });
            viewItems = filtered;
            selectEl.innerHTML = filtered.map((it, idx) => {
                const nm = escapeHtml(String(it.name || `stream_${it.stream_index}`));
                const bk = escapeHtml(String(it.bank_file || 'unknown.bank'));
                const d = formatDuration(it.duration_sec);
                return `<option value="${idx}">#${idx + 1} ${nm} (${d}) [${bk}]</option>`;
            }).join('');
            if (countEl) countEl.textContent = tr('audition.display_count', { visible: filtered.length, total: items.length }, `显示 ${filtered.length} / ${items.length} 条`);
        };

        const playSelected = async () => {
            try {
                if (!selectEl || !selectEl.value) {
                    if (app && typeof app.showAlert === 'function') {
                        app.showAlert(tr('common.info', {}, '提示'), tr('audition.select_voice_required', {}, '请先选择一条语音'), 'warn');
                    }
                    return;
                }
                if (!window.pywebview?.api?.audition_mod_stream) {
                    if (app && typeof app.showAlert === 'function') {
                        app.showAlert(tr('common.error', {}, '错误'), tr('audition.backend_play_unavailable', {}, '后端播放接口不可用'), 'error');
                    }
                    return;
                }
                const selected = viewItems[Number(selectEl.value)];
                if (!selected) return;

                playBtn.disabled = true;
                const oldHtml = playBtn.innerHTML;
                playBtn.innerHTML = `<i class="ri-loader-2-line"></i> ${escapeHtml(tr('audition.parsing', {}, '解析中...'))}`;
                const res = await pywebview.api.audition_mod_stream(
                    mod.id,
                    selected.bank_rel,
                    selected.chunk_index,
                    selected.stream_index,
                    12
                );
                playBtn.disabled = false;
                playBtn.innerHTML = oldHtml;
                if (!res || !res.success || !res.audio_url) {
                    const msg = (res && res.msg) ? res.msg : tr('mod.audition_failed', {}, '试听失败');
                    if (app && typeof app.showAlert === 'function') {
                        app.showAlert(tr('common.error', {}, '错误'), msg, 'error');
                    }
                    return;
                }
                if (!window.__aimerAuditionAudio) {
                    window.__aimerAuditionAudio = new Audio();
                }
                const player = window.__aimerAuditionAudio;
                player.pause();
                player.currentTime = 0;
                player.src = res.audio_url;
                await player.play();
                if (app && typeof app.showInfoToast === 'function') {
                    app.showInfoToast(tr('audition.playing_title', {}, '试听中'), tr('audition.playing_voice', { name: selected.name || ('#' + selected.stream_index) }, `正在播放：${selected.name || ('#' + selected.stream_index)}`));
                }
            } catch (e) {
                playBtn.disabled = false;
                playBtn.innerHTML = `<i class="ri-play-circle-line"></i> ${escapeHtml(tr('audition.play_selected_voice', {}, '播放选中语音'))}`;
                if (app && typeof app.showAlert === 'function') {
                    app.showAlert(tr('common.error', {}, '错误'), tr('mod.audition_failed_with_message', { message: e.message || e }, `试听失败: ${e.message || e}`), 'error');
                }
            }
        };

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) close();
        });
        if (closeBtn) closeBtn.addEventListener('click', close);
        if (playBtn) playBtn.addEventListener('click', playSelected);
        if (selectEl) selectEl.addEventListener('dblclick', playSelected);
        if (searchEl) searchEl.addEventListener('input', (e) => rebuild(e.target.value));
    }

    function openAuthorPreviewAudioPicker(mod, items) {
        const app = getApp();
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay show';
        overlay.style.zIndex = '10003';

        const optionsHtml = items.map((it, idx) => {
            const nm = escapeHtml(String(it.display_name || tr('mod.default_audio_name', { index: idx + 1 }, `试听音频${idx + 1}`)));
            const src = escapeHtml(String(it.source_name || it.source_file || 'unknown'));
            return `<option value="${idx}">#${idx + 1} ${nm} [${src}]</option>`;
        }).join('');

        overlay.innerHTML = `
            <div class="modal-content" style="max-width:980px;width:min(94vw,980px);padding:20px;max-height:86vh;display:flex;flex-direction:column;">
                <h3 style="margin:0 0 12px 0;">${escapeHtml(tr('audition.author_preview_title', {}, '作者提供的试听文件'))}</h3>
                <div style="display:flex;gap:8px;margin-bottom:10px;">
                    <input id="author-preview-search" type="text" placeholder="${escapeHtml(tr('audition.search_preview_placeholder', {}, '搜索试听名称 / 文件名'))}" style="flex:1;padding:10px;border:1px solid var(--border-color);border-radius:10px;">
                    <span id="author-preview-count" style="align-self:center;color:var(--text-secondary);font-size:13px;line-height:1;padding:8px 10px;border:1px solid var(--border-color);border-radius:8px;white-space:nowrap;">${escapeHtml(tr('audition.total_items', { count: items.length }, `共 ${items.length} 条`))}</span>
                </div>
                <select id="author-preview-select" size="18" style="width:100%;flex:1;min-height:280px;font-family:Consolas, monospace;padding:10px;border:1px solid var(--border-color);border-radius:10px;">${optionsHtml}</select>
                <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:12px;">
                    <button class="btn secondary" type="button" id="author-preview-close-btn">${escapeHtml(tr('common.close', {}, '关闭'))}</button>
                    <button class="btn primary" type="button" id="author-preview-play-btn"><i class="ri-play-circle-line"></i> ${escapeHtml(tr('audition.play_selected_preview', {}, '播放选中试听'))}</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        const selectEl = overlay.querySelector('#author-preview-select');
        const searchEl = overlay.querySelector('#author-preview-search');
        const countEl = overlay.querySelector('#author-preview-count');
        const playBtn = overlay.querySelector('#author-preview-play-btn');
        const closeBtn = overlay.querySelector('#author-preview-close-btn');
        let viewItems = [...items];

        const close = () => {
            if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
        };

        const rebuild = (keyword) => {
            const q = String(keyword || '').trim().toLowerCase();
            const filtered = items.filter((it) => {
                const name = String(it.display_name || '').toLowerCase();
                const source = String(it.source_name || it.source_file || '').toLowerCase();
                return !q || name.includes(q) || source.includes(q);
            });
            viewItems = filtered;
            selectEl.innerHTML = filtered.map((it, idx) => {
                const nm = escapeHtml(String(it.display_name || tr('mod.default_audio_name', { index: idx + 1 }, `试听音频${idx + 1}`)));
                const src = escapeHtml(String(it.source_name || it.source_file || 'unknown'));
                return `<option value="${idx}">#${idx + 1} ${nm} [${src}]</option>`;
            }).join('');
            if (countEl) countEl.textContent = tr('audition.display_count', { visible: filtered.length, total: items.length }, `显示 ${filtered.length} / ${items.length} 条`);
        };

        const playSelected = async () => {
            try {
                if (!selectEl || !selectEl.value) {
                    if (app && typeof app.showAlert === 'function') {
                        app.showAlert(tr('common.info', {}, '提示'), tr('audition.select_preview_required', {}, '请先选择一个试听文件'), 'warn');
                    }
                    return;
                }
                if (!window.pywebview?.api?.audition_mod_preview_audio) {
                    if (app && typeof app.showAlert === 'function') {
                        app.showAlert(tr('common.error', {}, '错误'), tr('audition.backend_unavailable', {}, '后端试听接口不可用'), 'error');
                    }
                    return;
                }
                const selected = viewItems[Number(selectEl.value)];
                if (!selected) return;

                playBtn.disabled = true;
                const oldHtml = playBtn.innerHTML;
                playBtn.innerHTML = `<i class="ri-loader-2-line"></i> ${escapeHtml(tr('audition.loading_preview', {}, '加载试听...'))}`;
                const res = await pywebview.api.audition_mod_preview_audio(
                    mod.id,
                    selected.preview_index
                );
                playBtn.disabled = false;
                playBtn.innerHTML = oldHtml;
                if (!res || !res.success || !res.audio_url) {
                    const msg = (res && res.msg) ? res.msg : tr('mod.audition_failed', {}, '试听失败');
                    if (app && typeof app.showAlert === 'function') {
                        app.showAlert(tr('common.error', {}, '错误'), msg, 'error');
                    }
                    return;
                }

                if (!window.__aimerAuditionAudio) {
                    window.__aimerAuditionAudio = new Audio();
                }
                const player = window.__aimerAuditionAudio;
                player.pause();
                player.currentTime = 0;
                player.src = res.audio_url;
                await player.play();
                if (app && typeof app.showInfoToast === 'function') {
                    app.showInfoToast(tr('audition.playing_title', {}, '试听中'), tr('audition.playing_voice', { name: res.preview_name || selected.display_name }, `正在播放：${res.preview_name || selected.display_name}`));
                }
            } catch (e) {
                playBtn.disabled = false;
                playBtn.innerHTML = `<i class="ri-play-circle-line"></i> ${escapeHtml(tr('audition.play_selected_preview', {}, '播放选中试听'))}`;
                if (app && typeof app.showAlert === 'function') {
                    app.showAlert(tr('common.error', {}, '错误'), tr('mod.audition_failed_with_message', { message: e.message || e }, `试听失败: ${e.message || e}`), 'error');
                }
            }
        };

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) close();
        });
        if (closeBtn) closeBtn.addEventListener('click', close);
        if (playBtn) playBtn.addEventListener('click', playSelected);
        if (selectEl) selectEl.addEventListener('dblclick', playSelected);
        if (searchEl) searchEl.addEventListener('input', (e) => rebuild(e.target.value));
    }

    app.onAuditionScanUpdate = function (modId, payload) {
        try {
            const st = window.__auditionPickerState;
            if (!st || !payload) return;
            if (String(st.modId || '') !== String(modId || '')) return;
            if (typeof st.update === 'function') st.update(payload);
        } catch (e) {
            console.error('onAuditionScanUpdate error:', e);
        }
    };

    function ensureAuthorWorksModal() {
        let overlay = document.getElementById(AUTHOR_WORKS_MODAL_ID);
        if (overlay) return overlay;

        overlay = document.createElement('div');
        overlay.id = AUTHOR_WORKS_MODAL_ID;
        overlay.className = 'modal-overlay author-works-overlay';
        overlay.innerHTML = `
            <div class="modal-content author-works-modal">
                <div class="author-works-header">
                    <div class="author-works-title-wrap">
                        <span class="author-works-icon"><i class="ri-user-3-line"></i></span>
                        <div>
                            <h3 id="author-works-title">${escapeHtml(tr('mod.author_other_packs', {}, '作者其他语音包'))}</h3>
                            <p id="author-works-subtitle">${escapeHtml(tr('mod.author_works_subtitle', {}, '发现更多高质量语音包'))}</p>
                        </div>
                    </div>
                    <button class="mod-preview-close-btn" type="button" id="btn-author-works-close" title="${escapeHtml(tr('common.close', {}, '关闭'))}"><i class="ri-close-line"></i></button>
                </div>
                <div class="author-works-body">
                    <div class="author-works-grid" id="author-works-grid"></div>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeAuthorWorksModal();
        });
        const closeBtn = overlay.querySelector('#btn-author-works-close');
        if (closeBtn) closeBtn.addEventListener('click', closeAuthorWorksModal);
        return overlay;
    }

    function collectAuthorWorks(mod) {
        const currentVersion = normalizeVersion(mod?.version || '1.0');
        const currentDate = String(mod?.date || '').trim() || new Date().toISOString().split('T')[0];
        const currentSize = String(mod?.size_str || '<1 MB').trim() || '<1 MB';
        const currentAuthor = String(mod?.author || tr('mod.unknown_author', {}, '未知作者')).trim() || tr('mod.unknown_author', {}, '未知作者');
        const related = normalizeRelatedVoicepacks(mod?.related_voicepacks || []);
        return related.map((item, idx) => {
            const title = item.name || tr('mod.related_pack', { index: idx + 1 }, `关联语音包${idx + 1}`);
            const description = item.description || tr('mod.author_recommended_pack', {}, '作者推荐语音包');
            const link = item.link;
            const coverUrl = item.avatar_url || 'assets/card_image.png';
            return {
                title,
                description,
                cover_url: coverUrl,
                link,
                detail_mod: {
                    id: `author-related-${idx + 1}`,
                    title,
                    author: currentAuthor,
                    version: currentVersion,
                    date: currentDate,
                    size_str: currentSize,
                    tags: [],
                    language: [],
                    note: description,
                    full_desc: description,
                    version_note: [{ version: currentVersion, note: tr('mod.related_note', {}, '来自关联语音包配置。') }],
                    cover_url: coverUrl,
                    link_bilibili: link,
                    link_wtlive: '',
                    link_video: '',
                    link_qq_group: '',
                    link_liker: '',
                    link_feedback: '',
                    related_voicepacks: [],
                    capabilities: {}
                }
            };
        });
    }

    function renderAuthorWorksGrid(overlay, items) {
        const grid = overlay?.querySelector('#author-works-grid');
        if (!grid) return;

        if (!Array.isArray(items) || items.length === 0) {
            grid.innerHTML = `<div class="author-works-empty">${escapeHtml(tr('mod.no_author_works', {}, '暂无可展示的语音包'))}</div>`;
            return;
        }

        grid.innerHTML = items.map((item, idx) => {
            const title = escapeHtml(String(item?.title || tr('mod.untitled_voice_pack', {}, '未命名语音包')).trim() || tr('mod.untitled_voice_pack', {}, '未命名语音包'));
            const desc = escapeHtml(String(item?.description || tr('mod.no_description', {}, '暂无描述')).trim() || tr('mod.no_description', {}, '暂无描述'));
            const cover = escapeHtml(String(item?.cover_url || 'assets/card_image.png').trim() || 'assets/card_image.png');
            const canDetail = Boolean(item?.detail_mod || String(item?.link || '').trim());
            return `
                <article class="author-work-card" data-work-index="${idx}">
                    <img class="author-work-cover" src="${cover}" alt="${title}" onerror="this.src='assets/card_image.png'">
                    <div class="author-work-mask"></div>
                    <div class="author-work-info">
                        <h4>${title}</h4>
                        <p>${desc}</p>
                        <div class="author-work-actions">
                            <button class="author-work-btn light ${canDetail ? '' : 'disabled'}" type="button" data-work-action="detail">
                                ${escapeHtml(tr('mod.detail', {}, '详情'))} <i class="ri-external-link-line"></i>
                            </button>
                        </div>
                    </div>
                </article>
            `;
        }).join('');

        grid.querySelectorAll('.author-work-card').forEach((card) => {
            const idx = Number(card.getAttribute('data-work-index'));
            if (!Number.isFinite(idx)) return;
            const item = items[idx];
            card.querySelectorAll('[data-work-action]').forEach((btn) => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (btn.getAttribute('data-work-action') !== 'detail') return;
                    if (item?.detail_mod) {
                        closeAuthorWorksModal();
                        openPreview(item.detail_mod);
                        return;
                    }
                    const link = String(item?.link || '').trim();
                    if (link) openExternal(link);
                });
            });
        });
    }

    function openAuthorWorksModal(mod, prebuiltItems = null) {
        const app = getApp();
        const overlay = ensureAuthorWorksModal();
        const author = String(mod?.author || tr('mod.author_fallback', {}, '作者')).trim() || tr('mod.author_fallback', {}, '作者');
        const items = Array.isArray(prebuiltItems) ? prebuiltItems : collectAuthorWorks(mod);
        if (!items.length) {
            if (app && typeof app.showInfoToast === 'function') {
                app.showInfoToast(tr('common.info', {}, '提示'), tr('mod.author_no_related', {}, '作者未配置可关联语音包'));
            }
            return;
        }

        const iconEl = overlay.querySelector('.author-works-icon');
        if (iconEl) {
            const avatarUrl = String(mod?.author_avatar || FALLBACK_AVATAR).trim() || FALLBACK_AVATAR;
            iconEl.innerHTML = `<img src="${escapeHtml(avatarUrl)}" alt="avatar" style="width:100%;height:100%;object-fit:cover;border-radius:50%;display:block;" onerror="this.src='${escapeHtml(FALLBACK_AVATAR)}'">`;
        }
        const titleEl = overlay.querySelector('#author-works-title');
        if (titleEl) titleEl.textContent = tr('mod.author_other_title', { author }, `${author} 的其他作品`);

        renderAuthorWorksGrid(overlay, items);
        overlay.classList.remove('hiding');
        overlay.classList.add('show');
    }

    function closeAuthorWorksModal() {
        const app = getApp();
        if (app && typeof app.closeModal === 'function') {
            app.closeModal(AUTHOR_WORKS_MODAL_ID);
            return;
        }
        const overlay = document.getElementById(AUTHOR_WORKS_MODAL_ID);
        if (!overlay) return;
        overlay.classList.remove('show');
        overlay.classList.remove('hiding');
    }

    function bindLinkActions(overlay, mod) {
        const getLink = (action) => {
            if (action === 'bili') return String(mod?.link_bilibili || '').trim();
            if (action === 'qq') return String(mod?.link_qq_group || '').trim();
            if (action === 'wtlive') return String(mod?.link_wtlive || '').trim();
            if (action === 'liker') return String(mod?.link_liker || '').trim();
            if (action === 'feedback') return String(mod?.link_feedback || '').trim();
            return '';
        };

        overlay.querySelectorAll('[data-link-action]').forEach((btn) => {
            const action = btn.dataset.linkAction;
            if (action === 'otherworks') {
                const works = collectAuthorWorks(mod);
                const enabled = works.length > 0;
                btn.classList.toggle('disabled', !enabled);
                btn.disabled = !enabled;
                btn.innerHTML = `<i class="ri-music-2-line"></i> ${escapeHtml(tr('mod.other_packs_button', { count: works.length }, `查看作者其他语音包 (${works.length})`))}`;
                btn.onclick = () => {
                    if (!enabled) return;
                    openAuthorWorksModal(mod, works);
                };
                return;
            }
            const url = getLink(action);
            const enabled = Boolean(url);
            btn.classList.toggle('disabled', !enabled);
            btn.disabled = !enabled;
            btn.onclick = () => {
                if (!enabled) return;
                return openExternal(url);
            };
        });
    }

    function alignPreviewHeaderRows(overlay) {
        if (!overlay || !overlay.classList.contains('show')) return;
        const modalEl = overlay.querySelector('.mod-preview-modal-v2');
        const rightEl = overlay.querySelector('.mod-preview-right');
        const attrsHeaderEl = overlay.querySelector('.mod-preview-attrs h4');
        const versionHeaderEl = overlay.querySelector('.mod-preview-bottom-grid .mod-preview-card h4');
        if (!modalEl || !rightEl || !attrsHeaderEl || !versionHeaderEl) return;

        const rightRect = rightEl.getBoundingClientRect();
        const attrsRect = attrsHeaderEl.getBoundingClientRect();
        const versionCardEl = versionHeaderEl.closest('.mod-preview-card');
        if (!versionCardEl) return;
        const versionCardRect = versionCardEl.getBoundingClientRect();

        const rowGap = parseFloat(getComputedStyle(rightEl).rowGap || '0') || 0;
        const headerOffsetInCard = Math.max(0, versionHeaderEl.getBoundingClientRect().top - versionCardRect.top);

        let targetTopRow = attrsRect.top - rightRect.top - rowGap - headerOffsetInCard;
        if (!Number.isFinite(targetTopRow)) return;
        targetTopRow = Math.max(120, Math.min(700, targetTopRow));
        modalEl.style.setProperty('--mod-preview-right-top-row', `${Math.round(targetTopRow)}px`);
    }

    function schedulePreviewHeaderAlign(overlay) {
        if (!overlay) return;
        const run = () => alignPreviewHeaderRows(overlay);
        requestAnimationFrame(() => requestAnimationFrame(run));
        setTimeout(run, 60);
        setTimeout(run, 220);
    }

    function openPreview(mod) {
        const overlay = ensureModal();
        const title = String(mod?.title || tr('mod.untitled_voice_pack', {}, '未命名语音包'));
        const author = String(mod?.author || tr('mod.unknown_author', {}, '未知作者'));
        const date = String(mod?.date || tr('mod.unknown_date', {}, '未知日期'));
        const authorAvatar = String(mod?.author_avatar || FALLBACK_AVATAR).trim() || FALLBACK_AVATAR;
        const sizeText = String(mod?.size_str || tr('mod.unknown_size', {}, '未知大小'));
        const cover = String(mod?.cover_url || 'assets/card_image.png');
        const version = normalizeVersion(mod?.version);
        const desc = resolveDescription(mod);
        const versionNoteHtml = buildVersionNoteHtml(mod);
        const tagHtml = buildTagHtml(mod);
        const tagCount = normalizeUserTags(mod).length || buildCapabilityTags(mod).length;

        const titleEl = overlay.querySelector('#mod-preview-title');
        const versionEl = overlay.querySelector('#mod-preview-version');
        const authorEl = overlay.querySelector('#mod-preview-author');
        const dateEl = overlay.querySelector('#mod-preview-date');
        const authorAvatarEl = overlay.querySelector('#mod-preview-author-avatar');
        const coverEl = overlay.querySelector('#mod-preview-cover');
        const sizeEl = overlay.querySelector('#mod-preview-size');
        const langEl = overlay.querySelector('#mod-preview-lang');
        const tagCountEl = overlay.querySelector('#mod-preview-tag-count');
        const tagsEl = overlay.querySelector('#mod-preview-tags');
        const descEl = overlay.querySelector('#mod-preview-desc');
        const versionNoteEl = overlay.querySelector('#mod-preview-version-note');

        if (titleEl) titleEl.textContent = title;
        if (versionEl) versionEl.textContent = `v${version}`;
        if (authorEl) authorEl.textContent = author;
        if (dateEl) dateEl.textContent = date;
        if (authorAvatarEl) {
            authorAvatarEl.src = authorAvatar;
            authorAvatarEl.onerror = () => { authorAvatarEl.src = FALLBACK_AVATAR; };
        }
        if (coverEl) {
            coverEl.src = cover;
            coverEl.onload = () => schedulePreviewHeaderAlign(overlay);
            coverEl.onerror = () => schedulePreviewHeaderAlign(overlay);
        }
        if (sizeEl) sizeEl.textContent = sizeText;
        if (langEl) langEl.innerHTML = buildLangHtml(mod);
        if (tagCountEl) tagCountEl.textContent = tr('mod.tag_count_unit', { count: tagCount }, `${tagCount} 个`);
        if (tagsEl) tagsEl.innerHTML = tagHtml || `<span class="mod-preview-empty">${escapeHtml(tr('mod.no_tags', {}, '暂无标签'))}</span>`;
        if (descEl) descEl.textContent = desc;
        if (versionNoteEl) versionNoteEl.innerHTML = versionNoteHtml;

        bindFooterActions(overlay, mod);
        bindLinkActions(overlay, mod);

        overlay.classList.remove('hiding');
        void overlay.offsetWidth; // 强制触发重排，确保渐入动画完美播放
        overlay.classList.add('show');
        schedulePreviewHeaderAlign(overlay);
    }

    function closePreview() {
        closeAuthorWorksModal();
        const app = getApp();
        if (app && typeof app.closeModal === 'function') {
            app.closeModal(MODAL_ID);
            return;
        }
        const el = document.getElementById(MODAL_ID);
        if (!el) return;
        el.classList.remove('show');
        el.classList.remove('hiding');
    }

    function shouldIgnoreClick(target) {
        return !!target.closest(
            '.mod-actions-col, .action-icon, .action-btn-load, .mod-copy-action, .mod-note, button, a'
        );
    }

    function bindCardPreviewClick() {
        const list = document.getElementById(LIST_ID);
        if (!list || list.dataset.previewBound === '1') return;
        list.dataset.previewBound = '1';

        list.addEventListener('click', (e) => {
            if (e.button !== 0) return;
            if (shouldIgnoreClick(e.target)) return;
            const card = e.target.closest('.mod-card');
            if (!card || !list.contains(card)) return;

            const mod = findModById(card.dataset.id || '');
            if (!mod) return;
            openPreview(mod);
        });
    }

    function init() {
        const app = getApp();
        if (!app) {
            setTimeout(init, 60);
            return;
        }

        app.openModPreview = (modOrId) => {
            const mod = (typeof modOrId === 'object') ? modOrId : findModById(modOrId);
            if (!mod) return;
            openPreview(mod);
        };
        app.closeModPreview = closePreview;

        bindCardPreviewClick();
        if (!app._cardPreviewObserver) {
            const observer = new MutationObserver(bindCardPreviewClick);
            observer.observe(document.body, { childList: true, subtree: true });
            app._cardPreviewObserver = observer;
        }

        document.addEventListener('click', (e) => {
            const wrapper = document.getElementById('theme-select-wrapper');
            if (wrapper && !wrapper.contains(e.target)) {
                wrapper.classList.remove('active');
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
})();
