"""Evaluation cases for the /ask text-to-SQL layer.

Each case: a natural-language question + a known-correct "gold" SQL + how to
compare. The runner generates SQL from the question, runs both, and compares
RESULTS (execution accuracy) — not the SQL text, since many SQLs are correct.

compare modes:
  "set"     -> result rows match as an unordered set (default)
  "ordered" -> result rows match in order (for ranking / top-N questions)
  "scalar"  -> single value matches (numeric within tolerance)

Most cases here were derived from real failures we found while testing, so they
double as regression tests: each guards a fix we made to the prompt.
"""

CASES = [
    # --- core mappings ---
    {
        "q": "أفضل معدل في بكالوريا رياضيات",
        "gold": "SELECT name, total FROM students WHERE stream='رياضيات' "
                "ORDER BY total DESC LIMIT 1",
        "mode": "ordered",
        "guards": "معدل -> total (not AVG); أفضل -> ORDER BY DESC",
    },
    {
        "q": "متوسط معدلات شعبة الرياضيات",
        "gold": "SELECT ROUND(AVG(total),2) FROM students WHERE stream='رياضيات'",
        "mode": "scalar",
        "guards": "متوسط -> AVG(total)",
    },
    {
        "q": "كم عدد الناجحين",
        "gold": "SELECT COUNT(*) FROM students WHERE status='ناجح'",
        "mode": "scalar",
        "guards": "ناجح -> status='ناجح'",
    },
    {
        "q": "كم عدد المؤجلين",
        "gold": "SELECT COUNT(*) FROM students WHERE status='مؤجل'",
        "mode": "scalar",
        "guards": "مؤجل is its own status (not lumped with fail)",
    },
    # --- regression: model must NOT add an unrequested passed/status filter ---
    {
        "q": "أفضل معدل في بكالوريا علوم الإعلامية",
        "gold": "SELECT name, total FROM students WHERE stream='علوم الإعلامية' "
                "ORDER BY total DESC LIMIT 1",
        "mode": "ordered",
        "guards": "no spurious status='ناجح'/passed filter (was the 18.11 bug)",
    },
    # --- multi-filter + status + bac average ---
    {
        "q": "الناجحون في شعبة علوم تجريبية بمعدل باك فوق 15",
        "gold": "SELECT name, total FROM students WHERE stream='علوم تجريبية' "
                "AND status='ناجح' AND total>15 ORDER BY total DESC",
        "mode": "set",
        "guards": "status + stream + total>15",
    },
    # --- grades join + subject vs stream ---
    {
        "q": "أعلى 3 أعداد في مادة الفلسفة في شعبة الآداب و أساميهم",
        "gold": "SELECT s.name, g.score FROM grades g JOIN students s "
                "ON g.registration_number=s.registration_number "
                "WHERE g.subject='الفلسفة' AND s.stream='آداب' "
                "ORDER BY g.score DESC LIMIT 3",
        "mode": "ordered",
        "guards": "subject (الفلسفة) vs stream (آداب); grades join; top-3",
    },
    # --- the correlated-subquery trap (as a COUNT so the 200-row cap can't skew it) ---
    {
        "q": "كم عدد التلاميذ فوق المعدل العام لشعبتهم",
        "gold": "SELECT COUNT(*) FROM students s "
                "WHERE s.total > (SELECT AVG(t.total) FROM students t "
                "WHERE t.stream=s.stream)",
        "mode": "scalar",
        "guards": "correlated subquery with distinct aliases (per-stream, not global)",
    },
    # --- per-group top-N (window function) ---
    {
        "q": "أفضل تلميذ في كل شعبة حسب معدل الباك",
        "gold": "SELECT name, stream, total FROM ("
                "SELECT *, ROW_NUMBER() OVER (PARTITION BY stream ORDER BY total DESC) rk "
                "FROM students) WHERE rk=1",
        "mode": "set",
        "guards": "top-N per group (window function)",
    },
]
