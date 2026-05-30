package main

import (
	"encoding/json"
	"log"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
)

// 配置持久化层：将 KV 配置存入 SQLite，服务重启后自动恢复

var configMu sync.RWMutex

// SaveConfig 将单个配置项写入数据库
func SaveConfig(key, value string) {
	configMu.Lock()
	defer configMu.Unlock()

	db.Where("key = ?", key).Assign(ContentConfig{Value: value}).FirstOrCreate(&ContentConfig{Key: key})
}

// LoadConfig 从数据库读取单个配置项
func LoadConfig(key string) string {
	configMu.RLock()
	defer configMu.RUnlock()

	var cfg ContentConfig
	if err := db.Where("key = ?", key).First(&cfg).Error; err != nil {
		return ""
	}
	return cfg.Value
}

// LoadAllConfigs 从数据库读取所有配置项
func LoadAllConfigs() map[string]string {
	configMu.RLock()
	defer configMu.RUnlock()

	var items []ContentConfig
	db.Find(&items)
	result := make(map[string]string, len(items))
	for _, item := range items {
		result[item.Key] = item.Value
	}
	return result
}

// PersistSysConfig 将当前 sysConfig 持久化到数据库
func PersistSysConfig() {
	data, err := json.Marshal(sysConfig)
	if err != nil {
		log.Printf("[Config] sysConfig 序列化失败: %v", err)
		return
	}
	SaveConfig("sys_config", string(data))
}

// RestoreSysConfig 从数据库恢复 sysConfig（服务启动时调用）
func RestoreSysConfig() {
	raw := LoadConfig("sys_config")
	if raw == "" {
		log.Println("[Config] 无历史配置，使用默认值")
		applyDefaultUserFeatureFlags(&sysConfig, nil)
		return
	}
	var rawMap map[string]json.RawMessage
	if err := json.Unmarshal([]byte(raw), &rawMap); err != nil {
		rawMap = nil
	}
	if err := json.Unmarshal([]byte(raw), &sysConfig); err != nil {
		log.Printf("[Config] sysConfig 反序列化失败: %v", err)
		applyDefaultUserFeatureFlags(&sysConfig, nil)
		return
	}
	applyDefaultUserFeatureFlags(&sysConfig, rawMap)
	log.Println("[Config] 已从数据库恢复 sysConfig")
}

// SaveAdCarouselItems 将广告轮播数据持久化。图片文件保留在素材库中，需由后台显式删除。
func SaveAdCarouselItems(items []AdCarouselItem) {
	data, err := json.Marshal(items)
	if err != nil {
		log.Printf("[Config] 广告轮播序列化失败: %v", err)
		return
	}
	SaveConfig("ad_carousel_items", string(data))
}

type UploadMediaReference struct {
	Source string `json:"source"`
	ID     string `json:"id,omitempty"`
	Field  string `json:"field,omitempty"`
	Label  string `json:"label"`
}

func isAllowedUploadImageFilename(filename string) bool {
	name := strings.TrimSpace(filename)
	if name == "" || strings.Contains(name, "/") || strings.Contains(name, "\\") || strings.Contains(name, "..") {
		return false
	}
	ext := strings.ToLower(filepath.Ext(name))
	switch ext {
	case ".jpg", ".jpeg", ".png", ".webp", ".gif":
		return true
	default:
		return false
	}
}

func safeUploadNamePart(value string) string {
	value = strings.TrimSpace(value)
	var builder strings.Builder
	lastUnderscore := false
	for _, r := range value {
		allowed := (r >= 'a' && r <= 'z') ||
			(r >= 'A' && r <= 'Z') ||
			(r >= '0' && r <= '9') ||
			r == '-' || r == '_'
		if allowed {
			builder.WriteRune(r)
			lastUnderscore = false
			continue
		}
		if !lastUnderscore && builder.Len() > 0 {
			builder.WriteByte('_')
			lastUnderscore = true
		}
	}
	result := strings.Trim(builder.String(), "_-.")
	if result == "" {
		return "item"
	}
	if len(result) > 48 {
		return result[:48]
	}
	return result
}

func uploadMediaFilename(raw string) string {
	value := strings.TrimSpace(raw)
	if value == "" {
		return ""
	}
	if idx := strings.Index(value, "/uploads/"); idx >= 0 {
		value = value[idx+len("/uploads/"):]
	} else if strings.HasPrefix(value, "uploads/") {
		value = strings.TrimPrefix(value, "uploads/")
	} else {
		return ""
	}
	value = strings.TrimLeft(value, "/\\")
	if !isAllowedUploadImageFilename(value) {
		return ""
	}
	return value
}

func collectUploadMediaReferences() map[string][]UploadMediaReference {
	refs := make(map[string][]UploadMediaReference)
	addRef := func(raw string, ref UploadMediaReference) {
		filename := uploadMediaFilename(raw)
		if filename == "" {
			return
		}
		refs[filename] = append(refs[filename], ref)
	}

	for _, item := range LoadAdCarouselItems() {
		label := "轮播广告"
		if strings.TrimSpace(item.ID) != "" {
			label += ": " + strings.TrimSpace(item.ID)
		}
		addRef(item.Image, UploadMediaReference{
			Source: "ad_carousel",
			ID:     strings.TrimSpace(item.ID),
			Field:  "image",
			Label:  label,
		})
	}

	for _, item := range loadKnowledgeAdsConfigData().Items {
		id := strings.TrimSpace(item.ID)
		if id == "" {
			id = "knowledge_ad"
		}
		addRef(item.Avatar, UploadMediaReference{
			Source: "knowledge_ads",
			ID:     id,
			Field:  "avatar",
			Label:  "信息库广告头像: " + id,
		})
		addRef(item.Background, UploadMediaReference{
			Source: "knowledge_ads",
			ID:     id,
			Field:  "background",
			Label:  "信息库广告背景: " + id,
		})
	}
	return refs
}

// LoadAdCarouselItems 从数据库加载广告轮播数据
func LoadAdCarouselItems() []AdCarouselItem {
	raw := LoadConfig("ad_carousel_items")
	if raw == "" {
		return []AdCarouselItem{}
	}
	var items []AdCarouselItem
	if err := json.Unmarshal([]byte(raw), &items); err != nil {
		log.Printf("[Config] 广告轮播反序列化失败: %v", err)
		return []AdCarouselItem{}
	}
	return items
}

// LoadAdCarouselInterval 返回广告轮播自动播放间隔，未配置时使用默认值
func LoadAdCarouselInterval() int {
	raw := LoadConfig("ad_carousel_interval_ms")
	if raw == "" {
		return 4500
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value <= 0 {
		return 4500
	}
	return value
}

func defaultKnowledgeAdsConfig() KnowledgeAdsConfig {
	items := make([]KnowledgeAdItem, 4)
	for i := range items {
		items[i] = KnowledgeAdItem{
			ID:     "kb_ad_" + strconv.Itoa(i+1),
			Action: "link",
		}
	}
	return KnowledgeAdsConfig{Items: items}
}

func normalizeKnowledgeAdsConfig(cfg KnowledgeAdsConfig) KnowledgeAdsConfig {
	normalized := defaultKnowledgeAdsConfig()
	for i := range normalized.Items {
		if i >= len(cfg.Items) {
			continue
		}
		src := cfg.Items[i]
		dst := &normalized.Items[i]
		dst.Enabled = src.Enabled
		dst.Title = strings.TrimSpace(src.Title)
		dst.Subtitle = strings.TrimSpace(src.Subtitle)
		dst.Avatar = strings.TrimSpace(src.Avatar)
		dst.Background = strings.TrimSpace(src.Background)
		dst.URL = strings.TrimSpace(src.URL)
		dst.PopupContent = strings.TrimSpace(src.PopupContent)
		if src.ID != "" {
			dst.ID = src.ID
		}
		if src.Action == "popup" {
			dst.Action = "popup"
		}
	}
	return normalized
}

func loadKnowledgeAdsConfigData() KnowledgeAdsConfig {
	raw := LoadConfig("knowledge_ads_config")
	if raw == "" {
		return defaultKnowledgeAdsConfig()
	}

	var cfg KnowledgeAdsConfig
	if err := json.Unmarshal([]byte(raw), &cfg); err == nil {
		return normalizeKnowledgeAdsConfig(cfg)
	}

	var generic map[string]json.RawMessage
	if err := json.Unmarshal([]byte(raw), &generic); err == nil {
		if itemsRaw, ok := generic["items"]; ok {
			var items []KnowledgeAdItem
			if err := json.Unmarshal(itemsRaw, &items); err == nil {
				return normalizeKnowledgeAdsConfig(KnowledgeAdsConfig{Items: items})
			}
		}
	}

	log.Printf("[Config] 信息库广告配置反序列化失败，已回退默认配置")
	return defaultKnowledgeAdsConfig()
}

// LoadKnowledgeAdsConfig 从数据库加载信息库广告位配置
func LoadKnowledgeAdsConfig() string {
	cfg := loadKnowledgeAdsConfigData()
	data, err := json.Marshal(cfg)
	if err != nil {
		log.Printf("[Config] 信息库广告配置序列化失败: %v", err)
		fallback, _ := json.Marshal(defaultKnowledgeAdsConfig())
		return string(fallback)
	}
	return string(data)
}

// SaveKnowledgeAdsConfig 将信息库广告位配置持久化
func SaveKnowledgeAdsConfig(data string) {
	var cfg KnowledgeAdsConfig
	if err := json.Unmarshal([]byte(data), &cfg); err != nil {
		log.Printf("[Config] 信息库广告配置保存失败，JSON 非法: %v", err)
		safe, _ := json.Marshal(defaultKnowledgeAdsConfig())
		SaveConfig("knowledge_ads_config", string(safe))
		return
	}

	normalized := normalizeKnowledgeAdsConfig(cfg)
	safe, err := json.Marshal(normalized)
	if err != nil {
		log.Printf("[Config] 信息库广告配置保存失败，序列化异常: %v", err)
		return
	}
	SaveConfig("knowledge_ads_config", string(safe))
}
