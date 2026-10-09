"""
SQL Answer Quality Judge.
Uses LLM to evaluate whether SQL answers
the actual question asked.
src/agents/judge_agent.py
"""

import os
import sqlite3
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

try:
    import streamlit as st
    GROQ_KEY = st.secrets.get("GROQ_API_KEY","")
except Exception:
    GROQ_KEY = ""
if not GROQ_KEY:
    GROQ_KEY = os.getenv("GROQ_API_KEY","")

MODEL   = "qwen/qwen3.8-27b"
DB_PATH = "data/processed/skdata.db"

log = logging.getLogger("JudgeAgent")

JUDGE_PROMPT = """You are a financial data QA judge.
Evaluate whether the SQL query correctly answers
the user question.

Score from 0.0 to 1.0:
  1.0 = Perfect — SQL directly answers the question
  0.8 = Good — answers the question with minor issues
  0.6 = Partial — answers part of the question
  0.4 = Poor — SQL is related but misses the point
  0.2 = Bad — SQL does not answer the question
  0.0 = Wrong — SQL answers a different question

Return ONLY a JSON object like this:
{
  "score": 0.9,
  "reason": "SQL correctly filters by sector and P/E ratio",
  "issues": ["Missing ORDER BY for ranking"],
  "verdict": "PASS"
}

verdict must be PASS (score>=0.7) or FAIL (score<0.7)"""


class JudgeAgent:
    """
    Evaluates SQL answer quality.
    Grades whether generated SQL answers
    the actual question asked.
    """

    def __init__(self):
        self.client    = None
        self.eval_log  = []

        if not GROQ_KEY:
            log.warning("GROQ_API_KEY not set")
            return

        try:
            from groq import Groq
            self.client = Groq(api_key=GROQ_KEY)
            log.info("Judge Agent initialised")
        except Exception as e:
            log.error(f"Init failed: {e}")

    def evaluate(
        self,
        question: str,
        sql:      str,
        columns:  list,
        rows:     list,
        latency:  int = 0,
    ) -> dict:
        """
        Evaluate SQL answer quality.
        Returns score, reason, verdict.
        """
        if not self.client:
            return self._heuristic_eval(
                question, sql, columns, rows
            )

        # Build context for judge
        result_preview = ""
        if rows:
            result_preview = (
                f"Result: {len(rows)} rows, "
                f"columns: {columns}\n"
                f"First row: {rows[0]}"
            )
        else:
            result_preview = "Result: 0 rows returned"

        user_prompt = (
            f"Question: {question}\n\n"
            f"SQL Generated:\n{sql}\n\n"
            f"{result_preview}\n\n"
            f"Does this SQL correctly answer "
            f"the question? Score 0.0-1.0."
        )

        try:
            r = self.client.chat.completions.create(
                model    = MODEL,
                messages = [
                    {
                        "role":    "system",
                        "content": JUDGE_PROMPT
                    },
                    {
                        "role":    "user",
                        "content": user_prompt
                    }
                ],
                temperature = 0.0,
                max_tokens  = 300,
            )

            content   = getattr(
                r.choices[0].message,"content",""
            ) or ""
            reasoning = getattr(
                r.choices[0].message,"reasoning",""
            ) or ""

            for text in [content, reasoning]:
                if text and "{" in text:
                    result = self._parse_json(text)
                    if result:
                        result["question"] = question
                        result["latency"]  = latency
                        self._log_eval(result)
                        return result

        except Exception as e:
            log.error(f"Judge eval error: {e}")

        return self._heuristic_eval(
            question, sql, columns, rows
        )

    def _parse_json(self, text: str) -> dict:
        """Extract JSON from LLM response."""
        import re, json
        match = re.search(
            r'\{[^{}]+\}', text, re.DOTALL
        )
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {}

    def _heuristic_eval(
        self,
        question: str,
        sql:      str,
        columns:  list,
        rows:     list,
    ) -> dict:
        """
        Fallback heuristic evaluation
        when LLM is unavailable.
        """
        score   = 0.5
        issues  = []
        sql_up  = sql.upper()
        q_lower = question.lower()

        # Check: results returned
        if not rows:
            score  -= 0.3
            issues.append("No rows returned")

        # Check: LIMIT present
        if "LIMIT" not in sql_up:
            score  -= 0.1
            issues.append("No LIMIT clause")

        # Check: ranking questions have ORDER BY
        rank_words = ["top","best","highest","lowest",
                      "most","least","ranked"]
        if any(w in q_lower for w in rank_words):
            if "ORDER BY" not in sql_up:
                score  -= 0.2
                issues.append(
                    "Ranking question missing ORDER BY"
                )

        # Check: comparison has multiple rows
        compare_words = ["compare","vs","versus",
                         "difference"]
        if any(w in q_lower for w in compare_words):
            if rows and len(rows) < 2:
                score  -= 0.2
                issues.append(
                    "Comparison returned only 1 row"
                )

        # Check: country filter for UAE questions
        if "uae" in q_lower or "dubai" in q_lower \
                or "abu dhabi" in q_lower:
            if "UAE" not in sql_up and \
                    "DFM" not in sql_up and \
                    "ADX" not in sql_up:
                score  -= 0.3
                issues.append("UAE filter missing")

        score   = max(0.0, min(1.0, score))
        verdict = "PASS" if score >= 0.7 else "FAIL"

        return {
            "score":    round(score, 2),
            "reason":   "Heuristic evaluation",
            "issues":   issues,
            "verdict":  verdict,
            "question": question,
            "method":   "heuristic",
        }

    def _log_eval(self, result: dict):
        """Store evaluation in database."""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS eval_log (
                    id       INTEGER PRIMARY KEY,
                    run_at   TEXT,
                    question TEXT,
                    score    REAL,
                    verdict  TEXT,
                    reason   TEXT,
                    issues   TEXT,
                    latency  INTEGER
                )
            """)
            conn.execute("""
                INSERT INTO eval_log
                (run_at, question, score,
                 verdict, reason, issues, latency)
                VALUES (?,?,?,?,?,?,?)
            """, (
                datetime.now().isoformat(),
                result.get("question",""),
                result.get("score", 0),
                result.get("verdict",""),
                result.get("reason",""),
                str(result.get("issues",[])),
                result.get("latency", 0),
            ))
            conn.commit()
            conn.close()
            self.eval_log.append(result)
        except Exception:
            pass

    def get_stats(self) -> dict:
        """Get evaluation statistics."""
        try:
            conn = sqlite3.connect(DB_PATH)
            rows = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    ROUND(AVG(score),3) as avg_score,
                    SUM(CASE WHEN verdict='PASS'
                        THEN 1 ELSE 0 END) as passes,
                    SUM(CASE WHEN verdict='FAIL'
                        THEN 1 ELSE 0 END) as fails,
                    MIN(score) as min_score,
                    MAX(score) as max_score
                FROM eval_log
            """).fetchone()
            conn.close()

            if rows and rows[0]:
                return {
                    "total":     rows[0],
                    "avg_score": rows[1],
                    "passes":    rows[2],
                    "fails":     rows[3],
                    "min_score": rows[4],
                    "max_score": rows[5],
                    "pass_rate": round(
                        rows[2]/rows[0]*100
                    ) if rows[0] else 0,
                }
        except Exception:
            pass
        return {}

    def get_recent_evals(
        self, limit: int = 20
    ) -> list:
        """Get recent evaluations for dashboard."""
        try:
            conn = sqlite3.connect(DB_PATH)
            rows = conn.execute("""
                SELECT run_at, question, score,
                       verdict, reason
                FROM eval_log
                ORDER BY id DESC
                LIMIT ?
            """, (limit,)).fetchall()
            conn.close()
            return [
                {
                    "time":     r[0][:16],
                    "question": r[1][:60],
                    "score":    r[2],
                    "verdict":  r[3],
                    "reason":   r[4],
                }
                for r in rows
            ]
        except Exception:
            return []


if __name__ == "__main__":
    judge = JudgeAgent()

    tests = [
        {
            "question": "Top 10 S&P 500 by market cap",
            "sql": """SELECT c.ticker, c.name,
                      m.market_cap FROM companies c
                      JOIN metrics m ON c.ticker=m.ticker
                      WHERE c.market='SP500'
                      ORDER BY m.market_cap DESC
                      LIMIT 10""",
            "columns": ["ticker","name","market_cap"],
            "rows":    [["NVDA","NVIDIA",5e12]]*10,
        },
        {
            "question": "UAE banks ROE",
            "sql": """SELECT c.ticker, m.roe
                      FROM companies c
                      JOIN metrics m ON c.ticker=m.ticker
                      WHERE c.sector='Technology'
                      LIMIT 10""",
            "columns": ["ticker","roe"],
            "rows":    [["NVDA",0.85]]*5,
        },
    ]

    for t in tests:
        result = judge.evaluate(
            t["question"], t["sql"],
            t["columns"], t["rows"]
        )
        print(f"Q: {t['question']}")
        print(f"Score:   {result['score']}")
        print(f"Verdict: {result['verdict']}")
        print(f"Reason:  {result['reason']}")
        if result.get("issues"):
            print(f"Issues:  {result['issues']}")
        print()