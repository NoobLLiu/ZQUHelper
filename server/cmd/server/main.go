// ZQUHelper 服务端入口。
//
// 启动流程：读 config.yaml → 打开 SQLite → 挂载 API → 监听。
// 配置文件默认在 server/config/config.yaml（由 config.example.yaml 复制而来）。
package main

import (
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"

	"github.com/gin-gonic/gin"
	"gopkg.in/yaml.v3"

	"github.com/NoobLLiu/ZQUHelper/server/internal/api"
	"github.com/NoobLLiu/ZQUHelper/server/internal/auth"
	"github.com/NoobLLiu/ZQUHelper/server/internal/jwgl"
	"github.com/NoobLLiu/ZQUHelper/server/internal/store"
)

// Config 与 config.example.yaml 对应。
type Config struct {
	Server struct {
		Addr string `yaml:"addr"`
	} `yaml:"server"`
	Storage struct {
		SQLitePath string `yaml:"sqlite_path"`
	} `yaml:"storage"`
	JWGL struct {
		PythonPath string `yaml:"python_path"`
		WorkerDir  string `yaml:"worker_dir"`
		Username   string `yaml:"username"`
		Password   string `yaml:"password"`
		Headless   bool   `yaml:"headless"`
	} `yaml:"jwgl"`
	Auth struct {
		Username      string `yaml:"username"`
		Password      string `yaml:"password"`
		TokenTTLHours int    `yaml:"token_ttl_hours"`
	} `yaml:"auth"`
}

func loadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var cfg Config
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, err
	}
	// 默认值
	if cfg.Server.Addr == "" {
		cfg.Server.Addr = "0.0.0.0:8787"
	}
	if cfg.Storage.SQLitePath == "" {
		cfg.Storage.SQLitePath = "data/zquhelper.db"
	}
	if cfg.JWGL.PythonPath == "" {
		cfg.JWGL.PythonPath = "python"
	}
	return &cfg, nil
}

func main() {
	cfgPath := flag.String("config", filepath.Join("config", "config.yaml"), "配置文件路径")
	flag.Parse()

	cfg, err := loadConfig(*cfgPath)
	if err != nil {
		log.Fatalf("读取配置失败: %v", err)
	}

	// 保证 SQLite 目录存在
	if dir := filepath.Dir(cfg.Storage.SQLitePath); dir != "" && dir != "." {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			log.Fatalf("创建数据目录失败: %v", err)
		}
	}

	st, err := store.Open(cfg.Storage.SQLitePath)
	if err != nil {
		log.Fatalf("打开数据库失败: %v", err)
	}
	defer st.Close()

	workerCfg := jwgl.Config{
		PythonPath: cfg.JWGL.PythonPath,
		WorkerDir:  cfg.JWGL.WorkerDir,
		Username:   cfg.JWGL.Username,
		Password:   cfg.JWGL.Password,
		Headless:   cfg.JWGL.Headless,
	}
	if workerCfg.WorkerDir == "" {
		workerCfg.WorkerDir = filepath.Join("tools", "zqu_fetch")
	}
	jwSvc := jwgl.NewService(workerCfg, st)

	mgr := auth.NewManager(cfg.Auth.Username, cfg.Auth.Password, cfg.Auth.TokenTTLHours)

	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(gin.Logger(), gin.Recovery())
	api.Register(r, mgr, jwSvc)

	log.Printf("ZQUHelper server listening on %s", cfg.Server.Addr)
	fmt.Printf("ZQUHelper server listening on http://%s (ping: /api/v1/ping)\n", cfg.Server.Addr)
	if err := r.Run(cfg.Server.Addr); err != nil {
		log.Fatalf("启动失败: %v", err)
	}
}
