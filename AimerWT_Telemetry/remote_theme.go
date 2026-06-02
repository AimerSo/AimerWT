package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

const remoteThemeMaxBytes = 64 * 1024

var remoteThemeFilenameRe = regexp.MustCompile(`^remote_[a-z0-9_]+\.json$`)
var remoteThemeDiskDir = filepath.Join("themes", "remote")

type RemoteThemeListItem struct {
	ID          uint   `json:"id,omitempty"`
	Filename    string `json:"filename"`
	Name        string `json:"name"`
	Author      string `json:"author"`
	Version     string `json:"version"`
	Visibility  string `json:"visibility"`
	Status      string `json:"status"`
	SortOrder   int    `json:"sort_order"`
	Checksum    string `json:"checksum"`
	FileSize    int    `json:"file_size"`
	Description string `json:"description,omitempty"`
	UpdatedAt   string `json:"updated_at,omitempty"`
}

type remoteThemeRequest struct {
	Filename    string          `json:"filename"`
	Name        string          `json:"name"`
	Author      string          `json:"author"`
	Version     string          `json:"version"`
	Visibility  string          `json:"visibility"`
	Status      string          `json:"status"`
	SortOrder   int             `json:"sort_order"`
	Description string          `json:"description"`
	ThemeData   json.RawMessage `json:"theme_data"`
}

type remoteThemeImportResult struct {
	Directory string   `json:"directory"`
	Imported  int      `json:"imported"`
	Updated   int      `json:"updated"`
	Skipped   int      `json:"skipped"`
	Errors    []string `json:"errors,omitempty"`
}

func computeRemoteThemeChecksum(themeData string) string {
	sum := sha256.Sum256([]byte(themeData))
	return hex.EncodeToString(sum[:])
}

func normalizeRemoteThemeVisibility(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "":
		return "restricted"
	case "public":
		return "public"
	case "restricted":
		return "restricted"
	default:
		return ""
	}
}

func normalizeRemoteThemeStatus(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "", "active":
		return "active"
	case "inactive":
		return "inactive"
	default:
		return ""
	}
}

func normalizeRemoteThemeData(raw json.RawMessage) (string, map[string]any, error) {
	if len(raw) == 0 {
		return "", nil, errors.New("theme_data 为必填")
	}

	var themeText string
	if err := json.Unmarshal(raw, &themeText); err == nil {
		themeText = strings.TrimSpace(themeText)
	} else {
		themeText = strings.TrimSpace(string(raw))
	}
	if themeText == "" {
		return "", nil, errors.New("theme_data 不能为空")
	}
	if len([]byte(themeText)) > remoteThemeMaxBytes {
		return "", nil, errors.New("主题文件不能超过 64KB")
	}

	decoder := json.NewDecoder(strings.NewReader(themeText))
	decoder.UseNumber()
	var parsed map[string]any
	if err := decoder.Decode(&parsed); err != nil {
		return "", nil, errors.New("theme_data 必须是合法 JSON 对象")
	}
	if len(parsed) == 0 {
		return "", nil, errors.New("theme_data 不能为空对象")
	}
	if err := validateRemoteThemeObject(parsed); err != nil {
		return "", nil, err
	}

	var buf bytes.Buffer
	encoder := json.NewEncoder(&buf)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(parsed); err != nil {
		return "", nil, errors.New("theme_data 序列化失败")
	}
	canonical := strings.TrimSpace(buf.String())
	if len([]byte(canonical)) > remoteThemeMaxBytes {
		return "", nil, errors.New("主题文件不能超过 64KB")
	}
	return canonical, parsed, nil
}

func validateRemoteThemeObject(parsed map[string]any) error {
	meta, ok := parsed["meta"].(map[string]any)
	if !ok {
		return errors.New("theme_data.meta 为必填对象")
	}
	if name, ok := meta["name"].(string); !ok || strings.TrimSpace(name) == "" {
		return errors.New("theme_data.meta.name 为必填")
	}

	hasPalette := false
	for _, sectionName := range []string{"colors", "light", "dark"} {
		rawSection, ok := parsed[sectionName]
		if !ok {
			continue
		}
		section, ok := rawSection.(map[string]any)
		if !ok {
			return errors.New(sectionName + " 必须是对象")
		}
		if len(section) > 0 {
			hasPalette = true
		}
		for key, value := range section {
			if strings.TrimSpace(key) == "" {
				return errors.New(sectionName + " 不能包含空键名")
			}
			if _, ok := value.(string); !ok {
				return errors.New(sectionName + "." + key + " 必须是字符串")
			}
		}
	}
	if !hasPalette {
		return errors.New("theme_data 至少需要 colors、light 或 dark 中的一个配色对象")
	}
	return nil
}

func remoteThemeMetaName(parsed map[string]any) string {
	meta, _ := parsed["meta"].(map[string]any)
	name, _ := meta["name"].(string)
	return strings.TrimSpace(name)
}

func remoteThemeMetaString(parsed map[string]any, key string) string {
	meta, _ := parsed["meta"].(map[string]any)
	value, _ := meta[key].(string)
	return strings.TrimSpace(value)
}

func remoteThemeMetaSortOrder(parsed map[string]any, fallback int) int {
	meta, _ := parsed["meta"].(map[string]any)
	switch value := meta["sort_order"].(type) {
	case json.Number:
		if n, err := value.Int64(); err == nil {
			return int(n)
		}
	case float64:
		return int(value)
	case int:
		return value
	}
	return fallback
}

func serializeRemoteThemeListItem(theme RemoteTheme, includeID bool) RemoteThemeListItem {
	item := RemoteThemeListItem{
		Filename:    theme.Filename,
		Name:        theme.Name,
		Author:      theme.Author,
		Version:     theme.Version,
		Visibility:  theme.Visibility,
		Status:      theme.Status,
		SortOrder:   theme.SortOrder,
		Checksum:    theme.Checksum,
		FileSize:    theme.FileSize,
		Description: theme.Description,
		UpdatedAt:   theme.UpdatedAt.Format("2006-01-02 15:04:05"),
	}
	if includeID {
		item.ID = theme.ID
	}
	return item
}

func listRemoteThemeItems(themes []RemoteTheme, includeID bool) []RemoteThemeListItem {
	items := make([]RemoteThemeListItem, 0, len(themes))
	for _, theme := range themes {
		items = append(items, serializeRemoteThemeListItem(theme, includeID))
	}
	return items
}

func handleListRemoteThemes(c *gin.Context) {
	machineID := strings.TrimSpace(c.Query("machine_id"))
	if !ensureClientMachineBinding(c, machineID) {
		return
	}

	var themes []RemoteTheme
	if err := db.Where("status = ? AND visibility = ?", "active", "public").
		Order("sort_order asc, id asc").
		Find(&themes).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "主题列表读取失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"themes": listRemoteThemeItems(themes, false)})
}

func handleDownloadRemoteTheme(c *gin.Context) {
	machineID := strings.TrimSpace(c.Query("machine_id"))
	if !ensureClientMachineBinding(c, machineID) {
		return
	}

	filename := strings.TrimSpace(c.Param("filename"))
	if !remoteThemeFilenameRe.MatchString(filename) {
		c.JSON(http.StatusBadRequest, gin.H{"error": "主题文件名无效"})
		return
	}

	var theme RemoteTheme
	if err := db.Where("filename = ? AND status = ? AND visibility = ?", filename, "active", "public").First(&theme).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			c.JSON(http.StatusNotFound, gin.H{"error": "主题不存在或不可下载"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "主题读取失败"})
		return
	}

	var themeData map[string]any
	if err := json.Unmarshal([]byte(theme.ThemeData), &themeData); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "主题数据损坏"})
		return
	}
	fileSize := theme.FileSize
	if fileSize <= 0 {
		fileSize = len([]byte(theme.ThemeData))
	}
	c.JSON(http.StatusOK, gin.H{
		"filename":   theme.Filename,
		"theme_data": themeData,
		"theme_text": theme.ThemeData,
		"checksum":   theme.Checksum,
		"file_size":  fileSize,
	})
}

func handleAdminListRemoteThemes(c *gin.Context) {
	var themes []RemoteTheme
	if err := db.Order("sort_order asc, id asc").Find(&themes).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "主题列表读取失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"themes": themes})
}

func handleAdminCreateRemoteTheme(c *gin.Context) {
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, remoteThemeMaxBytes*2)

	var req remoteThemeRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求数据格式错误"})
		return
	}

	theme, statusCode, errMessage := buildRemoteThemeFromRequest(req)
	if errMessage != "" {
		c.JSON(statusCode, gin.H{"error": errMessage})
		return
	}

	var existing RemoteTheme
	if err := db.Where("filename = ?", theme.Filename).First(&existing).Error; err == nil {
		c.JSON(http.StatusConflict, gin.H{"error": "同名 filename 已存在，请使用 PUT 更新"})
		return
	} else if !errors.Is(err, gorm.ErrRecordNotFound) {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "主题查询失败"})
		return
	}

	if err := db.Create(&theme).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "主题创建失败"})
		return
	}
	c.JSON(http.StatusCreated, gin.H{"status": "success", "theme": theme})
}

func buildRemoteThemeFromRequest(req remoteThemeRequest) (RemoteTheme, int, string) {
	filename := strings.TrimSpace(req.Filename)
	if !remoteThemeFilenameRe.MatchString(filename) {
		return RemoteTheme{}, http.StatusBadRequest, "filename 必须匹配 remote_[a-z0-9_]+.json"
	}

	visibility := normalizeRemoteThemeVisibility(req.Visibility)
	if visibility == "" {
		return RemoteTheme{}, http.StatusBadRequest, "visibility 仅支持 public 或 restricted"
	}
	status := normalizeRemoteThemeStatus(req.Status)
	if status == "" {
		return RemoteTheme{}, http.StatusBadRequest, "status 仅支持 active 或 inactive"
	}

	themeData, parsed, err := normalizeRemoteThemeData(req.ThemeData)
	if err != nil {
		return RemoteTheme{}, http.StatusBadRequest, err.Error()
	}

	name := strings.TrimSpace(req.Name)
	if name == "" {
		name = remoteThemeMetaName(parsed)
	}
	if name == "" {
		return RemoteTheme{}, http.StatusBadRequest, "name 为必填"
	}
	version := strings.TrimSpace(req.Version)
	if version == "" {
		return RemoteTheme{}, http.StatusBadRequest, "version 为必填"
	}

	return RemoteTheme{
		Filename:    filename,
		Name:        name,
		Author:      strings.TrimSpace(req.Author),
		Version:     version,
		Visibility:  visibility,
		Status:      status,
		SortOrder:   req.SortOrder,
		Description: strings.TrimSpace(req.Description),
		ThemeData:   themeData,
		Checksum:    computeRemoteThemeChecksum(themeData),
		FileSize:    len([]byte(themeData)),
	}, http.StatusOK, ""
}

func buildRemoteThemeFromDiskFile(filename string, raw []byte) (RemoteTheme, error) {
	filename = strings.TrimSpace(filename)
	if !remoteThemeFilenameRe.MatchString(filename) {
		return RemoteTheme{}, errors.New("文件名必须匹配 remote_[a-z0-9_]+.json")
	}

	themeData, parsed, err := normalizeRemoteThemeData(json.RawMessage(raw))
	if err != nil {
		return RemoteTheme{}, err
	}
	name := remoteThemeMetaName(parsed)
	if name == "" {
		return RemoteTheme{}, errors.New("theme_data.meta.name 为必填")
	}
	version := remoteThemeMetaString(parsed, "version")
	if version == "" {
		return RemoteTheme{}, errors.New("theme_data.meta.version 为必填")
	}

	return RemoteTheme{
		Filename:    filename,
		Name:        name,
		Author:      remoteThemeMetaString(parsed, "author"),
		Version:     version,
		Visibility:  "restricted",
		Status:      "active",
		SortOrder:   remoteThemeMetaSortOrder(parsed, 100),
		Description: "服务器主题文件导入",
		ThemeData:   themeData,
		Checksum:    computeRemoteThemeChecksum(themeData),
		FileSize:    len([]byte(themeData)),
	}, nil
}

func importRemoteThemesFromDisk(store *gorm.DB) (remoteThemeImportResult, error) {
	absDir, err := filepath.Abs(remoteThemeDiskDir)
	if err != nil {
		absDir = remoteThemeDiskDir
	}
	result := remoteThemeImportResult{Directory: absDir}

	if err := os.MkdirAll(remoteThemeDiskDir, 0755); err != nil {
		return result, err
	}
	entries, err := os.ReadDir(remoteThemeDiskDir)
	if err != nil {
		return result, err
	}

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		filename := entry.Name()
		if !remoteThemeFilenameRe.MatchString(filename) {
			result.Skipped++
			continue
		}

		raw, err := os.ReadFile(filepath.Join(remoteThemeDiskDir, filename))
		if err != nil {
			result.Skipped++
			result.Errors = append(result.Errors, filename+": 读取失败")
			continue
		}
		theme, err := buildRemoteThemeFromDiskFile(filename, raw)
		if err != nil {
			result.Skipped++
			result.Errors = append(result.Errors, filename+": "+err.Error())
			continue
		}

		var existing RemoteTheme
		if err := store.Where("filename = ?", theme.Filename).First(&existing).Error; err == nil {
			if theme.ThemeData != existing.ThemeData && theme.Version == existing.Version {
				result.Skipped++
				result.Errors = append(result.Errors, filename+": 主题内容变化时必须同步更新 version")
				continue
			}
			if strings.TrimSpace(existing.Visibility) != "" {
				theme.Visibility = existing.Visibility
			}
			if strings.TrimSpace(existing.Status) != "" {
				theme.Status = existing.Status
			}
			updates := map[string]any{
				"name":        theme.Name,
				"author":      theme.Author,
				"version":     theme.Version,
				"visibility":  theme.Visibility,
				"status":      theme.Status,
				"sort_order":  theme.SortOrder,
				"description": theme.Description,
				"theme_data":  theme.ThemeData,
				"checksum":    theme.Checksum,
				"file_size":   theme.FileSize,
			}
			if err := store.Model(&existing).Updates(updates).Error; err != nil {
				result.Skipped++
				result.Errors = append(result.Errors, filename+": 更新失败")
				continue
			}
			result.Updated++
		} else if errors.Is(err, gorm.ErrRecordNotFound) {
			if err := store.Create(&theme).Error; err != nil {
				result.Skipped++
				result.Errors = append(result.Errors, filename+": 导入失败")
				continue
			}
			result.Imported++
		} else {
			result.Skipped++
			result.Errors = append(result.Errors, filename+": 查询失败")
		}
	}

	return result, nil
}

func handleAdminImportRemoteThemes(c *gin.Context) {
	result, err := importRemoteThemesFromDisk(db)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "服务器主题文件扫描失败", "directory": result.Directory})
		return
	}
	c.JSON(http.StatusOK, gin.H{"status": "success", "result": result})
}

func handleAdminUpdateRemoteTheme(c *gin.Context) {
	id, err := strconv.ParseUint(strings.TrimSpace(c.Param("id")), 10, 64)
	if err != nil || id == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "主题 ID 无效"})
		return
	}

	var existing RemoteTheme
	if err := db.First(&existing, id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			c.JSON(http.StatusNotFound, gin.H{"error": "主题不存在"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "主题读取失败"})
		return
	}

	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, remoteThemeMaxBytes*2)
	body, err := io.ReadAll(c.Request.Body)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求数据格式错误"})
		return
	}
	var req remoteThemeRequest
	if err := json.Unmarshal(body, &req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求数据格式错误"})
		return
	}
	var rawFields map[string]json.RawMessage
	if err := json.Unmarshal(body, &rawFields); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求数据格式错误"})
		return
	}

	updates := map[string]any{}
	if strings.TrimSpace(req.Name) != "" {
		updates["name"] = strings.TrimSpace(req.Name)
	}
	if strings.TrimSpace(req.Author) != "" {
		updates["author"] = strings.TrimSpace(req.Author)
	}
	if strings.TrimSpace(req.Version) != "" {
		updates["version"] = strings.TrimSpace(req.Version)
	}
	if strings.TrimSpace(req.Visibility) != "" {
		visibility := normalizeRemoteThemeVisibility(req.Visibility)
		if visibility == "" {
			c.JSON(http.StatusBadRequest, gin.H{"error": "visibility 仅支持 public 或 restricted"})
			return
		}
		updates["visibility"] = visibility
	}
	if strings.TrimSpace(req.Status) != "" {
		status := normalizeRemoteThemeStatus(req.Status)
		if status == "" {
			c.JSON(http.StatusBadRequest, gin.H{"error": "status 仅支持 active 或 inactive"})
			return
		}
		updates["status"] = status
	}
	if _, ok := rawFields["sort_order"]; ok {
		updates["sort_order"] = req.SortOrder
	}
	if _, ok := rawFields["description"]; ok {
		updates["description"] = strings.TrimSpace(req.Description)
	}

	if len(req.ThemeData) > 0 {
		themeData, parsed, err := normalizeRemoteThemeData(req.ThemeData)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		nextVersion := strings.TrimSpace(req.Version)
		if nextVersion == "" {
			nextVersion = existing.Version
		}
		if themeData != existing.ThemeData && nextVersion == existing.Version {
			c.JSON(http.StatusBadRequest, gin.H{"error": "主题内容变化时必须同步更新 version"})
			return
		}
		if strings.TrimSpace(req.Name) == "" {
			updates["name"] = remoteThemeMetaName(parsed)
		}
		updates["theme_data"] = themeData
		updates["checksum"] = computeRemoteThemeChecksum(themeData)
		updates["file_size"] = len([]byte(themeData))
	}

	if err := db.Model(&existing).Updates(updates).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "主题更新失败"})
		return
	}
	db.First(&existing, id)
	c.JSON(http.StatusOK, gin.H{"status": "success", "theme": existing})
}

func handleAdminDeleteRemoteTheme(c *gin.Context) {
	id, err := strconv.ParseUint(strings.TrimSpace(c.Param("id")), 10, 64)
	if err != nil || id == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "主题 ID 无效"})
		return
	}
	if err := db.Delete(&RemoteTheme{}, id).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "主题删除失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"status": "success"})
}

func handleAdminToggleRemoteTheme(c *gin.Context) {
	id, err := strconv.ParseUint(strings.TrimSpace(c.Param("id")), 10, 64)
	if err != nil || id == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "主题 ID 无效"})
		return
	}

	var theme RemoteTheme
	if err := db.First(&theme, id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			c.JSON(http.StatusNotFound, gin.H{"error": "主题不存在"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "主题读取失败"})
		return
	}

	nextStatus := "inactive"
	if theme.Status == "inactive" {
		nextStatus = "active"
	} else if theme.Status != "active" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "当前状态不支持切换"})
		return
	}

	if err := db.Model(&theme).Update("status", nextStatus).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "主题状态更新失败"})
		return
	}
	theme.Status = nextStatus
	c.JSON(http.StatusOK, gin.H{"status": "success", "theme": theme})
}

func initRemoteThemeRoutes(r *gin.Engine, admin *gin.RouterGroup) {
	admin.GET("/remote-themes", handleAdminListRemoteThemes)
	admin.POST("/remote-themes", handleAdminCreateRemoteTheme)
	admin.POST("/remote-themes/import", handleAdminImportRemoteThemes)
	admin.PUT("/remote-themes/:id", handleAdminUpdateRemoteTheme)
	admin.DELETE("/remote-themes/:id", handleAdminDeleteRemoteTheme)
	admin.POST("/remote-themes/:id/toggle", handleAdminToggleRemoteTheme)

	r.GET("/api/themes", handleListRemoteThemes)
	r.GET("/api/themes/:filename", handleDownloadRemoteTheme)
}
