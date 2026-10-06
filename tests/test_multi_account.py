import json
from pathlib import Path
import tempfile
import unittest
import uuid

import claude_sync as sync


class MultiAccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "registry"
        self.projects = self.base / "projects"
        self.projects.mkdir()

    def profile(self, account, organization="org"):
        path = self.root / account / organization
        path.mkdir(parents=True, exist_ok=True)
        return path

    def chat(self, profile, project="project", **fields):
        cli = str(uuid.uuid4())
        record = {"sessionId": "local_" + str(uuid.uuid4()), "cliSessionId": cli,
                  "cwd": str(self.base / "synthetic" / project), "lastActivityAt": 100,
                  "completedTurns": 3, "title": project, **fields}
        self.put(profile, record)
        directory = self.projects / project
        directory.mkdir(exist_ok=True)
        (directory / (cli + ".jsonl")).write_text(json.dumps({
            "type": "user", "sessionId": cli,
            "message": {"role": "user", "content": "Synthetic"}}) + "\n")
        return record

    def put(self, profile, record):
        (profile / (record["sessionId"] + ".json")).write_bytes(sync.json_bytes(record))

    def snapshot(self, directory):
        return {str(path.relative_to(directory)): path.read_bytes()
                for path in directory.rglob("*") if path.is_file()}

    def plan(self):
        return sync.build_plan(self.root, self.projects, resolve_conflicts=True, include_unavailable=True)

    def test_union_idempotence_and_exact_undo_with_3_5_and_12_accounts(self):
        for count in (3, 5, 12):
            with self.subTest(accounts=count):
                self.root = self.base / f"registry-{count}"
                profiles = [self.profile(f"account-{i}") for i in range(count)]
                records = [self.chat(profile, project=f"project-{count}-{i}",
                                    permissionMode="plan", isArchived=i % 2 == 0,
                                    remoteMcpServersConfig=[{"name": f"private-{i}"}])
                           for i, profile in enumerate(profiles)]
                before = self.snapshot(self.root)
                transcripts = self.snapshot(self.projects)
                plan = self.plan()
                self.assertEqual(plan["summary"]["accounts"], count)
                self.assertEqual(plan["summary"]["copies"], count * (count - 1))
                self.assertEqual(plan["summary"]["conflicts"], 0)
                backup = self.base / f"backup-{count}"
                sync.apply_plan(self.root, plan, backup)
                for owner, profile in enumerate(profiles):
                    self.assertEqual(len(list(profile.glob("local_*.json"))), count)
                    for source, record in enumerate(records):
                        imported = json.loads((profile / (record["sessionId"] + ".json")).read_bytes())
                        self.assertEqual(sync.portable_record(imported), sync.portable_record(record))
                        if source == owner:
                            self.assertEqual(imported["permissionMode"], "plan")
                        else:
                            self.assertEqual(imported["permissionMode"], "default")
                            self.assertNotIn("remoteMcpServersConfig", imported)
                self.assertEqual(self.plan()["changes"], [])
                self.assertEqual(self.snapshot(self.projects), transcripts)
                sync.undo(self.root, backup)
                self.assertEqual(self.snapshot(self.root), before)

    def test_new_account_is_detected_on_the_next_run(self):
        first = self.profile("a")
        self.profile("b")
        record = self.chat(first)
        sync.apply_plan(self.root, self.plan(), self.base / "first-backup")
        third = self.profile("c")
        plan = self.plan()
        self.assertEqual(plan["summary"]["accounts"], 3)
        self.assertEqual(plan["summary"]["copies"], 1)
        sync.apply_plan(self.root, plan, self.base / "third-backup")
        self.assertEqual(json.loads((third / (record["sessionId"] + ".json")).read_bytes())["title"], "project")
        self.assertEqual(self.plan()["changes"], [])

    def test_two_identical_newest_copies_update_the_third(self):
        a, b, c = [self.profile(name) for name in ("a", "b", "c")]
        record = self.chat(b)
        self.put(c, {**record, "permissionMode": "auto"})
        self.put(a, {**record, "lastActivityAt": 50, "completedTurns": 1,
                     "permissionMode": "plan", "remoteMcpServersConfig": [{"name": "keep"}]})
        plan = self.plan()
        self.assertEqual(plan["summary"]["conflicts"], 0)
        self.assertEqual(plan["summary"]["updates"], 1)
        sync.apply_plan(self.root, plan, self.base / "backup")
        updated = json.loads((a / (record["sessionId"] + ".json")).read_bytes())
        self.assertEqual(updated["completedTurns"], 3)
        self.assertEqual(updated["permissionMode"], "plan")
        self.assertEqual(updated["remoteMcpServersConfig"], [{"name": "keep"}])
        self.assertEqual(self.plan()["changes"], [])

    def test_disagreeing_newest_copies_remain_pending_for_all_accounts(self):
        a, b, c, d = [self.profile(name) for name in ("a", "b", "c", "d")]
        record = self.chat(a)
        self.put(b, {**record, "title": "Different at the same time"})
        self.put(c, {**record, "lastActivityAt": 50})
        plan = self.plan()
        self.assertEqual(plan["summary"]["conflicts"], 1)
        self.assertEqual(plan["changes"], [])
        self.assertFalse((d / (record["sessionId"] + ".json")).exists())

    def test_account_count_does_not_count_organizations_as_accounts(self):
        a = self.profile("a", "org-one")
        self.profile("a", "org-two")
        self.profile("b", "org-one")
        self.chat(a)
        plan = self.plan()
        self.assertEqual(plan["summary"]["accounts"], 2)
        self.assertEqual(plan["summary"]["profiles"], 3)
        self.assertEqual(plan["summary"]["copies"], 2)

    def test_chat_created_in_a_different_account_reaches_every_account(self):
        profiles = [self.profile(f"account-{i}") for i in range(5)]
        self.chat(profiles[0])
        sync.apply_plan(self.root, self.plan(), self.base / "first-backup")
        later = self.chat(profiles[-1], project="another-project", lastActivityAt=200)
        plan = self.plan()
        self.assertEqual(plan["summary"]["copies"], 4)
        sync.apply_plan(self.root, plan, self.base / "second-backup")
        for profile in profiles:
            self.assertTrue((profile / (later["sessionId"] + ".json")).exists())
        self.assertEqual(self.plan()["changes"], [])


if __name__ == "__main__":
    unittest.main()
