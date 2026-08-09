(function () {
    function normalizeCode(value) {
        return String(value || '').trim();
    }

    function getThemeByFile(themeFile) {
        const list = Array.isArray(app.themeListData) ? app.themeListData : [];
        return list.find((item) => item.filename === themeFile) || null;
    }

    const redeemTypeDefaults = {
        sponsor_1: { style: 'style_sponsor_1', subtitle: '· 感谢支持 ·', button: '我们是好朋友', iconColor: '#64748b', badgeText: 'SUPPORTER · LEVEL 1' },
        sponsor_2: { style: 'style_sponsor_2', subtitle: '· 感谢支持 ·', button: '永远的好朋友', iconColor: '#0d9488', badgeText: 'SUPPORTER · LEVEL 2' },
        sponsor_3: { style: 'style_sponsor_3', subtitle: '· 感谢支持 ·', button: '永远的好朋友', iconColor: '#e8c9a0', badgeText: 'SUPPORTER · LEVEL 3' },
        sponsor_4: { style: 'style_sponsor_4', subtitle: '· 感谢支持 ·', button: '永远的好朋友', iconColor: '#fde68a', badgeText: 'SUPPORTER · LEVEL 4' },
        streamer: { style: 'style_streamer', subtitle: '· 专属福利 ·', button: '确认领取', iconColor: '#fcd34d', badgeText: 'STREAMER EXCLUSIVE' },
        streamer_share: { style: 'style_streamer_share', subtitle: '· 分享福利 ·', button: '好的', iconColor: '#fde68a', badgeText: 'STREAMER SHARE' },
        custom: { style: 'style_sponsor_1', subtitle: '· 感谢支持 ·', button: '确定', iconColor: '#64748b', badgeText: '' },
    };

    const redeemStyleDefaults = {
        style_sponsor_1: { subtitle: '· 感谢支持 ·', button: '我们是好朋友', iconColor: '#64748b', badgeText: 'SUPPORTER · LEVEL 1' },
        style_sponsor_2: { subtitle: '· 感谢支持 ·', button: '永远的好朋友', iconColor: '#0d9488', badgeText: 'SUPPORTER · LEVEL 2' },
        style_sponsor_3: { subtitle: '· 感谢支持 ·', button: '永远的好朋友', iconColor: '#e8c9a0', badgeText: 'SUPPORTER · LEVEL 3' },
        style_sponsor_4: { subtitle: '· 感谢支持 ·', button: '永远的好朋友', iconColor: '#fde68a', badgeText: 'SUPPORTER · LEVEL 4' },
        style_streamer: { subtitle: '· 专属福利 ·', button: '确认领取', iconColor: '#fcd34d', badgeText: 'STREAMER EXCLUSIVE' },
        style_streamer_share: { subtitle: '· 分享福利 ·', button: '好的', iconColor: '#fde68a', badgeText: 'STREAMER SHARE' },
    };

    const redeemLogoSvgMap = {
        gift: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 12 20 22 4 22 4 12"/><rect x="2" y="7" width="20" height="5"/><line x1="12" y1="22" x2="12" y2="7"/><path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z"/><path d="M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"/></svg>',
        star: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
        crown: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 4l3 12h14l3-12-6 7-4-9-4 9-6-7z"/><path d="M3 20h18"/></svg>',
        trophy: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h2"/><path d="M18 9h2a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2h-2"/><path d="M6 3h12v7a6 6 0 0 1-12 0V3z"/><path d="M12 16v2"/><path d="M8 22h8"/><path d="M8 22v-2h8v2"/></svg>',
        mic: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="8" y1="22" x2="16" y2="22"/></svg>',
        users: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
        heart: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>',
        shield: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
        diamond: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h12l4 6-10 13L2 9z"/><path d="M2 9h20"/><path d="M10 3l-4 6 6 13 6-13-4-6"/></svg>',
        rocket: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>',
        zap: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
        music: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>',
        camera: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>',
        bookmark: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>',
        compass: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>',
        feather: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20.24 12.24a6 6 0 0 0-8.49-8.49L5 10.5V19h8.5z"/><line x1="16" y1="8" x2="2" y2="22"/><line x1="17.5" y1="15" x2="9" y2="15"/></svg>',
        coffee: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/><line x1="6" y1="1" x2="6" y2="4"/><line x1="10" y1="1" x2="10" y2="4"/><line x1="14" y1="1" x2="14" y2="4"/></svg>',
        award: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/></svg>',
        hexagon: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>',
        sun: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>',
    };

    const redeemStyleTemplates = {
        style_sponsor_1: `<!-- 支持者一级 — 简洁清新风格 -->
<div style="width:360px; max-width:min(92vw,360px); background:#fff; border-radius:16px; overflow:hidden; box-shadow:0 20px 60px rgba(0,0,0,0.3); font-family:'Inter','PingFang SC','Microsoft YaHei',sans-serif;">
    <div style="height:4px; background:linear-gradient(90deg,#94a3b8,#cbd5e1);"></div>
    <div style="padding:32px 28px 28px; text-align:center;">
        <div style="margin:0 auto 20px; width:48px; height:48px; border-radius:12px; border:1.5px solid #cbd5e1; display:flex; align-items:center; justify-content:center;">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{{ICON_COLOR}}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 12 20 22 4 22 4 12"/><rect x="2" y="7" width="20" height="5"/>
                <line x1="12" y1="22" x2="12" y2="7"/><path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z"/>
                <path d="M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"/>
            </svg>
        </div>
        <div style="font-size:18px; font-weight:700; color:#1e293b; margin-bottom:6px;">{{TITLE}}</div>
        <div style="font-size:12px; color:#94a3b8; margin-bottom:4px; letter-spacing:0.5px;">{{BADGE_TEXT}}</div>
        <div style="font-size:13px; color:#94a3b8; margin-bottom:20px; letter-spacing:1px;">{{SUBTITLE}}</div>
        <div style="background:#f8fafc; border-radius:10px; padding:14px 16px; text-align:left; margin-bottom:20px;">
            {{REWARDS}}
        </div>
        <button style="width:100%; padding:10px; border:none; border-radius:10px; background:#64748b; color:#fff; font-size:14px; font-weight:600; cursor:pointer;">{{BUTTON}}</button>
    </div>
</div>`,
        style_sponsor_2: `<!-- 支持者二级 — 精致沉稳风格 -->
<div style="width:360px; max-width:min(92vw,360px); background:#fff; border-radius:16px; overflow:hidden; box-shadow:0 20px 60px rgba(0,0,0,0.3); font-family:'Inter','PingFang SC','Microsoft YaHei',sans-serif;">
    <div style="height:4px; background:linear-gradient(90deg,#0d9488,#2dd4bf);"></div>
    <div style="padding:32px 28px 28px; text-align:center;">
        <div style="margin:0 auto 20px; width:52px; height:52px; border-radius:14px; border:1.5px solid #99f6e4; background:rgba(13,148,136,0.04); display:flex; align-items:center; justify-content:center;">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="{{ICON_COLOR}}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
            </svg>
        </div>
        <div style="font-size:19px; font-weight:700; color:#0f172a; margin-bottom:6px;">{{TITLE}}</div>
        <div style="font-size:12px; color:#0d9488; margin-bottom:4px; letter-spacing:0.5px; font-weight:500;">{{BADGE_TEXT}}</div>
        <div style="font-size:13px; color:#0d9488; margin-bottom:20px; letter-spacing:1px;">{{SUBTITLE}}</div>
        <div style="background:#f0fdfa; border:1px solid #ccfbf1; border-radius:10px; padding:14px 16px; text-align:left; margin-bottom:20px;">
            {{REWARDS}}
        </div>
        <button style="width:100%; padding:11px; border:none; border-radius:10px; background:linear-gradient(135deg,#0d9488,#14b8a6); color:#fff; font-size:14px; font-weight:600; cursor:pointer;">{{BUTTON}}</button>
    </div>
</div>`,
        style_sponsor_3: `<!-- 支持者三级 — 琥珀风格 -->
<div style="width:370px; max-width:min(92vw,370px); background:linear-gradient(160deg,#3d2b1f,#4a3728); border-radius:18px; overflow:hidden; box-shadow:0 24px 64px rgba(61,43,31,0.25); font-family:'Inter','PingFang SC','Microsoft YaHei',sans-serif; position:relative;">
    <div style="height:3px; background:linear-gradient(90deg,#d4a574,#e8c9a0,#d4a574);"></div>
    <div style="padding:36px 30px 30px; text-align:center;">
        <div style="margin:0 auto 22px; width:56px; height:56px; border-radius:16px; border:1.5px solid rgba(212,165,116,0.35); background:rgba(212,165,116,0.1); display:flex; align-items:center; justify-content:center;">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="{{ICON_COLOR}}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 4l3 12h14l3-12-6 7-4-9-4 9-6-7z"/><path d="M3 20h18"/>
            </svg>
        </div>
        <div style="font-size:20px; font-weight:700; color:#fdf4e7; margin-bottom:6px;">{{TITLE}}</div>
        <div style="font-size:12px; color:#d4a574; margin-bottom:4px; letter-spacing:1px; font-weight:600;">{{BADGE_TEXT}}</div>
        <div style="font-size:13px; color:#e8c9a0; margin-bottom:22px; letter-spacing:1px;">{{SUBTITLE}}</div>
        <div style="background:rgba(212,165,116,0.1); border:1px solid rgba(212,165,116,0.2); border-radius:12px; padding:16px 18px; text-align:left; margin-bottom:22px; color:#f5e6d3;">
            {{REWARDS}}
        </div>
        <button style="width:100%; padding:12px; border:none; border-radius:12px; background:linear-gradient(135deg,#a0724a,#c4915e); color:#fff; font-size:14px; font-weight:600; cursor:pointer; box-shadow:0 4px 16px rgba(160,114,74,0.3);">{{BUTTON}}</button>
    </div>
</div>`,
        style_sponsor_4: `<!-- 支持者四级 — 极致奢华风格（浅色调） -->
<div style="width:380px; max-width:min(92vw,380px); background:linear-gradient(160deg,#2a2724 0%,#3a3530 50%,#2a2724 100%); border-radius:20px; overflow:hidden; box-shadow:0 28px 72px rgba(0,0,0,0.4); font-family:'Inter','PingFang SC','Microsoft YaHei',sans-serif; position:relative;">
    <div style="height:3px; background:linear-gradient(90deg,transparent,#fcd34d,#fef08a,#fcd34d,transparent);"></div>
    <div style="padding:40px 32px 32px; text-align:center; position:relative;">
        <div style="position:absolute; top:0; left:50%; transform:translateX(-50%); width:200px; height:120px; background:radial-gradient(ellipse,rgba(251,191,36,0.1),transparent 70%); pointer-events:none;"></div>
        <div style="margin:0 auto 24px; width:60px; height:60px; border-radius:16px; border:1.5px solid rgba(251,191,36,0.35); background:rgba(251,191,36,0.08); display:flex; align-items:center; justify-content:center; position:relative;">
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="{{ICON_COLOR}}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M6 9H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h2"/>
                <path d="M18 9h2a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2h-2"/>
                <path d="M6 3h12v7a6 6 0 0 1-12 0V3z"/>
                <path d="M12 16v2"/><path d="M8 22h8"/><path d="M8 22v-2h8v2"/>
            </svg>
        </div>
        <div style="font-size:22px; font-weight:700; color:#fef9c3; margin-bottom:6px; letter-spacing:0.3px;">{{TITLE}}</div>
        <div style="font-size:11px; color:#fbbf24; margin-bottom:4px; letter-spacing:2px; font-weight:700; text-transform:uppercase;">{{BADGE_TEXT}}</div>
        <div style="font-size:13px; color:#fbbf24; margin-bottom:24px; letter-spacing:1px;">{{SUBTITLE}}</div>
        <div style="background:rgba(251,191,36,0.06); border:1px solid rgba(251,191,36,0.15); border-radius:14px; padding:18px 20px; text-align:left; margin-bottom:24px; color:#fef3c7;">
            {{REWARDS}}
        </div>
        <button style="width:100%; padding:13px; border:1px solid rgba(251,191,36,0.35); border-radius:14px; background:linear-gradient(135deg,#d97706,#f59e0b,#fbbf24); color:#fff; font-size:15px; font-weight:700; cursor:pointer; box-shadow:0 6px 24px rgba(251,191,36,0.25); letter-spacing:0.5px;">{{BUTTON}}</button>
    </div>
</div>`,
        style_streamer: `<!-- 主播专属 — 琥珀暖色（浅底）直播风格 -->
<div style="width:360px; max-width:min(92vw,360px); background:linear-gradient(160deg,#292524,#3c3633); border-radius:16px; overflow:hidden; box-shadow:0 20px 60px rgba(0,0,0,0.28); font-family:'Inter','PingFang SC','Microsoft YaHei',sans-serif;">
    <div style="height:3px; background:linear-gradient(90deg,#fbbf24,#fcd34d,#fbbf24);"></div>
    <div style="padding:32px 28px 28px; text-align:center;">
        <div style="margin:0 auto 20px; width:52px; height:52px; border-radius:14px; border:1.5px solid rgba(251,191,36,0.3); background:rgba(251,191,36,0.08); display:flex; align-items:center; justify-content:center;">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="{{ICON_COLOR}}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                <line x1="12" y1="19" x2="12" y2="22"/>
                <line x1="8" y1="22" x2="16" y2="22"/>
            </svg>
        </div>
        <div style="font-size:19px; font-weight:700; color:#fefce8; margin-bottom:6px;">{{TITLE}}</div>
        <div style="font-size:12px; color:#fcd34d; margin-bottom:4px; letter-spacing:1px; font-weight:600;">{{BADGE_TEXT}}</div>
        <div style="font-size:13px; color:#fde68a; margin-bottom:20px; letter-spacing:1px;">{{SUBTITLE}}</div>
        <div style="background:rgba(251,191,36,0.08); border:1px solid rgba(251,191,36,0.18); border-radius:10px; padding:14px 16px; text-align:left; margin-bottom:20px; color:#fef3c7;">
            {{REWARDS}}
        </div>
        <button style="width:100%; padding:11px; border:none; border-radius:10px; background:linear-gradient(135deg,#eab308,#fbbf24); color:#1c1917; font-size:14px; font-weight:600; cursor:pointer; box-shadow:0 4px 16px rgba(234,179,8,0.25);">{{BUTTON}}</button>
    </div>
</div>`,
        style_streamer_share: `<!-- 主播分享 — 琥珀暖色（更浅底） -->
<div style="width:360px; max-width:min(92vw,360px); background:linear-gradient(160deg,#3c3633,#44403c); border-radius:16px; overflow:hidden; box-shadow:0 20px 60px rgba(0,0,0,0.22); font-family:'Inter','PingFang SC','Microsoft YaHei',sans-serif;">
    <div style="height:3px; background:linear-gradient(90deg,#fcd34d,#fde68a,#fcd34d);"></div>
    <div style="padding:32px 28px 28px; text-align:center;">
        <div style="margin:0 auto 20px; width:52px; height:52px; border-radius:14px; border:1.5px solid rgba(253,224,71,0.2); background:rgba(253,224,71,0.06); display:flex; align-items:center; justify-content:center;">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="{{ICON_COLOR}}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
                <circle cx="9" cy="7" r="4"/>
                <path d="M22 21v-2a4 4 0 0 0-3-3.87"/>
                <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
        </div>
        <div style="font-size:19px; font-weight:700; color:#fefce8; margin-bottom:6px;">{{TITLE}}</div>
        <div style="font-size:12px; color:#fde68a; margin-bottom:4px; letter-spacing:1px; font-weight:600;">{{BADGE_TEXT}}</div>
        <div style="font-size:13px; color:#fef3c7; margin-bottom:20px; letter-spacing:1px;">{{SUBTITLE}}</div>
        <div style="background:rgba(253,224,71,0.06); border:1px solid rgba(253,224,71,0.15); border-radius:10px; padding:14px 16px; text-align:left; margin-bottom:20px; color:#fef3c7;">
            {{REWARDS}}
        </div>
        <button style="width:100%; padding:11px; border:none; border-radius:10px; background:linear-gradient(135deg,#facc15,#fde68a); color:#1c1917; font-size:14px; font-weight:600; cursor:pointer; box-shadow:0 4px 16px rgba(250,204,21,0.2);">{{BUTTON}}</button>
    </div>
</div>`,
    };

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function normalizeStyleName(command) {
        const popupStyle = String(command?.popup_style || '').trim();
        if (popupStyle && popupStyle !== 'default') return popupStyle;
        const redeemType = String(command?.redeem_type || '').trim();
        return redeemTypeDefaults[redeemType]?.style || 'style_sponsor_1';
    }

    function normalizeIconColor(value) {
        const color = String(value || '').trim();
        return /^#[0-9a-fA-F]{6}$/.test(color) ? color : '';
    }

    function normalizeRewardLines(message) {
        const lines = String(message || '')
            .split(/\r?\n/)
            .map((line) => line.trim())
            .filter(Boolean);
        const filtered = lines.filter((line) => !/^(?:🎉\s*)?兑换成功[！!]?$/.test(line));
        return filtered.length ? filtered : lines;
    }

    function buildRewardHtml(message) {
        const lines = normalizeRewardLines(message);
        if (!lines.length) {
            return '<div style="font-size:13px; line-height:1.6; color:inherit;">兑换成功</div>';
        }
        const isList = lines.length > 1 || lines.some((line) => /^[✓✔☑·•\-]/u.test(line));
        if (!isList) {
            return `<div style="font-size:13px; line-height:1.65; white-space:pre-line; color:inherit;">${escapeHtml(lines.join('\n'))}</div>`;
        }
        return lines.map((line) => {
            const cleanLine = escapeHtml(line.replace(/^[✓✔☑·•\-\s]+/u, '').trim() || line);
            return `<div class="redeem-reward-item" style="display:flex; align-items:center; gap:8px; margin-bottom:6px; font-size:13px; color:inherit;">` +
                `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0; opacity:0.7;"><path d="M20 6L9 17l-5-5"/></svg>` +
                `<span>${cleanLine}</span></div>`;
        }).join('');
    }

    function ensureRedeemResultModal() {
        let modal = document.getElementById('modal-redeem-result');
        if (!modal) {
            document.body.insertAdjacentHTML('beforeend', `
                <div class="modal-overlay" id="modal-redeem-result">
                    <div class="modal-content" style="position:relative;">
                        <button type="button" class="redeem-popup-close-btn" aria-label="关闭" onclick="app.closeRedeemResultModal()">
                            <i class="ri-close-line" style="font-size:18px;"></i>
                        </button>
                        <div id="redeem-result-host" style="display:flex; justify-content:center;"></div>
                    </div>
                </div>
            `);
            modal = document.getElementById('modal-redeem-result');
        }
        return {
            modal,
            host: document.getElementById('redeem-result-host'),
        };
    }

    app.closeRedeemResultModal = function () {
        this.closeModal('modal-redeem-result');
    };

    app.showRedeemResult = function (command) {
        if (!command || command.success === false) {
            this.showAlert(command?.title || '兑换结果', command?.message || '兑换失败，请稍后重试', command?.success === false ? 'error' : 'info');
            return;
        }

        const styleName = normalizeStyleName(command);
        const template = redeemStyleTemplates[styleName];
        if (!template) {
            this.showAlert(command.title || '兑换成功', command.message || '兑换成功', 'success');
            return;
        }

        const redeemType = String(command.redeem_type || '').trim();
        const typeDefaults = redeemTypeDefaults[redeemType] || {};
        const styleDefaults = redeemStyleDefaults[styleName] || redeemStyleDefaults.style_sponsor_1;
        const title = String(command.title || '兑换成功').trim() || '兑换成功';
        const subtitle = String(command.popup_subtitle || '').trim() || typeDefaults.subtitle || styleDefaults.subtitle || '· 感谢支持 ·';
        const iconColor = normalizeIconColor(command.popup_icon_color) || typeDefaults.iconColor || styleDefaults.iconColor || '#64748b';
        const buttonText = String(command.popup_button || '').trim() || typeDefaults.button || styleDefaults.button || '确定';
        const badgeText = String(command.popup_badge_text || '').trim() || typeDefaults.badgeText || styleDefaults.badgeText || '';
        let html = template
            .replace('{{TITLE}}', escapeHtml(title))
            .replace('{{SUBTITLE}}', escapeHtml(subtitle))
            .replace('{{BUTTON}}', escapeHtml(buttonText))
            .replace('{{ICON_COLOR}}', iconColor)
            .replace('{{BADGE_TEXT}}', escapeHtml(badgeText))
            .replace('{{REWARDS}}', buildRewardHtml(command.message));

        const popupLogo = String(command.popup_logo || '').trim();
        if (popupLogo && popupLogo !== 'default' && redeemLogoSvgMap[popupLogo]) {
            const logoSvg = redeemLogoSvgMap[popupLogo].replace('<svg ', `<svg style="color:${iconColor};" `);
            html = html.replace(/<svg[^>]*>.*?<\/svg>/is, logoSvg);
        }

        const { modal, host } = ensureRedeemResultModal();
        if (!host) {
            this.showAlert(title, command.message || '兑换成功', 'success');
            return;
        }

        // 重置动画状态：先移除 show 再刷新内容，避免二次打开时闪烁
        if (modal) modal.classList.remove('show');
        host.innerHTML = html;

        // 给图标容器添加浮动动效 class
        const iconBox = host.querySelector('div[style*="border-radius"][style*="align-items:center"][style*="justify-content:center"]');
        if (iconBox) iconBox.classList.add('redeem-popup-icon');

        const themeFile = command.theme_file || '';
        const self = this;
        const actionBtn = host.querySelector('button');
        if (actionBtn) {
            actionBtn.type = 'button';
            actionBtn.classList.add('redeem-popup-action-btn');
            actionBtn.addEventListener('click', () => {
                self.closeRedeemResultModal();
                // 解锁主题后自动切换并通知
                if (themeFile && typeof self.selectTheme === 'function') {
                    try {
                        self.selectTheme(themeFile);
                        if (typeof self.showToast === 'function') {
                            self.showToast('已为您更换支持者主题，感谢您的支持！', 'success');
                        }
                    } catch (_) { /* 纯浏览器环境无 pywebview，忽略 */ }
                }
            });
        }

        // 下一帧再添加 show，保证动画从头触发
        requestAnimationFrame(() => {
            this.openModal('modal-redeem-result');
        });
    };

    app.openRedeemCodeModal = function () {
        this.openModal('modal-redeem-code');
        const input = document.getElementById('redeem-code-input');
        if (!input) return;
        input.value = '';
        setTimeout(() => {
            try {
                input.focus();
                input.select();
            } catch (e) {
            }
        }, 50);
    };

    app.submitRedeemCode = async function () {
		if (this._redeemSubmitInFlight) return;
		this._redeemSubmitInFlight = true;
		try {
        const input = document.getElementById('redeem-code-input');
        const code = normalizeCode(input?.value);

        if (!code) {
            this.showAlert('提示', '请输入兑换口令', 'warn');
            return;
        }

        // 本地隐藏主题口令优先处理，避免被服务端同名兑换码截走
        let result = null;
        try {
            result = await pywebview.api.redeem_theme_code(code);
        } catch (e) {
            console.error('Failed to redeem local theme code', e);
        }

        if (result?.success) {
            this.closeModal('modal-redeem-code');

            // 等待后端 save_config 完全落盘，避免后续 API 读到旧状态
            await new Promise(r => setTimeout(r, 80));
            await this.loadThemeList();

            let targetTheme = getThemeByFile(result.theme_file);

            // 首次 loadThemeList 可能因后端写盘时序而缺少刚解锁的主题，重试一次
            if (!targetTheme && result.theme_file) {
                await new Promise(r => setTimeout(r, 200));
                await this.loadThemeList();
                targetTheme = getThemeByFile(result.theme_file);
            }

            // 仍找不到时，直接从后端读取主题内容获取名称
            if (!targetTheme && result.theme_file) {
                try {
                    const content = await pywebview.api.load_theme_content(result.theme_file);
                    if (content && content.meta && content.meta.name) {
                        targetTheme = { filename: result.theme_file, name: content.meta.name };
                    }
                } catch (_e) { /* 纯兜底，不阻断流程 */ }
            }

            // 无论列表中是否包含该主题，都尝试切换应用
            if (result.theme_file) {
                try {
                    this.selectTheme(result.theme_file);
                } catch (_e) { console.warn('selectTheme failed after redeem', _e); }
            }

            const fileBaseName = String(result.theme_file || '').replace(/\.json$/i, '');
            const themeName = targetTheme?.name || fileBaseName || '该主题';
            const successText = result.already_unlocked
                ? `「${themeName}」已经解锁，现已为你应用`
                : `你已经成功解锁并应用「${themeName}」`;

            this.showAlert('解锁成功', successText, 'success');
            return;
        }

        // 本地主题口令无效时，再尝试服务端兑换码
        let serverResult = null;
        try {
            serverResult = await pywebview.api.redeem_code(code);
        } catch (e) {
            console.warn('Server redeem not available, trying local', e);
        }

        if (serverResult?.success) {
            this.closeModal('modal-redeem-code');
            const command = serverResult.command || {
                success: true,
                title: '兑换成功',
                message: serverResult.message || '兑换成功',
            };
            if (command.theme_unlocked) {
                await this.loadThemeList();
            }
            this.showRedeemResult(command);
            return;
        }

        const msg = serverResult?.message || result?.message || '兑换失败，请稍后重试';
        this.showAlert('兑换失败', msg, 'error');
		} finally {
			this._redeemSubmitInFlight = false;
		}
    };

    app.resetUnlockedThemes = async function () {
        let result = null;
        try {
            result = await pywebview.api.reset_unlocked_themes();
        } catch (e) {
            console.error('Failed to reset unlocked themes', e);
        }

        if (!result?.success) {
            this.showAlert('错误', '重置失败，请稍后重试', 'error');
            return;
        }

        const input = document.getElementById('redeem-code-input');
        if (input) {
            input.value = '';
        }

        await this.loadThemeList();
        this.selectTheme('default.json');
        this.showAlert('成功', '已重置本地口令解锁主题，支持者主题会继续保留', 'success');
    };

    document.addEventListener('DOMContentLoaded', function () {
        const input = document.getElementById('redeem-code-input');
        if (!input) return;

        input.addEventListener('keydown', function (e) {
            if (e.key !== 'Enter') return;
            e.preventDefault();
            app.submitRedeemCode();
        });
    });
})();
