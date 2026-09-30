"""WhatsApp intake: bounded read receipts, changed demand, media lineage and sharing boundaries."""

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]


def load_script(skill, name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "skills" / skill / "scripts" / f"{name}.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


intake = load_script("whatsapp-rfq", "prepare_rfq")
rfq = load_script("supplier-rfq", "build_supplier_rfq")


class WhatsAppRFQ(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name)
        self.data = json.loads((ROOT / "examples/whatsapp-rfq.json").read_text(encoding="utf-8"))

    def tearDown(self):
        self.temporary.cleanup()

    def run_packet(self, data=None, name="packet"):
        return intake.prepare(data or self.data, self.folder / name, ROOT / "examples")

    def test_changed_quantity_image_and_excluded_pending_and_withdrawn(self):
        result = self.run_packet()
        self.assertEqual((result["ready"], result["pending"], result["withdrawn"]), (1, 1, 1))
        self.assertFalse(result["sent"])
        packet = self.folder / "packet"
        public = json.loads((packet / "supplier-rfq.json").read_text(encoding="utf-8"))
        self.assertEqual(public["items"][0]["quantity"], "4")
        self.assertEqual(len(public["items"]), 1)
        visible = json.dumps(public)
        self.assertNotIn("demo-buyer@lid", visible)
        self.assertNotIn("DEMO-IMG-01", visible)
        self.assertNotIn("evidence", visible)
        self.assertNotIn("source_text", visible)
        output = packet / "supplier-rfq.xlsx"
        self.assertEqual(rfq.build(public, output, packet)["images"], 1)
        book = load_workbook(output)
        self.assertEqual(book.active["E7"].value, 4)
        self.assertEqual(book.active._images[0].anchor._from.row, 6)
        book.close()
        summary = json.loads((packet / "pending.json").read_text(encoding="utf-8"))
        self.assertIn("数量", summary["pending"][0]["missing"])
        self.assertEqual(summary["withdrawn"][0]["reason"], "客户已取消")

    def test_truncation_wrong_scope_and_page_gap_stop_before_output(self):
        mutations = (
            lambda d: d["pages"].pop(),
            lambda d: d["pages"][1]["arguments"].update(chat_jid="another-demo@lid"),
            lambda d: d["pages"][1]["arguments"].update(page=3),
            lambda d: d["pages"][0]["arguments"].update(include_context=True),
            lambda d: d["pages"][0]["arguments"].update(query="only lamps"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                data = copy.deepcopy(self.data)
                mutate(data)
                with self.assertRaises(ValueError):
                    self.run_packet(data)
                self.assertFalse((self.folder / "packet").exists())

    def test_error_is_not_zero_messages_and_repeated_page_is_not_completion(self):
        for response in (
            {"isError": True, "content": [{"type": "text", "text": "Failed"}]},
            "Database error",
            "",
        ):
            data = copy.deepcopy(self.data)
            data["pages"][-1]["result"] = response
            with self.assertRaises(ValueError):
                self.run_packet(data)
        data = copy.deepcopy(self.data)
        data["pages"][1]["result"] = data["pages"][0]["result"]
        with self.assertRaises(ValueError):
            self.run_packet(data)

    def test_citations_quantity_and_state_are_not_invented(self):
        mutations = (
            lambda d: d["items"][0]["evidence"][0].update(quote="Imagined demand"),
            lambda d: d["items"][0]["quantity_evidence"].update(page=99),
            lambda d: d["items"][0].pop("quantity_evidence"),
            lambda d: d["items"][0].pop("state"),
            lambda d: d["items"][1].update(missing=[]),
        )
        for mutate in mutations:
            data = copy.deepcopy(self.data)
            mutate(data)
            with self.assertRaises(ValueError):
                self.run_packet(data)
        for value in (None, True, 0, -2, "NaN", "Infinity"):
            data = copy.deepcopy(self.data)
            data["items"][0]["quantity"] = value
            with self.assertRaises(ValueError):
                self.run_packet(data)

    def test_wrong_chat_unknown_photo_uninspected_photo_and_missing_file(self):
        mutations = (
            lambda d: d["downloads"][0]["arguments"].update(chat_jid="other-demo@lid"),
            lambda d: d["downloads"][0]["arguments"].update(message_id="UNKNOWN"),
            lambda d: d["items"][0].update(photo_verified=False),
            lambda d: d["downloads"][0]["result"].update(file_path="missing.png"),
        )
        for mutate in mutations:
            data = copy.deepcopy(self.data)
            mutate(data)
            with self.assertRaises(ValueError):
                self.run_packet(data)

    def test_failed_media_only_blocks_affected_demand(self):
        data = copy.deepcopy(self.data)
        data["downloads"][0]["result"] = {"success": False, "message": "Unavailable"}
        with self.assertRaises(ValueError):
            self.run_packet(data)
        data["items"][0].update(state="pending", missing=["参考图下载失败"])
        result = self.run_packet(data)
        self.assertEqual(result["pending"], 2)
        self.assertEqual(result["download_failures"], 1)
        self.assertIsNone(result["supplier_input"])
        self.assertFalse((self.folder / "packet/supplier-rfq.json").exists())

    def test_structured_mcp_payload_and_chat_identity(self):
        data = copy.deepcopy(self.data)
        original = data["pages"][1]["result"]["content"][0]["text"]
        data["pages"][1]["result"] = {
            "structuredContent": {
                "result": [
                    {
                        "id": "DEMO-IMG-01",
                        "chat_jid": "demo-buyer@lid",
                        "media_type": "image",
                        "content": original,
                    }
                ]
            }
        }
        data["pages"][2]["result"] = {"structuredContent": {"result": []}}
        data["downloads"][0]["result"] = {
            "content": [{"type": "text", "text": json.dumps(self.data["downloads"][0]["result"])}]
        }
        self.assertEqual(self.run_packet(data)["ready"], 1)
        data["pages"][1]["result"]["structuredContent"]["result"][0]["chat_jid"] = "other-demo@lid"
        with self.assertRaises(ValueError):
            self.run_packet(data, "bad")

    def test_output_protection_and_common_private_fields(self):
        self.run_packet()
        before = (self.folder / "packet/private-evidence.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_packet()
        self.assertEqual((self.folder / "packet/private-evidence.json").read_bytes(), before)
        for value in ("buyer@example.invalid", "+000 000 000 000", "demo-buyer@lid", "$123"):
            data = copy.deepcopy(self.data)
            data["items"][0]["notes"] = value
            with self.assertRaises(ValueError):
                self.run_packet(data, "private")
        data = copy.deepcopy(self.data)
        data["customer_name"] = "Not a supported public header"
        with self.assertRaises(ValueError):
            self.run_packet(data, "private")


if __name__ == "__main__":
    unittest.main()
