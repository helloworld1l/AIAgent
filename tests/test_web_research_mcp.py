"""Tests for the MVP web research MCP pipeline."""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from config.settings import settings
from tools.mcp_web_research.research_tool import WebResearchToolchain


class WebResearchMCPTest(unittest.TestCase):
    def test_search_uses_configured_connect_timeout(self) -> None:
        with patch.object(settings, "WEB_SEARCH_PROVIDER", "duckduckgo_html", create=True), patch.object(
            settings,
            "WEB_FETCH_TIMEOUT_SEC",
            20,
        ), patch.object(settings, "WEB_CONNECT_TIMEOUT_SEC", 17, create=True):
            toolchain = WebResearchToolchain(project_root=Path.cwd())

        mock_response = Mock()
        mock_response.text = "<a class='result__a' href='https://example.com/page'>Example Page</a>"
        mock_response.raise_for_status.return_value = None

        with patch.object(toolchain.session, "get", return_value=mock_response) as mock_get:
            results = toolchain._search(query="example", max_results=3, allowed_domains=[])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://example.com/page")
        self.assertEqual(results[0]["provider"], "duckduckgo_html")
        self.assertEqual(mock_get.call_args.kwargs["timeout"], (17, 20))

    def test_auto_provider_falls_back_to_bing(self) -> None:
        with patch.object(settings, "WEB_SEARCH_PROVIDER", "auto", create=True):
            toolchain = WebResearchToolchain(project_root=Path.cwd())

        with patch.object(
            toolchain,
            "_search_duckduckgo_html",
            side_effect=RuntimeError("duck blocked"),
        ), patch.object(
            toolchain,
            "_search_bing_rss",
            return_value=[
                {
                    "title": "Satellite orbit equations",
                    "url": "https://example.com/orbit",
                    "snippet": "Two-body orbit equations and perturbations.",
                }
            ],
        ):
            results = toolchain._search(query="satellite orbit", max_results=3, allowed_domains=[])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["provider"], "bing_rss")
        self.assertEqual(toolchain.provider, "bing_rss")
        self.assertEqual(toolchain.search_providers_used, ["bing_rss"])
        self.assertEqual(toolchain.search_attempts[0]["provider"], "bing_rss")
        self.assertEqual(toolchain.search_attempts[0]["status"], "success")

    def test_toolchain_uses_enterprise_ca_and_proxy_settings(self) -> None:
        with patch.object(settings, "WEB_REQUESTS_VERIFY_SSL", True, create=True), patch.object(
            settings,
            "WEB_REQUESTS_CA_BUNDLE",
            "D:/certs/corp-root.pem",
            create=True,
        ), patch.object(
            settings,
            "WEB_REQUESTS_HTTP_PROXY",
            "http://proxy.example.local:8080",
            create=True,
        ), patch.object(
            settings,
            "WEB_REQUESTS_HTTPS_PROXY",
            "http://proxy.example.local:8080",
            create=True,
        ), patch.object(
            settings,
            "WEB_REQUESTS_NO_PROXY",
            "localhost,127.0.0.1",
            create=True,
        ), patch.object(settings, "WEB_REQUESTS_TRUST_ENV", False, create=True):
            toolchain = WebResearchToolchain(project_root=Path.cwd())

        self.assertEqual(toolchain.request_verify, "D:/certs/corp-root.pem")
        self.assertEqual(
            toolchain.request_proxies,
            {
                "http": "http://proxy.example.local:8080",
                "https": "http://proxy.example.local:8080",
                "no_proxy": "localhost,127.0.0.1",
            },
        )
        self.assertFalse(toolchain.session.trust_env)

    def test_search_timeout_returns_actionable_error(self) -> None:
        with patch.object(settings, "WEB_SEARCH_PROVIDER", "duckduckgo_html", create=True), patch.object(
            settings,
            "WEB_FETCH_TIMEOUT_SEC",
            20,
        ), patch.object(settings, "WEB_CONNECT_TIMEOUT_SEC", 15, create=True):
            toolchain = WebResearchToolchain(project_root=Path.cwd())

        with patch.object(
            toolchain.session,
            "get",
            side_effect=requests.exceptions.ConnectTimeout("timed out"),
        ):
            with self.assertRaises(RuntimeError) as context:
                toolchain._search(query="example", max_results=3, allowed_domains=[])

        message = str(context.exception)
        self.assertIn("WEB_CONNECT_TIMEOUT_SEC", message)
        self.assertIn("outbound network", message)

    def test_search_ssl_error_returns_actionable_ca_message(self) -> None:
        with patch.object(settings, "WEB_SEARCH_PROVIDER", "duckduckgo_html", create=True):
            toolchain = WebResearchToolchain(project_root=Path.cwd())

        with patch.object(
            toolchain.session,
            "get",
            side_effect=requests.exceptions.SSLError("certificate verify failed"),
        ):
            with self.assertRaises(RuntimeError) as context:
                toolchain._search(query="example", max_results=3, allowed_domains=[])

        message = str(context.exception)
        self.assertIn("WEB_REQUESTS_CA_BUNDLE", message)
        self.assertIn("WEB_REQUESTS_VERIFY_SSL=false", message)

    def test_research_query_persists_bundle_and_docs(self) -> None:
        toolchain = WebResearchToolchain(project_root=Path.cwd())
        toolchain.bundle_root = Path.cwd() / "generated_research_test_workspace"
        mocked_results = [
            {
                "title": "Rocket equation overview",
                "url": "https://example.com/rocket-equation",
                "snippet": "Mass ratio and effective exhaust velocity.",
                "domain": "example.com",
                "provider": "bing_rss",
            },
            {
                "title": "Atmospheric drag basics",
                "url": "https://example.org/drag",
                "snippet": "Simple drag coefficient references.",
                "domain": "example.org",
                "provider": "duckduckgo_html",
            },
        ]
        fetch_side_effect = [
            {
                "status": "success",
                "url": "https://example.com/rocket-equation",
                "final_url": "https://example.com/rocket-equation",
                "title": "Rocket equation overview",
                "content_type": "text/html",
                "text": "The rocket equation links mass ratio with achievable delta-v.",
                "excerpt": "The rocket equation links mass ratio with achievable delta-v.",
            },
            {
                "status": "success",
                "url": "https://example.org/drag",
                "final_url": "https://example.org/drag",
                "title": "Atmospheric drag basics",
                "content_type": "text/html",
                "text": "Drag is often modeled as one half rho v squared Cd A.",
                "excerpt": "Drag is often modeled as one half rho v squared Cd A.",
            },
        ]

        try:
            shutil.rmtree(toolchain.bundle_root, ignore_errors=True)
            with patch.object(toolchain, "_search", return_value=mocked_results), patch.object(
                toolchain,
                "_fetch_url",
                side_effect=fetch_side_effect,
            ), patch.object(
                toolchain.qdrant_indexer,
                "index_sources",
                return_value=toolchain.qdrant_indexer.default_result(status="disabled"),
            ):
                result = toolchain.research_query(
                    query="联网检索火箭上升段阻力与推力参数",
                    session_id="session-web",
                    max_results=5,
                    max_fetch=2,
                )

            self.assertEqual(result["status"], "success")
            self.assertEqual(len(result["docs"]), 2)
            self.assertTrue("provider_config" in result)
            bundle_dir = Path(result["bundle_dir"])
            self.assertTrue((bundle_dir / "query.json").exists())
            self.assertTrue((bundle_dir / "search_results.json").exists())
            self.assertTrue((bundle_dir / "fetched_sources.json").exists())
            self.assertTrue((bundle_dir / "evidence_summary.md").exists())
            self.assertTrue((bundle_dir / "modeling_brief.json").exists())
            self.assertTrue((bundle_dir / "result.json").exists())
            self.assertIn("qdrant_index", result)
            self.assertIn(result["qdrant_index"]["status"], {"disabled", "success", "failed"})
            for source in result["sources"]:
                self.assertTrue(Path(source["saved_path"]).exists())
                self.assertEqual(source["status"], "success")
        finally:
            shutil.rmtree(toolchain.bundle_root, ignore_errors=True)

    def test_research_query_continues_when_one_fetch_fails(self) -> None:
        toolchain = WebResearchToolchain(project_root=Path.cwd())
        toolchain.bundle_root = Path.cwd() / "generated_research_test_workspace"
        mocked_results = [
            {
                "title": "Rocket equation overview",
                "url": "https://example.com/rocket-equation",
                "snippet": "Mass ratio and effective exhaust velocity.",
                "domain": "example.com",
                "provider": "bing_rss",
            },
            {
                "title": "Atmospheric drag basics",
                "url": "https://example.org/drag",
                "snippet": "Simple drag coefficient references.",
                "domain": "example.org",
                "provider": "bing_rss",
            },
        ]
        fetch_side_effect = [
            RuntimeError("temporary fetch failure"),
            {
                "status": "success",
                "url": "https://example.org/drag",
                "final_url": "https://example.org/drag",
                "title": "Atmospheric drag basics",
                "content_type": "text/html",
                "text": "Drag is often modeled as one half rho v squared Cd A.",
                "excerpt": "Drag is often modeled as one half rho v squared Cd A.",
            },
        ]

        try:
            shutil.rmtree(toolchain.bundle_root, ignore_errors=True)
            with patch.object(toolchain, "_search", return_value=mocked_results), patch.object(
                toolchain,
                "_fetch_url",
                side_effect=fetch_side_effect,
            ), patch.object(
                toolchain.qdrant_indexer,
                "index_sources",
                return_value=toolchain.qdrant_indexer.default_result(status="disabled"),
            ):
                result = toolchain.research_query(
                    query="联网检索火箭上升段阻力与推力参数",
                    session_id="session-web",
                    max_results=5,
                    max_fetch=2,
                )

            self.assertEqual(result["status"], "success")
            self.assertEqual(len(result["sources"]), 2)
            self.assertEqual(result["sources"][0]["status"], "failed")
            self.assertIn("temporary fetch failure", result["sources"][0]["message"])
            self.assertEqual(result["sources"][1]["status"], "success")
            self.assertEqual(len(result["docs"]), 1)
            self.assertIn("qdrant_index", result)
            self.assertIn(result["qdrant_index"]["status"], {"disabled", "success", "failed"})
        finally:
            shutil.rmtree(toolchain.bundle_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
