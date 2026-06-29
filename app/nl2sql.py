"""Text-to-SQL: build the schema-linking prompt, validate, and run safely.

Strategy (schema linking): we hand the model the exact schema, an Arabic/franco
glossary, the real distinct values for categorical columns, and a few worked
examples. The model only proposes SQL; we validate it (SELECT-only, single
statement, enforced LIMIT) and run it on a READ-ONLY connection, so a write can
never reach the database even if the model emits one.
"""
from __future__ import annotations

import re
import sqlite3

# Words that must never appear — defense in depth on top of the read-only conn.
FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|"
    r"pragma|vacuum|reindex|grant|revoke)\b",
    re.IGNORECASE,
)

GLOSSARY = """\
المفردات (مرادفات المستخدم -> العمود):
- معدل / معدل الباك / mou3adel / moyenne du bac / المجموع / النتيجة النهائية -> total
- المعدل السنوي / moyenne annuelle / annual -> moyenne
- شعبة / filiere / section / stream            -> stream
- مؤسسة / معهد / lycee / school                -> institution
- ناجح / najah                                 -> status = 'ناجح'
- مؤجل / دورة المراقبة / session de contrôle    -> status = 'مؤجل'
- راسب / مرفوض / rasib / refusé / failed        -> status = 'مرفوض'
- ملاحظة / mention                             -> mention
- مادة / matiere / subject + نقطة/score        -> grades.subject, grades.score
- ريمونتادا / remontada / comeback             -> (total - moyenne) DESC
- اسم / nom / name                             -> name
- أوائل / top / أفضل / les meilleurs           -> ORDER BY ... DESC LIMIT N
"""

NOTES = """\
تنبيهات مهمة:
- "رياضيات" شعبة (عمود stream)، أمّا "الرياضيات" فمادة (grades.subject). انتبه للفرق.
- عمود total = معدل الباكالوريا النهائي (من 20) ويحدّد النجاح والملاحظة. إذا قال المستخدم "معدل" أو "معدل الباك" فالمقصود عمود total (نتيجة التلميذ).
- مهم جدًّا: كلمة "معدل" هنا تعني عمود total (نتيجة تلميذ)، وليست دالة المتوسط AVG.
  • "أفضل/أعلى معدل" أو "أحسن معدل" = ORDER BY total DESC LIMIT N (وليس AVG).
  • "أدنى/أضعف معدل" = ORDER BY total ASC LIMIT N.
  • استعمل AVG(total) فقط إذا طُلب صراحةً "متوسط" أو "معدل عام" أو "المعدل الوسطي".
- عمود moyenne = المعدل السنوي (معدل السنة الدراسية)، لا يُستعمل إلا إذا ذُكر "السنوي" صراحةً.
- لأسئلة المواد استعمل جدول grades مع ربطه بـ students.
- عند المقارنة بمتوسط مجموعة (مثل "فوق متوسط شعبته/مؤسسته") استعمل استعلامًا فرعيًا مترابطًا بأسماء مستعارة مختلفة للجدول الخارجي والداخلي (s و t)، وإلا سيُحسب المتوسط العام بالخطأ. مثال: ... FROM students s WHERE s.total > (SELECT AVG(t.total) FROM students t WHERE t.stream = s.stream).
"""

EXAMPLES = """\
أمثلة (سؤال -> SQL):
س: أفضل 5 معدلات في الرياضيات
SQL: SELECT name, total FROM students WHERE stream = 'رياضيات' ORDER BY total DESC LIMIT 5;

س: أفضل معدل في بكالوريا رياضيات
SQL: SELECT name, total FROM students WHERE stream = 'رياضيات' ORDER BY total DESC LIMIT 1;

س: متوسط معدلات شعبة الرياضيات
SQL: SELECT ROUND(AVG(total), 2) AS avg_total FROM students WHERE stream = 'رياضيات';

س: نسبة النجاح حسب الشعبة
SQL: SELECT stream, ROUND(100.0*SUM(passed)/COUNT(*),1) AS pass_rate FROM students GROUP BY stream ORDER BY pass_rate DESC;

س: كم عدد الناجحين في معهد المكناسي
SQL: SELECT COUNT(*) AS n FROM students WHERE institution LIKE '%المكناسي%' AND status = 'ناجح';

س: عدد المؤجلين حسب الشعبة
SQL: SELECT stream, COUNT(*) AS n FROM students WHERE status = 'مؤجل' GROUP BY stream ORDER BY n DESC;

س: الأوائل في مادة الرياضيات
SQL: SELECT s.name, s.stream, g.score FROM grades g JOIN students s ON g.registration_number = s.registration_number WHERE g.subject = 'الرياضيات' ORDER BY g.score DESC LIMIT 10;

س: معدل مادة الفلسفة في شعبة الآداب
SQL: SELECT ROUND(AVG(g.score),2) AS avg_score FROM grades g JOIN students s ON g.registration_number = s.registration_number WHERE g.subject = 'الفلسفة' AND s.stream = 'آداب';

س: التلاميذ بمعدل بين 12 و 14
SQL: SELECT name, stream, moyenne FROM students WHERE moyenne BETWEEN 12 AND 14 ORDER BY moyenne DESC;

س: التلاميذ فوق المعدل العام لشعبتهم
SQL: SELECT s.name, s.stream, s.total FROM students s WHERE s.total > (SELECT AVG(t.total) FROM students t WHERE t.stream = s.stream) ORDER BY s.total DESC;

س: أكبر ريمونتادا
SQL: SELECT name, stream, ROUND(total - moyenne, 2) AS gap FROM students ORDER BY gap DESC LIMIT 10;
"""


def scope_to_conditions(scope: dict) -> str:
    """Render an optional request scope as human-readable SQL conditions."""
    parts = []
    if scope.get("stream"):
        parts.append(f"- stream = '{scope['stream']}'")
    if scope.get("institution"):
        parts.append(f"- institution LIKE '%{scope['institution']}%'")
    if scope.get("passed") is not None:
        parts.append(f"- passed = {1 if scope['passed'] else 0}")
    if scope.get("min_bac") is not None:
        parts.append(f"- total >= {scope['min_bac']}")
    if scope.get("max_bac") is not None:
        parts.append(f"- total <= {scope['max_bac']}")
    if scope.get("min_annual") is not None:
        parts.append(f"- moyenne >= {scope['min_annual']}")
    if scope.get("max_annual") is not None:
        parts.append(f"- moyenne <= {scope['max_annual']}")
    return "\n".join(parts)


def build_system_prompt(conn: sqlite3.Connection, scope: dict | None = None) -> str:
    """Compose the system prompt with live distinct values for categoricals.

    If `scope` is given, its conditions are appended as mandatory constraints
    (soft enforcement — the model is instructed to add them to every WHERE).
    """
    streams = [r[0] for r in conn.execute(
        "SELECT DISTINCT stream FROM students ORDER BY stream")]
    mentions = [r[0] for r in conn.execute(
        "SELECT DISTINCT mention FROM students WHERE mention IS NOT NULL ORDER BY mention")]
    subjects = [r[0] for r in conn.execute(
        "SELECT DISTINCT subject FROM grades ORDER BY subject")]
    statuses = [r[0] for r in conn.execute(
        "SELECT DISTINCT status FROM students WHERE status IS NOT NULL ORDER BY status")]

    prompt = f"""\
أنت مساعد يحوّل أسئلة المستخدم إلى استعلام SQL لقاعدة بيانات SQLite لنتائج الباكالوريا.

المخطط (Schema):
students(registration_number INTEGER, id_number TEXT, name TEXT, institution TEXT,
         stream TEXT, result_raw TEXT,
         passed INTEGER /*1 إذا ناجح فقط*/,
         status TEXT /*ناجح أو مؤجل أو مرفوض*/,
         mention TEXT /*الملاحظة (حسن جدا/حسن/قريب من الحسن/متوسّط) للناجحين فقط، وإلا NULL*/,
         total REAL /*معدل الباكالوريا النهائي، من 20*/,
         moyenne REAL /*المعدل السنوي*/)
grades(registration_number INTEGER, subject TEXT, score REAL)
-- الربط: grades.registration_number = students.registration_number

قيم عمود stream الممكنة: {', '.join(streams)}
قيم عمود status الممكنة: {', '.join(statuses)}
قيم عمود mention الممكنة (للناجحين فقط): {', '.join(mentions)}
قيم عمود grades.subject الممكنة: {', '.join(subjects)}

{NOTES}
{GLOSSARY}
{EXAMPLES}

قواعد صارمة:
1. أرجع استعلام SELECT واحد فقط، دون أي شرح ودون فاصلة منقوطة متعددة.
2. لأسماء المؤسسات استعمل LIKE '%...%' لأن الكتابة قد تختلف.
3. عند طلب "الأوائل/الأفضل" استعمل ORDER BY ... DESC مع LIMIT.
4. لا تستعمل أي أمر تعديل (INSERT/UPDATE/DELETE/DROP...). القراءة فقط.
5. أرجع SQL فقط.
6. لا تُضِف أي شرط لم يُذكر في السؤال. خصوصًا: لا تَستعمل passed إطلاقًا إلا إذا ذكر المستخدم صراحةً النجاح أو الرسوب (ناجح/راسب/مرفوض/مؤجل). "أفضل معدل" لا يعني الناجحين فقط.
"""
    conditions = scope_to_conditions(scope or {})
    if conditions:
        prompt += (
            "\nقيود إجبارية: أضِف الشروط التالية في WHERE لكل استعلام "
            "ما لم يطلب المستخدم صراحةً خلاف ذلك:\n" + conditions + "\n"
        )
    return prompt


def validate_sql(sql: str) -> str:
    """Return a cleaned, safe single SELECT, or raise ValueError."""
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise ValueError("لم يُنتج النموذج أي استعلام.")
    if ";" in cleaned:
        raise ValueError("يُسمح باستعلام واحد فقط.")
    low = cleaned.lower()
    if not (low.startswith("select") or low.startswith("with")):
        raise ValueError("يُسمح باستعلامات SELECT فقط.")
    if FORBIDDEN.search(cleaned):
        raise ValueError("الاستعلام يحتوي على أمر غير مسموح به (تعديل بيانات).")
    # Enforce a row cap if the model didn't add one.
    if re.search(r"\blimit\b", low) is None:
        cleaned += " LIMIT 200"
    return cleaned


def run_query(sql: str, conn: sqlite3.Connection) -> tuple[list[str], list[dict]]:
    """Execute a validated SELECT on a read-only connection."""
    cur = conn.execute(sql)
    columns = [d[0] for d in cur.description] if cur.description else []
    rows = [dict(r) for r in cur.fetchall()]
    return columns, rows
