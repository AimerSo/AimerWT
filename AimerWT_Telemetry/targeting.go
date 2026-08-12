package main

import (
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
)

func normalizeAudienceValues(values []string, lower bool) []string {
	result := make([]string, 0, len(values))
	seen := make(map[string]bool, len(values))
	for _, raw := range values {
		value := strings.TrimSpace(raw)
		if lower {
			value = strings.ToLower(value)
		}
		if value == "" || seen[value] {
			continue
		}
		seen[value] = true
		result = append(result, value)
	}
	return result
}

func normalizeAudienceTargeting(targeting AudienceTargeting) (AudienceTargeting, error) {
	normalized := AudienceTargeting{Rules: make([]AudienceRule, 0, len(targeting.Rules))}
	for _, rule := range targeting.Rules {
		rule.MinimumVersion = strings.TrimSpace(rule.MinimumVersion)
		rule.Versions = normalizeAudienceValues(rule.Versions, false)
		rule.Tags = normalizeAudienceValues(rule.Tags, false)
		rule.SpecialGroups = normalizeAudienceValues(rule.SpecialGroups, true)
		for _, group := range rule.SpecialGroups {
			if group != "starred" && group != "admin" {
				return AudienceTargeting{}, fmt.Errorf("未知特殊用户组: %s", group)
			}
		}
		normalized.Rules = append(normalized.Rules, rule)
	}
	return normalized, nil
}

func parseAudienceTargeting(raw any) (AudienceTargeting, error) {
	data, err := json.Marshal(raw)
	if err != nil {
		return AudienceTargeting{}, err
	}
	var targeting AudienceTargeting
	if err := json.Unmarshal(data, &targeting); err != nil {
		return AudienceTargeting{}, err
	}
	return normalizeAudienceTargeting(targeting)
}

func recordTagSet(record TelemetryRecord) map[string]bool {
	var tags []string
	if err := json.Unmarshal([]byte(record.Tags), &tags); err != nil {
		return map[string]bool{}
	}
	result := make(map[string]bool, len(tags))
	for _, tag := range tags {
		if value := strings.TrimSpace(tag); value != "" {
			result[value] = true
		}
	}
	return result
}

func parseNumericVersion(raw string) ([3]int, bool) {
	var parsed [3]int
	value := strings.TrimSpace(raw)
	value = strings.TrimPrefix(strings.TrimPrefix(value, "v"), "V")
	if suffix_index := strings.IndexAny(value, "-+ "); suffix_index >= 0 {
		value = value[:suffix_index]
	}
	parts := strings.Split(value, ".")
	if len(parts) == 0 || len(parts) > len(parsed) {
		return parsed, false
	}
	for index, part := range parts {
		if part == "" {
			return parsed, false
		}
		number, err := strconv.Atoi(part)
		if err != nil || number < 0 {
			return parsed, false
		}
		parsed[index] = number
	}
	return parsed, true
}

func versionAtLeast(version, minimum_version string) bool {
	current, current_ok := parseNumericVersion(version)
	minimum, minimum_ok := parseNumericVersion(minimum_version)
	if !current_ok || !minimum_ok {
		return false
	}
	for index := range current {
		if current[index] != minimum[index] {
			return current[index] > minimum[index]
		}
	}
	return true
}

func matchAudienceRule(rule AudienceRule, record TelemetryRecord) bool {
	if rule.MinimumVersion != "" && !versionAtLeast(record.Version, rule.MinimumVersion) {
		return false
	}

	if len(rule.Versions) > 0 {
		matched := false
		for _, version := range rule.Versions {
			if strings.TrimSpace(version) == record.Version {
				matched = true
				break
			}
		}
		if !matched {
			return false
		}
	}

	if len(rule.Tags) > 0 {
		tag_set := recordTagSet(record)
		matched := false
		for _, tag := range rule.Tags {
			if tag_set[strings.TrimSpace(tag)] {
				matched = true
				break
			}
		}
		if !matched {
			return false
		}
	}

	if len(rule.SpecialGroups) > 0 {
		matched := false
		for _, group := range rule.SpecialGroups {
			switch strings.ToLower(strings.TrimSpace(group)) {
			case "starred":
				matched = matched || record.IsStarred
			case "admin":
				matched = matched || record.IsAdmin
			}
		}
		if !matched {
			return false
		}
	}

	return true
}

func matchAudienceTargeting(targeting AudienceTargeting, legacy_scope string, record TelemetryRecord) bool {
	if len(targeting.Rules) == 0 {
		return matchScope(legacy_scope, record)
	}
	for _, rule := range targeting.Rules {
		if matchAudienceRule(rule, record) {
			return true
		}
	}
	return false
}

func matchingAudienceMachineIDs(records []TelemetryRecord, targeting AudienceTargeting, legacy_scope string) map[string]bool {
	matched := make(map[string]bool)
	for _, record := range records {
		if record.MachineID != "" && matchAudienceTargeting(targeting, legacy_scope, record) {
			matched[record.MachineID] = true
		}
	}
	return matched
}

func audienceTargetsEveryone(targeting AudienceTargeting, legacy_scope string) bool {
	if len(targeting.Rules) == 0 {
		return legacy_scope == "" || legacy_scope == "all"
	}
	for _, rule := range targeting.Rules {
		if rule.MinimumVersion == "" && len(rule.Versions) == 0 && len(rule.Tags) == 0 && len(rule.SpecialGroups) == 0 {
			return true
		}
	}
	return false
}

func describeAudienceTargeting(targeting AudienceTargeting, legacy_scope string) string {
	if len(targeting.Rules) == 0 {
		if legacy_scope == "" || legacy_scope == "all" {
			return "全部用户"
		}
		return legacy_scope
	}
	parts := make([]string, 0, len(targeting.Rules))
	for _, rule := range targeting.Rules {
		conditions := make([]string, 0, 4)
		if rule.MinimumVersion != "" {
			conditions = append(conditions, "版本 "+rule.MinimumVersion+" 及以上")
		}
		if len(rule.Versions) > 0 {
			conditions = append(conditions, "版本 "+strings.Join(rule.Versions, "/"))
		}
		if len(rule.Tags) > 0 {
			conditions = append(conditions, "标签 "+strings.Join(rule.Tags, "/"))
		}
		if len(rule.SpecialGroups) > 0 {
			labels := make([]string, 0, len(rule.SpecialGroups))
			for _, group := range rule.SpecialGroups {
				if group == "starred" {
					labels = append(labels, "星标用户")
				} else if group == "admin" {
					labels = append(labels, "管理员")
				}
			}
			if len(labels) > 0 {
				conditions = append(conditions, strings.Join(labels, "/"))
			}
		}
		if len(conditions) == 0 {
			return "全部用户"
		}
		parts = append(parts, strings.Join(conditions, " 且 "))
	}
	return strings.Join(parts, "；或 ")
}

func filterSystemConfigForAudience(config SystemConfig, record TelemetryRecord) SystemConfig {
	client_config := config
	if !matchAudienceTargeting(config.AlertTargeting, config.AlertScope, record) {
		client_config.AlertActive = false
		client_config.AlertTitle = ""
		client_config.AlertContent = ""
	}
	if !matchAudienceTargeting(config.NoticeTargeting, config.NoticeScope, record) {
		client_config.NoticeActive = false
		client_config.NoticeContent = ""
		client_config.NoticeActionType = ""
		client_config.NoticeActionURL = ""
		client_config.NoticeActionTitle = ""
		client_config.NoticeActionContent = ""
		client_config.BannerItems = nil
		client_config.BannerInterval = 0
	}
	if !matchAudienceTargeting(config.UpdateTargeting, config.UpdateScope, record) {
		client_config.UpdateActive = false
		client_config.UpdateContent = ""
		client_config.UpdateUrl = ""
	}
	if !matchAudienceTargeting(config.NotificationCenterTargeting, config.NotificationCenterScope, record) {
		client_config.NotificationCenterEnabled = false
	}
	if config.HeartbeatScope != "" && !matchScope(config.HeartbeatScope, record) {
		client_config.HeartbeatInterval = 0
	}
	return client_config
}
