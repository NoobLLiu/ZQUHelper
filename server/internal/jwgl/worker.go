// Package jwgl 负责教务课表抓取。
//
// 架构说明：WebVPN 滑块破解与验证码 OCR 依赖真实浏览器（Playwright），
// 无法用纯 HTTP 在 Go 里重写，因此抓取由 server/tools/zqu_fetch/fetch_worker.py
// 以子进程方式执行，本包只负责「调度子进程 → 解析结果 JSON → 写缓存」。
package jwgl

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

// Config 是抓取 worker 的运行配置（来自 config.yaml）。
type Config struct {
	PythonPath string // Python 解释器路径，如 venv 里的 python.exe
	WorkerDir  string // fetch_worker.py 所在目录
	Username   string // 教务账号
	Password   string // 教务密码
	Headless   bool   // 浏览器无头模式（调试时可关掉观察）
}

// FetchResult 对应 fetch_worker.py 输出的 JSON。
type FetchResult struct {
	OK         bool            `json:"ok"`
	Mode       string          `json:"mode"`
	Error      string          `json:"error"`
	Term       string          `json:"term"`
	TermName   string          `json:"term_name"`
	TotalWeeks int             `json:"total_weeks"`
	Timetable  json.RawMessage `json:"timetable"`
	FetchedAt  string          `json:"fetched_at"`
}

// Fetch 同步执行一轮抓取（整学期，耗时可能数分钟，调用方应给足超时）。
// term/weeks 为空表示抓当前学期全部周。
// 结果 JSON 写到临时文件后读回，避免 stdout 与进度日志混在一起。
func Fetch(ctx context.Context, cfg Config, term, weeks string) (*FetchResult, string, error) {
	outFile := filepath.Join(os.TempDir(),
		fmt.Sprintf("zqu_fetch_%d.json", time.Now().UnixNano()))
	defer os.Remove(outFile)

	args := []string{
		"fetch_worker.py",
		"--mode", "auto",
		"--user", cfg.Username,
		"--pass", cfg.Password,
		"--out", outFile,
	}
	if term != "" {
		args = append(args, "--term", term)
	}
	if weeks != "" {
		args = append(args, "--weeks", weeks)
	}
	if cfg.Headless {
		args = append(args, "--headless")
	}

	cmd := exec.CommandContext(ctx, cfg.PythonPath, args...)
	cmd.Dir = cfg.WorkerDir
	out, err := cmd.CombinedOutput()
	logText := string(out)
	if err != nil {
		// worker 正常跑完但没抓到数据时也会以非 0 退出，此时仍有结果文件可读
		if res, rerr := readResult(outFile); rerr == nil {
			return res, logText, nil
		}
		return nil, logText, fmt.Errorf("fetch worker: %w", err)
	}
	res, rerr := readResult(outFile)
	if rerr != nil {
		return nil, logText, fmt.Errorf("read worker output: %w", rerr)
	}
	return res, logText, nil
}

func readResult(path string) (*FetchResult, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var res FetchResult
	if err := json.Unmarshal(data, &res); err != nil {
		return nil, err
	}
	return &res, nil
}
