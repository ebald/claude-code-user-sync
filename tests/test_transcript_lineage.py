import json
from pathlib import Path
import tempfile
import unittest
import uuid

import claude_sync as sync


class TranscriptLineageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.sid = str(uuid.uuid4())
        self.ancestor = str(uuid.uuid4())
        self.path = self.base / (self.sid + ".jsonl")

    def message(self, sid, parent=None, **fields):
        return {"type": "assistant", "sessionId": sid, "uuid": str(uuid.uuid4()),
                "parentUuid": parent, "message": {"role": "assistant", "content": "Synthetic"}, **fields}

    def put(self, messages):
        self.path.write_text("".join(json.dumps(message) + "\n" for message in messages))

    def test_connected_inherited_prefix_is_readable_without_modifying_history(self):
        ancestor = self.message(self.ancestor)
        first = self.message(self.sid, ancestor["uuid"])
        self.put([ancestor, first, self.message(self.sid, first["uuid"])])
        before = self.path.read_bytes()
        self.assertTrue(sync.valid_transcript(self.path))
        self.assertEqual(self.path.read_bytes(), before)

    def test_unrelated_foreign_prefix_is_not_claimed_readable(self):
        self.put([self.message(self.ancestor), self.message(self.sid)])
        self.assertFalse(sync.valid_transcript(self.path))

    def test_foreign_suffix_is_rejected(self):
        main = self.message(self.sid)
        self.put([main, self.message(self.ancestor, main["uuid"])])
        self.assertFalse(sync.valid_transcript(self.path))

    def test_wholly_foreign_session_is_rejected(self):
        self.put([self.message(self.ancestor)])
        self.assertFalse(sync.valid_transcript(self.path))

    def test_invalid_ancestor_uuid_and_malformed_json_are_rejected(self):
        ancestor = self.message(self.ancestor, uuid="not-a-uuid")
        self.put([ancestor, self.message(self.sid, ancestor["uuid"])])
        self.assertFalse(sync.valid_transcript(self.path))
        self.put([self.message(self.sid)])
        with self.path.open("a") as stream:
            stream.write("not JSON\n")
        self.assertFalse(sync.valid_transcript(self.path))

    def test_known_readable_history_clears_stale_unavailable_hints_on_all_profiles(self):
        root = self.base / "registry"
        project = self.base / "projects/project"
        project.mkdir(parents=True)
        self.path = project / (self.sid + ".jsonl")
        ancestor = self.message(self.ancestor)
        self.put([ancestor, self.message(self.sid, ancestor["uuid"])])
        record = {"sessionId": "local_" + str(uuid.uuid4()), "cliSessionId": self.sid,
                  "cwd": str(self.base / "synthetic/work"), "title": "Synthetic", "lastActivityAt": 100,
                  "transcriptUnavailable": True, "permissionMode": "plan"}
        profiles = [root / account / "org" for account in ("a", "b", "c")]
        for profile in profiles:
            profile.mkdir(parents=True)
            (profile / (record["sessionId"] + ".json")).write_bytes(sync.json_bytes(record))
        transcript_before = self.path.read_bytes()
        plan = sync.build_plan(root, project.parent, resolve_conflicts=True, include_unavailable=True)
        self.assertEqual(plan["summary"]["missing_transcripts"], 0)
        self.assertEqual(plan["summary"]["updates"], 3)
        sync.apply_plan(root, plan, self.base / "backup")
        for profile in profiles:
            actual = json.loads((profile / (record["sessionId"] + ".json")).read_bytes())
            self.assertNotIn("transcriptUnavailable", actual)
            self.assertEqual(actual["permissionMode"], "plan")
        self.assertEqual(self.path.read_bytes(), transcript_before)
        self.assertEqual(sync.build_plan(root, project.parent, resolve_conflicts=True, include_unavailable=True)["changes"], [])
        sync.undo(root, self.base / "backup")
        for profile in profiles:
            actual = json.loads((profile / (record["sessionId"] + ".json")).read_bytes())
            self.assertEqual(actual, record)


if __name__ == "__main__":
    unittest.main()
