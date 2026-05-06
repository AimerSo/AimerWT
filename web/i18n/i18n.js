(function () {
    const DEFAULT_LOCALE = "zh_cn";
    const SUPPORTED_LOCALES = ["zh_cn", "en_us"];

    function normalize_locale(locale) {
        return SUPPORTED_LOCALES.includes(locale) ? locale : DEFAULT_LOCALE;
    }

    window.I18N = {
        currentLocale: DEFAULT_LOCALE,
        _messages: {},

        register(locale, messages) {
            const normalized = normalize_locale(locale);
            this._messages[normalized] = { ...(this._messages[normalized] || {}), ...(messages || {}) };
        },

        t(key, params) {
            const dict = this._messages[this.currentLocale] || {};
            const fallback = this._messages[DEFAULT_LOCALE] || {};
            let text = dict[key];
            if (text === undefined) text = fallback[key];
            if (text === undefined) return key;
            if (params && typeof text === "string") {
                Object.keys(params).forEach((name) => {
                    text = text.replace(new RegExp("\\{" + name + "\\}", "g"), String(params[name]));
                });
            }
            return text;
        },

        applyToDOM(root) {
            const scope = root || document;
            if (!scope || typeof scope.querySelectorAll !== "function") return;

            scope.querySelectorAll("[data-i18n]").forEach((el) => {
                const key = el.getAttribute("data-i18n");
                if (key) el.textContent = this.t(key);
            });

            scope.querySelectorAll("[data-i18n-html]").forEach((el) => {
                const key = el.getAttribute("data-i18n-html");
                if (key) el.innerHTML = this.t(key);
            });

            scope.querySelectorAll("[data-i18n-title]").forEach((el) => {
                const key = el.getAttribute("data-i18n-title");
                if (key) el.title = this.t(key);
            });

            scope.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
                const key = el.getAttribute("data-i18n-placeholder");
                if (key) el.placeholder = this.t(key);
            });
        },

        setLocale(locale) {
            const normalized = normalize_locale(locale);
            this.currentLocale = normalized;
            document.documentElement.lang = normalized === "en_us" ? "en-US" : "zh-CN";
            this.applyToDOM();
            return normalized;
        },

        getLocaleName(locale) {
            return normalize_locale(locale) === "en_us" ? "English" : "简体中文";
        },

        isOnlineFeatureAvailable() {
            return this.currentLocale === DEFAULT_LOCALE;
        }
    };
})();
