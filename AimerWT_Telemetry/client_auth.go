package main

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

var clientAuthSecret = strings.TrimSpace(os.Getenv("TELEMETRY_CLIENT_SECRET"))

const (
	clientAuthClockSkew       = 5 * time.Minute
	clientDeviceTokenSize     = 32
	clientDeviceSessionTTL    = 90 * 24 * time.Hour
	clientDeviceSessionMax    = 8
	clientSessionTouchMinimum = 12 * time.Hour
)

const clientDeviceTokenHeader = "X-AimerWT-Device-Token"

func isClientAuthEnabled() bool {
	return clientAuthSecret != ""
}

func verifyClientSignatureValues(method, path, machineID, timestamp, signature string) bool {
	if !isClientAuthEnabled() {
		return false
	}

	timestamp = strings.TrimSpace(timestamp)
	signature = strings.TrimSpace(signature)
	machineID = strings.TrimSpace(machineID)
	if timestamp == "" || signature == "" {
		return false
	}

	ts, err := strconv.ParseInt(timestamp, 10, 64)
	if err != nil {
		return false
	}

	now := time.Now()
	requestTime := time.Unix(ts, 0)
	if requestTime.Before(now.Add(-clientAuthClockSkew)) || requestTime.After(now.Add(clientAuthClockSkew)) {
		return false
	}

	canonical := strings.Join([]string{
		strings.ToUpper(strings.TrimSpace(method)),
		strings.TrimSpace(path),
		machineID,
		timestamp,
	}, "\n")

	expectedMAC := hmac.New(sha256.New, []byte(clientAuthSecret))
	expectedMAC.Write([]byte(canonical))
	expected := expectedMAC.Sum(nil)

	provided, err := hex.DecodeString(signature)
	if err != nil {
		return false
	}
	return hmac.Equal(provided, expected)
}

func verifyClientSignature(c *gin.Context) bool {
	return verifyClientSignatureValues(
		c.Request.Method,
		c.Request.URL.Path,
		c.GetHeader("X-AimerWT-Machine"),
		c.GetHeader("X-AimerWT-Timestamp"),
		c.GetHeader("X-AimerWT-Signature"),
	)
}

func requireClientRequest(c *gin.Context) bool {
	if verifyClientSignature(c) {
		return true
	}
	c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"error": "访问被拒绝"})
	return false
}

func hashClientDeviceToken(token string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(token)))
	return hex.EncodeToString(sum[:])
}

func lookupClientDeviceToken(machineID string) (ClientDeviceToken, error) {
	var record ClientDeviceToken
	err := db.Where("machine_id = ?", strings.TrimSpace(machineID)).First(&record).Error
	return record, err
}

func maskMachineID(machineID string) string {
	normalized := strings.TrimSpace(machineID)
	if len(normalized) <= 16 {
		return normalized
	}
	return normalized[:12] + "..." + normalized[len(normalized)-8:]
}

func lookupClientDeviceTokenByToken(token string) (ClientDeviceToken, *ClientDeviceSession, error) {
	now := time.Now()
	var session ClientDeviceSession
	if err := db.Where("token_hash = ? AND expires_at > ?", hashClientDeviceToken(token), now).First(&session).Error; err == nil {
		return ClientDeviceToken{MachineID: session.MachineID, TokenHash: session.TokenHash}, &session, nil
	}
	var record ClientDeviceToken
	err := db.Where("token_hash = ?", hashClientDeviceToken(token)).First(&record).Error
	return record, nil, err
}

func generateClientDeviceToken() (string, error) {
	buf := make([]byte, clientDeviceTokenSize)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(buf), nil
}

func issueClientDeviceToken(machineID string) (string, error) {
	normalizedMachineID := strings.TrimSpace(machineID)
	if normalizedMachineID == "" {
		return "", errors.New("machine_id required")
	}

	token, err := generateClientDeviceToken()
	if err != nil {
		return "", err
	}

	now := time.Now()
	session := ClientDeviceSession{
		MachineID:  normalizedMachineID,
		TokenHash:  hashClientDeviceToken(token),
		ExpiresAt:  now.Add(clientDeviceSessionTTL),
		LastSeenAt: now,
	}
	if err := db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Create(&session).Error; err != nil {
			return err
		}
		var staleIDs []uint
		if err := tx.Model(&ClientDeviceSession{}).
			Where("machine_id = ?", normalizedMachineID).
			Order("created_at DESC, id DESC").
			Offset(clientDeviceSessionMax).
			Pluck("id", &staleIDs).Error; err != nil {
			return err
		}
		if len(staleIDs) > 0 {
			return tx.Where("id IN ?", staleIDs).Delete(&ClientDeviceSession{}).Error
		}
		return nil
	}); err != nil {
		return "", err
	}
	return token, nil
}

func hasClientDeviceToken(machineID string) bool {
	var count int64
	if err := db.Model(&ClientDeviceSession{}).
		Where("machine_id = ? AND expires_at > ?", strings.TrimSpace(machineID), time.Now()).
		Count(&count).Error; err == nil && count > 0 {
		return true
	}
	_, err := lookupClientDeviceToken(machineID)
	return err == nil
}

func verifyClientDeviceToken(machineID, token string) bool {
	if strings.TrimSpace(machineID) == "" || strings.TrimSpace(token) == "" {
		return false
	}

	provided := hashClientDeviceToken(token)
	now := time.Now()
	var session ClientDeviceSession
	if err := db.Where("machine_id = ? AND token_hash = ? AND expires_at > ?", strings.TrimSpace(machineID), provided, now).First(&session).Error; err == nil {
		if now.Sub(session.LastSeenAt) >= clientSessionTouchMinimum {
			if err := db.Model(&session).Updates(map[string]any{
				"last_seen_at": now,
				"expires_at":   now.Add(clientDeviceSessionTTL),
			}).Error; err != nil {
				return false
			}
		}
		return true
	}

	record, err := lookupClientDeviceToken(machineID)
	return err == nil && hmac.Equal([]byte(provided), []byte(record.TokenHash))
}

func migrateLegacyClientDeviceTokens() error {
	var legacyTokens []ClientDeviceToken
	if err := db.Find(&legacyTokens).Error; err != nil {
		return err
	}
	now := time.Now()
	return db.Transaction(func(tx *gorm.DB) error {
		for _, legacy := range legacyTokens {
			if strings.TrimSpace(legacy.MachineID) == "" || strings.TrimSpace(legacy.TokenHash) == "" {
				continue
			}
			session := ClientDeviceSession{
				MachineID:  strings.TrimSpace(legacy.MachineID),
				TokenHash:  strings.TrimSpace(legacy.TokenHash),
				ExpiresAt:  now.Add(clientDeviceSessionTTL),
				LastSeenAt: now,
				CreatedAt:  legacy.CreatedAt,
			}
			if session.CreatedAt.IsZero() {
				session.CreatedAt = now
			}
			if err := tx.Clauses(clause.OnConflict{DoNothing: true}).Create(&session).Error; err != nil {
				return err
			}
		}
		return nil
	})
}

var errIdentityProofRequired = errors.New("identity proof required")
var errIdentityCollision = errors.New("identity collision")

func machineIDIdentityExistsTx(tx *gorm.DB, machineID string) (bool, error) {
	normalized := strings.TrimSpace(machineID)
	for _, query := range []struct {
		model any
		field string
	}{
		{model: &TelemetryRecord{}, field: "machine_id"},
		{model: &ClientDeviceSession{}, field: "machine_id"},
		{model: &ClientDeviceToken{}, field: "machine_id"},
		{model: &MachineIDAlias{}, field: "alias_machine_id"},
	} {
		var count int64
		if err := tx.Model(query.model).Where(query.field+" = ?", normalized).Count(&count).Error; err != nil {
			return false, err
		}
		if count > 0 {
			return true, nil
		}
	}
	return false, nil
}

func reportedMachineIDAvailableForCanonicalTx(tx *gorm.DB, reported, canonical string) (bool, error) {
	reported = strings.TrimSpace(reported)
	canonical = strings.TrimSpace(canonical)
	if reported == canonical {
		return true, nil
	}
	var alias MachineIDAlias
	if err := tx.Where("alias_machine_id = ?", reported).First(&alias).Error; err == nil {
		return strings.TrimSpace(alias.CanonicalMachineID) == canonical, nil
	} else if !errors.Is(err, gorm.ErrRecordNotFound) {
		return false, err
	}
	for _, model := range []any{&TelemetryRecord{}, &ClientDeviceSession{}, &ClientDeviceToken{}} {
		var count int64
		if err := tx.Model(model).Where("machine_id = ?", reported).Count(&count).Error; err != nil {
			return false, err
		}
		if count > 0 {
			return false, nil
		}
	}
	return true, nil
}

func abortIdentityProofRequired(c *gin.Context) {
	c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"error": "需要设备身份凭证", "code": "identity_proof_required"})
}

func abortIdentityCollision(c *gin.Context) {
	c.AbortWithStatusJSON(http.StatusConflict, gin.H{"error": "设备身份冲突", "code": "identity_collision"})
}

func ensureClientDeviceToken(c *gin.Context, machineID string, allowBootstrap bool) bool {
	normalizedMachineID := strings.TrimSpace(machineID)
	if normalizedMachineID == "" {
		c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"error": "设备绑定不匹配"})
		return false
	}

	token := strings.TrimSpace(c.GetHeader(clientDeviceTokenHeader))
	if token != "" {
		if verifyClientDeviceToken(normalizedMachineID, token) {
			c.Set("_clientDeviceTokenValid", true)
			return true
		}
		if allowBootstrap {
			if record, historicalSession, err := lookupClientDeviceTokenByToken(token); err == nil {
				canonicalMachineID := strings.TrimSpace(record.MachineID)
				if canonicalMachineID != "" && canonicalMachineID != normalizedMachineID {
					available, err := reportedMachineIDAvailableForCanonicalTx(db, normalizedMachineID, canonicalMachineID)
					if err != nil {
						c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": "设备身份检查失败"})
						return false
					}
					if !available {
						abortIdentityCollision(c)
						return false
					}
					c.Set("_canonicalMachineID", canonicalMachineID)
					c.Set("_identityAliasAuthorized", true)
					if historicalSession != nil {
						c.Set("_historicalDeviceSessionID", historicalSession.ID)
					}
					log.Printf("[Auth] 设备令牌匹配历史机器码，沿用既有 UID: %s -> %s", maskMachineID(normalizedMachineID), maskMachineID(canonicalMachineID))
					return true
				}
			}
		}
		abortIdentityProofRequired(c)
		return false
	}

	if allowBootstrap {
		exists, err := machineIDIdentityExistsTx(db, normalizedMachineID)
		if err != nil {
			c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": "设备身份检查失败"})
			return false
		}
		if exists {
			abortIdentityProofRequired(c)
			return false
		}
		c.Set("_deviceTokenBootstrap", true)
		return true
	}

	abortIdentityProofRequired(c)
	return false
}

func ensureClientMachineBinding(c *gin.Context, machineID string) bool {
	expected := strings.TrimSpace(c.GetHeader("X-AimerWT-Machine"))
	actual := strings.TrimSpace(machineID)
	if expected == "" || actual == "" || expected != actual {
		c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"error": "设备绑定不匹配"})
		return false
	}

	allowBootstrap := c.Request.URL.Path == "/telemetry"
	return ensureClientDeviceToken(c, actual, allowBootstrap)
}
