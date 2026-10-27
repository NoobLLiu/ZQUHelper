/// 课表数据模型（对应服务端 /api/v1/timetable 返回的 JSON）。
library;

class Course {
  Course({
    required this.name,
    required this.teacher,
    required this.weekday,
    required this.date,
    required this.week,
    required this.periods,
    required this.periodText,
    required this.classroom,
    required this.className,
    required this.courseType,
  });

  final String name;
  final String teacher;
  final int weekday; // 1..7
  final String date; // YYYY-MM-DD
  final int week;
  final List<int> periods; // 节次
  final String periodText; // 如 "1-2节"
  final String classroom;
  final String className;
  final String courseType;

  int get startPeriod => periods.isEmpty ? 0 : periods.first;
  int get endPeriod => periods.isEmpty ? 0 : periods.last;

  factory Course.fromJson(Map<String, dynamic> j) => Course(
        name: j['name']?.toString() ?? '',
        teacher: j['teacher']?.toString() ?? '',
        weekday: (j['weekday'] as num?)?.toInt() ?? 0,
        date: j['date']?.toString() ?? '',
        week: (j['week'] as num?)?.toInt() ?? 0,
        periods: ((j['periods'] as List?) ?? [])
            .map((e) => (e as num).toInt())
            .toList(),
        periodText: j['period_text']?.toString() ?? '',
        classroom: j['classroom']?.toString() ?? '',
        className: j['class_name']?.toString() ?? '',
        courseType: j['course_type']?.toString() ?? '',
      );
}

class WeekSchedule {
  WeekSchedule({
    required this.week,
    required this.weekLabel,
    required this.dates,
    required this.courses,
  });

  final int week;
  final String weekLabel;
  final Map<int, String> dates; // weekday -> YYYY-MM-DD
  final List<Course> courses;

  factory WeekSchedule.fromJson(Map<String, dynamic> j) {
    final dates = <int, String>{};
    for (final d in ((j['dates'] as List?) ?? [])) {
      if (d is Map<String, dynamic>) {
        final wd = (d['weekday'] as num?)?.toInt() ?? 0;
        dates[wd] = d['date']?.toString() ?? '';
      }
    }
    return WeekSchedule(
      week: (j['week'] as num?)?.toInt() ?? 0,
      weekLabel: j['week_label']?.toString() ?? '',
      dates: dates,
      courses: ((j['courses'] as List?) ?? [])
          .whereType<Map<String, dynamic>>()
          .map(Course.fromJson)
          .toList(),
    );
  }
}

class Timetable {
  Timetable({
    required this.term,
    required this.termName,
    required this.totalWeeks,
    required this.fetchedAt,
    required this.weeks,
  });

  final String term;
  final String termName;
  final int totalWeeks;
  final String fetchedAt;
  final List<WeekSchedule> weeks;

  /// 当天是第几周（按第一周周一推算）；推不出返回 1。
  int get currentWeek {
    final w = weeks.where((w) => w.courses.isNotEmpty).toList();
    if (w.isEmpty) return 1;
    DateTime? firstMonday;
    for (final week in w) {
      final d = week.dates[1];
      if (d != null && d.isNotEmpty) {
        firstMonday = DateTime.tryParse(d);
        break;
      }
    }
    if (firstMonday == null) return 1;
    final today = DateTime.now();
    final diff = today.difference(firstMonday).inDays;
    final wk = diff ~/ 7 + 1;
    if (wk < 1) return 1;
    return wk > totalWeeks ? totalWeeks : wk;
  }

  /// 从 /api/v1/timetable 响应的 data 解析。
  factory Timetable.fromApi(Map<String, dynamic> data) {
    final tt = (data['timetable'] as Map<String, dynamic>?) ?? {};
    return Timetable(
      term: data['term']?.toString() ?? tt['term']?.toString() ?? '',
      termName: data['term_name']?.toString() ?? tt['term_name']?.toString() ?? '',
      totalWeeks: (data['total_weeks'] as num?)?.toInt() ??
          (tt['total_weeks'] as num?)?.toInt() ??
          0,
      fetchedAt: data['fetched_at']?.toString() ?? '',
      weeks: ((tt['weeks'] as List?) ?? [])
          .whereType<Map<String, dynamic>>()
          .map(WeekSchedule.fromJson)
          .toList(),
    );
  }
}
