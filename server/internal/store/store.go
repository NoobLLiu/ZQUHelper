// Package store 提供 SQLite 持久化（modernc.org/sqlite 纯 Go 驱动，免 CGO）。
package store

import (
	"database/sql"
	"fmt"

	_ "modernc.org/sqlite"
)

// Store 封装 SQLite 连接。
type Store struct {
	DB *sql.DB
}

// Open 打开（必要时创建）数据库并执行迁移。
func Open(path string) (*Store, error) {
	dsn := fmt.Sprintf("file:%s?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)", path)
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, err
	}
	if _, err := db.Exec(schema); err != nil {
		db.Close()
		return nil, fmt.Errorf("migrate: %w", err)
	}
	return &Store{DB: db}, nil
}

// Close 关闭数据库。
func (s *Store) Close() error { return s.DB.Close() }

const schema = `
CREATE TABLE IF NOT EXISTS timetable (
	term        TEXT PRIMARY KEY,   -- 学年学期代码，如 202601
	term_name   TEXT NOT NULL DEFAULT '',
	total_weeks INTEGER NOT NULL DEFAULT 0,
	data        TEXT NOT NULL,      -- 完整学期课表 JSON（TermSchedule 结构）
	fetched_at  TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS kv (
	k TEXT PRIMARY KEY,
	v TEXT NOT NULL
);
`

// TimetableRow 是一条已缓存的学期课表。
type TimetableRow struct {
	Term       string `json:"term"`
	TermName   string `json:"term_name"`
	TotalWeeks int    `json:"total_weeks"`
	Data       string `json:"data"` // 原样 JSON 字符串
	FetchedAt  string `json:"fetched_at"`
}

// SaveTimetable 写入/覆盖一个学期的课表缓存。
func (s *Store) SaveTimetable(term, termName string, totalWeeks int, data, fetchedAt string) error {
	_, err := s.DB.Exec(`INSERT INTO timetable(term, term_name, total_weeks, data, fetched_at)
		VALUES(?,?,?,?,?)
		ON CONFLICT(term) DO UPDATE SET
		  term_name=excluded.term_name, total_weeks=excluded.total_weeks,
		  data=excluded.data, fetched_at=excluded.fetched_at`,
		term, termName, totalWeeks, data, fetchedAt)
	return err
}

// GetTimetable 读取一个学期的课表缓存。
func (s *Store) GetTimetable(term string) (*TimetableRow, error) {
	row := s.DB.QueryRow(`SELECT term, term_name, total_weeks, data, fetched_at
		FROM timetable WHERE term=?`, term)
	var r TimetableRow
	if err := row.Scan(&r.Term, &r.TermName, &r.TotalWeeks, &r.Data, &r.FetchedAt); err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, err
	}
	return &r, nil
}

// LatestTimetable 返回最近抓取的学期课表（按 fetched_at 倒序）。
func (s *Store) LatestTimetable() (*TimetableRow, error) {
	row := s.DB.QueryRow(`SELECT term, term_name, total_weeks, data, fetched_at
		FROM timetable ORDER BY fetched_at DESC LIMIT 1`)
	var r TimetableRow
	if err := row.Scan(&r.Term, &r.TermName, &r.TotalWeeks, &r.Data, &r.FetchedAt); err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, err
	}
	return &r, nil
}

// ListTerms 返回所有已缓存学期概要。
func (s *Store) ListTerms() ([]TimetableRow, error) {
	rows, err := s.DB.Query(`SELECT term, term_name, total_weeks, '' , fetched_at
		FROM timetable ORDER BY term DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []TimetableRow
	for rows.Next() {
		var r TimetableRow
		if err := rows.Scan(&r.Term, &r.TermName, &r.TotalWeeks, &r.Data, &r.FetchedAt); err != nil {
			return nil, err
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

// KVSet 写入一个键值。
func (s *Store) KVSet(k, v string) error {
	_, err := s.DB.Exec(`INSERT INTO kv(k,v) VALUES(?,?)
		ON CONFLICT(k) DO UPDATE SET v=excluded.v`, k, v)
	return err
}

// KVGet 读取一个键值，不存在时返回 ("", nil)。
func (s *Store) KVGet(k string) (string, error) {
	var v string
	err := s.DB.QueryRow(`SELECT v FROM kv WHERE k=?`, k).Scan(&v)
	if err == sql.ErrNoRows {
		return "", nil
	}
	return v, err
}
