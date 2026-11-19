import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location(
    "auto_merge", pathlib.Path(__file__).resolve().parent.parent / "scripts" / "auto_merge.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

T0 = "2026-11-19T10:00:00Z"   # last commit
AFTER = "2026-11-19T11:00:00Z"
BEFORE = "2026-11-19T09:00:00Z"


def cfg(**kw):
    c = {"repo": "o/r", "default_branch": "main", "sensitive": m.parse_globs(".github/\nserver/**\n*.lock"),
         "ui": m.parse_globs("client/**"), "trusted": {"owner"}, "skip_labels": ["manuel"]}
    c.update(kw)
    return c


def pr(**kw):
    p = {"number": 1, "title": "fix: x", "draft": False, "base": "main", "head_repo": "o/r",
         "labels": [], "mergeable": True, "mergeable_state": "clean"}
    p.update(kw)
    return p


def com(body, at=AFTER, author="owner"):
    return {"author": author, "body": body, "created_at": at}


OK_REVIEW = com("Revue de code : OK\n\ndétails")
OK_QA = com("QA : OK")


class Globs(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(m.parse_globs("a/**\n\n# c\nb.json, c/  # x"), ["a/**", "b.json", "c/"])

    def test_match(self):
        g = m.parse_globs(".github/\nserver/**\n**/migrations/**\n*.lock\npackage.json")
        self.assertTrue(m.matches(".github/workflows/ci.yml", g))
        self.assertTrue(m.matches("server/src/db.ts", g))
        self.assertTrue(m.matches("apps/api/migrations/001.sql", g))
        self.assertTrue(m.matches("migrations/001.sql", g))
        self.assertTrue(m.matches("yarn.lock", g))
        self.assertTrue(m.matches("package.json", g))
        self.assertFalse(m.matches("client/src/App.tsx", g))
        self.assertFalse(m.matches("client/package.json.md", g))


class Verdict(unittest.TestCase):
    def test_latest_wins(self):
        cs = [com("Revue de code : OK", "2026-11-19T11:00:00Z"),
              com("Revue de code : CHANGEMENTS DEMANDÉS", "2026-11-19T12:00:00Z")]
        self.assertEqual(m.verdict(cs, "revue de code", {"owner"}, T0), "changes")
        cs.append(com("Revue de code : OK", "2026-11-19T13:00:00Z"))
        self.assertEqual(m.verdict(cs, "revue de code", {"owner"}, T0), "ok")

    def test_stale_after_new_commit(self):
        self.assertEqual(m.verdict([com("Revue de code : OK", BEFORE)], "revue de code", {"owner"}, T0), "stale")

    def test_untrusted_ignored(self):
        self.assertIsNone(m.verdict([com("Revue de code : OK", author="stranger")], "revue de code", {"owner"}, T0))

    def test_only_first_line_and_prefix(self):
        cs = [com("Merci !\nRevue de code : OK"), com("QA : OK")]
        self.assertIsNone(m.verdict(cs, "revue de code", {"owner"}, T0))
        self.assertEqual(m.verdict(cs, "qa", {"owner"}, T0), "ok")
        self.assertIsNone(m.verdict([com("Quality: OK")], "qa", {"owner"}, T0))

    def test_ok_with_reservation_text(self):
        # « OK sur le code. La fusion reste bloquée par la CI » : the verdict is OK, checks decide the rest
        self.assertEqual(m.verdict([com("Revue de code : OK sur le code. La CI est rouge.")], "revue de code", {"owner"}, T0), "ok")


class Checks(unittest.TestCase):
    def test_states(self):
        g = {"name": "ci", "status": "completed", "conclusion": "success"}
        self.assertEqual(m.checks_state([g], [], set()), "green")
        self.assertEqual(m.checks_state([], [], set()), "none")
        self.assertEqual(m.checks_state([g, {"name": "x", "status": "in_progress"}], [], set()), "pending")
        self.assertEqual(m.checks_state([g, {"name": "x", "status": "completed", "conclusion": "failure"}], [], set()), "red")
        self.assertEqual(m.checks_state([g, {"name": "auto-merge / merge", "status": "in_progress"}], [], {"auto-merge / merge"}), "green")
        self.assertEqual(m.checks_state([g], [{"state": "pending"}], set()), "pending")
        self.assertEqual(m.checks_state([g], [{"state": "failure"}], set()), "red")
        self.assertEqual(m.checks_state([g, {"name": "s", "status": "completed", "conclusion": "skipped"}], [], set()), "green")


class Decide(unittest.TestCase):
    def d(self, p=None, files=("src/a.ts",), comments=(OK_REVIEW,), checks="green", c=None):
        return m.decide(p or pr(), list(files), list(comments), T0, checks, c or cfg())

    def test_happy_path_backend(self):
        self.assertEqual(self.d(), (True, "all conditions met"))

    def test_ui_needs_qa(self):
        self.assertFalse(self.d(files=["client/src/App.tsx"])[0])
        self.assertTrue(self.d(files=["client/src/App.tsx"], comments=[OK_REVIEW, OK_QA])[0])

    def test_sensitive_blocks_even_with_everything_ok(self):
        ok, why = self.d(files=["src/a.ts", ".github/workflows/ci.yml"], comments=[OK_REVIEW, OK_QA])
        self.assertFalse(ok)
        self.assertIn("sensitive", why)

    def test_blockers(self):
        self.assertIn("draft", self.d(p=pr(draft=True))[1])
        self.assertIn("targets", self.d(p=pr(base="develop"))[1])
        self.assertIn("fork", self.d(p=pr(head_repo="evil/r"))[1])
        self.assertIn("label", self.d(p=pr(labels=["manuel"]))[1])
        self.assertIn("code review", self.d(comments=[])[1])
        self.assertIn("checks pending", self.d(checks="pending")[1])
        self.assertIn("checks none", self.d(checks="none")[1])
        self.assertIn("not mergeable", self.d(p=pr(mergeable=None))[1])
        self.assertIn("no file", self.d(files=[])[1])

    def test_review_older_than_last_commit(self):
        self.assertIn("stale", self.d(comments=[com("Revue de code : OK", BEFORE)])[1])


if __name__ == "__main__":
    unittest.main()
