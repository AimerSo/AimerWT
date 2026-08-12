package main

import "time"

type TelemetryRecord struct {
	ID                  uint              `gorm:"primaryKey;autoIncrement" json:"id"`
	MachineID           string            `gorm:"uniqueIndex;type:varchar(64)" json:"machine_id"`
	MachineIDCandidates []string          `gorm:"-" json:"machine_id_candidates,omitempty"`
	ContentCacheKeys    map[string]string `gorm:"-" json:"content_cache_keys,omitempty"`
	Alias               string            `json:"alias"`
	Version             string            `json:"version"`
	OS                  string            `json:"os"`
	OSRelease           string            `json:"os_release"`
	OSVersion           string            `json:"os_version"`
	Arch                string            `json:"arch"`
	CPUCount            int               `json:"cpu_count"`
	ScreenRes           string            `json:"screen_res"`
	PythonVersion       string            `json:"python_version"`
	Locale              string            `json:"locale"`
	SessionID           int               `json:"session_id"`
	CommandProtocol     int               `json:"command_protocol" gorm:"-"`
	PendingCommand      string            `json:"pending_command"`
	PendingCommandLogID uint              `json:"pending_command_log_id" gorm:"default:0"`
	IsStarred           bool              `json:"is_starred"`
	IsAdmin             bool              `json:"is_admin"`
	Tags                string            `gorm:"type:text;default:'[]'" json:"tags"`
	CommentPerms        string            `gorm:"type:text;default:'{}'" json:"comment_perms"`
	LastSeenAt          time.Time         `gorm:"autoUpdateTime;index" json:"last_seen_at"`
	CreatedAt           time.Time         `gorm:"autoCreateTime;index" json:"created_at"`
}

type StatsResponse struct {
	TotalUsers     int64            `json:"total_users"`
	OnlineUsers    int64            `json:"online_users"`
	TodayNew       int64            `json:"today_new"`
	DAU            int64            `json:"dau"`
	OSStats        []map[string]any `json:"os_stats"`
	ArchStats      []map[string]any `json:"arch_stats"`
	VersionStats   []map[string]any `json:"version_stats"`
	LocaleStats    []map[string]any `json:"locale_stats"`
	ScreenStats    []map[string]any `json:"screen_stats"`
	GrowthData     []map[string]any `json:"growth_data"`
	CompareGrowth  []map[string]any `json:"compare_growth_data,omitempty"`
	TotalUserTrend []map[string]any `json:"total_user_trend"`
	RecentUsers    []map[string]any `json:"recent_users"`
	OSOptions      []map[string]any `json:"os_options"`
	ArchOptions    []map[string]any `json:"arch_options"`
	VersionOptions []map[string]any `json:"version_options"`
	LocaleOptions  []map[string]any `json:"locale_options"`
	TagOptions     []UserTag        `json:"tag_options"`
}

type DrilldownResponse struct {
	Period string           `json:"period"`
	Items  []map[string]any `json:"items"`
}

type BannerItem struct {
	Type            string                 `json:"type"`
	Text            string                 `json:"text"`
	Icon            string                 `json:"icon"`
	Color           string                 `json:"color"`
	IconColor       string                 `json:"icon_color"`
	BackgroundColor string                 `json:"background_color"`
	ActionType      string                 `json:"action_type"`
	ActionURL       string                 `json:"action_url"`
	ActionTitle     string                 `json:"action_title"`
	ActionContent   string                 `json:"action_content"`
	TrackingType    string                 `json:"tracking_type"`
	TrackingID      string                 `json:"tracking_id"`
	Action          map[string]interface{} `json:"action,omitempty"`
}

type AudienceRule struct {
	MinimumVersion string   `json:"minimum_version,omitempty"`
	Versions       []string `json:"versions"`
	Tags           []string `json:"tags"`
	SpecialGroups  []string `json:"special_groups"`
}

type AudienceTargeting struct {
	Rules []AudienceRule `json:"rules"`
}

type SystemConfig struct {
	Maintenance    bool   `json:"maintenance"`
	MaintenanceMsg string `json:"maintenance_msg"`
	StopNewData    bool   `json:"stop_new_data"`

	// 紧急通知 (弹窗/模态)
	AlertActive  bool   `json:"alert_active"`
	AlertTitle   string `json:"alert_title"`
	AlertContent string `json:"alert_content"`
	AlertScope   string `json:"alert_scope"`

	AlertTargeting AudienceTargeting `json:"alert_targeting"`
	// 常驻公告 (覆盖公告栏文字)
	NoticeActive        bool              `json:"notice_active"`
	NoticeContent       string            `json:"notice_content"`
	NoticeScope         string            `json:"notice_scope"`
	NoticeActionType    string            `json:"notice_action_type"`
	NoticeTargeting     AudienceTargeting `json:"notice_targeting"`
	NoticeActionURL     string            `json:"notice_action_url"`
	NoticeActionTitle   string            `json:"notice_action_title"`
	NoticeActionContent string            `json:"notice_action_content"`
	BannerItems         []BannerItem      `json:"banner_items"`
	BannerInterval      int               `json:"banner_interval"`

	UpdateActive  bool   `json:"update_active"`
	UpdateContent string `json:"update_content"`
	UpdateUrl     string `json:"update_url"`
	UpdateScope   string `json:"update_scope"`

	UpdateTargeting AudienceTargeting `json:"update_targeting"`
	// 心跳上报间隔（秒），客户端据此动态调整上报频率
	HeartbeatInterval int    `json:"heartbeat_interval"`
	HeartbeatScope    string `json:"heartbeat_scope"` // all 或指定版本号

	// 在线判定阈值（分钟），超过此时间未上报视为离线
	OnlineThresholdMin int `json:"online_threshold_min"`

	// 项目状态（客户端信息库展示）
	ProjectStatus     string `json:"project_status"`      // active / warning / danger
	ProjectLastUpdate string `json:"project_last_update"` // 如 "2026 年 3 月 14 日"

	// 用户功能总开关（评论和表情默认关闭，其余默认开启）
	BadgeSystemEnabled          bool              `json:"badge_system_enabled"`
	NicknameChangeEnabled       bool              `json:"nickname_change_enabled"`
	AvatarUploadEnabled         bool              `json:"avatar_upload_enabled"`
	NoticeCommentEnabled        bool              `json:"notice_comment_enabled"`
	NoticeReactionEnabled       bool              `json:"notice_reaction_enabled"`
	RedeemCodeEnabled           bool              `json:"redeem_code_enabled"`
	FeedbackEnabled             bool              `json:"feedback_enabled"`
	NotificationCenterEnabled   bool              `json:"notification_center_enabled"`
	NotificationCenterScope     string            `json:"notification_center_scope"`
	NotificationCenterTargeting AudienceTargeting `json:"notification_center_targeting"`

	// 头像上传分组权限（按标签控制哪些用户组可上传头像）
	AvatarUploadAllowAll    bool   `json:"avatar_upload_allow_all"`
	AvatarUploadAllowedTags string `json:"avatar_upload_allowed_tags"`
}

// ContentConfig KV 配置持久化表，用于服务重启后恢复运行时状态
type ContentConfig struct {
	Key       string    `gorm:"primaryKey;type:varchar(128)" json:"key"`
	Value     string    `gorm:"type:text" json:"value"`
	UpdatedAt time.Time `gorm:"autoUpdateTime" json:"updated_at"`
}

// RemoteTheme 远程主题元数据与主题 JSON 内容。
type RemoteTheme struct {
	ID          uint      `gorm:"primaryKey;autoIncrement" json:"id"`
	Filename    string    `gorm:"uniqueIndex;type:varchar(128);not null" json:"filename"`
	Name        string    `gorm:"type:varchar(128);not null" json:"name"`
	Author      string    `gorm:"type:varchar(64)" json:"author"`
	Version     string    `gorm:"type:varchar(32);not null" json:"version"`
	Visibility  string    `gorm:"type:varchar(24);not null;default:'public';index" json:"visibility"`
	Status      string    `gorm:"type:varchar(24);not null;default:'active';index" json:"status"`
	SortOrder   int       `gorm:"default:0;index" json:"sort_order"`
	Checksum    string    `gorm:"type:varchar(64);not null" json:"checksum"`
	FileSize    int       `gorm:"default:0" json:"file_size"`
	Description string    `gorm:"type:text" json:"description"`
	ThemeData   string    `gorm:"type:text" json:"theme_data,omitempty"`
	CreatedAt   time.Time `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt   time.Time `gorm:"autoUpdateTime" json:"updated_at"`
}

// ClientDeviceToken 服务端签发给客户端的设备级访问令牌。
// 用于避免把打包进客户端的共享密钥直接当作长期信任边界。
type ClientDeviceToken struct {
	ID         uint      `gorm:"primaryKey;autoIncrement" json:"id"`
	MachineID  string    `gorm:"uniqueIndex;type:varchar(64);not null" json:"machine_id"`
	TokenHash  string    `gorm:"type:varchar(64);not null" json:"-"`
	LastIssued time.Time `gorm:"autoCreateTime" json:"last_issued"`
	CreatedAt  time.Time `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt  time.Time `gorm:"autoUpdateTime" json:"updated_at"`
}

// ClientDeviceSession 允许同一设备保留多个短期有效会话，避免并发重签互相覆盖。
type ClientDeviceSession struct {
	ID         uint      `gorm:"primaryKey;autoIncrement" json:"id"`
	MachineID  string    `gorm:"index;type:varchar(64);not null" json:"machine_id"`
	TokenHash  string    `gorm:"uniqueIndex;type:varchar(64);not null" json:"-"`
	ExpiresAt  time.Time `gorm:"index;not null" json:"expires_at"`
	LastSeenAt time.Time `gorm:"index;not null" json:"last_seen_at"`
	CreatedAt  time.Time `gorm:"autoCreateTime;index" json:"created_at"`
}

// MachineIDAlias 保存历史/候选 machine_id 到 canonical machine_id 的映射。
type MachineIDAlias struct {
	AliasMachineID     string    `gorm:"primaryKey;column:alias_machine_id;type:varchar(64)" json:"alias_machine_id"`
	CanonicalMachineID string    `gorm:"index;type:varchar(64);not null" json:"canonical_machine_id"`
	FirstSeenAt        time.Time `gorm:"autoCreateTime;index" json:"first_seen_at"`
	LastSeenAt         time.Time `gorm:"autoUpdateTime;index" json:"last_seen_at"`
}

func (MachineIDAlias) TableName() string {
	return "machine_id_aliases"
}

// AdCarouselItem 广告轮播数据结构（序列化后存入 ContentConfig）
type AdCarouselItem struct {
	ID        string `json:"id"`
	Image     string `json:"image"`
	Alt       string `json:"alt"`
	URL       string `json:"url"`
	PositionX int    `json:"position_x"` // object-position x% (0-100，默认 50)
	PositionY int    `json:"position_y"` // object-position y% (0-100，默认 50)
}

// KnowledgeAdItem 信息库广告位数据结构（固定 4 个槽位）
type KnowledgeAdItem struct {
	ID           string `json:"id"`
	Enabled      bool   `json:"enabled"`
	Title        string `json:"title"`
	Subtitle     string `json:"subtitle"`
	Avatar       string `json:"avatar"`
	Background   string `json:"background"`
	URL          string `json:"url"`
	Action       string `json:"action"` // link / popup
	PopupContent string `json:"popup_content"`
}

// KnowledgeAdsConfig 信息库广告位配置
type KnowledgeAdsConfig struct {
	Items []KnowledgeAdItem `json:"items"`
}

// AdClickEvent 广告点击事件（客户端上报，用于流量统计与广告效果分析）
type AdClickEvent struct {
	ID        uint      `gorm:"primaryKey;autoIncrement" json:"id"`
	MachineID string    `gorm:"index:idx_ad_click_machine_ad_created,priority:1;index:idx_ad_click_machine_medium_ad_created,priority:1;index:idx_ad_click_medium_ad_machine,priority:3;type:varchar(64)" json:"machine_id"`
	AdMedium  string    `gorm:"index;index:idx_ad_click_machine_medium_ad_created,priority:2;index:idx_ad_click_medium_ad_machine,priority:1;type:varchar(32)" json:"ad_medium"`
	AdID      string    `gorm:"index:idx_ad_click_machine_ad_created,priority:2;index:idx_ad_click_machine_medium_ad_created,priority:3;index:idx_ad_click_medium_ad_machine,priority:2;type:varchar(64)" json:"ad_id"`
	TargetURL string    `gorm:"type:text" json:"target_url"`
	CreatedAt time.Time `gorm:"autoCreateTime;index;index:idx_ad_click_machine_ad_created,priority:3;index:idx_ad_click_machine_medium_ad_created,priority:4" json:"created_at"`
}

// NoticeItem 公告列表数据表（对应客户端 notice_data.js 的数据结构）
type NoticeItem struct {
	ID        uint      `gorm:"primaryKey;autoIncrement" json:"id"`
	Type      string    `json:"type"` // urgent / update / event / normal
	Tag       string    `json:"tag"`  // 紧急 / 更新 / 活动 / 日常
	Title     string    `json:"title"`
	Summary   string    `json:"summary"`
	Content   string    `gorm:"type:text" json:"content"`
	Date      string    `json:"date"`
	IsPinned  bool      `json:"is_pinned" gorm:"default:false"`
	IconClass string    `json:"icon_class" gorm:"type:varchar(64);default:''"`
	SortOrder int       `json:"sort_order" gorm:"default:0"`
	CreatedAt time.Time `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt time.Time `gorm:"autoUpdateTime" json:"updated_at"`
}

// FeedbackRecord 用户反馈数据表
type FeedbackRecord struct {
	ID        uint      `gorm:"primaryKey;autoIncrement" json:"id"`
	MachineID string    `gorm:"index:idx_feedback_machine_created,priority:1;type:varchar(64)" json:"machine_id"`
	Version   string    `json:"version"`
	Contact   string    `json:"contact"`
	Content   string    `gorm:"type:text" json:"content"`
	Category  string    `json:"category"` // bug / suggestion / other
	OS        string    `json:"os"`
	OSVersion string    `json:"os_version"`
	ScreenRes string    `json:"screen_res"`
	Locale    string    `json:"locale"`
	Status    string    `json:"status" gorm:"default:'pending'"` // pending / read / resolved / ignored
	AdminNote string    `gorm:"type:text" json:"admin_note"`
	CreatedAt time.Time `gorm:"autoCreateTime;index:idx_feedback_machine_created,priority:2;index" json:"created_at"`
	UpdatedAt time.Time `gorm:"autoUpdateTime" json:"updated_at"`
}

// AIUsageRecord AI 对话用量记录
type AIUsageRecord struct {
	ID               uint      `gorm:"primaryKey;autoIncrement" json:"id"`
	MachineID        string    `gorm:"index;type:varchar(64)" json:"machine_id"`
	Model            string    `json:"model"`
	PromptTokens     int       `json:"prompt_tokens"`
	CompletionTokens int       `json:"completion_tokens"`
	TotalTokens      int       `json:"total_tokens"`
	CreatedAt        time.Time `gorm:"autoCreateTime" json:"created_at"`
}

// AIUserBan AI 功能封禁记录
type AIUserBan struct {
	ID        uint       `gorm:"primaryKey;autoIncrement" json:"id"`
	MachineID string     `gorm:"type:varchar(64);not null" json:"machine_id"`
	Reason    string     `gorm:"type:varchar(500);not null" json:"reason"`
	ExpiresAt *time.Time `gorm:"index" json:"expires_at,omitempty"`
	RevokedAt *time.Time `gorm:"index" json:"revoked_at,omitempty"`
	CreatedAt time.Time  `gorm:"autoCreateTime;index" json:"created_at"`
}

// FeedbackUserBan 反馈功能封禁记录，解除后保留历史。
type FeedbackUserBan struct {
	ID        uint       `gorm:"primaryKey;autoIncrement" json:"id"`
	MachineID string     `gorm:"type:varchar(64);not null" json:"machine_id"`
	Reason    string     `gorm:"type:varchar(500);not null" json:"reason"`
	ExpiresAt *time.Time `gorm:"index" json:"expires_at,omitempty"`
	RevokedAt *time.Time `gorm:"index" json:"revoked_at,omitempty"`
	CreatedAt time.Time  `gorm:"autoCreateTime;index" json:"created_at"`
}

// AIUserLimit 单用户每日限额覆盖（未设置则使用全局默认值）
type AIUserLimit struct {
	ID           uint   `gorm:"primaryKey;autoIncrement" json:"id"`
	MachineID    string `gorm:"uniqueIndex;type:varchar(64)" json:"machine_id"`
	DailyLimit   int    `json:"daily_limit"`
	BonusCredits int    `json:"bonus_credits"` // 永久固定额度（不随每日重置清零，用完为止）
}

// UserTag 用户标签元数据（管理标签名称/颜色/图标）
type UserTag struct {
	ID          uint      `gorm:"primaryKey" json:"id"`
	Name        string    `gorm:"uniqueIndex;type:varchar(32)" json:"name"`
	DisplayName string    `json:"display_name"`
	Color       string    `json:"color"`
	Icon        string    `json:"icon"`
	IsSystem    bool      `json:"is_system"`
	SortOrder   int       `json:"sort_order"`
	CreatedAt   time.Time `gorm:"autoCreateTime" json:"created_at"`
}

// RedeemCode 兑换码定义表
type RedeemCode struct {
	ID             uint       `gorm:"primaryKey;autoIncrement" json:"id"`
	Code           string     `gorm:"uniqueIndex;type:varchar(32)" json:"code"`
	Type           string     `gorm:"type:varchar(32)" json:"type"`
	Payload        string     `gorm:"type:text" json:"payload"`
	MaxUses        int        `json:"max_uses"`
	UsedCount      int        `json:"used_count" gorm:"default:0"`
	ExpiresAt      *time.Time `json:"expires_at"`
	IsActive       bool       `json:"is_active" gorm:"default:true"`
	Note           string     `gorm:"type:text" json:"note"`
	PopupTitle     string     `gorm:"type:varchar(128)" json:"popup_title"`
	PopupMessage   string     `gorm:"type:text" json:"popup_message"`
	PopupStyle     string     `gorm:"type:varchar(32);default:'default'" json:"popup_style"`
	PopupSubtitle  string     `gorm:"type:varchar(128)" json:"popup_subtitle"`
	PopupLogo      string     `gorm:"type:varchar(32)" json:"popup_logo"`
	PopupIconColor string     `gorm:"type:varchar(16)" json:"popup_icon_color"`
	PopupBadgeText string     `gorm:"type:varchar(128)" json:"popup_badge_text"`
	PopupButton    string     `gorm:"type:varchar(64)" json:"popup_button"`
	CreatedAt      time.Time  `gorm:"autoCreateTime" json:"created_at"`
}

// RedeemRecord 兑换码使用记录表
type RedeemRecord struct {
	ID              uint      `gorm:"primaryKey;autoIncrement" json:"id"`
	RedeemCodeID    uint      `gorm:"index;default:0" json:"redeem_code_id"`
	Code            string    `gorm:"uniqueIndex:idx_redeem_record_code_machine;type:varchar(32)" json:"code"`
	MachineID       string    `gorm:"uniqueIndex:idx_redeem_record_code_machine;type:varchar(64)" json:"machine_id"`
	PayloadSnapshot string    `gorm:"type:text" json:"payload_snapshot"`
	ResultCommand   string    `gorm:"type:text" json:"result_command"`
	CreatedAt       time.Time `gorm:"autoCreateTime" json:"created_at"`
}

// RewardLedger 权益变更流水，用于兑换和人工额度调整核账。
type RewardLedger struct {
	ID              uint      `gorm:"primaryKey;autoIncrement" json:"id"`
	EventID         string    `gorm:"uniqueIndex;type:varchar(160);not null" json:"event_id"`
	MachineID       string    `gorm:"index;type:varchar(64);not null" json:"machine_id"`
	SourceType      string    `gorm:"index;type:varchar(32);not null" json:"source_type"`
	SourceID        uint      `gorm:"index;default:0" json:"source_id"`
	RewardType      string    `gorm:"index;type:varchar(32);not null" json:"reward_type"`
	Delta           int       `json:"delta"`
	BalanceBefore   int       `json:"balance_before"`
	BalanceAfter    int       `json:"balance_after"`
	PayloadSnapshot string    `gorm:"type:text" json:"payload_snapshot"`
	CreatedAt       time.Time `gorm:"autoCreateTime;index" json:"created_at"`
}

// NoticeReaction 公告表情反应记录（用户对公告添加 emoji 反应）
type NoticeReaction struct {
	ID        uint      `gorm:"primaryKey;autoIncrement" json:"id"`
	NoticeID  uint      `gorm:"index:idx_notice_reaction_user,priority:1;not null" json:"notice_id"`
	MachineID string    `gorm:"index:idx_notice_reaction_user,priority:2;type:varchar(64);not null" json:"machine_id"`
	Emoji     string    `gorm:"type:varchar(32);not null" json:"emoji"`
	CreatedAt time.Time `gorm:"autoCreateTime" json:"created_at"`
}

// UserProfile 用户个人资料（昵称、头像、等级、经验、勋章）
// Level：0=未验证，1=已验证（管理员手动升级），2~9 由经验值自动计算
// Badges：JSON 数组，如 [{"id":"supporter","name":"支持者","icon":"🏅","color":"#f59e0b"}]
// Verified：管理员认证，认证后才可提交昵称/头像变更请求
type UserProfile struct {
	ID                   uint       `gorm:"primaryKey;autoIncrement" json:"id"`
	MachineID            string     `gorm:"uniqueIndex;type:varchar(64);not null" json:"machine_id"`
	Nickname             string     `gorm:"type:varchar(32)" json:"nickname"`
	BoundQQ              string     `gorm:"type:varchar(16)" json:"bound_qq"`
	AvatarData           string     `gorm:"type:text" json:"avatar_data"` // Base64 encoded webp image（裁剪至 128×128）
	Level                int        `gorm:"default:0;not null" json:"level"`
	Exp                  int        `gorm:"default:0;not null" json:"exp"`
	Badges               string     `gorm:"type:text;default:'[]'" json:"badges"` // JSON 数组
	Verified             bool       `gorm:"default:false;not null" json:"verified"`
	LastNicknameChangeAt *time.Time `json:"last_nickname_change_at"`
	LastAvatarChangeAt   *time.Time `json:"last_avatar_change_at"`
	CreatedAt            time.Time  `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt            time.Time  `gorm:"autoUpdateTime" json:"updated_at"`
}

// NicknameRequest 昵称变更请求（用户提交 → 管理员审批）
type NicknameRequest struct {
	ID            uint       `gorm:"primaryKey;autoIncrement" json:"id"`
	MachineID     string     `gorm:"index:idx_nickname_requests_machine_status_created,priority:1;type:varchar(64);not null" json:"machine_id"`
	Nickname      string     `gorm:"type:varchar(64);not null" json:"nickname"`
	Status        string     `gorm:"type:varchar(16);default:'pending';index;index:idx_nickname_requests_machine_status_created,priority:2" json:"status"` // pending / approved / rejected
	RejectReason  string     `gorm:"type:text" json:"reject_reason"`
	CooldownUntil *time.Time `json:"cooldown_until"`
	CreatedAt     time.Time  `gorm:"autoCreateTime;index;index:idx_nickname_requests_machine_status_created,priority:3" json:"created_at"`
	UpdatedAt     time.Time  `gorm:"autoUpdateTime" json:"updated_at"`
}

// AvatarRequest 头像变更请求（用户提交 → 管理员审批）
type AvatarRequest struct {
	ID            uint       `gorm:"primaryKey;autoIncrement" json:"id"`
	MachineID     string     `gorm:"index:idx_avatar_requests_machine_status,priority:1;type:varchar(64);not null" json:"machine_id"`
	AvatarData    string     `gorm:"type:text;not null" json:"avatar_data"` // Base64 encoded webp image
	Status        string     `gorm:"type:varchar(16);default:'pending';index;index:idx_avatar_requests_machine_status,priority:2" json:"status"`
	RejectReason  string     `gorm:"type:text" json:"reject_reason"`
	CooldownUntil *time.Time `json:"cooldown_until"`
	CreatedAt     time.Time  `gorm:"autoCreateTime;index" json:"created_at"`
	UpdatedAt     time.Time  `gorm:"autoUpdateTime" json:"updated_at"`
}

// LevelExpThresholds 各等级所需的最低经验值（0~9，0级和1级无需经验值）
var LevelExpThresholds = []int{0, 0, 200, 800, 2400, 4800, 9600, 19200, 38400, 76800}

// UserUIDMapping 公开 UID 映射表，将 machine_id 映射到连续递增的 seq_id。
// seq_id 由事务内的 UserUIDCounter 手动分配，不使用 SQLite AUTOINCREMENT，
// 避免心跳 upsert 导致序号空洞。
type UserUIDMapping struct {
	SeqID             uint      `gorm:"primaryKey;column:seq_id" json:"seq_id"`
	MachineID         string    `gorm:"uniqueIndex;type:varchar(64);not null" json:"machine_id"`
	TelemetryRecordID uint      `gorm:"index" json:"telemetry_record_id"`
	CreatedAt         time.Time `gorm:"autoCreateTime;index" json:"created_at"`
	UpdatedAt         time.Time `gorm:"autoUpdateTime" json:"updated_at"`
}

func (UserUIDMapping) TableName() string {
	return "user_uid_mappings"
}

// PushDeliveryLog 推送送达记录（心跳返回推送内容时写入）
type PushDeliveryLog struct {
	ID          uint      `gorm:"primaryKey;autoIncrement" json:"id"`
	MachineID   string    `gorm:"uniqueIndex:idx_push_delivery_unique,priority:1;type:varchar(64);not null" json:"machine_id"`
	PushType    string    `gorm:"uniqueIndex:idx_push_delivery_unique,priority:2;type:varchar(32);not null" json:"push_type"` // header_banner / ad_carousel / knowledge_ad / notice / alert / update
	PushKey     string    `gorm:"uniqueIndex:idx_push_delivery_unique,priority:3;type:varchar(64);not null" json:"push_key"`  // 内容哈希或 notice_<id>
	DeliveredAt time.Time `gorm:"autoCreateTime;index" json:"delivered_at"`
}

// UserCommandLog 用户指令操作日志（发送弹窗/提示/请求日志等）
type UserCommandLog struct {
	ID          uint       `gorm:"primaryKey;autoIncrement" json:"id"`
	MachineID   string     `gorm:"index;type:varchar(64);not null" json:"machine_id"`
	CommandType string     `gorm:"type:varchar(32);not null" json:"command_type"` // popup / toast / system_notification / upload_log / gift_theme
	Content     string     `gorm:"type:text" json:"content"`
	Status      string     `gorm:"type:varchar(16);default:'pending'" json:"status"` // pending / delivered / unsupported / failed / cancelled
	CreatedAt   time.Time  `gorm:"autoCreateTime;index" json:"created_at"`
	DeliveredAt *time.Time `json:"delivered_at"`
}

// ClientCommand 3.1 客户端可靠命令队列，确认前保持可重投。
type ClientCommand struct {
	ID               uint       `gorm:"primaryKey;autoIncrement" json:"id"`
	CommandID        string     `gorm:"uniqueIndex;type:varchar(64);not null" json:"command_id"`
	MachineID        string     `gorm:"index:idx_client_command_pending,priority:1;type:varchar(64);not null" json:"machine_id"`
	Payload          string     `gorm:"type:text;not null" json:"payload"`
	SourceType       string     `gorm:"type:varchar(32)" json:"source_type"`
	SourceID         uint       `gorm:"default:0" json:"source_id"`
	UserCommandLogID uint       `gorm:"index;default:0" json:"user_command_log_id"`
	Status           string     `gorm:"index:idx_client_command_pending,priority:2;type:varchar(16);default:'pending'" json:"status"`
	Attempts         int        `gorm:"default:0" json:"attempts"`
	MaxAttempts      int        `gorm:"default:5" json:"max_attempts"`
	LastError        string     `gorm:"type:varchar(500)" json:"last_error"`
	LastDeliveredAt  *time.Time `json:"last_delivered_at"`
	ExpiresAt        *time.Time `json:"expires_at"`
	AcknowledgedAt   *time.Time `json:"acknowledged_at"`
	CreatedAt        time.Time  `gorm:"autoCreateTime;index" json:"created_at"`
}

// UserUIDCounter 公开 UID 计数器，单行存储下一个可分配的 seq_id 值
type UserUIDCounter struct {
	Key       string    `gorm:"primaryKey;type:varchar(64)" json:"key"`
	NextSeq   uint      `gorm:"not null" json:"next_seq"`
	UpdatedAt time.Time `gorm:"autoUpdateTime" json:"updated_at"`
}

func (UserUIDCounter) TableName() string {
	return "user_uid_counters"
}
