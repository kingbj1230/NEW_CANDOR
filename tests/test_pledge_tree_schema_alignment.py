import unittest

from services.pledge_tree_service import insert_pledge_tree


class PledgeTreeSchemaAlignmentTests(unittest.TestCase):
    def test_insert_pledge_tree_does_not_insert_is_leaf_column(self):
        inserted_payloads = []

        def fake_now_iso():
            return "2026-03-27T00:00:00Z"

        def fake_insert_returning(table, payload):
            self.assertEqual(table, "pledge_nodes")
            # SCHEMA.md standard for pledge_nodes does not define is_leaf.
            self.assertNotIn("is_leaf", payload)
            inserted_payloads.append(dict(payload or {}))
            return {"id": f"node-{len(inserted_payloads)}"}

        insert_pledge_tree(
            "pledge-1",
            "\n".join(
                [
                    "\ubaa9\ud45c",
                    "- \uccad\ub144 \uc8fc\uac70 \uc548\uc815",
                    "\uc774\ud589\ubc29\ubc95",
                    "\u2460 \uc804\uc138 \uc9c0\uc6d0 \ud655\ub300",
                    "- \ud55c\ub3c4 \uc0c1\ud5a5",
                    "\uc774\ud589\uae30\uac04",
                    "- 2027\ub144\uae4c\uc9c0",
                    "\uc7ac\uc6d0\uc870\ub2ec\ubc29\uc548 \ub4f1",
                    "- \uae30\uc874 \uc608\uc0b0 \uc870\uc815",
                ]
            ),
            "user-1",
            now_iso_fn=fake_now_iso,
            supabase_insert_returning=fake_insert_returning,
            supabase_request=lambda *args, **kwargs: [],
        )

        self.assertGreaterEqual(len(inserted_payloads), 3)
        for payload in inserted_payloads:
            self.assertIn("pledge_id", payload)
            self.assertIn("node_type", payload)
            self.assertIn("level", payload)
            self.assertIn("content", payload)

        level1_titles = [payload.get("content") for payload in inserted_payloads if payload.get("level") == 1]
        self.assertIn("\ubaa9\ud45c", level1_titles)
        self.assertIn("\uc774\ud589 \ubc29\ubc95", level1_titles)
        self.assertIn("\uc774\ud589\uae30\uac04", level1_titles)
        self.assertIn("\uc7ac\uc6d0\uc870\ub2ec\ubc29\uc548 \ub4f1", level1_titles)


if __name__ == "__main__":
    unittest.main()