package jwgl

import (
	"context"
	"sync"
	"time"

	"github.com/NoobLLiu/ZQUHelper/server/internal/store"
)

// JobStatus 是一次抓取任务的状态。
type JobStatus struct {
	Running   bool      `json:"running"`
	StartedAt time.Time `json:"started_at,omitempty"`
	EndedAt   time.Time `json:"ended_at,omitempty"`
	OK        bool      `json:"ok"`
	Error     string    `json:"error,omitempty"`
	Mode      string    `json:"mode,omitempty"`
	LogTail   string    `json:"log_tail,omitempty"` // worker 输出末尾，便于排查
}

// Service 管理抓取任务（同一时间只允许一个）并把结果写入缓存。
type Service struct {
	cfg Config
	st  *store.Store

	mu      sync.Mutex
	running bool
	last    JobStatus
}

// NewService 创建课表服务。
func NewService(cfg Config, st *store.Store) *Service {
	return &Service{cfg: cfg, st: st}
}

// RefreshAsync 异步启动一轮抓取。若已有任务在跑则返回 false。
func (s *Service) RefreshAsync(term, weeks string) bool {
	s.mu.Lock()
	if s.running {
		s.mu.Unlock()
		return false
	}
	s.running = true
	s.last = JobStatus{Running: true, StartedAt: time.Now()}
	s.mu.Unlock()

	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 20*time.Minute)
		defer cancel()

		res, logText, err := Fetch(ctx, s.cfg, term, weeks)
		tail := logText
		if len(tail) > 2000 {
			tail = tail[len(tail)-2000:]
		}

		s.mu.Lock()
		s.running = false
		s.last.Running = false
		s.last.EndedAt = time.Now()
		s.last.LogTail = tail
		if err != nil {
			s.last.OK = false
			s.last.Error = err.Error()
		} else if !res.OK {
			s.last.OK = false
			s.last.Error = res.Error
			s.last.Mode = res.Mode
		} else {
			s.last.OK = true
			s.last.Mode = res.Mode
			saveErr := s.st.SaveTimetable(res.Term, res.TermName, res.TotalWeeks,
				string(res.Timetable), time.Now().Format(time.RFC3339))
			if saveErr != nil {
				s.last.OK = false
				s.last.Error = "保存缓存失败: " + saveErr.Error()
			}
		}
		s.mu.Unlock()
	}()
	return true
}

// Status 返回最近一次任务状态。
func (s *Service) Status() JobStatus {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.last
}

// GetTerm 返回指定学期缓存；term 为空时返回最近缓存的学期。
func (s *Service) GetTerm(term string) (*store.TimetableRow, error) {
	if term != "" {
		return s.st.GetTimetable(term)
	}
	return s.st.LatestTimetable()
}

// ListTerms 返回所有已缓存学期。
func (s *Service) ListTerms() ([]store.TimetableRow, error) {
	return s.st.ListTerms()
}
