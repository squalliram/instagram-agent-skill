import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILLS = Path(__file__).resolve().parent.parent / "skills"
for folder in ("ig-human", "ig-viral", "ig-reel", "ig-caption"):
    sys.path.insert(0, str(SKILLS / folder))

import caption  # noqa: E402
import detect  # noqa: E402
import hookscore  # noqa: E402
import swipe  # noqa: E402

LEXICON = json.loads((SKILLS / "ig-human" / "slop.json").read_text(encoding="utf-8"))


class DetectTests(unittest.TestCase):
    def test_short_reply_is_judged_on_the_checks_that_can_run(self):
        results, overall, verdict = detect.run("Ha, that's my exact Tuesday. Stealing the 4pm trick.", LEXICON)
        self.assertIsNone(results["BURSTINESS"][0])
        self.assertIsNone(results["SPECIFICITY"][0])
        self.assertIsNone(results["VOICE"][0])
        self.assertEqual(verdict, "PASS")
        self.assertGreaterEqual(overall, 70)

    def test_short_slop_still_fails(self):
        _, _, verdict = detect.run("Unlock the power of seamless synergy — delve in!", LEXICON)
        self.assertNotEqual(verdict, "PASS")

    def test_render_and_json_survive_unscored_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft = Path(tmp, "reply.txt")
            draft.write_text("Love this, saving it.", encoding="utf-8")
            out = io.StringIO()
            with mock.patch.object(sys, "argv", ["detect.py", str(draft), "--json"]):
                with contextlib.redirect_stdout(out):
                    detect.main()
            self.assertIsNone(json.loads(out.getvalue())["checks"]["BURSTINESS"]["score"])
            with mock.patch.object(sys, "argv", ["detect.py", str(draft)]):
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                    detect.main()


class SwipeTests(unittest.TestCase):
    def test_counts_keep_their_k_and_m_scale(self):
        self.assertEqual(swipe.parse_count("1.2M"), 1_200_000)
        self.assertEqual(swipe.parse_count("11K"), 11_000)
        self.assertEqual(swipe.parse_count("412,000"), 412_000)
        self.assertEqual(swipe.parse_count("48k followers"), 48_000)
        self.assertIsNone(swipe.parse_count(""))

    def test_outlier_uses_scaled_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            tsv = Path(tmp, "captured.tsv")
            tsv.write_text("account\tfollowers\tmedian\tviews\thook\n@a\t48K\t11K\t1.2M\tnobody tells you this\n",
                           encoding="utf-8")
            rows = swipe.read_rows(str(tsv))
        self.assertEqual(swipe.analyse(rows, None)["reels"][0]["outlier"], 109.09)

    def test_bare_out_filename_writes_in_the_current_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            tsv = Path(tmp, "captured.tsv")
            tsv.write_text("account\tmedian\tviews\thook\n@a\t1000\t5000\tstop pricing by the hour\n",
                           encoding="utf-8")
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with mock.patch.object(sys, "argv", ["swipe.py", str(tsv), "--out", "swipe.md"]):
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        swipe.main()
            finally:
                os.chdir(cwd)
            self.assertTrue(Path(tmp, "swipe.md").is_file())


class HookscoreTests(unittest.TestCase):
    def test_proper_name_counts_as_payload(self):
        _, detail = hookscore.check_frontload("I use Acme for proposals")
        self.assertIn("payload at word 3", detail)

    def test_words_that_start_with_a_weak_opener_are_not_penalised(self):
        for hook in ("Higher prices lost me two clients", "Hire slow, fire fast", "Sorry, I lied about rent"):
            _, detail = hookscore.check_frontload(hook)
            self.assertNotIn("weak opener", detail, hook)

    def test_real_weak_openers_are_still_penalised(self):
        for hook in ("Hi guys, quick tip", "So today I lost $400", "Let's talk rent"):
            _, detail = hookscore.check_frontload(hook)
            self.assertIn("weak opener", detail, hook)


class CaptionTests(unittest.TestCase):
    def test_non_ascii_hashtags_count_toward_the_limit(self):
        text = "Ramen night.\n\n#ラーメン #東京グルメ #麺スタグラム #café #食べ歩き #グルメ"
        self.assertEqual(len(caption.HASHTAG_RE.findall(text)), 6)


if __name__ == "__main__":
    unittest.main()
