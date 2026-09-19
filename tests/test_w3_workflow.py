"""W3 entry-point and output protection regressions using disposable fixtures.

No test writes to the project's real data/raw or delivery directories. Link
tests use a temporary sentinel file and only call preflight validation.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_week3 as cli
from src.data.clean import TelcoCleaner, load_config
from src.data import w3_workflow as workflow
from test_w3_cleaning import raw_fixture


class WorkflowOutputProtectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="w3-path-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "project"
        self.raw_dir = self.root / "data/raw"
        self.raw_dir.mkdir(parents=True)
        self.source = self.raw_dir / "sentinel.csv"
        self.source.write_bytes(b"synthetic source - must never change\n")
        self.before = self.source.read_bytes()
        self.output = self.root / "data/processed/w3"
        self.models = self.root / "models/w3"
        self.reports = self.root / "reports"

    def symlink(self, link: Path, target: Path, is_directory=False):
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            link.symlink_to(target, target_is_directory=is_directory)
        except (OSError, NotImplementedError) as error:
            if os.name == "nt" and is_directory:
                # Windows directory junctions exercise the same resolve-based
                # redirect protection without requiring symlink privileges.
                import _winapi
                try:
                    _winapi.CreateJunction(str(target), str(link))
                    return
                except OSError:
                    pass
            self.skipTest(f"Temporary file symlink unavailable (OS error {getattr(error, 'winerror', None)}); directory redirects and hard links are tested separately")

    def assert_preflight_rejects_before_any_read_or_write(self):
        with patch.object(workflow, "PROJECT_ROOT", self.root), \
             patch.object(workflow, "digest") as read_digest, \
             patch.object(workflow, "dump_csv") as write_csv:
            with self.assertRaises(ValueError):
                workflow.run_workflow(load_config(), self.source, self.output, self.models, self.reports)
            read_digest.assert_not_called()
            write_csv.assert_not_called()
        self.assertEqual(self.source.read_bytes(), self.before)
        self.assertFalse(self.models.exists())

    def test_new_and_existing_regular_output_files_are_validated_without_mutation(self):
        self.output.mkdir(parents=True)
        existing = self.output / "telco_clean.csv"
        existing.write_bytes(b"previous generated output\n")
        new_target = self.output / "new.csv"
        workflow.validate_output_targets(self.output, [existing, new_target])
        self.assertEqual(existing.read_bytes(), b"previous generated output\n")
        self.assertFalse(new_target.exists())
        self.assertEqual(self.source.read_bytes(), self.before)

    def test_existing_output_file_symlink_to_raw_is_rejected_before_workflow_runs(self):
        self.symlink(self.output / "telco_clean.csv", self.source)
        self.assert_preflight_rejects_before_any_read_or_write()

    def test_reports_tables_directory_link_to_raw_is_rejected_before_workflow_runs(self):
        self.symlink(self.reports / "tables", self.raw_dir, is_directory=True)
        self.assert_preflight_rejects_before_any_read_or_write()

    def test_redirected_output_root_is_rejected(self):
        self.symlink(self.output, self.raw_dir, is_directory=True)
        with self.assertRaises(ValueError):
            workflow.validate_output_targets(self.output, [self.output / "new.csv"])
        self.assertEqual(self.source.read_bytes(), self.before)
        self.assertFalse((self.raw_dir / "new.csv").exists())

    def test_directory_at_an_output_filename_is_rejected_before_workflow_runs(self):
        (self.output / "telco_clean.csv").mkdir(parents=True)
        self.assert_preflight_rejects_before_any_read_or_write()

    def test_output_target_traversal_cannot_escape_its_directory(self):
        with self.assertRaises(ValueError):
            workflow.validate_output_targets(self.output, [self.output / "../../raw/sentinel.csv"])
        self.assertEqual(self.source.read_bytes(), self.before)

    def test_hard_link_to_raw_is_rejected_before_workflow_runs(self):
        self.output.mkdir(parents=True)
        try:
            os.link(self.source, self.output / "telco_clean.csv")
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"This system cannot create the temporary hard link: {error}")
        self.assert_preflight_rejects_before_any_read_or_write()

    def test_external_input_is_rejected_before_any_workflow_io(self):
        outside = Path(self.temporary.name).resolve() / "outside.csv"
        outside.write_bytes(self.before)
        with patch.object(workflow, "PROJECT_ROOT", self.root), \
             patch.object(workflow, "digest") as read_digest:
            with self.assertRaisesRegex(ValueError, "inside the project"):
                workflow.run_workflow(load_config(), outside, self.output, self.models, self.reports)
            read_digest.assert_not_called()
        self.assertEqual(outside.read_bytes(), self.before)
        self.assertFalse(self.output.exists())

    def test_cli_rejects_unsafe_destinations_overlap_and_external_input_before_dispatch(self):
        variants = [
            ["--output-dir", "data/raw"],
            ["--model-dir", "src/data"],
            ["--reports-dir", "../outside"],
            ["--output-dir", ".cache/run", "--model-dir", ".cache/run/models"],
            ["--output-dir", ".cache/shared", "--reports-dir", ".cache/shared"],
            ["--input", str(Path(self.temporary.name).resolve() / "outside.csv")],
            ["--input", "data/processed/w3/input.csv"],
        ]
        for arguments in variants:
            with self.subTest(arguments=arguments):
                with patch.object(cli, "ROOT", self.root), \
                     patch.object(cli, "load_config", return_value=load_config()), \
                     patch.object(cli, "run_workflow") as dispatched, \
                     patch("sys.argv", ["run_week3.py", "--skip-notebook", *arguments]):
                    with self.assertRaises(ValueError):
                        cli.main()
                    dispatched.assert_not_called()
                self.assertEqual(self.source.read_bytes(), self.before)
                self.assertFalse(self.output.exists())
                self.assertFalse(self.models.exists())
                self.assertFalse(self.reports.exists())

    def test_cli_resolves_relative_paths_from_project_and_rejects_raw_redirect(self):
        with patch.object(cli, "ROOT", self.root):
            self.assertEqual(cli.resolve_path("configs/w3_cleaning.json"), self.root / "configs/w3_cleaning.json")
            self.assertEqual(cli.destination("data/processed/w3", "data"), self.output)
            self.symlink(self.output, self.raw_dir, is_directory=True)
            with self.assertRaises(ValueError):
                cli.destination("data/processed/w3", "data")
        self.assertEqual(self.source.read_bytes(), self.before)


class WorkflowQualityEvidenceTests(unittest.TestCase):
    def test_optional_lower_bound_and_configured_upper_bound_have_correct_audit_entries(self):
        config = load_config()
        config["numeric_rules"]["TotalCharges"]["minimum"] = None
        config["numeric_rules"]["MonthlyCharges"]["maximum"] = 100
        raw = raw_fixture()
        cleaned = TelcoCleaner(config).fit_transform(raw)
        _, _, evidence = workflow.quality_tables(raw, cleaned, config)
        indexed = evidence.set_index("rule")
        self.assertNotIn("below_minimum_TotalCharges", indexed.index)
        self.assertEqual(indexed.at["above_maximum_MonthlyCharges", "count"], 0)
        self.assertEqual(indexed.at["noninteger_tenure", "count"], 0)
        self.assertEqual(indexed.at["noninteger_SeniorCitizen", "count"], 0)
        self.assertEqual(indexed.at["missing_TotalCharges", "status"], "documented")


if __name__ == "__main__":
    unittest.main()
