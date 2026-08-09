package main

import "log"

func (h *WebSocketHub) BroadcastToAudience(message []byte, targeting AudienceTargeting, legacy_scope string) {
	if audienceTargetsEveryone(targeting, legacy_scope) {
		h.BroadcastToAll(message)
		return
	}

	h.mu.RLock()
	clients := make([]*ClientConnection, 0, len(h.clients))
	machine_ids := make([]string, 0, len(h.clients))
	seen_machine_ids := make(map[string]bool, len(h.clients))
	for client := range h.clients {
		if !client.IsAuthenticated {
			continue
		}
		clients = append(clients, client)
		if client.MachineID != "" && !seen_machine_ids[client.MachineID] {
			seen_machine_ids[client.MachineID] = true
			machine_ids = append(machine_ids, client.MachineID)
		}
	}
	h.mu.RUnlock()

	if len(machine_ids) == 0 {
		return
	}
	if db == nil {
		log.Println("[WebSocket] 受众筛选失败：数据库未初始化")
		return
	}

	var records []TelemetryRecord
	err := db.Select("machine_id", "version", "tags", "is_starred", "is_admin").
		Where("machine_id IN ?", machine_ids).
		Find(&records).Error
	if err != nil {
		log.Printf("[WebSocket] 受众筛选失败: %v", err)
		return
	}

	matched_machine_ids := matchingAudienceMachineIDs(records, targeting, legacy_scope)
	for _, client := range clients {
		if !matched_machine_ids[client.MachineID] {
			continue
		}
		if !client.send(message) {
			go func(connection *ClientConnection) {
				h.unregister <- connection
			}(client)
		}
	}
}
