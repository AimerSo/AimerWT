Object.assign(app, {
    _audience_rules: {},
    _audience_options: { versions: [], tags: [] },

    normalizeAudienceValues(values) {
        return [...new Set((Array.isArray(values) ? values : [])
            .map((value) => String(value || '').trim())
            .filter(Boolean))];
    },

    normalizeAudienceTargeting(targeting, legacy_scope = 'all') {
        if (targeting && Array.isArray(targeting.rules) && targeting.rules.length) {
            return {
                rules: targeting.rules.map((rule) => ({
                    versions: this.normalizeAudienceValues(rule?.versions),
                    tags: this.normalizeAudienceValues(rule?.tags),
                    special_groups: this.normalizeAudienceValues(rule?.special_groups)
                        .filter((group) => ['starred', 'admin'].includes(group))
                }))
            };
        }

        const scope = String(legacy_scope || 'all').trim();
        if (!scope || scope === 'all') return { rules: [{}] };
        if (scope === 'star') return { rules: [{ special_groups: ['starred'] }] };
        if (scope === 'admin') return { rules: [{ special_groups: ['admin'] }] };
        if (scope.startsWith('tag:')) return { rules: [{ tags: [scope.slice(4)] }] };
        return { rules: [{ versions: [scope] }] };
    },

    setAudienceOptions(data) {
        const versions = data?.version_stats || data?.version_options || [];
        const tags = data?.tag_options || [];
        this._audience_options = {
            versions: versions
                .map((item) => ({
                    value: String(item?.name || '').trim(),
                    label: `${String(item?.name || '').trim()}（${Number(item?.value || 0)} 人）`
                }))
                .filter((item) => item.value),
            tags: tags
                .map((item) => ({
                    value: String(item?.name || '').trim(),
                    label: String(item?.display_name || item?.name || '').trim()
                }))
                .filter((item) => item.value)
        };
        Object.keys(this._audience_rules).forEach((editor_id) => this.renderAudienceRuleEditor(editor_id));
    },

    setAudienceTargeting(editor_id, targeting, legacy_scope = 'all') {
        const normalized = this.normalizeAudienceTargeting(targeting, legacy_scope);
        this._audience_rules[editor_id] = normalized.rules.length ? normalized.rules : [{}];
        this.renderAudienceRuleEditor(editor_id);
    },

    readAudienceTargeting(editor_id) {
        const rules = this._audience_rules[editor_id] || [{}];
        return {
            rules: rules.map((rule) => ({
                versions: this.normalizeAudienceValues(rule.versions),
                tags: this.normalizeAudienceValues(rule.tags),
                special_groups: this.normalizeAudienceValues(rule.special_groups)
                    .filter((group) => ['starred', 'admin'].includes(group))
            }))
        };
    },

    legacyScopeForTargeting(targeting) {
        const rules = Array.isArray(targeting?.rules) ? targeting.rules : [];
        if (rules.length !== 1) return 'all';
        const rule = rules[0] || {};
        const versions = this.normalizeAudienceValues(rule.versions);
        const tags = this.normalizeAudienceValues(rule.tags);
        const groups = this.normalizeAudienceValues(rule.special_groups);
        const used_fields = [versions.length > 0, tags.length > 0, groups.length > 0].filter(Boolean).length;
        if (used_fields === 0) return 'all';
        if (used_fields !== 1) return 'all';
        if (versions.length === 1) return versions[0];
        if (tags.length === 1) return `tag:${tags[0]}`;
        if (groups.length === 1) return groups[0] === 'starred' ? 'star' : groups[0];
        return 'all';
    },

    audienceTargetingSummary(targeting) {
        const rules = Array.isArray(targeting?.rules) && targeting.rules.length ? targeting.rules : [{}];
        const group_summaries = rules.map((rule) => {
            const conditions = [];
            const versions = this.normalizeAudienceValues(rule?.versions);
            const tags = this.normalizeAudienceValues(rule?.tags);
            const groups = this.normalizeAudienceValues(rule?.special_groups);
            if (versions.length) conditions.push(`版本 ${versions.join('/')}`);
            if (tags.length) conditions.push(`用户组 ${tags.join('/')}`);
            if (groups.length) {
                const labels = groups.map((group) => group === 'starred' ? '星标用户' : group === 'admin' ? '管理员' : '').filter(Boolean);
                if (labels.length) conditions.push(labels.join('/'));
            }
            return conditions.length ? conditions.join(' 且 ') : '全部用户';
        });
        return group_summaries.includes('全部用户') ? '全部用户' : group_summaries.join('；或 ');
    },

    audienceRuleEditorMarkup(editor_id) {
        return `<div id="${this.escapeHtmlSafe(editor_id)}" class="audience-rule-editor"></div>`;
    },

    renderAudienceRuleEditor(editor_id) {
        const container = document.getElementById(editor_id);
        if (!container) return;
        const targeting = this.readAudienceTargeting(editor_id);
        const escape_value = (value) => this.escapeHtmlSafe(String(value || ''));
        const cards = targeting.rules.map((rule, rule_index) => {
            const selected_versions = new Set(rule.versions || []);
            const selected_tags = new Set(rule.tags || []);
            const version_options = [...this._audience_options.versions];
            selected_versions.forEach((value) => {
                if (!version_options.some((item) => item.value === value)) version_options.push({ value, label: value });
            });
            const tag_options = [...this._audience_options.tags];
            selected_tags.forEach((value) => {
                if (!tag_options.some((item) => item.value === value)) tag_options.push({ value, label: value });
            });
            const version_html = version_options.map((item) => (
                `<option value="${escape_value(item.value)}" ${selected_versions.has(item.value) ? 'selected' : ''}>${escape_value(item.label)}</option>`
            )).join('');
            const tag_html = tag_options.map((item) => (
                `<option value="${escape_value(item.value)}" ${selected_tags.has(item.value) ? 'selected' : ''}>${escape_value(item.label)}</option>`
            )).join('');
            const special_groups = new Set(rule.special_groups || []);
            return `
                <div class="audience-rule-card" data-audience-rule-index="${rule_index}">
                    <div class="audience-rule-card-header">
                        <span>规则组 ${rule_index + 1}</span>
                        <button type="button" class="btn audience-rule-remove" onclick="app.deleteAudienceRule('${editor_id}', ${rule_index})">${targeting.rules.length === 1 ? '清空条件' : '删除'}</button>
                    </div>
                    <div class="audience-rule-grid">
                        <label>
                            <span>客户端版本（可多选）</span>
                            <select class="select" multiple size="${Math.min(Math.max(version_options.length, 2), 4)}" data-audience-field="versions" onchange="app.updateAudienceRuleFromEditor('${editor_id}', ${rule_index})">${version_html}</select>
                        </label>
                        <label>
                            <span>用户组 / 标签（可多选）</span>
                            <select class="select" multiple size="${Math.min(Math.max(tag_options.length, 2), 4)}" data-audience-field="tags" onchange="app.updateAudienceRuleFromEditor('${editor_id}', ${rule_index})">${tag_html}</select>
                        </label>
                    </div>
                    <div class="audience-rule-special">
                        <label><input type="checkbox" data-special-group="starred" ${special_groups.has('starred') ? 'checked' : ''} onchange="app.updateAudienceRuleFromEditor('${editor_id}', ${rule_index})"> 星标用户</label>
                        <label><input type="checkbox" data-special-group="admin" ${special_groups.has('admin') ? 'checked' : ''} onchange="app.updateAudienceRuleFromEditor('${editor_id}', ${rule_index})"> 管理员</label>
                    </div>
                </div>`;
        }).join('');

        container.innerHTML = `${cards}
            <div class="audience-rule-footer">
                <button type="button" class="btn" onclick="app.addAudienceRule('${editor_id}')">+ 添加规则组（或）</button>
                <span class="audience-rule-summary">${escape_value(this.audienceTargetingSummary(targeting))}</span>
            </div>`;
    },

    updateAudienceRuleFromEditor(editor_id, rule_index) {
        const container = document.getElementById(editor_id);
        const card = container?.querySelector(`[data-audience-rule-index="${rule_index}"]`);
        if (!card) return;
        const selected_values = (field) => Array.from(card.querySelector(`[data-audience-field="${field}"]`)?.selectedOptions || [])
            .map((option) => option.value);
        const special_groups = Array.from(card.querySelectorAll('[data-special-group]:checked'))
            .map((input) => input.dataset.specialGroup);
        const rules = this._audience_rules[editor_id] || [{}];
        rules[rule_index] = {
            versions: selected_values('versions'),
            tags: selected_values('tags'),
            special_groups
        };
        this._audience_rules[editor_id] = rules;
        this.renderAudienceRuleEditor(editor_id);
    },

    addAudienceRule(editor_id) {
        const rules = this._audience_rules[editor_id] || [{}];
        rules.push({});
        this._audience_rules[editor_id] = rules;
        this.renderAudienceRuleEditor(editor_id);
    },

    deleteAudienceRule(editor_id, rule_index) {
        const rules = this._audience_rules[editor_id] || [{}];
        if (rules.length === 1) {
            this._audience_rules[editor_id] = [{}];
        } else {
            rules.splice(rule_index, 1);
            this._audience_rules[editor_id] = rules;
        }
        this.renderAudienceRuleEditor(editor_id);
    }
});
