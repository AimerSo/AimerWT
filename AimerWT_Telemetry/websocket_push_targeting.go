package main

import (
	"encoding/json"
	"time"
)

func BroadcastAlertToAudience(title, content, legacy_scope string, targeting AudienceTargeting) {
	msg := PushMessage{
		Type:   "alert",
		Action: "show",
		Data: map[string]string{
			"title":   title,
			"content": content,
			"scope":   legacy_scope,
		},
		Time: time.Now().Unix(),
	}
	data, err := json.Marshal(msg)
	if err == nil && wsHub != nil {
		wsHub.BroadcastToAudience(data, targeting, legacy_scope)
	}
}

func BroadcastNoticeToAudience(content, legacy_scope string, targeting AudienceTargeting) {
	msg := PushMessage{
		Type:   "notice",
		Action: "update",
		Data: map[string]string{
			"content": content,
			"scope":   legacy_scope,
		},
		Time: time.Now().Unix(),
	}
	data, err := json.Marshal(msg)
	if err == nil && wsHub != nil {
		wsHub.BroadcastToAudience(data, targeting, legacy_scope)
	}
}

func BroadcastUpdateToAudience(content, url, legacy_scope string, targeting AudienceTargeting) {
	msg := PushMessage{
		Type:   "update",
		Action: "notify",
		Data: map[string]string{
			"content": content,
			"url":     url,
			"scope":   legacy_scope,
		},
		Time: time.Now().Unix(),
	}
	data, err := json.Marshal(msg)
	if err == nil && wsHub != nil {
		wsHub.BroadcastToAudience(data, targeting, legacy_scope)
	}
}
