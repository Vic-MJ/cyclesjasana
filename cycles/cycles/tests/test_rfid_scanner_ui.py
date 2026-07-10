import re
from contextlib import suppress
from pathlib import Path

from odoo.addons.web.tests.test_js import unit_test_error_checker
from odoo.modules.module import get_module_path
from odoo.tests import HttpCase, tagged


FOCUSED_TEST_RE = re.compile(
    r"(?:^|[^\w$])(?:describe|test|QUnit)\.(?:only|debug)\s*\(",
    re.MULTILINE,
)


@tagged("post_install", "-at_install")
class TestRfidScannerUi(HttpCase):
    def test_cycles_rfid_scanner_hoot_suite_runs_in_ci(self):
        self.browser_js(
            "/web/tests?headless&loglevel=2&preset=mobile&timeout=15000"
            "&tag=cycles_rfid_scanner",
            "",
            "",
            login="admin",
            timeout=1800,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=unit_test_error_checker,
        )

    def _get_resource_path(self, module_name, *parts):
        module_path = get_module_path(module_name, display_warning=False)
        if not module_path:
            return None
        return str(Path(module_path, *parts))

    def test_cycles_assets_have_no_focused_tests(self):
        test_files = [
            self._get_resource_path("cycles", "static/tests/rfid_scanner.test.js"),
            self._get_resource_path(
                "web_responsive", "static/tests/apps_menu_search_tests.esm.js"
            ),
            self._get_resource_path(
                "web_responsive", "static/tests/apps_menu_tests.esm.js"
            ),
        ]

        for test_file in test_files:
            if not test_file:
                continue
            with suppress(FileNotFoundError):
                with open(test_file, "r", encoding="utf-8") as handler:
                    content = handler.read()
                self.assertFalse(
                    FOCUSED_TEST_RE.search(content),
                    f"Focused test helper found in {test_file}",
                )
