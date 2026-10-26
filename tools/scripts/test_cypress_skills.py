"""Check the vendored Cypress skills, retained references and native client entry points."""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class TestCypressSkills(unittest.TestCase):
    def test_pinned_skills_keep_their_versions_and_mit_license(self):
        manifest = json.loads((ROOT / ".agent/cypress-skills.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["repository"], "https://github.com/cypress-io/ai-toolkit")
        self.assertRegex(manifest["revision"], r"^[a-f0-9]{40}$")
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(
            set(manifest["skills"]),
            {"cypress-author", "cypress-explain", "cypress-docs", "cypress-tap"},
        )
        for name, version in manifest["skills"].items():
            with self.subTest(name=name):
                source = ROOT / ".agent/skills" / name
                skill = (source / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn(f"name: {name}", skill)
                self.assertRegex(skill, rf"(?m)^  version: {re.escape(version)}$")
                license_text = (source / "LICENSE").read_text(encoding="utf-8")
                self.assertIn("MIT License", license_text)
                self.assertIn("Permission is hereby granted", license_text)
                self.assertIn("Copyright (c) 2026 Cypress.io", license_text)

    def test_codex_cursor_and_claude_entry_points_reach_the_canonical_skill(self):
        manifest = json.loads((ROOT / ".agent/cypress-skills.json").read_text(encoding="utf-8"))
        for client in (".agents", ".claude"):
            for name in manifest["skills"]:
                with self.subTest(client=client, name=name):
                    wrapper = ROOT / client / "skills" / name / "SKILL.md"
                    text = wrapper.read_text(encoding="utf-8")
                    self.assertIn(f"name: {name}", text)
                    targets = re.findall(r"\]\(([^)]+)\)", text)
                    self.assertEqual(len(targets), 2)
                    for target in targets:
                        self.assertTrue((wrapper.parent / target).resolve().is_file(), target)
                    self.assertIn(f"../../../.agent/skills/{name}/SKILL.md", text)

    def test_tap_and_author_keep_their_linked_reference_files(self):
        for name in ("cypress-tap", "cypress-author"):
            skill = ROOT / ".agent/skills" / name / "SKILL.md"
            text = skill.read_text(encoding="utf-8")
            for target in re.findall(r"\]\(([^)]+\.md)\)", text):
                with self.subTest(skill=name, target=target):
                    self.assertTrue((skill.parent / target).resolve().is_file(), target)


if __name__ == "__main__":
    unittest.main()
