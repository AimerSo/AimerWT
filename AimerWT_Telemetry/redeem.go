package main

import (
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"math"
	"math/big"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

// 兑换码字符集（大写字母+数字，去掉易混淆字符 O/0/I/1）
const redeemCharset = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

// generateCode 生成指定长度的随机兑换码（格式：XXXX-XXXX-XXXX）
func generateCode(segLen, segCount int) (string, error) {
	if segLen <= 0 || segCount <= 0 || segLen*segCount+segCount-1 > 32 {
		return "", errors.New("兑换码长度参数无效")
	}
	segments := make([]string, segCount)
	for s := 0; s < segCount; s++ {
		seg := make([]byte, segLen)
		for i := range seg {
			n, err := rand.Int(rand.Reader, big.NewInt(int64(len(redeemCharset))))
			if err != nil {
				return "", fmt.Errorf("安全随机数生成失败: %w", err)
			}
			seg[i] = redeemCharset[n.Int64()]
		}
		segments[s] = string(seg)
	}
	return strings.Join(segments, "-"), nil
}

func maskRedeemCode(code string) string {
	code = strings.TrimSpace(code)
	if len(code) <= 4 {
		return "****"
	}
	return "****" + code[len(code)-4:]
}

// 预定义赞助码类型
var redeemPresets = []map[string]interface{}{
	{
		"name":     "sponsor_1",
		"label":    "支持者一级",
		"type":     "sponsor_1",
		"payload":  `{"theme":"supporter.json","bonus":50,"daily_limit_bonus":5,"tag":"sponsor_1"}`,
		"max_uses": 1,
	},
	{
		"name":     "sponsor_2",
		"label":    "支持者二级",
		"type":     "sponsor_2",
		"payload":  `{"theme":"supporter.json","bonus":100,"daily_limit_bonus":10,"tag":"sponsor_2"}`,
		"max_uses": 1,
	},
	{
		"name":     "sponsor_3",
		"label":    "支持者三级",
		"type":     "sponsor_3",
		"payload":  `{"theme":"supporter.json","bonus":150,"daily_limit_bonus":20,"tag":"sponsor_3"}`,
		"max_uses": 1,
	},
	{
		"name":     "sponsor_4",
		"label":    "支持者四级",
		"type":     "sponsor_4",
		"payload":  `{"theme":"supporter.json","bonus":200,"daily_limit_bonus":30,"tag":"sponsor_4"}`,
		"max_uses": 1,
	},
	{
		"name":     "streamer",
		"label":    "主播专属",
		"type":     "streamer",
		"payload":  `{"theme":"supporter.json","bonus":0,"tag":""}`,
		"max_uses": 1,
	},
	{
		"name":     "streamer_share",
		"label":    "主播分享",
		"type":     "streamer_share",
		"payload":  `{"theme":"supporter.json","bonus":0,"tag":""}`,
		"max_uses": 10,
	},
}

var errRedeemRejected = errors.New("redeem rejected")

type redeemPresentation struct {
	Type           string
	Note           string
	PopupTitle     string
	PopupMessage   string
	PopupStyle     string
	PopupSubtitle  string
	PopupLogo      string
	PopupIconColor string
	PopupBadgeText string
	PopupButton    string
}

func validateRedeemPresentation(value redeemPresentation) error {
	value.Type = strings.TrimSpace(value.Type)
	if len(value.Type) == 0 || len(value.Type) > 32 {
		return errors.New("type 长度需在 1-32 个字符之间")
	}
	for _, char := range value.Type {
		if (char >= 'a' && char <= 'z') || (char >= 'A' && char <= 'Z') || (char >= '0' && char <= '9') || char == '-' || char == '_' {
			continue
		}
		return errors.New("type 仅允许字母、数字、下划线和连字符")
	}
	allowedStyles := map[string]bool{
		"": true, "default": true,
		"style_sponsor_1": true, "style_sponsor_2": true, "style_sponsor_3": true,
		"style_sponsor_4": true, "style_streamer": true, "style_streamer_share": true,
	}
	if !allowedStyles[strings.TrimSpace(value.PopupStyle)] {
		return errors.New("popup_style 不在允许列表中")
	}
	allowedLogos := map[string]bool{
		"": true, "default": true, "gift": true, "star": true, "crown": true,
		"trophy": true, "mic": true, "users": true, "heart": true, "shield": true,
		"diamond": true, "rocket": true, "zap": true, "music": true, "camera": true,
		"bookmark": true, "compass": true, "feather": true, "coffee": true, "award": true,
		"hexagon": true, "sun": true,
	}
	if !allowedLogos[strings.TrimSpace(value.PopupLogo)] {
		return errors.New("popup_logo 不在允许列表中")
	}
	color := strings.TrimSpace(value.PopupIconColor)
	if color != "" && (len(color) != 7 || color[0] != '#') {
		return errors.New("popup_icon_color 必须是 #RRGGBB")
	}
	if color != "" {
		for _, char := range color[1:] {
			if (char >= '0' && char <= '9') || (char >= 'a' && char <= 'f') || (char >= 'A' && char <= 'F') {
				continue
			}
			return errors.New("popup_icon_color 必须是 #RRGGBB")
		}
	}
	lengthLimits := []struct {
		name  string
		value string
		limit int
	}{
		{"note", value.Note, 500},
		{"popup_title", value.PopupTitle, 128},
		{"popup_message", value.PopupMessage, 2000},
		{"popup_subtitle", value.PopupSubtitle, 128},
		{"popup_badge_text", value.PopupBadgeText, 128},
		{"popup_button", value.PopupButton, 64},
	}
	for _, field := range lengthLimits {
		if len([]rune(field.value)) > field.limit {
			return fmt.Errorf("%s 长度不能超过 %d 个字符", field.name, field.limit)
		}
	}
	return nil
}

type redeemThemeOption struct {
	Source      string `json:"source"`
	Filename    string `json:"filename"`
	Name        string `json:"name"`
	Author      string `json:"author,omitempty"`
	Version     string `json:"version,omitempty"`
	Visibility  string `json:"visibility"`
	Status      string `json:"status"`
	SortOrder   int    `json:"sort_order"`
	Checksum    string `json:"checksum,omitempty"`
	FileSize    int    `json:"file_size,omitempty"`
	Description string `json:"description,omitempty"`
	UpdatedAt   string `json:"updated_at,omitempty"`
}

var redeemLocalThemes = []redeemThemeOption{
	{Source: "local", Filename: "supporter.json", Name: "支持者主题", Visibility: "local", Status: "active", SortOrder: 10},
	{Source: "local", Filename: "bi_an.json", Name: "彼岸主题", Visibility: "local", Status: "active", SortOrder: 20},
	{Source: "local", Filename: "beiku.json", Name: "beiku 主题", Visibility: "local", Status: "active", SortOrder: 30},
	{Source: "local", Filename: "lianying.json", Name: "爱樱主题", Visibility: "local", Status: "active", SortOrder: 40},
	{Source: "local", Filename: "chifeng.json", Name: "赤峰主题", Visibility: "local", Status: "active", SortOrder: 50},
	{Source: "local", Filename: "wuye_fuyin.json", Name: "午夜福音的主题", Visibility: "local", Status: "active", SortOrder: 60},
	{Source: "local", Filename: "zqrx_mifuyu.json", Name: "zqrx-mifuyu", Visibility: "local", Status: "active", SortOrder: 70},
}

func redeemLocalThemeName(filename string) (string, bool) {
	filename = strings.TrimSpace(filename)
	for _, item := range redeemLocalThemes {
		if item.Filename == filename {
			return item.Name, true
		}
	}
	return "", false
}

func validateRedeemPayload(store *gorm.DB, payload string) error {
	if strings.TrimSpace(payload) == "" {
		return errors.New("payload 不能为空")
	}
	var parsed map[string]interface{}
	if err := json.Unmarshal([]byte(payload), &parsed); err != nil {
		return fmt.Errorf("payload 不是合法 JSON: %w", err)
	}
	allowedFields := map[string]bool{
		"theme": true, "bonus": true, "daily_limit_bonus": true, "tag": true,
	}
	for key := range parsed {
		if !allowedFields[key] {
			return fmt.Errorf("不支持的奖励字段: %s", key)
		}
	}
	hasReward := false
	if rawTheme, ok := parsed["theme"]; ok {
		themeFile, ok := rawTheme.(string)
		if !ok {
			return errors.New("theme 必须是字符串")
		}
		themeFile = strings.TrimSpace(themeFile)
		if themeFile != "" {
			hasReward = true
			if _, ok := redeemLocalThemeName(themeFile); !ok {
				if !remoteThemeFilenameRe.MatchString(themeFile) {
					return errors.New("theme 不在可兑换主题列表中")
				}
				var count int64
				if err := store.Model(&RemoteTheme{}).
					Where("filename = ? AND status = ?", themeFile, "active").
					Count(&count).Error; err != nil {
					return fmt.Errorf("主题查询失败: %w", err)
				}
				if count == 0 {
					return errors.New("服务器主题不存在或未启用")
				}
			}
		}
	}
	for _, key := range []string{"bonus", "daily_limit_bonus"} {
		rawValue, ok := parsed[key]
		if !ok {
			continue
		}
		value, ok := rawValue.(float64)
		if !ok || math.Trunc(value) != value {
			return fmt.Errorf("%s 必须是整数", key)
		}
		if value < 0 || value > 100000 {
			return fmt.Errorf("%s 必须在 0-100000 之间", key)
		}
		if value > 0 {
			hasReward = true
		}
	}
	if rawTag, ok := parsed["tag"]; ok {
		tagName, ok := rawTag.(string)
		if !ok {
			return errors.New("tag 必须是字符串")
		}
		tagName = strings.TrimSpace(tagName)
		if len(tagName) > 32 {
			return errors.New("tag 长度不能超过 32 个字符")
		}
		if tagName != "" {
			var count int64
			if err := store.Model(&UserTag{}).Where("name = ?", tagName).Count(&count).Error; err != nil {
				return fmt.Errorf("标签查询失败: %w", err)
			}
			if count == 0 {
				return errors.New("标签不存在")
			}
			hasReward = true
		}
	}
	if !hasReward {
		return errors.New("payload 未包含有效奖励")
	}
	return nil
}

func buildRedeemThemeOptions(store *gorm.DB) ([]redeemThemeOption, error) {
	options := make([]redeemThemeOption, 0, len(redeemLocalThemes))
	options = append(options, redeemLocalThemes...)

	var remoteThemes []RemoteTheme
	if err := store.Order("sort_order asc, id asc").Find(&remoteThemes).Error; err != nil {
		return nil, err
	}
	for _, theme := range remoteThemes {
		fileSize := theme.FileSize
		if fileSize <= 0 {
			fileSize = len([]byte(theme.ThemeData))
		}
		options = append(options, redeemThemeOption{
			Source:      "remote",
			Filename:    theme.Filename,
			Name:        theme.Name,
			Author:      theme.Author,
			Version:     theme.Version,
			Visibility:  theme.Visibility,
			Status:      theme.Status,
			SortOrder:   theme.SortOrder,
			Checksum:    theme.Checksum,
			FileSize:    fileSize,
			Description: theme.Description,
			UpdatedAt:   theme.UpdatedAt.Format("2006-01-02 15:04:05"),
		})
	}
	return options, nil
}

func loadRedeemRemoteTheme(store *gorm.DB, filename string) (*RemoteTheme, error) {
	var theme RemoteTheme
	if err := store.Where("filename = ? AND status = ?", filename, "active").First(&theme).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, errors.New("服务器主题不存在或未启用")
		}
		return nil, err
	}
	return &theme, nil
}

func buildRedeemRemoteThemeBundle(theme RemoteTheme) (map[string]interface{}, error) {
	var themeData map[string]interface{}
	if err := json.Unmarshal([]byte(theme.ThemeData), &themeData); err != nil {
		return nil, errors.New("服务器主题数据损坏")
	}
	fileSize := theme.FileSize
	if fileSize <= 0 {
		fileSize = len([]byte(theme.ThemeData))
	}
	return map[string]interface{}{
		"filename":    theme.Filename,
		"name":        theme.Name,
		"author":      theme.Author,
		"version":     theme.Version,
		"visibility":  theme.Visibility,
		"status":      theme.Status,
		"sort_order":  theme.SortOrder,
		"checksum":    theme.Checksum,
		"file_size":   fileSize,
		"description": theme.Description,
		"updated_at":  theme.UpdatedAt.Format("2006-01-02 15:04:05"),
		"theme_data":  themeData,
		"theme_text":  theme.ThemeData,
	}, nil
}

func getOrCreateAIUserLimit(store *gorm.DB, machineID string) (*AIUserLimit, error) {
	var existing AIUserLimit
	err := store.Where("machine_id = ?", machineID).First(&existing).Error
	if err == nil {
		return &existing, nil
	}
	if !errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, err
	}

	existing = AIUserLimit{MachineID: machineID}
	if err := store.Create(&existing).Error; err != nil {
		return nil, err
	}
	return &existing, nil
}

func recordRewardLedger(store *gorm.DB, entry RewardLedger) error {
	if strings.TrimSpace(entry.EventID) == "" || strings.TrimSpace(entry.MachineID) == "" {
		return errors.New("权益流水缺少事件或用户标识")
	}
	return store.Create(&entry).Error
}

// executeRedeemPayload 执行兑换码对应的功能，支持自定义弹窗
func executeRedeemPayload(store *gorm.DB, machineID string, redeemCode *RedeemCode) (map[string]interface{}, error) {
	var payload map[string]interface{}
	if err := json.Unmarshal([]byte(redeemCode.Payload), &payload); err != nil {
		return nil, fmt.Errorf("payload 解析失败: %v", err)
	}

	var messages []string

	// 处理主题解锁
	themeFile, _ := payload["theme"].(string)
	themeUnlocked := themeFile != ""
	themeName := ""
	var remoteThemeBundle map[string]interface{}
	if themeUnlocked {
		themeFile = strings.TrimSpace(themeFile)
		if localName, ok := redeemLocalThemeName(themeFile); ok {
			themeName = localName
		} else if remoteThemeFilenameRe.MatchString(themeFile) {
			remoteTheme, err := loadRedeemRemoteTheme(store, themeFile)
			if err != nil {
				return nil, err
			}
			bundle, err := buildRedeemRemoteThemeBundle(*remoteTheme)
			if err != nil {
				return nil, err
			}
			themeName = remoteTheme.Name
			remoteThemeBundle = bundle
		} else {
			return nil, errors.New("主题不在可兑换主题列表中")
		}
		if themeName == "" {
			themeName = themeFile
		}
	}

	// 处理 AI 永久额度增加
	if bonusVal, ok := payload["bonus"]; ok {
		bonusNumber, ok := bonusVal.(float64)
		if !ok || math.Trunc(bonusNumber) != bonusNumber || bonusNumber < 0 || bonusNumber > 100000 {
			return nil, errors.New("bonus 奖励值无效")
		}
		bonus := int(bonusNumber)
		if bonus > 0 {
			existing, err := getOrCreateAIUserLimit(store, machineID)
			if err != nil {
				return nil, fmt.Errorf("读取 AI 额度失败: %w", err)
			}
			if err := store.Model(existing).Update("bonus_credits", gorm.Expr("bonus_credits + ?", bonus)).Error; err != nil {
				return nil, fmt.Errorf("发放 AI 永久额度失败: %w", err)
			}
			before := existing.BonusCredits
			if err := store.Where("machine_id = ?", machineID).First(existing).Error; err != nil {
				return nil, fmt.Errorf("核对 AI 永久额度失败: %w", err)
			}
			if err := recordRewardLedger(store, RewardLedger{
				EventID:         fmt.Sprintf("redeem:%d:%s:bonus", redeemCode.ID, machineID),
				MachineID:       machineID,
				SourceType:      "redeem",
				SourceID:        redeemCode.ID,
				RewardType:      "bonus_credits",
				Delta:           bonus,
				BalanceBefore:   before,
				BalanceAfter:    existing.BonusCredits,
				PayloadSnapshot: redeemCode.Payload,
			}); err != nil {
				return nil, fmt.Errorf("记录 AI 永久额度流水失败: %w", err)
			}
			messages = append(messages, fmt.Sprintf("获得 %d 次永久AI对话额度", bonus))
		}
	}

	// 处理每日对话上限增加
	if dlbVal, ok := payload["daily_limit_bonus"]; ok {
		dailyNumber, ok := dlbVal.(float64)
		if !ok || math.Trunc(dailyNumber) != dailyNumber || dailyNumber < 0 || dailyNumber > 100000 {
			return nil, errors.New("daily_limit_bonus 奖励值无效")
		}
		dlb := int(dailyNumber)
		if dlb > 0 {
			existing, err := getOrCreateAIUserLimit(store, machineID)
			if err != nil {
				return nil, fmt.Errorf("读取每日额度失败: %w", err)
			}
			baseLimit := existing.DailyLimit
			if baseLimit <= 0 {
				baseLimit = aiConfig.DailyLimit
			}
			if baseLimit <= 0 {
				baseLimit = defaultAIConfig().DailyLimit
			}
			newLimit := baseLimit + dlb
			if err := store.Model(existing).Update("daily_limit", newLimit).Error; err != nil {
				return nil, fmt.Errorf("发放每日额度失败: %w", err)
			}
			if err := recordRewardLedger(store, RewardLedger{
				EventID:         fmt.Sprintf("redeem:%d:%s:daily", redeemCode.ID, machineID),
				MachineID:       machineID,
				SourceType:      "redeem",
				SourceID:        redeemCode.ID,
				RewardType:      "daily_limit",
				Delta:           dlb,
				BalanceBefore:   baseLimit,
				BalanceAfter:    newLimit,
				PayloadSnapshot: redeemCode.Payload,
			}); err != nil {
				return nil, fmt.Errorf("记录每日额度流水失败: %w", err)
			}
			messages = append(messages, "每日对话额度增加")
		}
	}

	// 处理用户标签
	if tagName, ok := payload["tag"].(string); ok && tagName != "" {
		var tagDef UserTag
		if err := store.Where("name = ?", tagName).First(&tagDef).Error; err != nil {
			return nil, errors.New("兑换标签不存在")
		}
		var record TelemetryRecord
		err := store.Where("machine_id = ?", machineID).First(&record).Error
		if err != nil {
			if !errors.Is(err, gorm.ErrRecordNotFound) {
				return nil, fmt.Errorf("读取用户标签失败: %w", err)
			}
			record = TelemetryRecord{
				MachineID:  machineID,
				LastSeenAt: time.Now(),
			}
			if err := store.Create(&record).Error; err != nil {
				return nil, fmt.Errorf("创建用户记录失败: %w", err)
			}
		}
		if _, err := ensureUserUIDTx(store, machineID, record.ID); err != nil {
			return nil, fmt.Errorf("创建用户 UID 失败: %w", err)
		}

		var currentTags []string
		if record.Tags != "" {
			_ = json.Unmarshal([]byte(record.Tags), &currentTags)
		}
		found := false
		for _, t := range currentTags {
			if t == tagName {
				found = true
				break
			}
		}
		if !found {
			currentTags = append(currentTags, tagName)
			tagsJSON, _ := json.Marshal(currentTags)
			if err := store.Model(&record).Update("tags", string(tagsJSON)).Error; err != nil {
				return nil, fmt.Errorf("写入用户标签失败: %w", err)
			}
		}

		messages = append(messages, fmt.Sprintf("获得「%s」称号", tagDef.DisplayName))
		if err := recordRewardLedger(store, RewardLedger{
			EventID:         fmt.Sprintf("redeem:%d:%s:tag", redeemCode.ID, machineID),
			MachineID:       machineID,
			SourceType:      "redeem",
			SourceID:        redeemCode.ID,
			RewardType:      "tag",
			PayloadSnapshot: redeemCode.Payload,
		}); err != nil {
			return nil, fmt.Errorf("记录标签流水失败: %w", err)
		}
	}

	if themeUnlocked {
		messages = append(messages, fmt.Sprintf("解锁「%s」主题", themeName))
		if err := recordRewardLedger(store, RewardLedger{
			EventID:         fmt.Sprintf("redeem:%d:%s:theme", redeemCode.ID, machineID),
			MachineID:       machineID,
			SourceType:      "redeem",
			SourceID:        redeemCode.ID,
			RewardType:      "theme",
			PayloadSnapshot: redeemCode.Payload,
		}); err != nil {
			return nil, fmt.Errorf("记录主题流水失败: %w", err)
		}
	}

	// 构建客户端指令（优先使用自定义弹窗设置）
	resultMsg := "兑换成功！"
	if len(messages) > 0 {
		resultMsg = "🎉 兑换成功！\n" + strings.Join(messages, "\n")
	}
	title := "兑换成功"
	if redeemCode.PopupTitle != "" {
		title = redeemCode.PopupTitle
	}
	if redeemCode.PopupMessage != "" {
		resultMsg = redeemCode.PopupMessage
	}

	cmd := map[string]interface{}{
		"type":             "redeem_result",
		"success":          true,
		"redeem_type":      redeemCode.Type,
		"title":            title,
		"message":          resultMsg,
		"popup_style":      redeemCode.PopupStyle,
		"popup_subtitle":   redeemCode.PopupSubtitle,
		"popup_logo":       redeemCode.PopupLogo,
		"popup_icon_color": redeemCode.PopupIconColor,
		"popup_badge_text": redeemCode.PopupBadgeText,
		"popup_button":     redeemCode.PopupButton,
		"theme_unlocked":   themeUnlocked,
	}
	if themeUnlocked {
		cmd["theme_file"] = themeFile
	}
	if remoteThemeBundle != nil {
		cmd["remote_theme"] = remoteThemeBundle
	}

	return cmd, nil
}

// initRedeemRoutes 注册兑换码管理 API
func initRedeemRoutes(admin *gin.RouterGroup) {
	redeem := admin.Group("/redeem")
	{
		// 获取兑换码列表
		redeem.GET("", func(c *gin.Context) {
			var codes []RedeemCode
			db.Order("created_at DESC").Find(&codes)

			// 关联每个码的使用记录数（覆盖 used_count 以确保准确）
			result := make([]map[string]interface{}, len(codes))
			for i, code := range codes {
				codeJSON, _ := json.Marshal(code)
				var m map[string]interface{}
				json.Unmarshal(codeJSON, &m)

				// 判断状态
				status := "active"
				if !code.IsActive {
					status = "disabled"
				} else if code.ExpiresAt != nil && code.ExpiresAt.Before(time.Now()) {
					status = "expired"
				} else if code.MaxUses > 0 && code.UsedCount >= code.MaxUses {
					status = "used"
				}
				m["status"] = status
				result[i] = m
			}

			c.JSON(200, gin.H{"codes": result})
		})

		// 获取预定义类型列表
		redeem.GET("/presets", func(c *gin.Context) {
			c.JSON(200, gin.H{"presets": redeemPresets})
		})

		// 获取可绑定到兑换码的主题列表
		redeem.GET("/themes", func(c *gin.Context) {
			themes, err := buildRedeemThemeOptions(db)
			if err != nil {
				c.JSON(500, gin.H{"error": "主题列表读取失败"})
				return
			}
			c.JSON(200, gin.H{"themes": themes})
		})

		// 生成兑换码（单个或批量，支持自定义码）
		redeem.POST("", func(c *gin.Context) {
			var req struct {
				Type           string `json:"type"`
				Payload        string `json:"payload"`
				MaxUses        *int   `json:"max_uses"`
				Count          int    `json:"count"`
				CustomCode     string `json:"custom_code"`
				Note           string `json:"note"`
				ExpireIn       int    `json:"expire_in"`
				PopupTitle     string `json:"popup_title"`
				PopupMessage   string `json:"popup_message"`
				PopupStyle     string `json:"popup_style"`
				PopupSubtitle  string `json:"popup_subtitle"`
				PopupLogo      string `json:"popup_logo"`
				PopupIconColor string `json:"popup_icon_color"`
				PopupBadgeText string `json:"popup_badge_text"`
				PopupButton    string `json:"popup_button"`
			}
			if err := c.ShouldBindJSON(&req); err != nil {
				c.JSON(400, gin.H{"error": "参数错误"})
				return
			}

			if req.Count <= 0 {
				req.Count = 1
			}
			if req.Count > 100 {
				c.JSON(400, gin.H{"error": "单次最多生成 100 个兑换码"})
				return
			}
			maxUses := 1
			if req.MaxUses != nil {
				maxUses = *req.MaxUses
			}
			if maxUses < 0 {
				c.JSON(400, gin.H{"error": "max_uses 不能为负数"})
				return
			}
			if req.PopupStyle == "" {
				req.PopupStyle = "default"
			}
			if req.ExpireIn < 0 || req.ExpireIn > 3650 {
				c.JSON(400, gin.H{"error": "expire_in 必须在 0-3650 天之间"})
				return
			}
			presentation := redeemPresentation{
				Type:           req.Type,
				Note:           req.Note,
				PopupTitle:     req.PopupTitle,
				PopupMessage:   req.PopupMessage,
				PopupStyle:     req.PopupStyle,
				PopupSubtitle:  req.PopupSubtitle,
				PopupLogo:      req.PopupLogo,
				PopupIconColor: req.PopupIconColor,
				PopupBadgeText: req.PopupBadgeText,
				PopupButton:    req.PopupButton,
			}
			if err := validateRedeemPresentation(presentation); err != nil {
				c.JSON(400, gin.H{"error": err.Error()})
				return
			}
			req.Type = strings.TrimSpace(req.Type)
			if err := validateRedeemPayload(db, req.Payload); err != nil {
				c.JSON(400, gin.H{"error": err.Error()})
				return
			}

			// 自定义码校验：统一大写，仅允许字母、数字、连字符，长度 3-32
			customCode := strings.ToUpper(strings.TrimSpace(req.CustomCode))
			if customCode != "" {
				if len(customCode) < 3 || len(customCode) > 32 {
					c.JSON(400, gin.H{"error": "自定义兑换码长度需在 3-32 个字符之间"})
					return
				}
				for _, ch := range customCode {
					if !((ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9') || ch == '-') {
						c.JSON(400, gin.H{"error": "自定义兑换码仅允许字母、数字和连字符"})
						return
					}
				}
				req.Count = 1
			}

			var expiresAt *time.Time
			if req.ExpireIn > 0 {
				t := time.Now().Add(time.Duration(req.ExpireIn) * 24 * time.Hour)
				expiresAt = &t
			}

			created := make([]RedeemCode, 0, req.Count)

			// 自定义码：直接入库，不走随机生成循环
			if customCode != "" {
				code := RedeemCode{
					Code:           customCode,
					Type:           req.Type,
					Payload:        req.Payload,
					MaxUses:        maxUses,
					IsActive:       true,
					Note:           req.Note,
					ExpiresAt:      expiresAt,
					PopupTitle:     req.PopupTitle,
					PopupMessage:   req.PopupMessage,
					PopupStyle:     req.PopupStyle,
					PopupSubtitle:  req.PopupSubtitle,
					PopupLogo:      req.PopupLogo,
					PopupIconColor: req.PopupIconColor,
					PopupBadgeText: req.PopupBadgeText,
					PopupButton:    req.PopupButton,
				}
				if err := db.Create(&code).Error; err != nil {
					if strings.Contains(strings.ToLower(err.Error()), "unique") {
						c.JSON(409, gin.H{"error": "该兑换码已存在"})
						return
					}
					log.Printf("[Redeem] 创建自定义兑换码失败: %v", err)
					c.JSON(500, gin.H{"error": "创建失败"})
					return
				}
				log.Printf("[Redeem] 创建自定义兑换码 %s (类型: %s)", maskRedeemCode(customCode), req.Type)
				c.JSON(200, gin.H{"status": "success", "codes": []RedeemCode{code}, "count": 1})
				return
			}

			if err := db.Transaction(func(tx *gorm.DB) error {
				for i := 0; i < req.Count; i++ {
					codeTemplate := RedeemCode{
						Type:           req.Type,
						Payload:        req.Payload,
						MaxUses:        maxUses,
						IsActive:       true,
						Note:           req.Note,
						ExpiresAt:      expiresAt,
						PopupTitle:     req.PopupTitle,
						PopupMessage:   req.PopupMessage,
						PopupStyle:     req.PopupStyle,
						PopupSubtitle:  req.PopupSubtitle,
						PopupLogo:      req.PopupLogo,
						PopupIconColor: req.PopupIconColor,
						PopupBadgeText: req.PopupBadgeText,
						PopupButton:    req.PopupButton,
					}

					var createdCode RedeemCode
					createdOK := false
					for attempt := 0; attempt < 10; attempt++ {
						code := codeTemplate
						generatedCode, err := generateCode(4, 3)
						if err != nil {
							return err
						}
						code.Code = generatedCode
						if err := tx.Create(&code).Error; err != nil {
							if strings.Contains(strings.ToLower(err.Error()), "unique") {
								continue
							}
							return err
						}
						createdCode = code
						createdOK = true
						break
					}
					if !createdOK {
						return errors.New("重试后仍未生成唯一兑换码")
					}
					created = append(created, createdCode)
				}
				return nil
			}); err != nil {
				log.Printf("[Redeem] 批量创建兑换码失败: %v", err)
				c.JSON(500, gin.H{"error": "批量创建失败，未保存任何兑换码"})
				return
			}

			log.Printf("[Redeem] 批量生成 %d 个兑换码 (类型: %s)", len(created), req.Type)
			c.JSON(200, gin.H{"status": "success", "codes": created, "count": len(created)})
		})

		// 修改兑换码（停用/启用/自定义弹窗/payload）
		redeem.PUT("/:id", func(c *gin.Context) {
			id := c.Param("id")
			var req struct {
				IsActive       *bool   `json:"is_active"`
				Note           *string `json:"note"`
				MaxUses        *int    `json:"max_uses"`
				Payload        *string `json:"payload"`
				Type           *string `json:"type"`
				PopupTitle     *string `json:"popup_title"`
				PopupMessage   *string `json:"popup_message"`
				PopupStyle     *string `json:"popup_style"`
				PopupSubtitle  *string `json:"popup_subtitle"`
				PopupLogo      *string `json:"popup_logo"`
				PopupIconColor *string `json:"popup_icon_color"`
				PopupBadgeText *string `json:"popup_badge_text"`
				PopupButton    *string `json:"popup_button"`
			}
			if err := c.ShouldBindJSON(&req); err != nil {
				c.JSON(400, gin.H{"error": "参数错误"})
				return
			}

			var code RedeemCode
			if err := db.First(&code, id).Error; err != nil {
				c.JSON(404, gin.H{"error": "兑换码不存在"})
				return
			}
			candidate := redeemPresentation{
				Type:           code.Type,
				Note:           code.Note,
				PopupTitle:     code.PopupTitle,
				PopupMessage:   code.PopupMessage,
				PopupStyle:     code.PopupStyle,
				PopupSubtitle:  code.PopupSubtitle,
				PopupLogo:      code.PopupLogo,
				PopupIconColor: code.PopupIconColor,
				PopupBadgeText: code.PopupBadgeText,
				PopupButton:    code.PopupButton,
			}
			if req.Note != nil {
				candidate.Note = *req.Note
			}
			if req.Type != nil {
				candidate.Type = strings.TrimSpace(*req.Type)
			}
			if req.PopupTitle != nil {
				candidate.PopupTitle = *req.PopupTitle
			}
			if req.PopupMessage != nil {
				candidate.PopupMessage = *req.PopupMessage
			}
			if req.PopupStyle != nil {
				candidate.PopupStyle = *req.PopupStyle
			}
			if req.PopupSubtitle != nil {
				candidate.PopupSubtitle = *req.PopupSubtitle
			}
			if req.PopupLogo != nil {
				candidate.PopupLogo = *req.PopupLogo
			}
			if req.PopupIconColor != nil {
				candidate.PopupIconColor = *req.PopupIconColor
			}
			if req.PopupBadgeText != nil {
				candidate.PopupBadgeText = *req.PopupBadgeText
			}
			if req.PopupButton != nil {
				candidate.PopupButton = *req.PopupButton
			}
			if req.MaxUses != nil && *req.MaxUses < 0 {
				c.JSON(400, gin.H{"error": "max_uses 不能为负数"})
				return
			}
			if err := validateRedeemPresentation(candidate); err != nil {
				c.JSON(400, gin.H{"error": err.Error()})
				return
			}

			updates := map[string]interface{}{}
			if req.IsActive != nil {
				updates["is_active"] = *req.IsActive
			}
			if req.Note != nil {
				updates["note"] = *req.Note
			}
			if req.MaxUses != nil {
				updates["max_uses"] = *req.MaxUses
			}
			if req.Payload != nil {
				if err := validateRedeemPayload(db, *req.Payload); err != nil {
					c.JSON(400, gin.H{"error": err.Error()})
					return
				}
				updates["payload"] = *req.Payload
			}
			if req.Type != nil {
				updates["type"] = candidate.Type
			}
			if req.PopupTitle != nil {
				updates["popup_title"] = *req.PopupTitle
			}
			if req.PopupMessage != nil {
				updates["popup_message"] = *req.PopupMessage
			}
			if req.PopupStyle != nil {
				updates["popup_style"] = *req.PopupStyle
			}
			if req.PopupSubtitle != nil {
				updates["popup_subtitle"] = *req.PopupSubtitle
			}
			if req.PopupLogo != nil {
				updates["popup_logo"] = *req.PopupLogo
			}
			if req.PopupIconColor != nil {
				updates["popup_icon_color"] = *req.PopupIconColor
			}
			if req.PopupBadgeText != nil {
				updates["popup_badge_text"] = *req.PopupBadgeText
			}
			if req.PopupButton != nil {
				updates["popup_button"] = *req.PopupButton
			}
			if len(updates) > 0 {
				if err := db.Model(&code).Updates(updates).Error; err != nil {
					c.JSON(500, gin.H{"error": "保存失败"})
					return
				}
			}
			c.JSON(200, gin.H{"status": "success"})
		})

		// 删除兑换码
		redeem.DELETE("/:id", func(c *gin.Context) {
			id := c.Param("id")
			if err := db.Delete(&RedeemCode{}, id).Error; err != nil {
				c.JSON(500, gin.H{"error": "删除失败"})
				return
			}
			c.JSON(200, gin.H{"status": "success"})
		})

		// 批量删除兑换码
		redeem.POST("/batch/delete", func(c *gin.Context) {
			var req struct {
				IDs []uint `json:"ids"`
			}
			if err := c.ShouldBindJSON(&req); err != nil || len(req.IDs) == 0 {
				c.JSON(400, gin.H{"error": "参数错误"})
				return
			}
			result := db.Where("id IN ?", req.IDs).Delete(&RedeemCode{})
			if result.Error != nil {
				c.JSON(500, gin.H{"error": "批量删除失败"})
				return
			}
			log.Printf("[Redeem] 批量删除 %d 个兑换码", result.RowsAffected)
			c.JSON(200, gin.H{"status": "success", "deleted": result.RowsAffected})
		})

		// 批量更新兑换码状态（启用/停用）
		redeem.PUT("/batch", func(c *gin.Context) {
			var req struct {
				IDs      []uint `json:"ids"`
				IsActive *bool  `json:"is_active"`
			}
			if err := c.ShouldBindJSON(&req); err != nil || len(req.IDs) == 0 || req.IsActive == nil {
				c.JSON(400, gin.H{"error": "参数错误"})
				return
			}
			result := db.Model(&RedeemCode{}).Where("id IN ?", req.IDs).Update("is_active", *req.IsActive)
			if result.Error != nil {
				c.JSON(500, gin.H{"error": "批量更新失败"})
				return
			}
			action := "启用"
			if !*req.IsActive {
				action = "停用"
			}
			log.Printf("[Redeem] 批量%s %d 个兑换码", action, result.RowsAffected)
			c.JSON(200, gin.H{"status": "success", "updated": result.RowsAffected})
		})

		// 使用记录查询
		redeem.GET("/records", func(c *gin.Context) {
			var records []RedeemRecord
			db.Order("created_at DESC").Limit(1000).Find(&records)

			result := make([]map[string]interface{}, len(records))
			for i, r := range records {
				// 关联用户别名
				var alias string
				db.Model(&TelemetryRecord{}).Where("machine_id = ?", r.MachineID).Select("alias").Scan(&alias)

				result[i] = map[string]interface{}{
					"id":         r.ID,
					"code":       r.Code,
					"machine_id": r.MachineID,
					"alias":      alias,
					"created_at": r.CreatedAt.Format("2006-01-02 15:04:05"),
				}
			}
			c.JSON(200, gin.H{"records": result})
		})
	}
}

func setTelemetryPendingCommandTx(tx *gorm.DB, machineID string, pendingCommand string) error {
	machineID = strings.TrimSpace(machineID)
	if machineID == "" {
		return fmt.Errorf("machine_id required")
	}

	pendingUpdate := tx.Model(&TelemetryRecord{}).
		Where("machine_id = ?", machineID).
		Update("pending_command", pendingCommand)
	if pendingUpdate.Error != nil {
		return pendingUpdate.Error
	}
	if pendingUpdate.RowsAffected == 0 {
		placeholder := TelemetryRecord{
			MachineID:      machineID,
			PendingCommand: pendingCommand,
			LastSeenAt:     time.Now(),
		}
		if err := tx.Create(&placeholder).Error; err != nil {
			return err
		}
	}

	var telemetryRecord TelemetryRecord
	if err := tx.Select("id", "machine_id").
		Where("machine_id = ?", machineID).
		First(&telemetryRecord).Error; err != nil {
		return err
	}
	_, err := ensureUserUIDTx(tx, machineID, telemetryRecord.ID)
	if err != nil {
		return err
	}
	_, err = enqueueClientCommandTx(tx, machineID, pendingCommand, "redeem", 0, 0)
	return err
}

// handleRedeem 客户端提交兑换码验证（公开端点，UA 校验）
func handleRedeem(c *gin.Context) {
	if !sysConfig.RedeemCodeEnabled {
		c.JSON(403, gin.H{"error": "兑换码功能已关闭"})
		return
	}

	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, 8<<10)
	var req struct {
		Code      string `json:"code"`
		MachineID string `json:"machine_id"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"error": "参数错误"})
		return
	}

	code := strings.TrimSpace(strings.ToUpper(req.Code))
	if code == "" {
		c.JSON(400, gin.H{"error": "请输入兑换码"})
		return
	}
	if req.MachineID == "" {
		c.JSON(400, gin.H{"error": "缺少设备标识"})
		return
	}
	if !ensureClientMachineBinding(c, req.MachineID) {
		return
	}

	var (
		cmd        map[string]interface{}
		failMsg    string
		redeemType string
	)
	err := db.Transaction(func(tx *gorm.DB) error {
		var existingRecord RedeemRecord
		existingErr := tx.Where("code = ? AND machine_id = ?", code, req.MachineID).First(&existingRecord).Error
		if existingErr == nil {
			if strings.TrimSpace(existingRecord.ResultCommand) == "" {
				failMsg = "您已使用过此兑换码，旧记录无可重放结果"
				return errRedeemRejected
			}
			if err := json.Unmarshal([]byte(existingRecord.ResultCommand), &cmd); err != nil {
				return fmt.Errorf("兑换结果快照损坏: %w", err)
			}
			redeemType, _ = cmd["redeem_type"].(string)
			return nil
		}
		if !errors.Is(existingErr, gorm.ErrRecordNotFound) {
			return existingErr
		}

		var redeemCode RedeemCode
		if err := tx.Where("code = ?", code).First(&redeemCode).Error; err != nil {
			failMsg = "兑换码无效或不存在"
			return errRedeemRejected
		}

		if !redeemCode.IsActive {
			failMsg = "该兑换码已被停用"
			return errRedeemRejected
		}
		if redeemCode.ExpiresAt != nil && redeemCode.ExpiresAt.Before(time.Now()) {
			failMsg = "该兑换码已过期"
			return errRedeemRejected
		}
		if redeemCode.MaxUses > 0 && redeemCode.UsedCount >= redeemCode.MaxUses {
			failMsg = "该兑换码已被使用完毕"
			return errRedeemRejected
		}

		record := RedeemRecord{
			RedeemCodeID:    redeemCode.ID,
			Code:            code,
			MachineID:       req.MachineID,
			PayloadSnapshot: redeemCode.Payload,
		}
		if err := tx.Create(&record).Error; err != nil {
			if strings.Contains(strings.ToLower(err.Error()), "unique") {
				failMsg = "您已使用过此兑换码"
				return errRedeemRejected
			}
			return err
		}

		executedCmd, err := executeRedeemPayload(tx, req.MachineID, &redeemCode)
		if err != nil {
			return err
		}

		updateQuery := tx.Model(&RedeemCode{}).Where("id = ?", redeemCode.ID)
		if redeemCode.MaxUses > 0 {
			updateQuery = updateQuery.Where("used_count < max_uses")
		}
		updateResult := updateQuery.Update("used_count", gorm.Expr("used_count + 1"))
		if updateResult.Error != nil {
			return updateResult.Error
		}
		if updateResult.RowsAffected == 0 {
			failMsg = "该兑换码已被使用完毕"
			return errRedeemRejected
		}

		commandID, err := newClientCommandID()
		if err != nil {
			return fmt.Errorf("生成命令标识失败: %w", err)
		}
		executedCmd["command_id"] = commandID
		cmdJSON, err := json.Marshal(executedCmd)
		if err != nil {
			return fmt.Errorf("序列化兑换结果失败: %w", err)
		}
		if err := tx.Model(&record).Update("result_command", string(cmdJSON)).Error; err != nil {
			return fmt.Errorf("保存兑换结果失败: %w", err)
		}
		if supportsClientCommandAcknowledgement(c) {
			if err := setTelemetryPendingCommandTx(tx, req.MachineID, string(cmdJSON)); err != nil {
				return err
			}
		}

		cmd = executedCmd
		redeemType = redeemCode.Type
		return nil
	})
	if err != nil {
		if errors.Is(err, errRedeemRejected) {
			c.JSON(200, gin.H{"status": "fail", "error": failMsg})
			return
		}
		log.Printf("[Redeem] 执行失败: %v", err)
		c.JSON(500, gin.H{"status": "fail", "error": "兑换执行失败"})
		return
	}

	log.Printf("[Redeem] 兑换成功 - 码: %s, 用户: %s, 类型: %s", maskRedeemCode(code), req.MachineID, redeemType)

	c.JSON(200, gin.H{
		"status":  "success",
		"message": "兑换成功",
		"command": cmd,
	})
}

// 统计辅助函数
func getRedeemStats() map[string]interface{} {
	var total, active, used, expired int64

	db.Model(&RedeemCode{}).Count(&total)
	db.Model(&RedeemCode{}).Where("is_active = ? AND (expires_at IS NULL OR expires_at > ?) AND (max_uses = 0 OR used_count < max_uses)", true, time.Now()).Count(&active)
	db.Model(&RedeemCode{}).Where("max_uses > 0 AND used_count >= max_uses").Count(&used)
	db.Model(&RedeemCode{}).Where("expires_at IS NOT NULL AND expires_at <= ?", time.Now()).Count(&expired)

	var totalRecords int64
	db.Model(&RedeemRecord{}).Count(&totalRecords)

	return map[string]interface{}{
		"total":         total,
		"active":        active,
		"used":          used,
		"expired":       expired,
		"total_records": totalRecords,
	}
}
