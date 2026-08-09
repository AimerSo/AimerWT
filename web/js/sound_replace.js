(function () {
    if (!window.app) return;

    const app = window.app;

    function t(key, params) {
        return typeof app.t === 'function' ? app.t(key, params) : key;
    }

    function escapeHtml(value) {
        if (typeof app._escapeHtml === 'function') return app._escapeHtml(value);
        return String(value || '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    function notify(level, title, message) {
        if (level === 'error' && typeof app.showErrorToast === 'function') {
            app.showErrorToast(title, message);
            return;
        }
        if (level === 'warn' && typeof app.showWarnToast === 'function') {
            app.showWarnToast(title, message);
            return;
        }
        if (typeof app.showInfoToast === 'function') {
            app.showInfoToast(title, message);
            return;
        }
        if (typeof app.showToast === 'function') {
            app.showToast(message, level === 'error' ? 'error' : 'success');
        }
    }

    function getSoundStateErrorMessage(result, fallbackKey) {
        if (result?.error_code === 'manifest_corrupt') {
            return t('sound_replace.manifest_corrupt_help');
        }
        if (result?.error_code === 'pending_conflict') {
            return t('sound_replace.pending_conflict_help');
        }
        return result?.error || result?.msg || t(fallbackKey);
    }

    function closeDynamicModal(modalId) {
        const modal = document.getElementById(modalId);
        if (!modal) return;
        modal.classList.add('hiding');
        setTimeout(() => modal.remove(), 180);
    }

    function showChoiceDialog({ modalId, title, subtitle, options, confirmText }) {
        return new Promise((resolve) => {
            const existing = document.getElementById(modalId);
            if (existing) existing.remove();

            const overlay = document.createElement('div');
            overlay.id = modalId;
            overlay.className = 'modal-overlay show';
            const optionHtml = options.map((option, index) => `
                <button type="button" class="option-card${index === 0 ? ' active' : ''}" data-value="${escapeHtml(option.value)}">
                    <div class="option-card-icon"><i class="${escapeHtml(option.icon)}"></i></div>
                    <div class="option-card-content">
                        <div class="option-card-title">${escapeHtml(option.label)}</div>
                        <div class="option-card-desc">${escapeHtml(option.desc)}</div>
                    </div>
                </button>
            `).join('');

            overlay.innerHTML = `
                <div class="modal-content" style="max-width: 560px; text-align: left;">
                    <h2 style="margin-top: 0;">${escapeHtml(title)}</h2>
                    <div class="subtitle" style="margin-bottom: 18px; color: var(--text-sec); font-size: 13px; line-height: 1.5;">${subtitle}</div>
                    <div style="display: grid; gap: 12px;">${optionHtml}</div>
                    <div class="modal-actions" style="margin-top: 20px;">
                        <button type="button" class="btn secondary" data-action="cancel">${escapeHtml(t('common.cancel'))}</button>
                        <button type="button" class="btn primary" data-action="confirm">
                            <i class="ri-check-line"></i> <span>${escapeHtml(confirmText || t('common.confirm'))}</span>
                        </button>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);

            let selected = options[0]?.value || null;
            overlay.querySelectorAll('.option-card').forEach((btn) => {
                btn.addEventListener('click', () => {
                    overlay.querySelectorAll('.option-card').forEach((item) => item.classList.remove('active'));
                    btn.classList.add('active');
                    selected = btn.dataset.value || null;
                });
            });

            const finish = (value) => {
                closeDynamicModal(modalId);
                resolve(value);
            };
            overlay.querySelector('[data-action="cancel"]').addEventListener('click', () => finish(null));
            overlay.querySelector('[data-action="confirm"]').addEventListener('click', () => finish(selected));
            overlay.addEventListener('click', (event) => {
                if (event.target === overlay) finish(null);
            });
        });
    }

    app.showInstallModeDialog = async function (mod) {
        const mode = await showChoiceDialog({
            modalId: 'modal-sound-install-mode',
            title: t('sound_replace.install_mode_title'),
            subtitle: t('sound_replace.install_mode_subtitle', { name: mod?.title || mod?.id || '' }),
            confirmText: t('sound_replace.continue'),
            options: [
                {
                    value: 'official_mod',
                    icon: 'ri-shield-check-line',
                    label: t('sound_replace.official_mode'),
                    desc: t('sound_replace.official_mode_desc'),
                },
                {
                    value: 'sound_replace',
                    icon: 'ri-alert-line',
                    label: t('sound_replace.sound_mode'),
                    desc: t('sound_replace.sound_mode_desc'),
                },
            ],
        });
        if (mode !== 'sound_replace') return mode;
        const accepted = await app.ensureSoundReplaceDisclaimerAccepted();
        return accepted ? 'sound_replace' : null;
    };

    app.ensureSoundReplaceDisclaimerAccepted = async function () {
        const api = window.pywebview?.api;
        if (!api?.check_sound_replace_disclaimer || !api?.accept_sound_replace_disclaimer) {
            notify('error', t('common.error'), t('common.feature_not_ready'));
            return false;
        }
        try {
            const status = await api.check_sound_replace_disclaimer();
            if (status?.accepted) return true;
        } catch (error) {
            notify('error', t('common.error'), t('common.call_failed', { message: error?.message || error }));
            return false;
        }

        return new Promise((resolve) => {
            const modalId = 'modal-sound-replace-disclaimer';
            const existing = document.getElementById(modalId);
            if (existing) existing.remove();

            const overlay = document.createElement('div');
            overlay.id = modalId;
            overlay.className = 'modal-overlay show';
            overlay.innerHTML = `
                <div class="modal-content" style="max-width: 620px; text-align: left;">
                    <h2 style="margin-top: 0; color: var(--danger);">${escapeHtml(t('sound_replace.disclaimer_title'))}</h2>
                    <p class="subtitle">${escapeHtml(t('sound_replace.disclaimer_subtitle'))}</p>
                    <div style="background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.22); border-radius: 8px; padding: 14px; line-height: 1.65; color: var(--text-main);">
                        ${t('sound_replace.disclaimer_html')}
                    </div>
                    <label style="display: block; margin-top: 16px; font-size: 13px; color: var(--text-sec);">
                        ${escapeHtml(t('sound_replace.type_yes_label'))}
                    </label>
                    <input id="sound-replace-yes-input" type="text" autocomplete="off" style="width: 100%; margin-top: 8px; height: 38px; border-radius: 8px; border: 1px solid var(--border-color); background: var(--input-bg); color: var(--text-main); padding: 0 12px;">
                    <div class="modal-actions" style="margin-top: 20px;">
                        <button type="button" class="btn secondary" data-action="cancel">${escapeHtml(t('common.cancel'))}</button>
                        <button type="button" class="btn danger" data-action="confirm" disabled>
                            <i class="ri-alert-line"></i> <span>${escapeHtml(t('sound_replace.accept_risk'))}</span>
                        </button>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);

            const input = overlay.querySelector('#sound-replace-yes-input');
            const confirmBtn = overlay.querySelector('[data-action="confirm"]');
            const finish = (value) => {
                closeDynamicModal(modalId);
                resolve(value);
            };

            input.addEventListener('input', () => {
                confirmBtn.disabled = input.value.trim().toLowerCase() !== 'yes';
            });
            overlay.querySelector('[data-action="cancel"]').addEventListener('click', () => finish(false));
            confirmBtn.addEventListener('click', async () => {
                try {
                    const result = await api.accept_sound_replace_disclaimer(true);
                    finish(!!result?.success);
                } catch (error) {
                    notify('error', t('common.error'), t('common.call_failed', { message: error?.message || error }));
                    finish(false);
                }
            });
            setTimeout(() => input.focus(), 60);
        });
    };

    app.confirmSoundReplaceInstall = async function (allFiles) {
        const api = window.pywebview?.api;
        if (!api?.preview_sound_replace_install || !api?.install_sound_replace) {
            notify('error', t('common.error'), t('common.feature_not_ready'));
            return;
        }

        let preview = null;
        try {
            preview = await api.preview_sound_replace_install(app.currentModId, JSON.stringify(allFiles || []));
        } catch (error) {
            notify('error', t('common.error'), t('common.call_failed', { message: error?.message || error }));
            return;
        }
        if (!preview?.success) {
            app.showAlert(
                t('common.error'),
                getSoundStateErrorMessage(preview, 'sound_replace.preview_failed'),
                'error'
            );
            return;
        }
        if (!preview.installable_count) {
            app.showAlert(t('common.info'), t('sound_replace.no_matching_targets'), 'warn');
            return;
        }

        const backupBytes = preview.backup_size_bytes || 0;
        const diskFreeKnown = !!preview.backup_disk_free_known;
        const diskFreeBytes = Number(preview.backup_disk_free_bytes || 0);
        const soundBankBytes = preview.sound_bank_size_bytes || 0;
        const existingUnbackedCount = preview.backup_skipped_existing_count || 0;
        const fmt = typeof app._formatBytes === 'function' ? app._formatBytes : (b) => `${(b / 1024 / 1024).toFixed(1)} MB`;
        const backupSizeText = fmt(backupBytes);
        const diskFreeText = diskFreeKnown ? fmt(diskFreeBytes) : t('sound_replace.backup_space_unknown');
        const soundBankText = fmt(soundBankBytes);
        const spaceEnough = !diskFreeKnown || diskFreeBytes > backupBytes * 1.1;

        let skipBackup = false;
        const cleanPath = (function (p) {
            if (!p) return '';
            let clean = p.replace(/\\/g, '/');
            while (clean.includes('/../')) {
                clean = clean.replace(/[^/]+\/\.\.\//, '');
            }
            clean = clean.replace(/\/\.\//g, '/');
            return clean.replace(/\//g, '\\');
        })(preview.backup_dir || '');

        const pathJsEscaped = cleanPath.replace(/\\/g, '\\\\').replace(/'/g, "\\'");

        const unbackedHtml = existingUnbackedCount > 0
            ? `<div style="margin-top: 10px; background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.2); border-radius: 8px; padding: 8px 12px; display: flex; align-items: center; gap: 8px; font-size: 12px; color: #d97706;">` +
              `<i class="ri-alert-line" style="font-size: 15px; flex-shrink: 0;"></i>` +
              `<span style="line-height: 1.45;">检测到已有备份，覆盖将更新备份文件。已跳过 ${existingUnbackedCount} 个不重复文件的二次备份。</span>` +
              `</div>`
            : '';

        const subtitleHtml = `
            <div style="font-size: 13px; color: var(--text-sec); line-height: 1.5; margin-bottom: 12px;">
                在替换游戏 Sound 源文件前，建议您创建备份以支持一键还原。
            </div>
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 12px;">
                <div style="background: var(--card-bg, #ffffff); border: 1px solid var(--border-color, #e2e8f0); border-radius: 8px; padding: 10px; display: flex; flex-direction: column; gap: 2px; box-shadow: 0 1px 2px rgba(0,0,0,0.02);">
                    <span style="font-size: 10px; color: var(--text-sec); text-transform: uppercase; letter-spacing: 0.5px;">变更文件</span>
                    <span style="font-size: 13px; font-weight: 600; color: var(--text-main);">替换 ${preview.installable_count} <span style="font-weight: normal; font-size: 11px; color: var(--text-sec);">/ 跳过 ${preview.skipped_count || 0}</span></span>
                </div>
                <div style="background: var(--card-bg, #ffffff); border: 1px solid var(--border-color, #e2e8f0); border-radius: 8px; padding: 10px; display: flex; flex-direction: column; gap: 2px; box-shadow: 0 1px 2px rgba(0,0,0,0.02);">
                    <span style="font-size: 10px; color: var(--text-sec); text-transform: uppercase; letter-spacing: 0.5px;">预计新增 / 盘余</span>
                    <span style="font-size: 13px; font-weight: 600; color: #10b981;">${backupSizeText} <span style="font-weight: normal; font-size: 11px; color: var(--text-sec);">/ ${diskFreeText}</span></span>
                </div>
            </div>
            <div style="background: var(--input-bg, #f1f5f9); border: 1px solid var(--border-color, #e2e8f0); border-radius: 8px; padding: 8px 12px; display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 12px; box-shadow: inset 0 1px 2px rgba(0,0,0,0.01);">
                <div style="display: flex; flex-direction: column; min-width: 0; flex: 1;">
                    <span style="font-size: 10px; color: var(--text-sec); margin-bottom: 1px;">备份存储位置</span>
                    <div style="font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 11px; color: var(--text-main); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; direction: rtl; text-align: left;" title="${escapeHtml(cleanPath)}">
                        ${escapeHtml(cleanPath)}
                    </div>
                </div>
                <button type="button" class="btn secondary" onclick="navigator.clipboard.writeText('${pathJsEscaped}').then(() => { if(typeof app.showToast==='function') app.showToast('备份路径已复制到剪贴板', 'success'); else alert('已复制！'); })" style="padding: 4px 8px; font-size: 11px; height: auto; display: flex; align-items: center; gap: 4px; border-radius: 6px; flex-shrink: 0; background: var(--card-bg, #ffffff); border: 1px solid var(--border-color, #e2e8f0); cursor: pointer; color: var(--text-main);">
                    <i class="ri-file-copy-line" style="font-size: 12px;"></i>复制
                </button>
            </div>
            ${unbackedHtml}
        `;
        const backupChoice = await showChoiceDialog({
            modalId: 'modal-sound-backup-choice',
            title: t('sound_replace.backup_choice_title'),
            subtitle: subtitleHtml,
            confirmText: t('sound_replace.continue'),
            options: [
                {
                    value: 'with_backup',
                    icon: 'ri-save-3-line',
                    label: t('sound_replace.backup_choice_with_backup'),
                    desc: spaceEnough
                        ? t('sound_replace.backup_choice_with_backup_desc')
                        : t('sound_replace.backup_choice_with_backup_low_space_desc'),
                },
                {
                    value: 'skip_backup',
                    icon: 'ri-alert-line',
                    label: t('sound_replace.backup_choice_without_backup'),
                    desc: t('sound_replace.backup_choice_without_backup_desc'),
                },
            ],
        });
        if (!backupChoice) return;
        if (backupChoice === 'skip_backup') {
            skipBackup = await app.showSkipBackupConfirm(preview, backupSizeText, diskFreeText);
            if (!skipBackup) return;
        }

        if (typeof MinimalistLoading !== 'undefined') {
            MinimalistLoading.show(false, t('sound_replace.install_preparing'));
        }
        const result = await api.install_sound_replace(app.currentModId, JSON.stringify(allFiles || []), skipBackup);
        if (!result?.success) {
            if (typeof MinimalistLoading !== 'undefined') MinimalistLoading.hide();
            notify('error', t('common.error'), getSoundStateErrorMessage(result, 'sound_replace.install_start_failed'));
            return;
        }
        app.closeModal('modal-install');
    };

    app.showSkipBackupConfirm = function (preview, backupSizeText, diskFreeText) {
        return new Promise((resolve) => {
            const modalId = 'modal-skip-backup-confirm';
            const existing = document.getElementById(modalId);
            if (existing) existing.remove();

            const overlay = document.createElement('div');
            overlay.id = modalId;
            overlay.className = 'modal-overlay show';
            overlay.innerHTML = `
                <div class="modal-content" style="max-width: 620px; text-align: left;">
                    <h2 style="margin-top: 0; color: var(--danger);">${escapeHtml(t('sound_replace.skip_backup_title'))}</h2>
                    <p class="subtitle">${escapeHtml(t('sound_replace.skip_backup_subtitle'))}</p>
                    <div style="background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.22); border-radius: 8px; padding: 14px; line-height: 1.65; color: var(--text-main);">
                        ${t('sound_replace.skip_backup_html', { size: escapeHtml(backupSizeText), free: escapeHtml(diskFreeText), count: preview.installable_count || 0 })}
                    </div>
                    <label style="display: block; margin-top: 16px; font-size: 13px; color: var(--text-sec);">
                        ${escapeHtml(t('sound_replace.skip_backup_yes_label'))}
                    </label>
                    <input id="skip-backup-yes-input" type="text" autocomplete="off" style="width: 100%; margin-top: 8px; height: 38px; border-radius: 8px; border: 1px solid var(--border-color); background: var(--input-bg); color: var(--text-main); padding: 0 12px;">
                    <div class="modal-actions" style="margin-top: 20px;">
                        <button type="button" class="btn secondary" data-action="cancel">${escapeHtml(t('common.cancel'))}</button>
                        <button type="button" class="btn danger" data-action="confirm" disabled>
                            <i class="ri-alert-line"></i> <span>${escapeHtml(t('sound_replace.skip_backup_confirm_btn'))}</span>
                        </button>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);

            const input = overlay.querySelector('#skip-backup-yes-input');
            const confirmBtn = overlay.querySelector('[data-action="confirm"]');
            const finish = (value) => {
                closeDynamicModal(modalId);
                resolve(value);
            };

            input.addEventListener('input', () => {
                confirmBtn.disabled = input.value.trim().toLowerCase() !== 'yes';
            });
            overlay.querySelector('[data-action="cancel"]').addEventListener('click', () => finish(false));
            confirmBtn.addEventListener('click', () => finish(true));
            overlay.addEventListener('click', (event) => {
                if (event.target === overlay) finish(false);
            });
            setTimeout(() => input.focus(), 60);
        });
    };

    app.onSoundInstallResult = function (result) {
        if (result?.partial_success) {
            notify('warn', t('common.warn'), t('sound_replace.install_partial', {
                replaced: result.replaced || 0,
                failed: result.failed || 0,
            }));
            return;
        }
        if (result?.success) {
            notify('info', t('common.success'), t('sound_replace.install_success', { count: result.replaced || 0 }));
            return;
        }
        notify('error', t('common.error'), getSoundStateErrorMessage(result, 'sound_replace.install_failed'));
    };

    app.showRestoreModeDialog = async function () {
        const api = window.pywebview?.api;
        if (!api?.get_restore_options) return 'official_mod';
        let options = null;
        try {
            options = await api.get_restore_options();
        } catch (error) {
            return 'official_mod';
        }
        if (!options?.success) return 'official_mod';

        const hasSoundBackup = !!options.sound_replace?.available;
        const soundDesc = hasSoundBackup
            ? t('sound_replace.restore_sound_desc', { count: options.sound_replace.active_count || 0 })
            : t('sound_replace.restore_sound_unavailable_desc');

        return showChoiceDialog({
            modalId: 'modal-sound-restore-mode',
            title: t('sound_replace.restore_mode_title'),
            subtitle: t('sound_replace.restore_mode_subtitle'),
            confirmText: t('modal.confirm_restore'),
            options: [
                {
                    value: 'official_mod',
                    icon: 'ri-folder-reduce-line',
                    label: t('sound_replace.restore_official'),
                    desc: t('sound_replace.restore_official_desc'),
                },
                {
                    value: 'sound_replace',
                    icon: 'ri-reset-left-line',
                    label: t('sound_replace.restore_sound'),
                    desc: soundDesc,
                },
                {
                    value: 'all',
                    icon: 'ri-refresh-line',
                    label: t('sound_replace.restore_all'),
                    desc: t('sound_replace.restore_all_desc'),
                },
            ],
        });
    };

    app.getRestoreConfirmMessage = function (restoreMode) {
        if (restoreMode === 'sound_replace') return t('sound_replace.restore_sound_confirm');
        if (restoreMode === 'all') return t('sound_replace.restore_all_confirm');
        return t('settings.restore_confirm_message');
    };

    app.onSoundRestoreResult = async function (result) {
        if (result?.error_code === 'manifest_corrupt' || result?.error_code === 'pending_conflict') {
            notify('error', t('common.error'), getSoundStateErrorMessage(result, 'sound_replace.restore_failed'));
            return;
        }
        const restored = result?.restored || 0;
        const skipped = result?.skipped || 0;
        const skippedFiles = Array.isArray(result?.skipped_files) ? result.skipped_files : [];
        const staleReasons = new Set(['target_changed_externally', 'target_missing', 'backup_missing']);
        const staleSkippedCount = skippedFiles.filter((item) => staleReasons.has(item?.reason)).length;
        const backupSkippedCount = skippedFiles.filter((item) => item?.reason === 'backup_skipped').length;
        if (staleSkippedCount > 0) {
            notify('warn', t('common.warn'), t('sound_replace.restore_stale_skipped', {
                restored,
                skipped: staleSkippedCount,
            }));
            const api = window.pywebview?.api;
            if (api?.clear_sound_replace_stale_records && typeof app.confirm === 'function') {
                const shouldClear = await app.confirm(
                    t('sound_replace.clear_stale_title'),
                    t('sound_replace.clear_stale_confirm'),
                    true
                );
                if (shouldClear) {
                    try {
                        const clearResult = await api.clear_sound_replace_stale_records(true, true);
                        if (clearResult?.success) {
                            notify('info', t('common.success'), t('sound_replace.clear_stale_success', {
                                count: clearResult.cleared || 0,
                                backups: clearResult.removed_backups || 0,
                            }));
                        } else {
                            notify('error', t('common.error'), clearResult?.msg || t('sound_replace.clear_stale_failed'));
                        }
                    } catch (error) {
                        notify('error', t('common.error'), t('common.call_failed', { message: error?.message || error }));
                    }
                }
            }
            return;
        }
        if (backupSkippedCount > 0) {
            notify('warn', t('common.warn'), t('sound_replace.restore_backup_skipped', {
                restored,
                skipped: backupSkippedCount,
            }));
            const api = window.pywebview?.api;
            if (api?.clear_sound_replace_skipped_records && typeof app.confirm === 'function') {
                const shouldClear = await app.confirm(
                    t('sound_replace.clear_unbacked_title'),
                    t('sound_replace.clear_unbacked_confirm'),
                    true
                );
                if (shouldClear) {
                    try {
                        const clearResult = await api.clear_sound_replace_skipped_records();
                        if (clearResult?.success) {
                            notify('info', t('common.success'), t('sound_replace.clear_unbacked_success', { count: clearResult.cleared || 0 }));
                        } else {
                            notify('error', t('common.error'), clearResult?.msg || t('sound_replace.clear_unbacked_failed'));
                        }
                    } catch (error) {
                        notify('error', t('common.error'), t('common.call_failed', { message: error?.message || error }));
                    }
                }
            }
            return;
        }
        if (result?.success && skipped > 0) {
            notify('warn', t('common.warn'), t('sound_replace.restore_partial_skipped', { restored, skipped }));
            return;
        }
        if (result?.success) {
            notify('info', t('common.success'), t('sound_replace.restore_success', { count: restored }));
            return;
        }
        if (skipped > 0 && restored === 0) {
            notify('warn', t('common.warn'), t('sound_replace.restore_all_skipped', { skipped }));
            return;
        }
        if (!restored && !skipped && !(result?.failed > 0) && result?.msg) {
            notify('warn', t('common.warn'), result.msg);
            return;
        }
        notify('error', t('common.error'), result?.msg || t('sound_replace.restore_failed'));
    };
})();
