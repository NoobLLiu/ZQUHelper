// Package auth 提供最简单的单用户 Token 认证。
//
// 账号密码来自 config.yaml（服务端访问凭据，不是教务账号），
// Token 存内存、重启失效（单机自用场景够用）。
package auth

import (
	"crypto/rand"
	"encoding/hex"
	"net/http"
	"strings"
	"sync"
	"time"
)

// Manager 管理登录凭据与 Token。
type Manager struct {
	username string
	password string
	ttl      time.Duration

	mu     sync.Mutex
	tokens map[string]time.Time // token -> 过期时间
}

// NewManager 创建认证管理器。
func NewManager(username, password string, ttlHours int) *Manager {
	if ttlHours <= 0 {
		ttlHours = 720
	}
	return &Manager{
		username: username,
		password: password,
		ttl:      time.Duration(ttlHours) * time.Hour,
		tokens:   make(map[string]time.Time),
	}
}

// Login 校验账号密码，成功返回新 Token。
func (m *Manager) Login(username, password string) (string, bool) {
	if username != m.username || password != m.password {
		return "", false
	}
	buf := make([]byte, 24)
	if _, err := rand.Read(buf); err != nil {
		return "", false
	}
	token := hex.EncodeToString(buf)
	m.mu.Lock()
	m.tokens[token] = time.Now().Add(m.ttl)
	m.mu.Unlock()
	return token, true
}

// Validate 校验 Bearer Token 是否有效；无效返回 false。
func (m *Manager) Validate(token string) bool {
	if token == "" {
		return false
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	exp, ok := m.tokens[token]
	if !ok {
		return false
	}
	if time.Now().After(exp) {
		delete(m.tokens, token)
		return false
	}
	return true
}

// BearerToken 从请求头提取 Bearer Token。
func BearerToken(r *http.Request) string {
	return strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
}
