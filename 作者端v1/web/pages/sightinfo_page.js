window.AuthorPageModules = window.AuthorPageModules || {};

const SIGHT_CATEGORY_IDS = ["historical", "competitive", "fun"];
const SIGHT_UI_STORAGE_KEY = "aimerwt_author_sightinfo_ui_v1";
const SIGHT_FILE_PAGE_SIZE = 30;
const SIGHT_ANALYSIS_CONFIDENCE_LABELS = {
    high: "高置信度",
    medium: "中置信度",
    low: "低置信度"
};
const SIGHT_ANALYSIS_FIELD_LABELS = {
    distance_correction: "距离修正",
    apply_correction_to_gun: "自动抬炮",
    has_variable_range: "可变标尺",
    range_min: "最小距离",
    range_max: "最大距离",
    suspected_mask: "疑似遮罩",
    match_exp_class_status: "兼容匹配块",
    tail_comment: "尾部注释",
    tail_comment_confidence: "注释判断"
};
const SIGHT_ANALYSIS_REASON_LABELS = {
    distance_correction_defaulted: "距离修正采用默认值",
    apply_correction_to_gun_defaulted: "自动抬炮采用默认值",
    compatibility_unreadable: "兼容匹配块不可确认",
    no_explicit_features: "未找到可确认的显式特征",
    legacy_analysis_cache: "旧版缓存缺少置信度信息"
};
const SIGHT_ANALYSIS_STATUS_LABELS = {
    present_with_entries: "存在且含匹配项",
    present_empty: "存在但为空",
    missing: "未声明",
    unknown_unreadable: "无法读取确认",
    source_hint: "可能含来源提示",
    technical_note: "技术性注释",
    unknown: "无法判断"
};

const SIGHT_FILE_RAIL_LIMIT = 200;
const SIGHT_PREVIEW_CARD_WIDTH = 344;
const SIGHT_PREVIEW_CARD_HEIGHT = 252;
const SIGHT_PREVIEW_SIDEBAR_SCALE = 0.82;
const SIGHT_PREVIEW_DETAIL_SCALE = 1.45;
const SIGHT_AMMO_OPTIONS = [
    ["", "未指定"],
    ["apfsds", "APFSDS"], ["heat", "HEAT"], ["heatfs", "HEAT-FS"],
    ["aphe", "APHE"], ["he", "HE"], ["atgm", "ATGM"], ["apds", "APDS"],
    ["hesh", "HESH"], ["smoke", "Smoke"], ["universal", "Universal"],
    ["ap", "AP"], ["apbc", "APBC"], ["apc", "APC"], ["apcbc", "APCBC"],
    ["aphebc", "APHEBC"], ["aphec", "APHEC"], ["aphecbc", "APHECBC"],
    ["sapcbc", "SAPCBC"], ["apcr", "APCR"], ["heat_mp", "HEAT-MP"],
    ["he_or", "HE-OR"], ["heat_grenade", "HEAT Grenade"], ["he_tf", "HE-TF"],
    ["he_vt", "HE-VT"], ["shrapnel", "Shrapnel"], ["he_grenade", "HE Grenade"],
    ["rocket", "Rocket"], ["vog", "VOG"], ["atgm_tandem", "ATGM Tandem"],
    ["atgm_he", "ATGM-HE"], ["atgm_top_attack", "ATGM Top Attack"],
    ["atgm_vt", "ATGM-VT"], ["sam", "SAM"]
];

window.AuthorPageModules.sightinfo = {
    _initialized: false,
    _app: null,
    _projects: [],
    _workspace: null,
    _vehicle_catalog: [],
    _project_name: "",
    _draft: null,
    _baseline_json: "",
    _dirty: false,
    _loading: false,
    _active_tab: "basic",
    _selected_file_index: -1,
    _project_query: "",
    _file_query: "",
    _file_page: 1,
    _scan: null,
    _cover_preview: "",
    _report: null,
    _validation_stale: false,
    _analysis_results: {},
    _ui_prefs: {},
    _preview_resize_observer: null,
    _preview_focus_return: null,
    _preview_kind: "single",
    _preview_tooltip_card: null,
    _preview_tooltip_card_title: "",

    init(app) {
        this._app = app;
        this._load_ui_prefs();
        this._active_tab = this._ui_prefs.active_tab || "basic";
        this._project_query = this._ui_prefs.project_query || "";
        this._bind_ui();
    },

    onEnter() {
        this._bind_ui();
        this._enter_page();
    },

    async _enter_page() {
        if (!this._workspace) await this._load_workspace();
        await this._refresh_projects(false);
        if (!this._project_name && this._ui_prefs.last_project) {
            const exists = this._projects.some((item) => item.project_name === this._ui_prefs.last_project);
            if (exists) await this._load_project(this._ui_prefs.last_project, false);
        }
    },

    _bind_ui() {
        if (this._initialized) return;
        const root = document.getElementById("sightinfo-shell");
        if (!root) return;
        const preview_tooltip = document.getElementById("sight-preview-tooltip");
        if (preview_tooltip && preview_tooltip.parentElement !== document.body) {
            document.body.appendChild(preview_tooltip);
        }

        this._bind_click("btn-sight-new", () => this._create_project());
        this._bind_click("btn-sight-import-folder", () => this._import_project("folder"));
        this._bind_click("btn-sight-import-blk", () => this._import_project("blk"));
        this._bind_click("btn-sight-import-zip", () => this._import_project("zip"));
        this._bind_click("btn-sight-refresh-projects", () => this._refresh_projects(true));
        this._bind_click("btn-sight-open-project", () => this._open_project_folder());
        this._bind_click("btn-sight-open-exports", () => this._open_export_folder());
        this._bind_click("btn-sight-rename", () => this._rename_project());
        this._bind_click("btn-sight-delete", () => this._delete_project());
        this._bind_click("btn-sight-save", () => this._save_project());
        this._bind_click("btn-sight-rescan", () => this._rescan_project());
        this._bind_click("btn-sight-validate", () => this._validate_project());
        this._bind_click("btn-sight-export", () => this._export_project());
        this._bind_click("btn-sight-analyze-all", () => this._analyze_files([]));
        this._bind_click("btn-sight-apply-batch", () => this._apply_file_batch());
        this._bind_click("btn-sight-add-group", () => this._add_group());
        this._bind_click("btn-sight-select-cover", () => this._select_cover());
        this._bind_click("btn-sight-clear-cover", () => this._clear_cover());

        const project_search = document.getElementById("sight-project-search");
        if (project_search) {
            project_search.value = this._project_query;
            project_search.addEventListener("input", (event) => {
                this._project_query = String(event.target.value || "").trim();
                this._ui_prefs.project_query = this._project_query;
                this._save_ui_prefs();
                this._refresh_projects(false);
            });
        }

        const file_search = document.getElementById("sight-file-search");
        if (file_search) {
            file_search.addEventListener("input", (event) => {
                this._file_query = String(event.target.value || "").trim().toLowerCase();
                this._file_page = 1;
                this._render_file_list();
                this._render_file_editor();
            });
        }

        const select_all = document.getElementById("sight-select-all-files");
        if (select_all) {
            select_all.addEventListener("change", () => {
                root.querySelectorAll("[data-sight-batch-select]").forEach((input) => {
                    input.checked = select_all.checked;
                });
            });
        }

        root.addEventListener("click", (event) => this._handle_root_click(event));
        root.addEventListener("keydown", (event) => {
            const source_card = event.target.closest?.("[data-sight-preview-open]");
            if (!source_card || !(event.key === "Enter" || event.key === " ")) return;
            event.preventDefault();
            this._open_preview_page(source_card.dataset.sightPreviewOpen || "single", source_card);
        });
        root.addEventListener("mouseover", (event) => {
            const anchor = event.target.closest?.("[data-sight-desc]");
            if (!anchor || anchor.contains(event.relatedTarget)) return;
            const text = String(anchor.dataset.sightDesc || "").trim();
            if (text) this._show_preview_tooltip(anchor, text);
        });
        root.addEventListener("mouseout", (event) => {
            const anchor = event.target.closest?.("[data-sight-desc]");
            if (anchor && !anchor.contains(event.relatedTarget)) this._hide_preview_tooltip();
        });
        root.addEventListener("focusin", (event) => {
            const anchor = event.target.closest?.("[data-sight-desc]");
            const text = String(anchor?.dataset.sightDesc || "").trim();
            if (anchor && text) this._show_preview_tooltip(anchor, text, event.target);
        });
        root.addEventListener("focusout", (event) => {
            if (event.target.closest?.("[data-sight-desc]")) this._hide_preview_tooltip();
        });
        root.addEventListener("input", (event) => this._handle_editor_event(event, "input"));
        root.addEventListener("change", (event) => this._handle_editor_event(event, "change"));

        const preview_viewports = root.querySelectorAll("[data-sight-preview-viewport]");
        if (preview_viewports.length && typeof ResizeObserver === "function") {
            this._preview_resize_observer = new ResizeObserver(() => this._fit_card_previews());
            preview_viewports.forEach((viewport) => this._preview_resize_observer.observe(viewport));
        }
        window.addEventListener("resize", () => this._fit_card_previews());
        window.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && !document.getElementById("sight-preview-page")?.hidden) this._close_preview_page();
        });

        window.addEventListener("beforeunload", (event) => {
            if (!this._dirty) return;
            event.preventDefault();
            event.returnValue = "";
        });

        this._set_active_tab(this._active_tab, false);
        this._render_empty_state();
        this._initialized = true;
    },

    _bind_click(id, handler) {
        const button = document.getElementById(id);
        if (!button) return;
        button.addEventListener("click", handler);
    },

    async _handle_root_click(event) {
        const target = event.target;
        const close_action = target.closest("[data-sight-preview-close]");
        if (close_action) {
            this._close_preview_page();
            return;
        }

        const source_card = target.closest("[data-sight-preview-open]");
        if (source_card) {
            this._open_preview_page(source_card.dataset.sightPreviewOpen || "single", source_card);
            return;
        }

        const empty_action = target.closest("[data-sight-empty-action]");
        if (empty_action) {
            const action = empty_action.dataset.sightEmptyAction;
            if (action === "new") await this._create_project();
            if (action === "folder") await this._import_project("folder");
            if (action === "blk") await this._import_project("blk");
            if (action === "zip") await this._import_project("zip");
            return;
        }

        const tab = target.closest("[data-sight-tab]");
        if (tab) {
            this._set_active_tab(tab.dataset.sightTab || "basic");
            return;
        }

        const project_item = target.closest("[data-sight-project]");
        if (project_item) {
            await this._request_project_switch(project_item.dataset.sightProject || "");
            return;
        }

        const file_item = target.closest("[data-sight-file-index]");
        if (file_item && file_item.closest("#sight-file-list")) {
            this._selected_file_index = Number(file_item.dataset.sightFileIndex);
            const filtered_index = this._filtered_file_rows().findIndex((row) => row.index === this._selected_file_index);
            this._file_page = Math.floor(Math.max(0, filtered_index) / SIGHT_FILE_PAGE_SIZE) + 1;
            this._set_active_tab("files");
            this._render_file_list();
            this._render_file_editor();
            requestAnimationFrame(() => {
                document.querySelector(`[data-sight-file-card="${this._selected_file_index}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
            });
            return;
        }

        const page_action = target.closest("[data-sight-file-page]");
        if (page_action) {
            this._file_page = Math.max(1, Number(page_action.dataset.sightFilePage || 1));
            this._render_file_editor();
            return;
        }

        const file_action = target.closest("[data-sight-file-action]");
        if (file_action) {
            const index = Number(file_action.dataset.fileIndex);
            if (file_action.dataset.sightFileAction === "analyze") {
                const row = this._draft?.files?.[index];
                if (row) await this._analyze_files([row.output_path]);
            }
            if (file_action.dataset.sightFileAction === "write_blk") {
                await this._write_blk(index);
            }
            return;
        }

        const group_action = target.closest("[data-sight-group-action]");
        if (group_action) {
            const index = Number(group_action.dataset.groupIndex);
            const action = group_action.dataset.sightGroupAction;
            if (action === "delete") await this._delete_group(index);
            if (action === "up") this._move_group(index, -1);
            if (action === "down") this._move_group(index, 1);
            return;
        }

        const vehicle_action = target.closest("[data-sight-vehicle-action]");
        if (vehicle_action) {
            const scope = vehicle_action.dataset.vehicleScope || "package";
            const index = Number(vehicle_action.dataset.vehicleIndex ?? -1);
            if (vehicle_action.dataset.sightVehicleAction === "match_legacy") {
                this._match_legacy_vehicles(scope, index);
            }
            if (vehicle_action.dataset.sightVehicleAction === "apply_package_to_files") {
                this._apply_package_recommendation_to_files();
            }
            return;
        }

        const issue = target.closest("[data-sight-issue-index]");
        if (issue) this._focus_report_issue(issue.dataset.issueType, Number(issue.dataset.sightIssueIndex));
    },

    _handle_editor_event(event, event_type) {
        if (!this._draft) return;
        const target = event.target;
        const is_discrete = target.matches("select, input[type='checkbox'], input[type='radio']");
        if ((is_discrete && event_type !== "change") || (!is_discrete && event_type !== "input")) return;

        if (target.matches("[data-sight-recommendation-mode], [data-sight-vehicle-field], [data-sight-vehicle-list-field], [data-sight-legacy-vehicles]")) {
            const scope = target.dataset.vehicleScope || "package";
            const index = Number(target.dataset.vehicleIndex ?? -1);
            const recommendation = this._recommendation_target(scope, index);
            if (!recommendation) return;
            if (target.matches("[data-sight-recommendation-mode]")) {
                recommendation.recommended_apply_mode = target.value;
                if (target.value === "all_tanks") {
                    recommendation.primary_vehicle_id = "";
                    recommendation.compatible_vehicle_ids = [];
                }
            } else if (target.matches("[data-sight-vehicle-field]")) {
                recommendation[target.dataset.sightVehicleField] = String(target.value || "").trim().toLowerCase();
            } else if (target.matches("[data-sight-vehicle-list-field]")) {
                recommendation[target.dataset.sightVehicleListField] = this._split_list(target.value).map((value) => value.toLowerCase());
            } else {
                recommendation.recommended_vehicles = this._split_list(target.value);
            }
            this._mark_dirty();
            if (target.matches("[data-sight-recommendation-mode]")) {
                this._render_recommendation_scope(scope);
            }
            return;
        }

        if (target.matches("[data-sight-optional-bool-field]")) {
            const raw_value = String(target.value || "");
            const value = raw_value === "true" ? true : (raw_value === "false" ? false : null);
            const field_path = target.dataset.sightOptionalBoolField;
            this._set_by_path(this._draft, field_path, value);
            this._mark_dirty();
            this._after_general_field_change(field_path);
            return;
        }

        if (target.matches("[data-sight-field]")) {
            const value = target.type === "checkbox" ? target.checked : target.value;
            this._set_by_path(this._draft, target.dataset.sightField, value);
            this._mark_dirty();
            this._after_general_field_change(target.dataset.sightField);
            return;
        }

        if (target.matches("[data-sight-list-field]")) {
            this._set_by_path(this._draft, target.dataset.sightListField, this._split_list(target.value));
            if (target.dataset.sightListField === "package.target_resolutions") {
                this._draft.package.target_resolution = this._draft.package.target_resolutions[0] || "";
            }
            this._mark_dirty();
            this._after_general_field_change(target.dataset.sightListField);
            return;
        }

        if (target.id === "sight-custom-tags" || target.matches("[data-sight-category]")) {
            this._sync_tags_from_ui();
            this._mark_dirty();
            this._render_card_preview();
            return;
        }

        if (target.matches("[data-sight-file-field]")) {
            this._update_file_field(target);
            return;
        }

        if (target.matches("[data-sight-file-list-field]")) {
            const index = Number(target.dataset.fileIndex);
            const row = this._draft.files[index];
            if (!row) return;
            row[target.dataset.sightFileListField] = this._split_list(target.value);
            this._mark_dirty();
            return;
        }

        if (target.matches("[data-sight-group-field]")) {
            const index = Number(target.dataset.groupIndex);
            const row = this._draft.groups[index];
            if (!row) return;
            const field = target.dataset.sightGroupField;
            row[field] = target.type === "checkbox" ? target.checked : target.value;
            this._mark_dirty();
            if (["name", "group_id"].includes(field)) this._render_assignment_editor();
            return;
        }

        if (target.matches("[data-sight-group-list-field]")) {
            const index = Number(target.dataset.groupIndex);
            const row = this._draft.groups[index];
            if (!row) return;
            row[target.dataset.sightGroupListField] = this._split_list(target.value);
            this._mark_dirty();
            return;
        }

        if (target.matches("[data-sight-assignment]")) {
            this._assign_file_group(target.dataset.outputPath || "", target.value || "");
            return;
        }

        if (target.id === "sight-migration-confirmed") {
            this._draft.import_meta.migration_confirmed = target.checked;
            this._mark_dirty();
        }
    },

    _after_general_field_change(path) {
        if (path.startsWith("package.")) {
            this._sync_current_project_row();
            this._render_project_header();
            this._render_card_preview();
        }
        if (path === "export.archive_name") this._render_project_header();
    },

    _update_file_field(target) {
        const index = Number(target.dataset.fileIndex);
        const row = this._draft.files[index];
        if (!row) return;
        const field = target.dataset.sightFileField;
        const old_output_path = String(row.output_path || "");
        row[field] = target.type === "checkbox" ? target.checked : target.value;

        if (field === "output_path" && old_output_path !== row.output_path) {
            this._draft.groups.forEach((group) => {
                group.files = (group.files || []).map((path) => path === old_output_path ? row.output_path : path);
            });
            this._selected_file_index = index;
            this._render_file_list();
            this._render_assignment_editor();
        }
        if (field === "display_name" || field === "include") this._render_file_list();
        if (field === "include") {
            this._sync_current_project_row();
            this._render_project_header();
            this._render_assignment_editor();
            this._render_summary();
            this._render_card_preview();
        }
        this._mark_dirty();
    },

    async _load_workspace() {
        const response = await this._api_call("get_sight_workspace");
        if (!response?.success) return;
        this._workspace = response.data || {};
        this._vehicle_catalog = Array.isArray(this._workspace.vehicle_catalog)
            ? this._workspace.vehicle_catalog
            : [];
        this._render_vehicle_catalog();
        this._set_text("sight-workspace-library", this._workspace.library_dir || "-");
        this._set_text("sight-workspace-export", this._workspace.export_dir || "-");
        this._set_text("sight-schema-version", this._workspace.schema_version ?? "-");
        this._set_text("sight-meta-version", this._workspace.meta_version ?? "-");
    },

    async _refresh_projects(manual = false) {
        if (manual) this._app.notifyToast("info", "正在刷新炮镜项目…");
        const response = await this._api_call("list_sight_projects", this._project_query || "");
        if (!response?.success) {
            this._projects = [];
            this._render_project_list(response?.msg || "读取炮镜项目失败");
            if (manual) this._notify_api_error(response, "读取炮镜项目失败");
            return;
        }
        this._projects = Array.isArray(response.data?.projects) ? response.data.projects : [];
        this._render_project_list();
        if (manual) this._app.notifyToast("success", `已读取 ${this._projects.length} 个炮镜项目`);
    },

    async _request_project_switch(project_name) {
        if (!project_name || project_name === this._project_name || this._loading) return;
        if (!await this._confirm_leave_dirty(`切换到“${project_name}”`)) return;
        await this._load_project(project_name, true);
    },

    async _load_project(project_name, show_feedback = true) {
        await this._with_loading("正在载入炮镜项目…", async () => {
            const response = await this._api_call("load_sight_project", project_name);
            if (!response?.success) {
                this._notify_api_error(response, "载入炮镜项目失败");
                return;
            }
            this._apply_project_data(response.data, true);
            this._ui_prefs.last_project = project_name;
            this._save_ui_prefs();
            if (show_feedback) this._app.notifyToast("success", `已载入：${project_name}`);
        });
    },

    async _create_project() {
        if (!await this._confirm_leave_dirty("新建炮镜项目")) return;
        const dialog = await this._app.showInputDialog({
            title: "新建炮镜项目",
            message: "项目名称只用于作者端工作区，也会作为默认 ZIP 名称。",
            inputLabel: "项目文件夹名称",
            placeholder: "例如：Aimer 历史炮镜包",
            confirmText: "创建项目"
        });
        if (!dialog?.ok) return;
        const project_name = String(dialog.value || "").trim();
        if (!project_name) {
            this._app.notifyToast("warn", "请输入项目名称");
            return;
        }
        await this._with_loading("正在创建炮镜项目…", async () => {
            const response = await this._api_call("create_sight_project", project_name, this._profile_defaults());
            if (!response?.success) {
                this._notify_api_error(response, "创建炮镜项目失败");
                return;
            }
            this._apply_project_data(response.data, true);
            this._ui_prefs.last_project = response.data?.project_name || project_name;
            this._save_ui_prefs();
            await this._refresh_projects(false);
            this._app.notifyToast("success", response.msg || "炮镜项目已创建");
        });
    },

    async _import_project(source_type) {
        if (!await this._confirm_leave_dirty("导入另一个炮镜项目")) return;
        const loading_text = source_type === "zip"
            ? "正在导入炮镜 ZIP…"
            : source_type === "blk"
                ? "正在导入单个炮镜 BLK…"
                : "正在导入炮镜文件夹…";
        await this._with_loading(loading_text, async () => {
            const response = await this._api_call("import_sight_project", source_type, "", this._profile_defaults());
            if (!response?.success) {
                if (response?.data?.cancelled) return;
                this._notify_api_error(response, "导入炮镜项目失败");
                return;
            }
            this._apply_project_data(response.data, true);
            this._ui_prefs.last_project = response.data?.project_name || "";
            this._save_ui_prefs();
            await this._refresh_projects(false);
            const warning_count = Array.isArray(response.warnings) ? response.warnings.length : 0;
            this._app.notifyToast(warning_count ? "warn" : "success", warning_count ? `导入完成，包含 ${warning_count} 项需要确认的信息` : (response.msg || "炮镜项目已导入"));
        });
    },

    async _write_blk(index) {
        const initial_row = this._draft?.files?.[index];
        if (!this._project_name || !initial_row || initial_row.missing_source) return;
        const file_id = String(initial_row.file_id || "");
        if (!file_id) {
            this._app.notifyToast("warn", "当前文件缺少稳定标识，请先重新扫描并保存项目");
            return;
        }
        if (this._dirty && !await this._save_project(false)) return;

        const row = (this._draft?.files || []).find((item) => String(item.file_id || "") === file_id);
        if (!row) return;
        const choices = [];
        if (String(row.origin_path || "").trim()) {
            choices.push({
                value: "save_original",
                title: "保存到原文件",
                description: "只替换原 BLK 尾部的 AimerWT 注释；若炮镜主体已在外部变化会停止保存。"
            });
        }
        choices.push({
            value: "save_as",
            title: "另存为新 BLK",
            description: "从作者工作副本生成一个带当前元数据的新文件，不修改原件。"
        });
        const dialog = await this._app.showChoiceDialog({
            title: "写入真实炮镜 BLK",
            message: `目标：${row.display_name || row.output_path || "当前炮镜"}`,
            choiceValue: choices[0].value,
            choices,
            confirmText: "继续",
            cancelText: "取消"
        });
        if (!dialog?.ok) return;
        const mode = String(dialog.choice || choices[0].value);

        await this._with_loading(mode === "save_original" ? "正在安全写入原 BLK…" : "正在生成新的 BLK…", async () => {
            const response = await this._api_call(
                "write_sight_project_blk",
                this._project_name,
                this._clone(this._draft),
                file_id,
                mode
            );
            if (!response?.success) {
                if (response?.data?.cancelled) return;
                this._notify_api_error(response, "写入炮镜 BLK 失败");
                return;
            }
            this._app.notifyToast(
                "success",
                mode === "save_original" ? "当前作者信息已安全写入原 BLK" : "新的炮镜 BLK 已生成"
            );
        });
    },
    async _rename_project() {
        if (!this._project_name || !await this._confirm_leave_dirty("重命名当前项目")) return;
        const old_name = this._project_name;
        let renamed_name = "";
        const dialog = await this._app.showInputDialog({
            title: "重命名炮镜项目",
            message: "只修改作者端项目文件夹名；作品公开名称可在基础信息中单独编辑。",
            inputLabel: "新项目名称",
            value: old_name,
            confirmText: "重命名"
        });
        if (!dialog?.ok) return;
        const new_name = String(dialog.value || "").trim();
        if (!new_name || new_name === old_name) return;
        await this._with_loading("正在重命名项目…", async () => {
            const response = await this._api_call("rename_sight_project", old_name, new_name);
            if (!response?.success) {
                this._notify_api_error(response, "重命名项目失败");
                return;
            }
            renamed_name = response.data?.project_name || new_name;
            await this._refresh_projects(false);
        });
        if (renamed_name) {
            await this._load_project(renamed_name, false);
            this._app.notifyToast("success", "炮镜项目已重命名");
        }
    },

    async _delete_project() {
        if (!this._project_name) return;
        const project_name = this._project_name;
        const confirmed = await this._app.showConfirmDialog({
            title: "删除炮镜作者项目",
            message: `将删除作者端“炮镜库”中的项目“${project_name}”及其工作副本。已导出的 ZIP 不受影响，此操作不可撤销。`,
            confirmText: "确认删除",
            cancelText: "保留项目"
        });
        if (!confirmed) return;
        await this._with_loading("正在删除炮镜项目…", async () => {
            const response = await this._api_call("delete_sight_project", project_name);
            if (!response?.success) {
                this._notify_api_error(response, "删除炮镜项目失败");
                return;
            }
            this._reset_project_state();
            this._ui_prefs.last_project = "";
            this._save_ui_prefs();
            await this._refresh_projects(false);
            this._app.notifyToast("success", response.msg || "炮镜项目已删除");
        });
    },

    async _save_project(show_feedback = true) {
        if (!this._project_name || !this._draft) return false;
        let saved = false;
        await this._with_loading("正在保存炮镜项目…", async () => {
            saved = await this._save_project_internal(show_feedback);
        });
        return saved;
    },

    async _save_project_internal(show_feedback = true) {
        const response = await this._api_call("save_sight_project", this._project_name, this._clone(this._draft));
        if (response?.data?.project) this._apply_normalized_project(response.data, Boolean(response.success));
        if (!response?.success) {
            this._notify_api_error(response, "保存炮镜项目失败");
            return false;
        }
        this._baseline_json = this._stable_json(this._draft);
        this._set_dirty(false);
        await this._refresh_projects(false);
        if (show_feedback) this._app.notifyToast("success", response.msg || "炮镜项目已保存");
        return true;
    },

    async _rescan_project() {
        if (!this._project_name || !this._draft) return;
        await this._with_loading("正在重新扫描项目文件…", async () => {
            const response = await this._api_call("rescan_sight_project", this._project_name, this._clone(this._draft));
            if (!response?.success) {
                this._notify_api_error(response, "重新扫描炮镜项目失败");
                return;
            }
            this._apply_normalized_project(response.data, false);
            this._report = null;
            this._validation_stale = true;
            this._set_dirty(this._stable_json(this._draft) !== this._baseline_json);
            this._app.notifyToast("success", this._scan_feedback(response.data?.scan));
        });
    },

    async _analyze_files(output_paths) {
        if (!this._project_name || !this._draft) return;
        await this._with_loading("正在分析 BLK 特征…", async () => {
            const response = await this._api_call("analyze_sight_files", this._project_name, output_paths || [], this._clone(this._draft));
            if (!response?.success) {
                this._notify_api_error(response, "BLK 分析失败");
                return;
            }
            if (response.data?.project) this._draft = response.data.project;
            this._analysis_results = { ...this._analysis_results, ...(response.data?.results || {}) };
            this._mark_dirty();
            this._render_file_editor();
            const count = Number(response.data?.analyzed_count || 0);
            const analysis_results = Object.values(response.data?.results || {});
            const confidence_counts = analysis_results.reduce((summary, result) => {
                const confidence = String(result?.confidence || "");
                if (confidence in summary) summary[confidence] += 1;
                return summary;
            }, { high: 0, medium: 0, low: 0 });
            const confidence_text = ["high", "medium", "low"]
                .filter((confidence) => confidence_counts[confidence])
                .map((confidence) => `${SIGHT_ANALYSIS_CONFIDENCE_LABELS[confidence]} ${confidence_counts[confidence]}`)
                .join("，");
            const failed_count = analysis_results.filter((result) => result?.error).length;
            const details = [confidence_text, failed_count ? `失败 ${failed_count}` : ""].filter(Boolean).join("，");
            this._app.notifyToast(
                confidence_counts.low || failed_count ? "warn" : "success",
                count ? `已分析 ${count} 个 BLK${details ? `：${details}` : ""}` : "没有可分析的真实 BLK",
            );
        });
    },

    async _validate_project(show_feedback = true) {
        if (!this._project_name || !this._draft) return false;
        let valid = false;
        await this._with_loading("正在执行兼容检查…", async () => {
            valid = await this._validate_project_internal(show_feedback);
        });
        return valid;
    },

    async _validate_project_internal(show_feedback = true) {
        const response = await this._api_call("validate_sight_project", this._project_name, this._clone(this._draft));
        if (!response?.success && !response?.data?.report) {
            this._notify_api_error(response, "兼容检查失败");
            return false;
        }
        if (response?.data?.project) this._draft = response.data.project;
        this._scan = response?.data?.scan || this._scan;
        this._report = response?.data?.report || null;
        this._validation_stale = false;
        this._set_dirty(this._stable_json(this._draft) !== this._baseline_json);
        this._render_all();
        const valid = Boolean(this._report?.valid);
        if (show_feedback) {
            this._app.notifyToast(valid ? "success" : "warn", valid ? "兼容检查通过，可以导出 ZIP" : `兼容检查发现 ${this._report?.summary?.error_count || 0} 个阻断问题`);
        }
        return valid;
    },

    async _export_project() {
        if (!this._project_name || !this._draft) return;
        await this._with_loading("正在准备炮镜 ZIP…", async () => {
            if (this._dirty && !await this._save_project_internal(false)) return;
            if ((this._validation_stale || !this._report) && !await this._validate_project_internal(false)) {
                this._app.notifyToast("warn", "兼容检查未通过，未生成 ZIP");
                return;
            }
            if (!this._report?.valid) {
                this._app.notifyToast("warn", "请先处理兼容检查中的阻断问题");
                return;
            }
            const response = await this._api_call("export_sight_project_zip", this._project_name, this._clone(this._draft));
            if (response?.data?.report) {
                this._report = response.data.report;
                this._validation_stale = false;
                this._render_report();
                this._render_summary();
            }
            if (!response?.success) {
                this._notify_api_error(response, "导出炮镜 ZIP 失败");
                return;
            }
            this._app.notifyToast("success", `已导出：${response.data?.file_name || "炮镜 ZIP"}`);
        });
    },

    async _select_cover() {
        if (!this._project_name) return;
        await this._with_loading("正在复制封面素材…", async () => {
            const response = await this._api_call("select_sight_cover", this._project_name);
            if (!response?.success) {
                if (response?.data?.cancelled) return;
                this._notify_api_error(response, "选择封面失败");
                return;
            }
            this._draft.cover = response.data?.cover || { source_path: "", output_name: "preview.webp" };
            this._cover_preview = response.data?.cover_preview || "";
            this._mark_dirty();
            this._render_cover();
            this._render_card_preview();
            this._app.notifyToast("success", response.msg || "封面素材已加入项目");
        });
    },

    async _clear_cover() {
        if (!this._project_name || !this._draft?.cover?.source_path) return;
        const confirmed = await this._app.showConfirmDialog({
            title: "清除项目封面",
            message: "将从当前项目配置移除封面引用。保存后导出包不再包含 preview.webp；项目内工作副本会保留，放弃修改时仍可恢复原封面。",
            confirmText: "清除封面",
            cancelText: "保留封面"
        });
        if (!confirmed) return;
        this._draft.cover = { source_path: "", output_name: "preview.webp" };
        this._cover_preview = "";
        this._mark_dirty();
        this._sync_current_project_row();
        this._render_cover();
        this._render_card_preview();
        this._app.notifyToast("success", "封面已从当前草稿移除，保存后生效");
    },

    async _open_project_folder() {
        if (!this._project_name) return;
        const response = await this._api_call("open_sight_project_folder", this._project_name);
        if (!response?.success) this._notify_api_error(response, "打开项目目录失败");
    },

    async _open_export_folder() {
        const response = await this._api_call("open_sight_export_folder");
        if (!response?.success) this._notify_api_error(response, "打开炮镜导出区失败");
    },

    _apply_project_data(data, clean) {
        this._project_name = String(data?.project_name || data?.project?.project_name || "");
        this._draft = this._clone(data?.project || null);
        this._scan = data?.scan || null;
        this._cover_preview = String(data?.cover_preview || "");
        this._report = data?.report || null;
        this._validation_stale = !this._report;
        this._analysis_results = {};
        this._selected_file_index = this._draft?.files?.length ? 0 : -1;
        this._file_page = 1;
        if (clean) this._baseline_json = this._stable_json(this._draft);
        this._set_dirty(clean ? false : this._stable_json(this._draft) !== this._baseline_json);
        this._render_all();
    },

    _apply_normalized_project(data, clean) {
        if (data?.project) this._draft = this._clone(data.project);
        if (data?.scan) this._scan = data.scan;
        if (data?.report) {
            this._report = data.report;
            this._validation_stale = false;
        }
        if (clean) this._baseline_json = this._stable_json(this._draft);
        this._set_dirty(clean ? false : this._stable_json(this._draft) !== this._baseline_json);
        this._render_all();
    },

    _reset_project_state() {
        this._project_name = "";
        this._draft = null;
        this._baseline_json = "";
        this._dirty = false;
        this._scan = null;
        this._cover_preview = "";
        this._report = null;
        this._validation_stale = false;
        this._analysis_results = {};
        this._selected_file_index = -1;
        this._file_page = 1;
        this._render_all();
    },

    _render_all() {
        this._render_empty_state();
        this._render_project_header();
        this._render_project_list();
        this._render_vehicle_catalog();
        this._render_basic_fields();
        this._render_file_list();
        this._render_file_editor();
        this._render_group_editor();
        this._render_assignment_editor();
        this._render_cover();
        this._render_advanced();
        this._render_summary();
        this._render_report();
        this._render_card_preview();
        this._sync_action_state();
    },

    _render_empty_state() {
        const empty = document.getElementById("sight-empty-state");
        const content = document.getElementById("sight-editor-content");
        if (empty) empty.hidden = Boolean(this._draft);
        if (content) content.hidden = !this._draft;
    },

    _render_project_header() {
        const package_info = this._draft?.package || {};
        const included_count = this._included_files().length;
        this._set_text("sight-current-title", this._draft ? (package_info.package_name || this._project_name || "未命名作品") : "尚未选择炮镜项目");
        this._set_text("sight-project-subtitle", this._draft ? `作者项目：${this._project_name} · 导出类型由 ${included_count} 个真实 BLK 自动推导` : "建立作者项目，映射真实 BLK，并在导出前完成兼容检查。");
        this._set_text("sight-project-type", this._draft ? (included_count === 1 ? "单炮镜" : "炮镜包") : "等待载入");
        const badge = document.getElementById("sight-dirty-badge");
        if (badge) badge.hidden = !this._dirty;
        this._set_text("sight-tab-file-count", String(this._draft?.files?.length || 0));
        this._set_text("sight-tab-group-count", String(this._draft?.groups?.length || 0));
    },

    _render_project_list(error_message = "") {
        const container = document.getElementById("sight-project-list");
        if (!container) return;
        this._set_text("sight-project-count", String(this._projects.length));
        if (error_message) {
            container.innerHTML = `<div class="sightinfo-list-placeholder error">${this._escape(error_message)}</div>`;
            return;
        }
        if (!this._projects.length) {
            container.innerHTML = `<div class="sightinfo-list-placeholder">${this._project_query ? "没有匹配的炮镜项目" : "还没有炮镜项目"}</div>`;
            return;
        }
        container.innerHTML = this._projects.map((item) => {
            const active = item.project_name === this._project_name ? " active" : "";
            const type_label = item.derived_type === "single_sight" ? "单炮镜" : "炮镜包";
            const cover_icon = item.has_cover ? "ri-image-line" : "ri-image-off-line";
            return `
                <button class="sightinfo-project-item${active}" type="button" role="option" aria-selected="${active ? "true" : "false"}" data-sight-project="${this._escape(item.project_name)}">
                    <span class="sightinfo-project-item-icon"><i class="ri-focus-3-line"></i></span>
                    <span class="sightinfo-project-item-main">
                        <strong>${this._escape(item.package_name || item.project_name)}</strong>
                        <small title="${this._escape(item.project_name)}">${this._escape(item.project_name)}</small>
                        <span><em>${type_label}</em><em>${Number(item.file_count || 0)} BLK</em><i class="${cover_icon}" title="${item.has_cover ? "已有封面" : "无封面"}"></i></span>
                    </span>
                </button>`;
        }).join("");
    },

    _render_basic_fields() {
        if (!this._draft) return;
        document.querySelectorAll("#page-sightinfo [data-sight-optional-bool-field]").forEach((input) => {
            const value = this._get_by_path(this._draft, input.dataset.sightOptionalBoolField);
            input.value = value === true ? "true" : (value === false ? "false" : "");
        });
        document.querySelectorAll("#page-sightinfo [data-sight-field]").forEach((input) => {
            const value = this._get_by_path(this._draft, input.dataset.sightField);
            input.value = this._field_text(value);
        });
        document.querySelectorAll("#page-sightinfo [data-sight-list-field]").forEach((input) => {
            input.value = this._join_list(this._get_by_path(this._draft, input.dataset.sightListField));
        });
        const tags = Array.isArray(this._draft.package?.tags) ? this._draft.package.tags : [];
        document.querySelectorAll("#page-sightinfo [data-sight-category]").forEach((input) => {
            input.checked = tags.includes(input.value);
        });
        const custom = tags.filter((tag) => !SIGHT_CATEGORY_IDS.includes(String(tag).toLowerCase()));
        const custom_input = document.getElementById("sight-custom-tags");
        if (custom_input) custom_input.value = custom.join(", ");
        this._render_package_vehicle_selector();
        this._set_active_tab(this._active_tab, false);
    },

    _render_vehicle_catalog() {
        const catalog = document.getElementById("sight-vehicle-catalog");
        if (!catalog) return;
        catalog.innerHTML = this._vehicle_catalog.map((vehicle) => `
            <option value="${this._escape(vehicle.vehicle_id || "")}">${this._escape(vehicle.display_name || vehicle.vehicle_id || "")}</option>
        `).join("");
    },

    _render_package_vehicle_selector() {
        const container = document.getElementById("sight-package-vehicle-selector");
        if (!container || !this._draft?.package) return;
        container.innerHTML = this._vehicle_selector_html("package", -1, this._draft.package);
    },

    _vehicle_selector_html(scope, index, recommendation) {
        const mode = String(recommendation?.recommended_apply_mode || "");
        const primary_vehicle_id = String(recommendation?.primary_vehicle_id || "");
        const compatible_vehicle_ids = Array.isArray(recommendation?.compatible_vehicle_ids)
            ? recommendation.compatible_vehicle_ids
            : [];
        const legacy_vehicles = Array.isArray(recommendation?.recommended_vehicles)
            ? recommendation.recommended_vehicles
            : [];
        const index_attr = scope === "file"
            ? ` data-vehicle-index="${index}"`
            : (scope === "group" ? ` data-vehicle-index="${index}"` : "");
        const scope_label = scope === "package" ? "作品" : (scope === "group" ? "分组" : "单文件");
        const layout_class = scope === "file" ? " span-4" : (scope === "group" ? " span-2" : "");
        const vehicle_fields_disabled = mode === "all_tanks" ? " disabled" : "";
        const selected_ids = mode === "all_tanks"
            ? ["all_tanks"]
            : [primary_vehicle_id, ...compatible_vehicle_ids].filter(Boolean);
        const chips = selected_ids.length
            ? selected_ids.map((vehicle_id, vehicle_index) => {
                const is_all_tanks = vehicle_id === "all_tanks";
                const label = is_all_tanks ? "全部坦克" : this._vehicle_display_name(vehicle_id);
                const chip_class = vehicle_index === 0 && !is_all_tanks ? " primary" : "";
                return `<span class="sightinfo-vehicle-chip${chip_class}">${this._escape(label)}<code>${this._escape(vehicle_id)}</code></span>`;
            }).join("")
            : '<span class="sightinfo-vehicle-empty">尚未填写结构化推荐，用户端将按兼容规则回退。</span>';
        const package_action = scope === "package"
            ? '<button class="btn-v2" type="button" data-sight-vehicle-action="apply_package_to_files" data-vehicle-scope="package" data-sight-desc="复制当前作品级推荐到所有尚无单文件结构化推荐的文件；已有单文件设置不会被覆盖。复制后各文件独立保存，不再自动跟随作品级变化。"><i class="ri-file-copy-2-line"></i><span>应用到未单独设置的文件</span></button>'
            : "";
        return `
            <section class="sightinfo-vehicle-selector${layout_class}" data-sight-vehicle-scope="${scope}"${index_attr}>
                <div class="sightinfo-vehicle-head">
                    <div><strong>${scope_label}级推荐车辆</strong><span>主要车辆用于排序和说明；未填写不会阻止保存或导出。</span></div>
                    ${package_action}
                </div>
                <div class="sightinfo-vehicle-grid">
                    <label class="sightinfo-field" data-sight-desc="决定客户端如何理解推荐范围：未结构化沿用旧文字；指定车辆使用车辆 ID；全部坦克表示通用。单文件设置优先于分组，分组优先于作品级。"><span>推荐模式</span><select class="sightinfo-select" data-sight-recommendation-mode data-vehicle-scope="${scope}"${index_attr}>
                        <option value="" ${!mode ? "selected" : ""}>未结构化（兼容旧资源）</option>
                        <option value="vehicles" ${mode === "vehicles" ? "selected" : ""}>按指定车辆推荐</option>
                        <option value="all_tanks" ${mode === "all_tanks" ? "selected" : ""}>推荐全部坦克</option>
                    </select></label>
                    <label class="sightinfo-field" data-sight-desc="填写一个稳定的游戏车辆 ID，作为首要推荐对象，并用于客户端排序和说明。"><span>主要适配车辆</span><input class="sightinfo-input mono" type="text" list="sight-vehicle-catalog" data-sight-vehicle-field="primary_vehicle_id" data-vehicle-scope="${scope}"${index_attr} value="${this._escape(primary_vehicle_id)}" placeholder="例如 cn_ztz_99a"${vehicle_fields_disabled}></label>
                    <label class="sightinfo-field span-2" data-sight-desc="填写同样适配的其他车辆 ID，多个值用逗号分隔；它们不会替代主要车辆。"><span>其他同样适配车辆</span><input class="sightinfo-input mono" type="text" list="sight-vehicle-catalog" data-sight-vehicle-list-field="compatible_vehicle_ids" data-vehicle-scope="${scope}"${index_attr} value="${this._escape(this._join_list(compatible_vehicle_ids))}" placeholder="多个车辆 ID 以逗号分隔"${vehicle_fields_disabled}></label>
                    <label class="sightinfo-field span-2" data-sight-desc="保留旧资源中的载具名称或说明文字，主要用于兼容和展示；它不会直接作为安装目录，也不是结构化车辆 ID。"><span>旧版推荐载具展示文字</span><input class="sightinfo-input" type="text" data-sight-legacy-vehicles data-vehicle-scope="${scope}"${index_attr} value="${this._escape(this._join_list(legacy_vehicles))}" placeholder="旧资源兼容字段；不会直接作为安装目录"></label>
                </div>
                <div class="sightinfo-vehicle-footer">
                    <div class="sightinfo-vehicle-chips">${chips}</div>
                    <button class="btn-v2" type="button" data-sight-vehicle-action="match_legacy" data-vehicle-scope="${scope}"${index_attr} data-sight-desc="把旧版展示文字按车辆 ID、显示名称或别名进行不区分大小写的精确匹配为结构化车辆 ID；不是模糊搜索，也不会删除原文字。首个匹配项作为主要车辆。"><i class="ri-magic-line"></i><span>匹配旧文字</span></button>
                </div>
            </section>`;
    },

    _vehicle_display_name(vehicle_id) {
        const key = String(vehicle_id || "").toLowerCase();
        const matched = this._vehicle_catalog.find((vehicle) => String(vehicle.vehicle_id || "").toLowerCase() === key);
        return matched ? String(matched.display_name || matched.vehicle_id) : `${vehicle_id}（目录未收录）`;
    },

    _recommendation_target(scope, index) {
        if (!this._draft) return null;
        if (scope === "file") return this._draft.files?.[index] || null;
        if (scope === "group") return this._draft.groups?.[index] || null;
        return this._draft.package || null;
    },

    _render_recommendation_scope(scope) {
        if (scope === "file") this._render_file_editor();
        else if (scope === "group") this._render_group_editor();
        else this._render_package_vehicle_selector();
    },

    _has_explicit_recommendation(recommendation) {
        return Boolean(
            recommendation?.recommended_apply_mode
            || recommendation?.primary_vehicle_id
            || (Array.isArray(recommendation?.compatible_vehicle_ids) && recommendation.compatible_vehicle_ids.length)
        );
    },

    _match_legacy_vehicles(scope, index) {
        const recommendation = this._recommendation_target(scope, index);
        if (!recommendation) return;
        const lookup = new Map();
        this._vehicle_catalog.forEach((vehicle) => {
            const vehicle_id = String(vehicle.vehicle_id || "");
            const display_name = String(vehicle.display_name || "");
            if (vehicle_id) lookup.set(vehicle_id.toLowerCase(), vehicle_id);
            if (display_name) lookup.set(display_name.toLowerCase(), vehicle_id);
            (Array.isArray(vehicle.aliases) ? vehicle.aliases : []).forEach((alias) => {
                const normalized_alias = String(alias || "").trim().toLowerCase();
                if (normalized_alias) lookup.set(normalized_alias, vehicle_id);
            });
        });
        const source = Array.isArray(recommendation.recommended_vehicles)
            ? recommendation.recommended_vehicles
            : [];
        const matched_ids = [...new Set(source.map((value) => lookup.get(String(value || "").trim().toLowerCase())).filter(Boolean))];
        if (!matched_ids.length) {
            this._app.notifyToast("warn", "旧版展示文字未能与当前车辆目录精确匹配，可直接填写车辆内部 ID");
            return;
        }
        recommendation.recommended_apply_mode = "vehicles";
        recommendation.primary_vehicle_id = matched_ids[0];
        recommendation.compatible_vehicle_ids = matched_ids.slice(1);
        this._mark_dirty();
        this._render_recommendation_scope(scope);
        const unmatched_count = Math.max(0, source.length - matched_ids.length);
        this._app.notifyToast(
            unmatched_count ? "warn" : "success",
            unmatched_count
                ? `已匹配 ${matched_ids.length} 个车辆，另有 ${unmatched_count} 项需人工确认`
                : `已匹配 ${matched_ids.length} 个结构化车辆`,
        );
    },

    _apply_package_recommendation_to_files() {
        const source = this._draft?.package;
        if (!source || !this._has_explicit_recommendation(source)) {
            this._app.notifyToast("warn", "请先填写作品级结构化推荐车辆");
            return;
        }
        let updated_count = 0;
        (this._draft.files || []).forEach((row) => {
            if (this._has_explicit_recommendation(row)) return;
            row.recommended_apply_mode = String(source.recommended_apply_mode || "");
            row.primary_vehicle_id = String(source.primary_vehicle_id || "");
            row.compatible_vehicle_ids = Array.isArray(source.compatible_vehicle_ids)
                ? [...source.compatible_vehicle_ids]
                : [];
            updated_count += 1;
        });
        if (!updated_count) {
            this._app.notifyToast("info", "所有文件都已有显式结构化设置，未覆盖任何内容");
            return;
        }
        this._mark_dirty();
        this._render_file_editor();
        this._app.notifyToast("success", `已应用到 ${updated_count} 个未单独设置的文件`);
    },
    _render_file_list() {
        const container = document.getElementById("sight-file-list");
        if (!container) return;
        const files = Array.isArray(this._draft?.files) ? this._draft.files : [];
        const included = files.filter((item) => item.include !== false).length;
        this._set_text("sight-file-count", `${included} / ${files.length}`);
        if (!files.length) {
            container.innerHTML = `<div class="sightinfo-list-placeholder">${this._draft ? "source 中还没有真实 BLK" : "选择项目后显示文件"}</div>`;
            return;
        }
        const matched_rows = this._filtered_file_rows();
        if (!matched_rows.length) {
            container.innerHTML = '<div class="sightinfo-list-placeholder">没有匹配的 BLK</div>';
            return;
        }
        const rows = matched_rows.slice(0, SIGHT_FILE_RAIL_LIMIT);
        const limit_hint = matched_rows.length > rows.length
            ? `<div class="sightinfo-rail-limit">项目共有 ${matched_rows.length} 个匹配文件，左栏仅显示前 ${rows.length} 个；可用搜索框精确定位。</div>`
            : "";
        container.innerHTML = rows.map(({ item, index }) => {
            const selected = index === this._selected_file_index ? " active" : "";
            const disabled = item.include === false ? " excluded" : "";
            const missing = item.missing_source ? '<i class="ri-error-warning-line" title="源文件缺失"></i>' : "";
            return `
                <button class="sightinfo-file-item${selected}${disabled}" type="button" role="option" aria-selected="${selected ? "true" : "false"}" data-sight-file-index="${index}">
                    <span class="sightinfo-file-state"><i class="ri-file-code-line"></i></span>
                    <span><strong>${this._escape(item.display_name || `炮镜 ${index + 1}`)}</strong><small>${this._escape(item.output_path || "未设置导出路径")}</small></span>
                    ${missing}
                </button>`;
        }).join("") + limit_hint;
    },

    _render_file_editor() {
        const container = document.getElementById("sight-file-editor");
        if (!container) return;
        const files = Array.isArray(this._draft?.files) ? this._draft.files : [];
        const matched_rows = this._filtered_file_rows();
        const select_all = document.getElementById("sight-select-all-files");
        if (select_all) select_all.checked = false;
        if (!matched_rows.length) {
            container.innerHTML = `<div class="sightinfo-panel-empty"><i class="ri-file-code-line"></i><strong>${files.length ? "没有匹配的 BLK" : "没有可编辑的真实 BLK"}</strong><p>把 .blk 文件放入项目 source 目录后点击“重新扫描”，或从现有文件夹、ZIP 导入。</p></div>`;
            return;
        }

        const page_count = Math.max(1, Math.ceil(matched_rows.length / SIGHT_FILE_PAGE_SIZE));
        this._file_page = Math.min(Math.max(1, this._file_page), page_count);
        const page_start = (this._file_page - 1) * SIGHT_FILE_PAGE_SIZE;
        const rows = matched_rows.slice(page_start, page_start + SIGHT_FILE_PAGE_SIZE);
        const pager = this._file_pager_html(page_count, matched_rows.length);
        const cards = rows.map(({ item, index }) => {
            const analysis = this._analysis_results[item.output_path] || null;
            const analysis_html = analysis ? this._render_analysis_result(analysis) : "";
            const ammo_options = this._ammo_options_html(item.ammo_type);
            return `
                <article class="sightinfo-file-card${item.missing_source ? " has-error" : ""}" data-sight-file-card="${index}">
                    <header>
                        <label class="sightinfo-row-selector" title="加入批量操作"><input type="checkbox" data-sight-batch-select data-file-index="${index}"><span></span></label>
                        <div><strong>${this._escape(item.display_name || `炮镜 ${index + 1}`)}</strong><code>${this._escape(item.source_path || "源文件未匹配")}</code></div>
                        <label class="sightinfo-include-switch" data-sight-desc="开启后此文件会进入导出 ZIP，并参与兼容检查和批量分析；关闭后仅保留在作者项目中。"><input type="checkbox" data-sight-file-field="include" data-file-index="${index}" ${item.include !== false ? "checked" : ""}><span>进入发布包</span></label>
                        <button class="btn-v2" type="button" data-sight-file-action="write_blk" data-file-index="${index}" ${item.missing_source ? "disabled" : ""} data-sight-desc="将当前项目元数据写入此 BLK 的尾部 V2 注释。操作时可选择安全写入工作副本或另存为；导出 ZIP 不要求先点此按钮。"><i class="ri-save-2-line"></i><span>写入 BLK</span></button>
                        <button class="btn-v2" type="button" data-sight-file-action="analyze" data-file-index="${index}" data-sight-desc="只读取当前 BLK 并刷新它的分析结果，不会写入或修改文件。"><i class="ri-radar-line"></i><span>分析此 BLK</span></button>
                    </header>
                    <div class="sightinfo-file-grid">
                        <label class="sightinfo-field"><span>显示名称</span><input class="sightinfo-input" type="text" data-sight-file-field="display_name" data-file-index="${index}" value="${this._escape(item.display_name || "")}"></label>
                        <label class="sightinfo-field span-2" data-sight-desc="这是文件在最终 ZIP 中的相对路径，也用于元数据匹配和安装目录推导；必须以 .blk 结尾，且不能跳出 ZIP 根目录。"><span>ZIP 内输出路径 <b>*</b></span><input class="sightinfo-input mono" type="text" data-sight-file-field="output_path" data-file-index="${index}" value="${this._escape(item.output_path || "")}" placeholder="例如：germ_tiger1/my_sight.blk"></label>
                        <label class="sightinfo-field" data-sight-desc="说明这个 BLK 的主要适用弹种，供详情展示、筛选和作者分组使用；不会改动炮镜刻度。"><span>弹种</span><select class="sightinfo-select" data-sight-file-field="ammo_type" data-file-index="${index}">${ammo_options}</select></label>
                        <label class="sightinfo-field" data-sight-desc="说明此 BLK 按哪个屏幕分辨率制作，供客户端兼容提示；不会自动缩放文件内容。"><span>目标分辨率</span><input class="sightinfo-input" type="text" data-sight-file-field="target_resolution" data-file-index="${index}" value="${this._escape(item.target_resolution || "")}" placeholder="1920x1080"></label>
                        ${this._vehicle_selector_html("file", index, item)}
                        <label class="sightinfo-field span-4"><span>文件说明</span><input class="sightinfo-input" type="text" data-sight-file-field="note" data-file-index="${index}" value="${this._escape(item.note || "")}" placeholder="说明这个变体的刻度、弹种或使用区别"></label>
                    </div>
                    ${item.missing_source ? '<div class="sightinfo-inline-alert error"><i class="ri-error-warning-line"></i><span>源 BLK 已不存在；重新放回文件或取消“进入发布包”。</span></div>' : ""}
                    ${analysis_html}
                </article>`;
        }).join("");
        container.innerHTML = pager + cards + (page_count > 1 ? pager : "");
    },

    _file_pager_html(page_count, total_count) {
        return `
            <div class="sightinfo-file-pager">
                <span>共 ${total_count} 个文件 · 每页 ${SIGHT_FILE_PAGE_SIZE} 个</span>
                <div>
                    <button type="button" data-sight-file-page="${this._file_page - 1}" ${this._file_page <= 1 ? "disabled" : ""}><i class="ri-arrow-left-s-line"></i></button>
                    <em>${this._file_page} / ${page_count}</em>
                    <button type="button" data-sight-file-page="${this._file_page + 1}" ${this._file_page >= page_count ? "disabled" : ""}><i class="ri-arrow-right-s-line"></i></button>
                </div>
            </div>`;
    },

    _render_analysis_result(result) {
        if (result.error) return `<div class="sightinfo-analysis-result error"><i class="ri-error-warning-line"></i><span>${this._escape(result.error)}</span></div>`;
        const confidence = String(result.confidence || "low");
        const confidence_label = SIGHT_ANALYSIS_CONFIDENCE_LABELS[confidence] || "置信度未知";
        const reasons = (Array.isArray(result.confidence_reasons) ? result.confidence_reasons : [])
            .map((reason) => SIGHT_ANALYSIS_REASON_LABELS[reason] || String(reason || ""))
            .filter(Boolean);
        const rows = Object.entries(result)
            .filter(([key]) => !["cached", "confidence", "confidence_reasons"].includes(key))
            .slice(0, 9);
        const render_value = (value) => {
            if (typeof value === "boolean") return value ? "是" : "否";
            if (value === null || value === undefined || value === "") return "未识别";
            const status_label = SIGHT_ANALYSIS_STATUS_LABELS[String(value)];
            return status_label || this._field_text(value);
        };
        const feature_html = rows.map(([key, value]) => `
            <span>
                <b>${this._escape(SIGHT_ANALYSIS_FIELD_LABELS[key] || key)}</b>
                <code>${this._escape(render_value(value))}</code>
            </span>`).join("");
        const reason_html = reasons.length ? `
            <span>
                <b>需确认项</b>
                <code>${this._escape(reasons.join("；"))}</code>
            </span>` : "";
        return `
            <details class="sightinfo-analysis-result" open>
                <summary><span>BLK 分析参考</span><em>${result.cached ? "缓存结果" : "本次分析"} · ${confidence_label}</em></summary>
                <div>${feature_html || reason_html ? `${feature_html}${reason_html}` : "未发现可展示特征"}</div>
            </details>`;
    },

    _render_group_editor() {
        const container = document.getElementById("sight-group-editor");
        if (!container) return;
        const groups = Array.isArray(this._draft?.groups) ? this._draft.groups : [];
        if (!groups.length) {
            container.innerHTML = '<div class="sightinfo-panel-empty compact"><i class="ri-stack-line"></i><strong>尚未建立作者分组</strong><p>单炮镜不需要分组；多文件包可按弹种、国家、玩法或版本组织。</p></div>';
            return;
        }
        container.innerHTML = groups.map((group, index) => `
            <article class="sightinfo-group-card">
                <header>
                    <div><span>分组 ${index + 1}</span><code>${this._escape(group.group_id || "")}</code></div>
                    <div class="sightinfo-order-actions">
                        <button type="button" data-sight-group-action="up" data-group-index="${index}" ${index === 0 ? "disabled" : ""} title="上移"><i class="ri-arrow-up-line"></i></button>
                        <button type="button" data-sight-group-action="down" data-group-index="${index}" ${index === groups.length - 1 ? "disabled" : ""} title="下移"><i class="ri-arrow-down-line"></i></button>
                        <button type="button" class="danger" data-sight-group-action="delete" data-group-index="${index}" title="删除分组"><i class="ri-delete-bin-line"></i></button>
                    </div>
                </header>
                <div class="sightinfo-form-grid two-column">
                    <label class="sightinfo-field"><span>分组名称</span><input class="sightinfo-input" type="text" data-sight-group-field="name" data-group-index="${index}" value="${this._escape(group.name || "")}" maxlength="40"></label>
                    <label class="sightinfo-field"><span>分组 ID</span><input class="sightinfo-input mono" type="text" data-sight-group-field="group_id" data-group-index="${index}" value="${this._escape(group.group_id || "")}" maxlength="48" placeholder="唯一且稳定"></label>
                    <label class="sightinfo-field span-2"><span>分组说明</span><input class="sightinfo-input" type="text" data-sight-group-field="description" data-group-index="${index}" value="${this._escape(group.description || "")}" maxlength="160"></label>
                    <label class="sightinfo-field"><span>弹种集合</span><input class="sightinfo-input" type="text" data-sight-group-list-field="ammo_types" data-group-index="${index}" value="${this._escape(this._join_list(group.ammo_types))}" placeholder="apcbc, heat_fs"></label>
                    <label class="sightinfo-field"><span>目标分辨率</span><input class="sightinfo-input" type="text" data-sight-group-list-field="target_resolutions" data-group-index="${index}" value="${this._escape(this._join_list(group.target_resolutions))}"></label>
                    ${this._vehicle_selector_html("group", index, group)}
                    <label class="sightinfo-field"><span>平台</span><input class="sightinfo-input" type="text" data-sight-group-list-field="platforms" data-group-index="${index}" value="${this._escape(this._join_list(group.platforms))}" placeholder="PC"></label>
                    <label class="sightinfo-field"><span>标签</span><input class="sightinfo-input" type="text" data-sight-group-list-field="tags" data-group-index="${index}" value="${this._escape(this._join_list(group.tags))}"></label>
                    <label class="sightinfo-field"><span>排序值</span><input class="sightinfo-input" type="number" data-sight-group-field="sort_order" data-group-index="${index}" value="${Number(group.sort_order || ((index + 1) * 100))}"></label>
                    <label class="sightinfo-featured-toggle span-2"><input type="checkbox" data-sight-group-field="featured" data-group-index="${index}" ${group.featured ? "checked" : ""}><span>在该包内标为推荐分组</span></label>
                </div>
            </article>`).join("");
    },

    _render_assignment_editor() {
        const container = document.getElementById("sight-assignment-editor");
        if (!container) return;
        const files = this._included_files();
        const groups = Array.isArray(this._draft?.groups) ? this._draft.groups : [];
        if (!files.length || !groups.length) {
            container.innerHTML = "";
            return;
        }
        const assignment = new Map();
        groups.forEach((group) => (group.files || []).forEach((path) => {
            if (!assignment.has(String(path).toLowerCase())) assignment.set(String(path).toLowerCase(), group.group_id);
        }));
        container.innerHTML = `
            <div class="sightinfo-assignment-head"><div><strong>BLK 归属</strong><span>同一文件只能选择一个作者分组</span></div><em>${files.length} 个发布文件</em></div>
            <div class="sightinfo-assignment-list">
                ${files.map((file) => {
                    const selected = assignment.get(String(file.output_path || "").toLowerCase()) || "";
                    return `<label><span><strong>${this._escape(file.display_name || file.output_path)}</strong><code>${this._escape(file.output_path || "")}</code></span><select class="sightinfo-select" data-sight-assignment data-output-path="${this._escape(file.output_path || "")}"><option value="">未分组</option>${groups.map((group) => `<option value="${this._escape(group.group_id)}" ${selected === group.group_id ? "selected" : ""}>${this._escape(group.name || group.group_id)}</option>`).join("")}</select></label>`;
                }).join("")}
            </div>`;
    },

    _render_cover() {
        const image = document.getElementById("sight-cover-preview");
        const placeholder = document.getElementById("sight-cover-placeholder");
        const source = this._draft?.cover?.source_path || "";
        if (image) {
            image.hidden = !this._cover_preview;
            if (this._cover_preview) image.src = this._cover_preview;
            else image.removeAttribute("src");
        }
        if (placeholder) placeholder.hidden = Boolean(this._cover_preview);
        this._set_text("sight-cover-source", source || "未设置");
        const clear_button = document.getElementById("btn-sight-clear-cover");
        if (clear_button) clear_button.disabled = !source || this._loading;
    },

    _render_advanced() {
        if (!this._draft) return;
        this._set_text("sight-schema-version", this._draft.schema_version ?? this._workspace?.schema_version ?? "-");
        this._set_text("sight-meta-version", this._workspace?.meta_version ?? "1");
        const import_meta = this._draft.import_meta || {};
        const migration_box = document.getElementById("sight-migration-box");
        const migration_input = document.getElementById("sight-migration-confirmed");
        if (migration_box) migration_box.hidden = !import_meta.migration_required;
        if (migration_input) migration_input.checked = Boolean(import_meta.migration_confirmed);
        this._set_text("sight-migration-detail", `来源标记：${import_meta.source_marker || "未知"}；来源版本：${import_meta.source_meta_version ?? "未知"}。确认后会以当前 V1 重新生成。`);

        const top_count = Object.keys(this._draft.extra_meta || {}).length;
        const file_count = (this._draft.files || []).reduce((sum, item) => sum + Object.keys(item.extra_meta || {}).length, 0);
        const group_count = (this._draft.groups || []).reduce((sum, item) => sum + Object.keys(item.extra_meta || {}).length, 0);
        const total = top_count + file_count + group_count;
        this._set_text("sight-preserved-summary", total ? `保留 ${total} 个未知字段：作品级 ${top_count}、文件级 ${file_count}、分组级 ${group_count}。作者端不会擅自改写其值。` : "当前项目没有需要保留的未知字段。");
    },

    _render_summary() {
        const container = document.getElementById("sight-report-summary");
        if (!container) return;
        const summary = this._report?.summary || {};
        const included_files = this._included_files();
        const count = included_files.length;
        const display_type = summary.display_type || (count === 1 ? "single_sight" : "sight_package");
        const display_label = display_type === "single_sight" ? "单炮镜" : "炮镜包";
        const matched_label = this._report ? `${Number(summary.matched_meta_count || 0)} / ${count}` : "待检查";
        const group_count = Number(summary.group_count ?? (this._draft?.groups?.length || 0));
        const assigned_paths = new Set((this._draft?.groups || []).flatMap((group) => group.files || []).map((path) => String(path).toLowerCase()));
        const ungrouped_count = Number(summary.ungrouped_count ?? included_files.filter((item) => !assigned_paths.has(String(item.output_path || "").toLowerCase())).length);
        const cover_label = summary.cover_output || (this._draft?.cover?.source_path ? "preview.webp" : "默认图");
        container.innerHTML = `
            <div><span>发布载体</span><strong>ZIP</strong></div>
            <div><span>显示类型</span><strong>${display_label}</strong></div>
            <div><span>真实 BLK</span><strong>${Number(summary.real_blk_count ?? count)}</strong></div>
            <div><span>元数据 BLK</span><strong>${Number(summary.meta_blk_count ?? 0)}</strong></div>
            <div><span>精确匹配</span><strong>${matched_label}</strong></div>
            <div><span>作者分组</span><strong>${group_count}</strong></div>
            <div><span>未分组</span><strong>${ungrouped_count}</strong></div>
            <div><span>封面输出</span><strong>${this._escape(cover_label)}</strong></div>`;
        this._set_text("sight-target-mode", this._target_mode_label(summary.target_mode));
        const map = document.getElementById("sight-install-map");
        if (!map) return;
        const entries = Array.isArray(summary.install_entries) ? summary.install_entries : [];
        if (!entries.length) {
            map.innerHTML = '<div class="sightinfo-list-placeholder compact">检查后显示 ZIP 路径到 UserSights 的映射</div>';
            return;
        }
        const target_root = summary.target_dir ? `UserSights/${summary.target_dir}` : "UserSights";
        map.innerHTML = `
            <div class="sightinfo-target-root"><i class="ri-folder-3-line"></i><span>${this._escape(target_root)}</span></div>
            ${entries.map((entry) => `<div class="sightinfo-map-row"><code>${this._escape(entry.source_relative_path || "")}</code><i class="ri-arrow-right-line"></i><code>${this._escape(entry.target_relative_path || "")}</code></div>`).join("")}`;
    },

    _render_report() {
        const state = document.getElementById("sight-report-state");
        const dot = document.getElementById("sight-report-dot");
        const list = document.getElementById("sight-report-list");
        if (!state || !dot || !list) return;
        dot.className = "sightinfo-report-dot";
        if (!this._report) {
            state.textContent = this._draft ? "尚未检查" : "等待项目";
            dot.classList.add("idle");
            this._set_text("sight-report-count", "0 项");
            list.innerHTML = '<div class="sightinfo-report-empty"><i class="ri-shield-check-line"></i><span>运行兼容检查后，这里会列出阻断项和建议。</span></div>';
            return;
        }
        const errors = Array.isArray(this._report.errors) ? this._report.errors : [];
        const warnings = Array.isArray(this._report.warnings) ? this._report.warnings : [];
        const info = Array.isArray(this._report.info) ? this._report.info : [];
        const total = errors.length + warnings.length + info.length;
        if (this._validation_stale) {
            state.textContent = "内容已变化，需复查";
            dot.classList.add("stale");
        } else if (errors.length) {
            state.textContent = `${errors.length} 个阻断问题`;
            dot.classList.add("error");
        } else if (warnings.length) {
            state.textContent = `通过，${warnings.length} 项提醒`;
            dot.classList.add("warning");
        } else {
            state.textContent = "兼容检查通过";
            dot.classList.add("success");
        }
        this._set_text("sight-report-count", `${total} 项`);
        const sections = [
            ["error", "阻断", errors],
            ["warning", "提醒", warnings],
            ["info", "推导", info]
        ];
        list.innerHTML = sections.filter(([, , items]) => items.length).map(([type, label, items]) => `
            <div class="sightinfo-report-group ${type}">
                <div class="sightinfo-report-group-title"><span>${label}</span><em>${items.length}</em></div>
                ${items.map((item, index) => `<button type="button" class="sightinfo-report-item" data-sight-issue-index="${index}" data-issue-type="${type}"><i class="${this._issue_icon(type)}"></i><span><strong>${this._escape(item.message || item.code || "检查信息")}</strong>${this._issue_detail(item)}</span></button>`).join("")}
            </div>`).join("") || '<div class="sightinfo-report-empty success"><i class="ri-checkbox-circle-line"></i><span>没有发现兼容问题。</span></div>';
    },

    _preview_card_data() {
        const package_info = this._draft?.package || {};
        const included_files = this._included_files();
        const append_values = (target, value) => {
            const values = Array.isArray(value) ? value : String(value || "").split(/[,，;；|、\n]+/);
            values.map((item) => String(item || "").trim()).filter(Boolean).forEach((item) => {
                if (!target.some((current) => current.toLowerCase() === item.toLowerCase())) target.push(item);
            });
        };

        const resolutions = [];
        append_values(resolutions, package_info.target_resolutions);
        append_values(resolutions, package_info.target_resolution);
        included_files.forEach((item) => append_values(resolutions, item.target_resolution));
        const resolution_key = (value) => {
            const pair = String(value || "").trim().toLowerCase().match(/(\d{3,5})\s*[x×*]\s*(\d{3,5})/);
            return pair ? `${Number(pair[1])}x${Number(pair[2])}` : String(value || "").trim().toLowerCase().replace(/\s+/g, "");
        };
        const screen_ratio = Number(window.devicePixelRatio || 1) || 1;
        const screen_key = resolution_key(`${Math.round(Number(window.screen?.width || 0) * screen_ratio)}x${Math.round(Number(window.screen?.height || 0) * screen_ratio)}`);
        const reversed_screen_key = screen_key.replace(/^(\d+)x(\d+)$/, "$2x$1");
        const matched_resolution_index = resolutions.findIndex((value) => {
            const key = resolution_key(value);
            return key === screen_key || key === reversed_screen_key;
        });
        const primary_resolution_index = matched_resolution_index >= 0 ? matched_resolution_index : 0;
        const primary_resolution = resolutions[primary_resolution_index] || "";
        const hidden_resolutions = resolutions.filter((_, index) => index !== primary_resolution_index);

        const raw_tags = Array.isArray(package_info.tags) ? package_info.tags : [];
        const tag_aliases = {
            historical: "historical", history: "historical", historic: "historical", "史实": "historical", "史实瞄具": "historical",
            competitive: "competitive", competition: "competitive", esports: "competitive", "竞技": "competitive", "竞技瞄具": "competitive",
            fun: "fun", casual: "fun", entertainment: "fun", "娱乐": "fun", "娱乐瞄具": "fun"
        };
        const normalized_tags = new Set(raw_tags.map((tag) => {
            const text = String(tag || "").trim().toLowerCase();
            return tag_aliases[text] || tag_aliases[text.replace(/[\s_-]+/g, "")] || "";
        }).filter(Boolean));
        const category_tags = [
            { key: "historical", label: "史实瞄具" },
            { key: "competitive", label: "竞技瞄具" },
            { key: "fun", label: "娱乐瞄具" }
        ].filter((item) => normalized_tags.has(item.key));

        const hover_text = package_info.hover_text && typeof package_info.hover_text === "object" ? package_info.hover_text : {};
        const first_file = included_files[0] || {};
        const first_analysis = this._analysis_results[first_file.output_path] || {};
        const declared_correction = package_info.apply_correction_to_gun;
        const analyzed_correction = first_analysis.apply_correction_to_gun;
        const effective_correction = typeof declared_correction === "boolean" ? declared_correction : analyzed_correction;
        let gun_correction = "未知";
        if (typeof effective_correction === "boolean") gun_correction = effective_correction ? "是" : "否";
        else if (effective_correction !== undefined && effective_correction !== null) gun_correction = String(effective_correction).trim() || "未知";
        const correction_custom_text = String(hover_text.gun_correction || hover_text.apply_correction_to_gun || "").trim();
        const gun_correction_parts = [`自动抬炮：${gun_correction}`, correction_custom_text];
        if (first_analysis.note) gun_correction_parts.push(`作者说明：${String(first_analysis.note).trim()}`);
        if (first_analysis.target_resolution) gun_correction_parts.push(`分辨率：${String(first_analysis.target_resolution).trim()}`);
        if (first_analysis.range_min !== null && first_analysis.range_min !== undefined
            && first_analysis.range_max !== null && first_analysis.range_max !== undefined) {
            gun_correction_parts.push(`瞄距：${first_analysis.range_min}–${first_analysis.range_max} m`);
        }
        const resolution_tooltip = [
            String(hover_text.target_resolution || "").trim(),
            hidden_resolutions.length ? `还支持：${hidden_resolutions.join("、")}` : ""
        ].filter(Boolean).join("；");
        const size_bytes = included_files.reduce((total, item) => total + Math.max(0, Number(item?.signature?.size || item?.size || 0) || 0), 0);

        return {
            name: String(package_info.package_name || this._project_name || "未命名作品").trim(),
            author: String(package_info.author || "未知作者").trim(),
            description: String(package_info.description || package_info.note || "暂无简介").trim(),
            count: included_files.length,
            category_tags,
            resolutions,
            primary_resolution,
            hidden_resolution_count: hidden_resolutions.length,
            resolution_tooltip,
            gun_correction,
            gun_correction_tooltip: Array.from(new Set(gun_correction_parts.filter(Boolean))).join("；"),
            hover_text,
            size_text: this._format_preview_size(size_bytes),
            cover_url: this._cover_preview || "assets/card_image_small.png",
            cover_is_default: !this._cover_preview,
            links: {
                video: String(package_info.link_video || "").trim(),
                wtlive: String(package_info.link_wtlive || "").trim(),
                bili: String(package_info.link_bilibili || "").trim()
            }
        };
    },

    _format_preview_size(size_bytes) {
        const size = Math.max(0, Number(size_bytes) || 0);
        if (size < 1024) return `${Math.round(size)} B`;
        if (size < 1024 * 1024) return `${(size / 1024).toFixed(size < 10 * 1024 ? 1 : 0)} KB`;
        if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(size < 10 * 1024 * 1024 ? 1 : 0)} MB`;
        return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
    },

    _render_preview_summary(category_tags) {
        if (!category_tags.length) return "";
        return `
            <div class="sight-card-summary">
                ${category_tags.map((tag) => `<span class="sight-card-summary-chip sight-tag-${tag.key}">${this._escape(tag.label)}</span>`).join("")}
            </div>`;
    },

    _render_preview_links(preview_data) {
        const link_defs = [
            { key: "video", label: "视频", icon: "ri-play-circle-line", url: preview_data.links.video },
            { key: "wtlive", label: "WT", icon: "ri-global-line", url: preview_data.links.wtlive },
            { key: "bili", label: "B站", icon: "ri-bilibili-line", url: preview_data.links.bili }
        ];
        const links_html = link_defs.map((item) => {
            const disabled = item.url ? "" : ' disabled aria-disabled="true"';
            const title = item.url ? item.label : `${item.label} 暂未配置`;
            return `
                <button class="sight-featured-link-btn is-${item.key}${item.url ? "" : " is-disabled"}" type="button" tabindex="-1"${disabled} title="${this._escape(title)}">
                    <i class="${item.icon}"></i><span>${this._escape(item.label)}</span>
                </button>`;
        }).join("");
        return `
            <div class="sight-featured-single-links">
                ${links_html}
                <button class="sight-featured-link-btn is-delete" type="button" tabindex="-1" title="删除炮镜">
                    <i class="ri-delete-bin-line"></i><span>删除炮镜</span>
                </button>
            </div>`;
    },

    _render_runtime_single_card(preview_data, options = {}) {
        const open_attributes = options.openable === false ? "" : ' data-sight-preview-open="single" role="button" tabindex="0" aria-label="放大查看单个炮镜卡片"';
        const summary_html = this._render_preview_summary(preview_data.category_tags);
        const summary_tooltip = this._escape(preview_data.hover_text.sight_type || "");
        const summary_row_html = summary_html ? `
            <div class="sight-featured-single-info-row is-sight-tags"${summary_tooltip ? ` data-sight-desc="${summary_tooltip}" tabindex="0"` : ""}>
                <i class="ri-crosshair-2-line"></i>${summary_html}
            </div>` : "";
        const resolution_row_html = preview_data.primary_resolution ? `
            <div class="sight-featured-single-info-row is-resolution">
                <i class="ri-aspect-ratio-line"></i>
                <div class="sight-featured-single-resolution-wrap"${preview_data.resolution_tooltip ? ` data-sight-desc="${this._escape(preview_data.resolution_tooltip)}" tabindex="0"` : ""}>
                    <span class="sight-featured-single-resolution">${this._escape(preview_data.primary_resolution)}</span>
                    ${preview_data.hidden_resolution_count ? `<span class="sight-featured-single-resolution-more">+${preview_data.hidden_resolution_count}</span>` : ""}
                </div>
            </div>` : "";
        const cover_class = preview_data.cover_is_default ? " is-default-cover" : "";
        return `
            <div class="small-card sight-package-card is-featured is-featured-single" title="${this._escape(preview_data.name)}" data-sight-kind="single" data-sight-featured="1"${open_attributes}>
                <div class="small-card-img-wrapper" style="position:relative;">
                    <img class="small-card-img${cover_class}" src="${this._escape(preview_data.cover_url)}" loading="lazy" alt="">
                    <div class="sight-image-status"><span class="sight-state-badge is-enabled"><i></i>已启用</span></div>
                    <div class="sight-package-actions is-single-actions sight-card-quick-actions" role="group" aria-label="更多操作">
                        <button class="sight-card-more-action sight-card-quick-action" type="button" tabindex="-1" title="编辑页" aria-label="编辑页"><i class="ri-edit-line"></i></button>
                        <button class="sight-card-more-action sight-card-quick-action" type="button" tabindex="-1" title="详情页" aria-label="详情页"><i class="ri-file-list-3-line"></i></button>
                        <button class="sight-card-more-action sight-card-quick-action" type="button" tabindex="-1" title="打开文件夹" aria-label="打开文件夹"><i class="ri-folder-open-line"></i></button>
                    </div>
                </div>
                <div class="small-card-body sight-package-card-body">
                    <div class="sight-featured-single-content">
                        <div class="sight-featured-single-main">
                            <div class="small-card-title sight-package-name" title="${this._escape(preview_data.name)}">${this._escape(preview_data.name)}</div>
                            <div class="sight-package-author" title="${this._escape(preview_data.author)}"><i class="ri-user-3-line"></i>${this._escape(preview_data.author)}</div>
                            ${summary_row_html}
                            <div class="sight-featured-single-info-row is-gun-correction" data-sight-desc="${this._escape(preview_data.gun_correction_tooltip)}" tabindex="0">
                                <i class="ri-arrow-up-circle-line"></i>
                                <span class="sight-featured-single-gun-correction"><b>自动抬炮：</b>${this._escape(preview_data.gun_correction)}</span>
                            </div>
                            ${resolution_row_html}
                            <div class="sight-package-desc" title="" aria-label="${this._escape(preview_data.description)}" data-sight-desc="${this._escape(preview_data.description)}" tabindex="0">${this._escape(preview_data.description)}</div>
                        </div>
                        <div class="small-card-meta sight-package-meta sight-featured-single-footer">
                            ${this._render_preview_links(preview_data)}
                        </div>
                    </div>
                </div>
            </div>`;
    },

    _render_runtime_package_card(preview_data, options = {}) {
        const open_attributes = options.openable === false ? "" : ' data-sight-preview-open="package" role="button" tabindex="0" aria-label="放大查看炮镜组卡片"';
        const cover_class = preview_data.cover_is_default ? " is-default-cover" : "";
        const summary_html = this._render_preview_summary(preview_data.category_tags);
        return `
            <div class="small-card sight-package-card is-featured" title="${this._escape(preview_data.name)}" data-sight-kind="package" data-sight-featured="1"${open_attributes}>
                <div class="small-card-img-wrapper" style="position:relative;">
                    <img class="small-card-img${cover_class}" src="${this._escape(preview_data.cover_url)}" loading="lazy" alt="">
                    <div class="sight-package-actions is-preview-overlay-actions">
                        <button class="sight-card-main-action" type="button" tabindex="-1" title="查看炮镜包内容" aria-label="查看炮镜包内容"><i class="ri-folder-open-line"></i><span>查看炮镜包内容</span></button>
                        <button class="sight-card-more-action" type="button" tabindex="-1" title="编辑炮镜" aria-label="编辑炮镜"><i class="ri-more-2-fill"></i></button>
                    </div>
                </div>
                <div class="small-card-body sight-package-card-body">
                    <div class="small-card-title sight-package-name" title="${this._escape(preview_data.name)}">${this._escape(preview_data.name)}</div>
                    <div class="sight-package-author sight-package-author-with-size">
                        <span class="sight-package-author-main" title="${this._escape(preview_data.author)}"><i class="ri-user-3-line"></i>${this._escape(preview_data.author)}</span>
                        <span class="sight-package-size" title="${this._escape(preview_data.size_text)}">${this._escape(preview_data.size_text)}</span>
                    </div>
                    <div class="sight-package-desc" title="" aria-label="${this._escape(preview_data.description)}" data-sight-desc="${this._escape(preview_data.description)}" tabindex="0">${this._escape(preview_data.description)}</div>
                    ${summary_html}
                    <div class="small-card-meta sight-package-meta">
                        <span class="sight-state-badge is-enabled"><i></i>已启用</span>
                        <span class="sight-count-badge"><i class="ri-crosshair-2-line"></i>${preview_data.count} 个炮镜</span>
                    </div>
                </div>
            </div>`;
    },

    _open_preview_page(preview_kind, source_card) {
        const page = document.getElementById("sight-preview-page");
        const stage = document.getElementById("sight-preview-detail-stage");
        if (!page || !stage) return;
        const preview_data = this._preview_card_data();
        this._preview_kind = preview_kind === "package" ? "package" : "single";
        this._preview_focus_return = source_card || document.activeElement;
        stage.innerHTML = this._preview_kind === "package"
            ? this._render_runtime_package_card(preview_data, { openable: false })
            : this._render_runtime_single_card(preview_data, { openable: false });
        this._set_text("sight-preview-page-title", this._preview_kind === "package" ? "炮镜组卡片等比预览" : "单个炮镜卡片等比预览");
        page.hidden = false;
        document.querySelectorAll("#sightinfo-shell > .sightinfo-project-bar, #sightinfo-shell > .sightinfo-workspace").forEach((section) => {
            section.inert = true;
            section.setAttribute("aria-hidden", "true");
        });
        requestAnimationFrame(() => {
            this._fit_card_previews();
            page.querySelector("[data-sight-preview-close]")?.focus();
        });
    },

    _close_preview_page() {
        const page = document.getElementById("sight-preview-page");
        if (!page || page.hidden) return;
        this._hide_preview_tooltip();
        page.hidden = true;
        document.querySelectorAll("#sightinfo-shell > .sightinfo-project-bar, #sightinfo-shell > .sightinfo-workspace").forEach((section) => {
            section.inert = false;
            section.removeAttribute("aria-hidden");
        });
        const focus_return = this._preview_focus_return;
        this._preview_focus_return = null;
        if (focus_return?.isConnected) requestAnimationFrame(() => focus_return.focus());
    },

    _show_preview_tooltip(anchor, text, described_element = anchor) {
        const tooltip = document.getElementById("sight-preview-tooltip");
        if (!tooltip || !anchor || !text) return;
        this._hide_preview_tooltip();
        const described_target = described_element?.setAttribute ? described_element : anchor;
        const card = anchor.closest(".small-card");
        if (card?.hasAttribute("title")) {
            this._preview_tooltip_card = card;
            this._preview_tooltip_card_title = card.getAttribute("title") || "";
            card.removeAttribute("title");
        }
        tooltip.textContent = text;
        tooltip.hidden = false;
        described_target.setAttribute("aria-describedby", "sight-preview-tooltip");
        const anchor_rect = anchor.getBoundingClientRect();
        const tooltip_rect = tooltip.getBoundingClientRect();
        const viewport_padding = 12;
        const left = Math.min(
            window.innerWidth - tooltip_rect.width - viewport_padding,
            Math.max(viewport_padding, anchor_rect.left + (anchor_rect.width - tooltip_rect.width) / 2)
        );
        const below_top = anchor_rect.bottom + 9;
        const top = below_top + tooltip_rect.height <= window.innerHeight - viewport_padding
            ? below_top
            : Math.max(viewport_padding, anchor_rect.top - tooltip_rect.height - 9);
        tooltip.style.left = `${Math.round(left)}px`;
        tooltip.style.top = `${Math.round(top)}px`;
    },

    _hide_preview_tooltip() {
        const tooltip = document.getElementById("sight-preview-tooltip");
        if (tooltip) {
            tooltip.hidden = true;
            tooltip.style.left = "";
            tooltip.style.top = "";
        }
        document.querySelectorAll("#page-sightinfo [aria-describedby='sight-preview-tooltip']").forEach((anchor) => anchor.removeAttribute("aria-describedby"));
        if (this._preview_tooltip_card) this._preview_tooltip_card.setAttribute("title", this._preview_tooltip_card_title);
        this._preview_tooltip_card = null;
        this._preview_tooltip_card_title = "";
    },

    _fit_card_previews() {
        document.querySelectorAll("#page-sightinfo [data-sight-preview-viewport]").forEach((viewport) => {
            if (!viewport.clientWidth || viewport.closest("[hidden]")) return;
            const is_detail = viewport.hasAttribute("data-sight-preview-detail-viewport");
            const scale_limit = is_detail ? SIGHT_PREVIEW_DETAIL_SCALE : SIGHT_PREVIEW_SIDEBAR_SCALE;
            const width_scale = viewport.clientWidth / SIGHT_PREVIEW_CARD_WIDTH;
            const height_scale = is_detail && viewport.clientHeight ? viewport.clientHeight / SIGHT_PREVIEW_CARD_HEIGHT : scale_limit;
            const preview_scale = Math.max(0.1, Math.min(scale_limit, width_scale, height_scale));
            viewport.style.setProperty("--sight-preview-scale", preview_scale.toFixed(4));
            viewport.style.height = is_detail ? "" : `${Math.ceil(SIGHT_PREVIEW_CARD_HEIGHT * preview_scale)}px`;
            if (is_detail) this._set_text("sight-preview-page-scale", `${SIGHT_PREVIEW_CARD_WIDTH} × ${SIGHT_PREVIEW_CARD_HEIGHT} · 等比 ${Math.round(preview_scale * 100)}%`);
        });
    },

    _render_card_preview() {
        const preview_data = this._preview_card_data();
        const single_preview = document.getElementById("sight-card-preview");
        const package_preview = document.getElementById("sight-package-card-preview");
        if (single_preview) single_preview.innerHTML = this._render_runtime_single_card(preview_data);
        if (package_preview) package_preview.innerHTML = this._render_runtime_package_card(preview_data);
        const detail_page = document.getElementById("sight-preview-page");
        const detail_stage = document.getElementById("sight-preview-detail-stage");
        if (detail_stage && detail_page && !detail_page.hidden) {
            detail_stage.innerHTML = this._preview_kind === "package"
                ? this._render_runtime_package_card(preview_data, { openable: false })
                : this._render_runtime_single_card(preview_data, { openable: false });
        }
        requestAnimationFrame(() => this._fit_card_previews());
    },

    _set_active_tab(tab_name, persist = true) {
        const allowed = ["basic", "files", "groups", "cover", "advanced"];
        const next = allowed.includes(tab_name) ? tab_name : "basic";
        this._active_tab = next;
        document.querySelectorAll("#page-sightinfo [data-sight-tab]").forEach((tab) => {
            const active = tab.dataset.sightTab === next;
            tab.classList.toggle("active", active);
            tab.setAttribute("aria-selected", active ? "true" : "false");
        });
        document.querySelectorAll("#page-sightinfo [data-sight-panel]").forEach((panel) => {
            const active = panel.dataset.sightPanel === next;
            panel.classList.toggle("active", active);
            panel.hidden = !active;
        });
        if (persist) {
            this._ui_prefs.active_tab = next;
            this._save_ui_prefs();
        }
    },

    _sync_tags_from_ui() {
        if (!this._draft?.package) return;
        const categories = Array.from(document.querySelectorAll("#page-sightinfo [data-sight-category]:checked")).map((input) => input.value);
        const custom = this._split_list(document.getElementById("sight-custom-tags")?.value || "").filter((tag) => !SIGHT_CATEGORY_IDS.includes(tag.toLowerCase()));
        this._draft.package.tags = [...new Set([...categories, ...custom])];
    },

    _sync_current_project_row() {
        const row = this._projects.find((item) => item.project_name === this._project_name);
        if (!row || !this._draft) return;
        row.package_name = this._draft.package?.package_name || this._project_name;
        row.author = this._draft.package?.author || "";
        row.version = this._draft.package?.version || "";
        row.file_count = this._included_files().length;
        row.derived_type = row.file_count === 1 ? "single_sight" : "sight_package";
        row.has_cover = Boolean(this._draft.cover?.source_path);
        this._render_project_list();
    },

    _apply_file_batch() {
        if (!this._draft) return;
        const indexes = Array.from(document.querySelectorAll("#sight-file-editor [data-sight-batch-select]:checked")).map((input) => Number(input.dataset.fileIndex));
        if (!indexes.length) {
            this._app.notifyToast("warn", "请先勾选当前页需要批量编辑的 BLK");
            return;
        }
        const ammo_type = document.getElementById("sight-batch-ammo")?.value || "";
        const target_dir = String(document.getElementById("sight-batch-target-dir")?.value || "").trim().replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
        const resolution = String(document.getElementById("sight-batch-resolution")?.value || "").trim();
        const vehicles_text = String(document.getElementById("sight-batch-vehicles")?.value || "").trim();
        if (!ammo_type && !target_dir && !resolution && !vehicles_text) {
            this._app.notifyToast("warn", "请至少填写一个批量字段");
            return;
        }
        indexes.forEach((index) => {
            const row = this._draft.files[index];
            if (!row) return;
            const old_output_path = String(row.output_path || "");
            if (ammo_type) row.ammo_type = ammo_type;
            if (resolution) row.target_resolution = resolution;
            if (vehicles_text) row.recommended_vehicles = this._split_list(vehicles_text);
            if (target_dir) {
                const source_name = String(row.source_path || "").replace(/\\/g, "/").split("/").pop();
                const output_name = old_output_path.replace(/\\/g, "/").split("/").pop() || source_name || `sight_${index + 1}.blk`;
                row.output_path = `${target_dir}/${output_name}`;
                const old_key = old_output_path.toLowerCase();
                this._draft.groups.forEach((group) => {
                    group.files = (group.files || []).map((path) => String(path).toLowerCase() === old_key ? row.output_path : path);
                });
            }
        });
        this._mark_dirty();
        this._render_file_list();
        this._render_file_editor();
        this._render_assignment_editor();
        this._app.notifyToast("success", `已更新当前页所选的 ${indexes.length} 个 BLK`);
    },

    _add_group() {
        if (!this._draft) return;
        const next_index = this._draft.groups.length + 1;
        let group_id = `group_${next_index}`;
        const used = new Set(this._draft.groups.map((item) => String(item.group_id || "").toLowerCase()));
        while (used.has(group_id.toLowerCase())) group_id = `group_${next_index}_${Math.random().toString(36).slice(2, 6)}`;
        this._draft.groups.push({
            group_id,
            name: `分组 ${next_index}`,
            description: "",
            ammo_types: [],
            recommended_vehicles: [],
            recommended_apply_mode: "",
            primary_vehicle_id: "",
            compatible_vehicle_ids: [],
            target_resolutions: [],
            platforms: [],
            tags: [],
            featured: false,
            sort_order: next_index * 100,
            files: [],
            extra_meta: {}
        });
        this._mark_dirty();
        this._render_group_editor();
        this._render_assignment_editor();
        this._render_project_header();
    },

    async _delete_group(index) {
        const group = this._draft?.groups?.[index];
        if (!group) return;
        const confirmed = await this._app.showConfirmDialog({
            title: "删除作者分组",
            message: `删除“${group.name || group.group_id}”后，原来归入其中的 BLK 会变为未分组，文件本身不会被删除。`,
            confirmText: "删除分组",
            cancelText: "取消"
        });
        if (!confirmed) return;
        this._draft.groups.splice(index, 1);
        this._normalize_group_order();
        this._mark_dirty();
        this._render_group_editor();
        this._render_assignment_editor();
        this._render_project_header();
    },

    _move_group(index, direction) {
        const target = index + direction;
        if (!this._draft?.groups?.[index] || target < 0 || target >= this._draft.groups.length) return;
        const [group] = this._draft.groups.splice(index, 1);
        this._draft.groups.splice(target, 0, group);
        this._normalize_group_order();
        this._mark_dirty();
        this._render_group_editor();
        this._render_assignment_editor();
    },

    _normalize_group_order() {
        this._draft.groups.forEach((group, index) => {
            group.sort_order = (index + 1) * 100;
        });
    },

    _assign_file_group(output_path, group_id) {
        if (!output_path || !this._draft) return;
        const key = output_path.toLowerCase();
        this._draft.groups.forEach((group) => {
            group.files = (group.files || []).filter((path) => String(path).toLowerCase() !== key);
        });
        if (group_id) {
            const group = this._draft.groups.find((item) => item.group_id === group_id);
            if (group) group.files.push(output_path);
        }
        this._mark_dirty();
    },

    _mark_dirty() {
        this._validation_stale = true;
        this._set_dirty(this._stable_json(this._draft) !== this._baseline_json);
        this._render_project_header();
        this._render_report();
        this._render_card_preview();
        this._sync_action_state();
    },

    _set_dirty(value) {
        this._dirty = Boolean(value);
        const badge = document.getElementById("sight-dirty-badge");
        if (badge) badge.hidden = !this._dirty;
        this._sync_action_state();
    },

    async _confirm_leave_dirty(action_label) {
        if (!this._dirty) return true;
        const save_first = await this._app.showConfirmDialog({
            title: "当前项目有未保存修改",
            message: `${action_label}前，是否先保存当前炮镜项目？`,
            confirmText: "保存并继续",
            cancelText: "更多选择"
        });
        if (save_first) return await this._save_project(true);
        return await this._app.showConfirmDialog({
            title: "放弃未保存修改？",
            message: "继续后，当前尚未写入项目描述的修改会丢失；已经复制进项目的素材副本不受影响。",
            confirmText: "放弃修改并继续",
            cancelText: "返回编辑"
        });
    },

    async _with_loading(message, operation) {
        if (this._loading) return;
        this._set_loading(true, message);
        try {
            await operation();
        } catch (error) {
            console.error("sightinfo operation failed", error);
            this._app.notifyToast("warn", error?.message || "炮镜项目操作失败");
        } finally {
            this._set_loading(false, "");
        }
    },

    _set_loading(loading, message) {
        this._loading = Boolean(loading);
        const root = document.getElementById("sightinfo-shell");
        const layer = document.getElementById("sight-busy-layer");
        if (root) {
            root.classList.toggle("is-busy", this._loading);
            root.setAttribute("aria-busy", this._loading ? "true" : "false");
        }
        if (layer) layer.hidden = !this._loading;
        this._set_text("sight-busy-text", message || "正在处理…");
        this._sync_action_state();
    },

    _sync_action_state() {
        const has_project = Boolean(this._project_name && this._draft);
        const current_ids = ["btn-sight-open-project", "btn-sight-rename", "btn-sight-delete", "btn-sight-rescan", "btn-sight-validate", "btn-sight-analyze-all", "btn-sight-add-group", "btn-sight-select-cover"];
        current_ids.forEach((id) => {
            const button = document.getElementById(id);
            if (button) button.disabled = this._loading || !has_project;
        });
        ["btn-sight-new", "btn-sight-import-folder", "btn-sight-import-blk", "btn-sight-import-zip", "btn-sight-refresh-projects", "btn-sight-open-exports"].forEach((id) => {
            const button = document.getElementById(id);
            if (button) button.disabled = this._loading;
        });
        const save = document.getElementById("btn-sight-save");
        if (save) save.disabled = this._loading || !has_project || !this._dirty;
        const export_button = document.getElementById("btn-sight-export");
        if (export_button) {
            const can_export = has_project && !this._dirty && !this._validation_stale && Boolean(this._report?.valid);
            export_button.disabled = this._loading || !can_export;
            export_button.title = can_export ? "导出当前兼容检查已通过的项目" : "请先保存项目并通过兼容检查";
        }
        const clear = document.getElementById("btn-sight-clear-cover");
        if (clear) clear.disabled = this._loading || !has_project || !this._draft?.cover?.source_path;
    },

    _focus_report_issue(type, index) {
        const source = type === "error" ? this._report?.errors : type === "warning" ? this._report?.warnings : this._report?.info;
        const issue = source?.[index];
        if (!issue) return;
        const field = String(issue.field || "");
        let tab = "files";
        if (field.startsWith("package.")) tab = "basic";
        else if (field.startsWith("export.") || issue.code?.includes("meta_") || issue.code?.includes("migration")) tab = "advanced";
        else if (issue.group_id || issue.code?.startsWith("group_") || issue.code === "file_ungrouped") tab = "groups";
        else if (issue.code === "cover_missing" || issue.code === "link_missing") tab = "cover";
        this._set_active_tab(tab);
        if (field) requestAnimationFrame(() => document.querySelector(`#page-sightinfo [data-sight-field="${CSS.escape(field)}"]`)?.focus());
    },

    async _api_call(method, ...args) {
        const api = window.pywebview?.api;
        if (!api || typeof api[method] !== "function") {
            return { success: false, msg: "炮镜作者端后端尚未就绪", data: {}, errors: [], warnings: [] };
        }
        return await api[method](...args);
    },

    _notify_api_error(response, fallback) {
        const first_error = Array.isArray(response?.errors) ? response.errors.find((item) => item?.message) : null;
        this._app.notifyToast("warn", response?.msg || first_error?.message || fallback);
        if (response?.data?.report) {
            this._report = response.data.report;
            this._validation_stale = false;
            this._render_report();
            this._render_summary();
        }
    },

    _profile_defaults() {
        const profile = this._app?.state?.profile || {};
        const links = profile.links || {};
        return {
            package: {
                author: String(profile.name || ""),
                link_wtlive: String(links.wtlive || ""),
                link_bilibili: String(links.bilibili || "")
            }
        };
    },

    _filtered_file_rows() {
        const files = Array.isArray(this._draft?.files) ? this._draft.files : [];
        return files.map((item, index) => ({ item, index })).filter(({ item }) => {
            if (!this._file_query) return true;
            return `${item.display_name || ""} ${item.output_path || ""} ${item.source_path || ""}`.toLowerCase().includes(this._file_query);
        });
    },

    _included_files() {
        return Array.isArray(this._draft?.files) ? this._draft.files.filter((item) => item.include !== false) : [];
    },

    _scan_feedback(scan) {
        if (!scan) return "项目文件状态已重新扫描";
        const parts = [`识别 ${Number(scan.real_blk_count || 0)} 个真实 BLK`];
        if (scan.new_files?.length) parts.push(`新增 ${scan.new_files.length}`);
        if (scan.changed_files?.length) parts.push(`变化 ${scan.changed_files.length}`);
        if (scan.missing_files?.length) parts.push(`缺失 ${scan.missing_files.length}`);
        return parts.join("，");
    },

    _ammo_options_html(current_value) {
        const value = String(current_value || "");
        const known = SIGHT_AMMO_OPTIONS.some(([id]) => id === value);
        const rows = known || !value ? SIGHT_AMMO_OPTIONS : [...SIGHT_AMMO_OPTIONS, [value, `${value}（自定义）`]];
        return rows.map(([id, label]) => `<option value="${this._escape(id)}" ${id === value ? "selected" : ""}>${this._escape(label)}</option>`).join("");
    },

    _target_mode_label(mode) {
        const labels = { usersights_structure: "载具目录结构", specified_dir: "指定目录", single_folder: "单顶层目录", archive_folder: "ZIP 文件名目录" };
        return labels[mode] || "等待检查";
    },

    _issue_icon(type) {
        if (type === "error") return "ri-error-warning-line";
        if (type === "warning") return "ri-alert-line";
        return "ri-information-line";
    },

    _issue_detail(issue) {
        const detail = issue.path || issue.field || issue.group_id || issue.value || "";
        return detail ? `<small>${this._escape(this._field_text(detail))}</small>` : "";
    },

    _field_text(value) {
        if (value === null || value === undefined) return "";
        if (typeof value === "object") {
            try { return JSON.stringify(value); } catch (_error) { return String(value); }
        }
        return String(value);
    },

    _split_list(value) {
        const seen = new Set();
        return String(value || "").split(/[,，、;；\n]+/).map((item) => item.trim()).filter((item) => {
            const key = item.toLowerCase();
            if (!item || seen.has(key)) return false;
            seen.add(key);
            return true;
        });
    },

    _join_list(value) {
        return Array.isArray(value) ? value.join(", ") : "";
    },

    _get_by_path(target, path) {
        return String(path || "").split(".").reduce((value, key) => value && value[key] !== undefined ? value[key] : "", target);
    },

    _set_by_path(target, path, value) {
        const keys = String(path || "").split(".").filter(Boolean);
        if (!keys.length) return;
        let cursor = target;
        keys.slice(0, -1).forEach((key) => {
            if (!cursor[key] || typeof cursor[key] !== "object" || Array.isArray(cursor[key])) cursor[key] = {};
            cursor = cursor[key];
        });
        cursor[keys[keys.length - 1]] = value;
    },

    _clone(value) {
        return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
    },

    _stable_json(value) {
        try { return JSON.stringify(value); } catch (_error) { return ""; }
    },

    _escape(value) {
        return this._app?.escapeHtml ? this._app.escapeHtml(String(value ?? "")) : String(value ?? "");
    },

    _set_text(id, value) {
        const element = document.getElementById(id);
        if (element) element.textContent = String(value ?? "");
    },

    _load_ui_prefs() {
        try {
            const parsed = JSON.parse(localStorage.getItem(SIGHT_UI_STORAGE_KEY) || "{}");
            this._ui_prefs = parsed && typeof parsed === "object" ? parsed : {};
        } catch (_error) {
            this._ui_prefs = {};
        }
    },

    _save_ui_prefs() {
        try {
            localStorage.setItem(SIGHT_UI_STORAGE_KEY, JSON.stringify(this._ui_prefs));
        } catch (_error) {
            // UI 偏好写入失败不影响项目数据
        }
    }
};
