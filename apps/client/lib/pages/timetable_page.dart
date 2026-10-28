import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../models/timetable.dart';
import 'login_page.dart';

/// 课表页：周视图网格（左列节次 + 周一~周日），参考拾光课程表风格。
class TimetablePage extends StatefulWidget {
  const TimetablePage({super.key});

  @override
  State<TimetablePage> createState() => _TimetablePageState();
}

class _TimetablePageState extends State<TimetablePage> {
  final ScrollController _hScroll = ScrollController(); // 表头与网格横向同步
  Timetable? _tt;
  bool _loading = true;
  String? _error;
  int _week = 1;
  bool _refreshing = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _hScroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await ApiClient.fetchTimetable();
      final tt = Timetable.fromApi(data);
      setState(() {
        _tt = tt;
        _week = tt.currentWeek;
        _loading = false;
      });
    } on ApiException catch (e) {
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  /// 触发服务端重新抓取并轮询状态。
  Future<void> _refresh() async {
    setState(() => _refreshing = true);
    try {
      await ApiClient.refreshTimetable();
      // 轮询任务状态，最多 15 分钟（整学期抓取较慢）
      for (var i = 0; i < 180; i++) {
        await Future.delayed(const Duration(seconds: 5));
        final st = await ApiClient.fetchStatus();
        if (st['running'] != true) {
          if (st['ok'] == true) {
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('课表已更新')));
            }
            await _load();
          } else {
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                  content: Text('抓取失败: ${st['error'] ?? '未知错误'}')));
            }
          }
          break;
        }
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _refreshing = false);
    }
  }

  Future<void> _logout() async {
    await ApiClient.clear();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const LoginPage()));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('课程表'),
            if (_tt != null)
              Text('${_tt!.termName} · 抓取于 ${_tt!.fetchedAt.substring(0, 10)}',
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: theme.colorScheme.outline)),
          ],
        ),
        actions: [
          if (_refreshing)
            const Padding(
              padding: EdgeInsets.all(14),
              child: SizedBox(
                  width: 22, height: 22,
                  child: CircularProgressIndicator(strokeWidth: 2)),
            )
          else
            IconButton(onPressed: _refresh, icon: const Icon(Icons.refresh)),
          IconButton(onPressed: _logout, icon: const Icon(Icons.logout)),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(_error!, textAlign: TextAlign.center),
                    const SizedBox(height: 12),
                    FilledButton(onPressed: _load, child: const Text('重试')),
                  ]))
              : _buildGrid(theme),
    );
  }

  Widget _buildGrid(ThemeData theme) {
    final tt = _tt!;
    final week = tt.weeks.where((w) => w.week == _week).toList();
    final ws = week.isEmpty
        ? WeekSchedule(week: _week, weekLabel: '', dates: {}, courses: [])
        : week.first;
    final courses = ws.courses;
    final maxPeriod = courses.fold<int>(8, (m, c) => c.endPeriod > m ? c.endPeriod : m);

    // 网格几何常量：左列节次宽 / 每天列宽 / 每节行高
    const leftW = 56.0, colW = 64.0, rowH = 56.0;
    const headerH = 48.0;
    final gridW = leftW + 7 * colW;
    final gridH = maxPeriod * rowH;

    return Column(
      children: [
        // 周次切换条
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: Row(
            children: [
              IconButton(
                  onPressed: _week > 1 ? () => setState(() => _week--) : null,
                  icon: const Icon(Icons.chevron_left)),
              Expanded(
                child: Center(
                  child: Text('第 $_week 周',
                      style: theme.textTheme.titleMedium
                          ?.copyWith(fontWeight: FontWeight.bold)),
                ),
              ),
              IconButton(
                  onPressed:
                      _week < tt.totalWeeks ? () => setState(() => _week++) : null,
                  icon: const Icon(Icons.chevron_right)),
            ],
          ),
        ),
        // 表头：节 + 周一~周日（含日期），与网格共用横向滚动
        SingleChildScrollView(
          controller: _hScroll,
          scrollDirection: Axis.horizontal,
          child: SizedBox(
            width: gridW,
            height: headerH,
            child: Row(children: [
              _headerCell('节', leftW, headerH, theme),
              for (var d = 1; d <= 7; d++)
                _headerCell('周$d\n${ws.dates[d]?.substring(5) ?? ''}',
                    colW, headerH, theme),
            ]),
          ),
        ),
        Expanded(
          child: SingleChildScrollView(
            child: SingleChildScrollView(
              controller: _hScroll,
              scrollDirection: Axis.horizontal,
              child: SizedBox(
                width: gridW,
                height: gridH,
                child: Stack(
                  clipBehavior: Clip.none,
                  children: [
                    // 背景网格线 + 左列节次号
                    Positioned.fill(
                      child: CustomPaint(
                        painter: _GridPainter(
                            leftW: leftW,
                            colW: colW,
                            rowH: rowH,
                            rows: maxPeriod,
                            color: theme.dividerColor.withValues(alpha: 0.35)),
                      ),
                    ),
                    for (var p = 1; p <= maxPeriod; p++)
                      Positioned(
                        left: 0,
                        top: (p - 1) * rowH,
                        width: leftW,
                        height: rowH,
                        child: Center(
                          child: Text('$p',
                              style: TextStyle(
                                  fontSize: 11,
                                  color: theme.colorScheme.outline)),
                        ),
                      ),
                    // 课程卡片：连堂课按节数跨行占格
                    for (final c in courses)
                      if (c.weekday >= 1 &&
                          c.weekday <= 7 &&
                          c.startPeriod >= 1)
                        Positioned(
                          left: leftW + (c.weekday - 1) * colW + 2,
                          top: (c.startPeriod - 1) * rowH + 2,
                          width: colW - 4,
                          height:
                              (c.endPeriod - c.startPeriod + 1) * rowH - 4,
                          child: _courseCard(c, theme),
                        ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _headerCell(String text, double w, double h, ThemeData theme) {
    return Container(
      width: w,
      height: h,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        border: Border.all(
            color: theme.dividerColor.withValues(alpha: 0.35), width: 0.5),
      ),
      child: Text(text,
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
    );
  }

  /// 课程卡片：高度由外层 Positioned 决定（连堂课跨多行）。
  Widget _courseCard(Course c, ThemeData theme) {
    final color = courseColor(c.name);
    return GestureDetector(
      onTap: () => _showCourseDetail(c),
      child: Container(
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.18),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withValues(alpha: 0.6), width: 1),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(c.name,
                maxLines: 3, overflow: TextOverflow.ellipsis,
                style: TextStyle(
                    fontSize: 11, fontWeight: FontWeight.w600, color: color)),
            const Spacer(),
            if (c.classroom.isNotEmpty)
              Text('@${c.classroom}',
                  maxLines: 1, overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 10, color: theme.colorScheme.outline)),
          ],
        ),
      ),
    );
  }

  void _showCourseDetail(Course c) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (_) => Padding(
        padding: const EdgeInsets.fromLTRB(24, 0, 24, 32),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(c.name, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          _kv('时间', '第${c.week}周 ${_weekdayCn(c.weekday)} ${c.periodText}'),
          if (c.date.isNotEmpty) _kv('日期', c.date),
          _kv('教室', c.classroom.isEmpty ? '待定' : c.classroom),
          _kv('教师', c.teacher.isEmpty ? '—' : c.teacher),
          if (c.className.isNotEmpty) _kv('教学班', c.className),
          if (c.courseType.isNotEmpty) _kv('类型', c.courseType),
        ]),
      ),
    );
  }

  Widget _kv(String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(
              width: 52,
              child: Text(k,
                  style: TextStyle(
                      color: Theme.of(context).colorScheme.outline))),
          Expanded(child: Text(v)),
        ]),
      );

  String _weekdayCn(int d) =>
      const ['', '周一', '周二', '周三', '周四', '周五', '周六', '周日'][d.clamp(0, 7)];
}

/// 网格背景线：左列分隔 + 每天列分隔 + 每节行分隔。
class _GridPainter extends CustomPainter {
  _GridPainter({
    required this.leftW,
    required this.colW,
    required this.rowH,
    required this.rows,
    required this.color,
  });

  final double leftW;
  final double colW;
  final double rowH;
  final int rows;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 0.5;

    // 横线（每节一行）
    for (var r = 0; r <= rows; r++) {
      final y = r * rowH;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }
    // 竖线（左列 + 7 天）
    for (var c = 0; c <= 8; c++) {
      final x = c == 0 ? 0.0 : leftW + (c - 1) * colW;
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
    }
  }

  @override
  bool shouldRepaint(covariant _GridPainter old) =>
      old.rows != rows || old.rowH != rowH || old.color != color;
}

/// 按课程名散列取色，保证同一课程每周同色。
Color courseColor(String name) {
  const palette = [
    Color(0xFF4F6EF7), Color(0xFFE5484D), Color(0xFF30A46C),
    Color(0xFFE5883D), Color(0xFF8E4EC6), Color(0xFF00A2C7),
    Color(0xFFD6409F), Color(0xFF6E56CF),
  ];
  var h = 0;
  for (final rune in name.codeUnits) {
    h = (h * 31 + rune) & 0x7fffffff;
  }
  return palette[h % palette.length];
}
