package main

import (
	"fmt"
	"strings"

	"gorm.io/gorm"
)

const userUIDCounterKey = "public_user_uid"

// migrateUserUIDMappings 启动时将现有 telemetry_records 按注册时间回填到 user_uid_mappings。
// 幂等：保留已有映射，为缺失记录继续分配公开 UID，并将 counter 校正到下一个可用值。
func migrateUserUIDMappings() error {
	return db.Transaction(func(tx *gorm.DB) error {
		var mappings []UserUIDMapping
		if err := tx.Find(&mappings).Error; err != nil {
			return err
		}

		mapped := make(map[string]UserUIDMapping, len(mappings))
		var maxSeq uint
		for _, mapping := range mappings {
			machineID := strings.TrimSpace(mapping.MachineID)
			if machineID == "" {
				continue
			}
			mapped[machineID] = mapping
			if mapping.SeqID > maxSeq {
				maxSeq = mapping.SeqID
			}
		}

		var records []TelemetryRecord
		if err := tx.
			Where("machine_id IS NOT NULL AND TRIM(machine_id) <> ''").
			Order("created_at ASC, id ASC").
			Find(&records).Error; err != nil {
			return err
		}

		nextSeq := maxSeq + 1
		if nextSeq == 0 {
			nextSeq = 1
		}
		for _, record := range records {
			machineID := strings.TrimSpace(record.MachineID)
			if machineID == "" {
				continue
			}
			if existing, ok := mapped[machineID]; ok {
				if existing.TelemetryRecordID == 0 && record.ID != 0 {
					if err := tx.Model(&UserUIDMapping{}).
						Where("machine_id = ?", machineID).
						Update("telemetry_record_id", record.ID).Error; err != nil {
						return err
					}
				}
				continue
			}

			mapping := UserUIDMapping{
				SeqID:             nextSeq,
				MachineID:         machineID,
				TelemetryRecordID: record.ID,
				CreatedAt:         record.CreatedAt,
			}
			if err := tx.Create(&mapping).Error; err != nil {
				return err
			}
			mapped[machineID] = mapping
			nextSeq++
		}

		var counter UserUIDCounter
		err := tx.Where("key = ?", userUIDCounterKey).First(&counter).Error
		if err == gorm.ErrRecordNotFound {
			counter = UserUIDCounter{Key: userUIDCounterKey, NextSeq: nextSeq}
			return tx.Create(&counter).Error
		}
		if err != nil {
			return err
		}
		if counter.NextSeq != nextSeq {
			if err := tx.Model(&UserUIDCounter{}).
				Where("key = ?", userUIDCounterKey).
				Update("next_seq", nextSeq).Error; err != nil {
				return err
			}
		}

		return nil
	})
}

// ensureUserUID 为指定 machine_id 分配或返回已有的公开 UID。
// 已存在的用户直接返回，不推进计数器。
func ensureUserUID(machineID string, telemetryRecordID uint) (uint, error) {
	var seqID uint
	err := db.Transaction(func(tx *gorm.DB) error {
		value, err := ensureUserUIDTx(tx, machineID, telemetryRecordID)
		if err != nil {
			return err
		}
		seqID = value
		return nil
	})
	return seqID, err
}

// ensureUserUIDTx 事务内版本：查找已有映射或分配新 UID。
// counter 更新和 mapping 插入在同一事务内，防止 gap。
func ensureUserUIDTx(tx *gorm.DB, machineID string, telemetryRecordID uint) (uint, error) {
	machineID = strings.TrimSpace(machineID)
	if machineID == "" {
		return 0, fmt.Errorf("machine_id required")
	}

	var existing UserUIDMapping
	err := tx.Where("machine_id = ?", machineID).First(&existing).Error
	if err == nil {
		// 已有映射，补填 telemetry_record_id（如首次迁移时未关联）
		if existing.TelemetryRecordID == 0 && telemetryRecordID != 0 {
			if err := tx.Model(&UserUIDMapping{}).
				Where("machine_id = ?", machineID).
				Update("telemetry_record_id", telemetryRecordID).Error; err != nil {
				return 0, err
			}
		}
		return existing.SeqID, nil
	}
	if err != gorm.ErrRecordNotFound {
		return 0, err
	}

	// 获取或创建计数器
	var maxSeq uint
	if err := tx.Model(&UserUIDMapping{}).Select("COALESCE(MAX(seq_id), 0)").Scan(&maxSeq).Error; err != nil {
		return 0, err
	}
	nextSeq := maxSeq + 1
	if nextSeq == 0 {
		nextSeq = 1
	}

	var counter UserUIDCounter
	// SQLite 单写者模式（MaxOpenConns=1）下事务内操作天然串行，无需行锁
	err = tx.Where("key = ?", userUIDCounterKey).First(&counter).Error
	if err == gorm.ErrRecordNotFound {
		counter = UserUIDCounter{Key: userUIDCounterKey, NextSeq: nextSeq}
		if err := tx.Create(&counter).Error; err != nil {
			return 0, err
		}
	} else if err != nil {
		return 0, err
	}
	if counter.NextSeq != nextSeq {
		if err := tx.Model(&UserUIDCounter{}).
			Where("key = ?", userUIDCounterKey).
			Update("next_seq", nextSeq).Error; err != nil {
			return 0, err
		}
		counter.NextSeq = nextSeq
	}

	seqID := counter.NextSeq
	if seqID == 0 {
		seqID = 1
	}

	// 先推进计数器
	if err := tx.Model(&UserUIDCounter{}).
		Where("key = ?", userUIDCounterKey).
		Update("next_seq", seqID+1).Error; err != nil {
		return 0, err
	}

	// 插入映射
	mapping := UserUIDMapping{
		SeqID:             seqID,
		MachineID:         machineID,
		TelemetryRecordID: telemetryRecordID,
	}
	if err := tx.Create(&mapping).Error; err != nil {
		return 0, err
	}

	return seqID, nil
}

// buildUserUIDMap 批量查询 machine_id → 公开 UID 映射
func buildUserUIDMap(machineIDs []string) map[string]uint {
	if len(machineIDs) == 0 {
		return map[string]uint{}
	}
	normalizedIDs := normalizeMachineIDList(machineIDs)
	if len(normalizedIDs) == 0 {
		return map[string]uint{}
	}
	type uidRow struct {
		MachineID string
		SeqID     uint
	}
	var rows []uidRow
	if err := db.Model(&UserUIDMapping{}).Where("machine_id IN ?", normalizedIDs).Select("machine_id, seq_id").Scan(&rows).Error; err != nil {
		return map[string]uint{}
	}
	result := make(map[string]uint, len(rows))
	for _, r := range rows {
		result[r.MachineID] = r.SeqID
	}

	missingIDs := make([]string, 0)
	for _, machineID := range normalizedIDs {
		if _, ok := result[machineID]; !ok {
			missingIDs = append(missingIDs, machineID)
		}
	}
	if len(missingIDs) > 0 {
		var missingRecordCount int64
		err := db.Model(&TelemetryRecord{}).Where("machine_id IN ?", missingIDs).Count(&missingRecordCount).Error
		if err == nil && missingRecordCount > 0 && migrateUserUIDMappings() == nil {
			rows = rows[:0]
			if err := db.Model(&UserUIDMapping{}).Where("machine_id IN ?", normalizedIDs).Select("machine_id, seq_id").Scan(&rows).Error; err != nil {
				return result
			}
			result = make(map[string]uint, len(rows))
			for _, r := range rows {
				result[r.MachineID] = r.SeqID
			}
		}
	}

	for _, raw := range machineIDs {
		machineID := strings.TrimSpace(raw)
		if seqID, ok := result[machineID]; ok {
			result[raw] = seqID
		}
	}

	return result
}

func normalizeMachineIDList(machineIDs []string) []string {
	seen := make(map[string]struct{}, len(machineIDs))
	result := make([]string, 0, len(machineIDs))
	for _, raw := range machineIDs {
		machineID := strings.TrimSpace(raw)
		if machineID == "" {
			continue
		}
		if _, ok := seen[machineID]; ok {
			continue
		}
		seen[machineID] = struct{}{}
		result = append(result, machineID)
	}
	return result
}

// lookupUserUID 查询单个 machine_id 的公开 UID
func lookupUserUID(machineID string) (uint, bool) {
	machineID = strings.TrimSpace(machineID)
	if machineID == "" {
		return 0, false
	}
	var mapping UserUIDMapping
	if err := db.Where("machine_id = ?", machineID).First(&mapping).Error; err != nil {
		return 0, false
	}
	return mapping.SeqID, true
}

// lookupUserUIDWithFallback 查询公开 UID，找不到时尝试分配
func lookupUserUIDWithFallback(machineID string, telemetryRecordID uint) uint {
	seqID, ok := lookupUserUID(machineID)
	if ok {
		return seqID
	}
	value, err := ensureUserUID(machineID, telemetryRecordID)
	if err != nil {
		return 0
	}
	return value
}

// resetUserUIDCounterForTest 仅用于测试：重置计数器（不导出，包内可见）
func resetUserUIDCounterForTest() {
	db.Where("1 = 1").Delete(&UserUIDMapping{})
	db.Where("1 = 1").Delete(&UserUIDCounter{})
}
