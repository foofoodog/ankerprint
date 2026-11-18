"""Unit and integration tests for ankerprint CLI."""

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import ankerprint

class TestAnkerprintCLI(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_cli_help(self):
        result = self.runner.invoke(ankerprint.cli, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("AnkerPrint - Lean, zero-server CLI", result.output)
        self.assertIn("scan", result.output)
        self.assertIn("print", result.output)
        self.assertIn("gcode", result.output)
        self.assertIn("ble", result.output)

    def test_gcode_help(self):
        result = self.runner.invoke(ankerprint.cli, ["gcode", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--home", result.output)
        self.assertIn("--home-xy", result.output)
        self.assertIn("--home-z", result.output)
        self.assertIn("--level", result.output)
        self.assertIn("--motors-off", result.output)
        self.assertIn("-n, --no-act", result.output)

    def test_gcode_no_args_shows_guidance(self):
        result = self.runner.invoke(ankerprint.cli, ["gcode"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No G-code command provided", result.output)

    @patch("ankerprint.stream_gcode_to_printer")
    @patch("ankerprint.config.load_printers")
    def test_gcode_home_flag(self, mock_load_printers, mock_stream):
        mock_load_printers.return_value = [
            {"name": "AnkerMake", "duid": "TEST-DUID-1234", "ip": "192.168.1.100"}
        ]
        result = self.runner.invoke(ankerprint.cli, ["gcode", "--home", "-n"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Executing G-code: G28", result.output)
        mock_stream.assert_called_once()
        args, kwargs = mock_stream.call_args
        self.assertEqual(args[0], "192.168.1.100")
        self.assertEqual(args[1], "TEST-DUID-1234")
        self.assertIn(b"G28", args[2])
        self.assertTrue(kwargs.get("no_act"))

    @patch("ankerprint.stream_gcode_to_printer")
    @patch("ankerprint.config.load_printers")
    def test_gcode_multiple_shortcuts_and_custom(self, mock_load_printers, mock_stream):
        mock_load_printers.return_value = [
            {"name": "AnkerMake", "duid": "TEST-DUID-1234", "ip": "192.168.1.100"}
        ]
        result = self.runner.invoke(
            ankerprint.cli,
            ["gcode", "--home", "--level", "M104 S200", "M140 S60", "-n"]
        )
        self.assertEqual(result.exit_code, 0)
        mock_stream.assert_called_once()
        gcode_bytes = mock_stream.call_args[0][2]
        decoded = gcode_bytes.decode("utf-8")
        self.assertIn("G28", decoded)
        self.assertIn("G29", decoded)
        self.assertIn("M104 S200", decoded)
        self.assertIn("M140 S60", decoded)

    @patch("ankerprint.stream_gcode_to_printer")
    @patch("ankerprint.config.load_printers")
    def test_gcode_stdin(self, mock_load_printers, mock_stream):
        mock_load_printers.return_value = [
            {"name": "AnkerMake", "duid": "TEST-DUID-1234", "ip": "192.168.1.100"}
        ]
        result = self.runner.invoke(
            ankerprint.cli,
            ["gcode", "-", "-n"],
            input="G28 X Y\nG1 X100 Y100 F3000\n"
        )
        self.assertEqual(result.exit_code, 0)
        mock_stream.assert_called_once()
        decoded = mock_stream.call_args[0][2].decode("utf-8")
        self.assertIn("G28 X Y", decoded)
        self.assertIn("G1 X100 Y100 F3000", decoded)

    @patch("ankerprint.config.load_printers")
    def test_scan_command_outputs_cache(self, mock_load_printers):
        mock_load_printers.return_value = [
            {"name": "AnkerMake", "duid": "TEST-DUID-5678", "ip": "192.168.1.50"}
        ]
        # Test scan help and invocation
        result = self.runner.invoke(ankerprint.cli, ["scan", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Scan local network", result.output)

    @patch("ankerprint.stream_gcode_to_printer")
    @patch("ankerprint.config.load_printers")
    def test_print_dry_run(self, mock_load_printers, mock_stream):
        mock_load_printers.return_value = [
            {"name": "AnkerMake", "duid": "TEST-DUID-1234", "ip": "192.168.1.100"}
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.gcode")
            with open(file_path, "w") as f:
                f.write(";TIME:60\nG28\nG1 Z10\n")
            result = self.runner.invoke(ankerprint.cli, ["print", file_path, "-n"])
            self.assertEqual(result.exit_code, 0)
            mock_stream.assert_called_once()
            self.assertTrue(mock_stream.call_args[1].get("no_act"))

if __name__ == "__main__":
    unittest.main()
