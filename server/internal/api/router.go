// Package api 挂载 HTTP 路由。
package api

import (
	"encoding/json"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/NoobLLiu/ZQUHelper/server/internal/auth"
	"github.com/NoobLLiu/ZQUHelper/server/internal/jwgl"
)

// resp 统一包装 {code, msg, data}。
func resp(c *gin.Context, code int, msg string, data any) {
	c.JSON(http.StatusOK, gin.H{"code": code, "msg": msg, "data": data})
}

func timeNow() string { return time.Now().Format(time.RFC3339) }

// Register 注册全部路由。
func Register(r *gin.Engine, mgr *auth.Manager, jw *jwgl.Service) {
	r.GET("/api/v1/ping", func(c *gin.Context) {
		resp(c, 0, "pong", gin.H{"time": timeNow()})
	})

	api := r.Group("/api/v1")

	// ---- 登录（不需要 Token） ----
	api.POST("/auth/login", func(c *gin.Context) {
		var body struct {
			Username string `json:"username"`
			Password string `json:"password"`
		}
		if err := c.ShouldBindJSON(&body); err != nil {
			resp(c, 400, "参数错误", nil)
			return
		}
		token, ok := mgr.Login(body.Username, body.Password)
		if !ok {
			resp(c, 401, "账号或密码错误", nil)
			return
		}
		resp(c, 0, "ok", gin.H{"token": token})
	})

	// ---- 以下路由需要 Token ----
	authMW := func(c *gin.Context) {
		if mgr.Validate(auth.BearerToken(c.Request)) {
			c.Next()
			return
		}
		c.AbortWithStatusJSON(http.StatusUnauthorized,
			gin.H{"code": 401, "msg": "未登录或 Token 已失效", "data": nil})
	}
	authed := api.Group("", authMW)

	// 课表
	tt := authed.Group("/timetable")
	{
		// GET /timetable?term=202601&week=5
		// term 省略时返回最近缓存学期；week 省略时返回整学期。
		tt.GET("", func(c *gin.Context) {
			row, err := jw.GetTerm(c.Query("term"))
			if err != nil {
				resp(c, 500, "读取缓存失败: "+err.Error(), nil)
				return
			}
			if row == nil {
				resp(c, 404, "暂无课表缓存，请先触发刷新", nil)
				return
			}
			resp(c, 0, "ok", gin.H{
				"term": row.Term, "term_name": row.TermName,
				"total_weeks": row.TotalWeeks, "fetched_at": row.FetchedAt,
				"timetable": filterWeek(row.Data, c.Query("week")),
			})
		})

		tt.GET("/terms", func(c *gin.Context) {
			terms, err := jw.ListTerms()
			if err != nil {
				resp(c, 500, "读取学期列表失败", nil)
				return
			}
			resp(c, 0, "ok", terms)
		})

		// POST /timetable/refresh  {"term":"202601","weeks":"1,2,3"}（都可省略）
		tt.POST("/refresh", func(c *gin.Context) {
			var body struct {
				Term  string `json:"term"`
				Weeks string `json:"weeks"`
			}
			_ = c.ShouldBindJSON(&body)
			if !jw.RefreshAsync(body.Term, body.Weeks) {
				resp(c, 409, "已有抓取任务在进行中", nil)
				return
			}
			resp(c, 0, "抓取任务已启动", nil)
		})

		tt.GET("/status", func(c *gin.Context) {
			resp(c, 0, "ok", jw.Status())
		})
	}
}

// filterWeek 从整学期 JSON 中挑出某一周；week 为空时原样返回整学期。
// data 结构: {"term":..., "term_name":..., "total_weeks":..., "weeks":[{"week":1,...}, ...]}
func filterWeek(data, week string) json.RawMessage {
	if week == "" {
		return json.RawMessage(data)
	}
	var full struct {
		Term       string            `json:"term"`
		TermName   string            `json:"term_name"`
		TotalWeeks int               `json:"total_weeks"`
		Weeks      []json.RawMessage `json:"weeks"`
	}
	if err := json.Unmarshal([]byte(data), &full); err != nil {
		return json.RawMessage(data)
	}
	for _, w := range full.Weeks {
		var wm struct {
			Week int `json:"week"`
		}
		if err := json.Unmarshal(w, &wm); err != nil {
			continue
		}
		if strconv.Itoa(wm.Week) == week {
			out, _ := json.Marshal(gin.H{
				"term": full.Term, "term_name": full.TermName,
				"total_weeks": full.TotalWeeks, "week": json.RawMessage(w),
			})
			return out
		}
	}
	return nil
}
