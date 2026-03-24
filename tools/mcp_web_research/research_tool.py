"""Web research pipeline for search -> fetch -> persist -> evidence docs."""

from __future__ import annotations

import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests

from config.settings import settings
from tools.mcp_web_research.qdrant_indexer import WebResearchQdrantIndexer

logger = logging.getLogger(__name__)

SUPPORTED_SEARCH_PROVIDERS = {"auto", "bing_rss", "duckduckgo_html"}
DEFAULT_SEARCH_PROVIDER_ORDER = ["bing_rss", "duckduckgo_html"]


class SearchResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self._current_href = ""
        self._collect_title = False
        self._title_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: (value or "") for key, value in attrs}
        if tag != "a":
            return
        class_name = attr_map.get("class", "")
        href = attr_map.get("href", "")
        if "result__a" in class_name or "result-link" in class_name:
            self._current_href = href
            self._collect_title = True
            self._title_parts = []

    def handle_data(self, data: str) -> None:
        if self._collect_title:
            self._title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._collect_title:
            return
        title = _normalize_whitespace("".join(self._title_parts))
        href = _normalize_duckduckgo_href(self._current_href)
        if title and href:
            self.results.append({"title": title, "url": href, "snippet": ""})
        self._current_href = ""
        self._collect_title = False
        self._title_parts = []


class HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._title_parts: List[str] = []
        self._text_parts: List[str] = []
        self._inside_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag == "title":
            self._inside_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title":
            self._inside_title = False

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self._title_parts.append(data)
        if self._skip_depth > 0:
            return
        text = _normalize_whitespace(data)
        if text:
            self._text_parts.append(text)

    @property
    def title(self) -> str:
        return _normalize_whitespace(" ".join(self._title_parts))

    @property
    def text(self) -> str:
        return _normalize_whitespace(" ".join(self._text_parts))


class WebResearchToolchain:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path(__file__).resolve().parents[2]
        self.bundle_root = self.project_root / str(getattr(settings, "WEB_RESEARCH_DIR", "generated_research"))
        self.provider_config = str(getattr(settings, "WEB_SEARCH_PROVIDER", "auto") or "auto")
        self.provider = self.provider_config
        self.search_attempts: List[Dict[str, Any]] = []
        self.search_providers_used: List[str] = []
        self.request_timeout = max(3, int(getattr(settings, "WEB_FETCH_TIMEOUT_SEC", 12)))
        self.connect_timeout = max(3, int(getattr(settings, "WEB_CONNECT_TIMEOUT_SEC", self.request_timeout)))
        self.max_results_default = max(1, int(getattr(settings, "WEB_SEARCH_MAX_RESULTS", 5)))
        self.max_fetch_default = max(1, int(getattr(settings, "WEB_FETCH_MAX_SOURCES", 3)))
        self.max_chars = max(1000, int(getattr(settings, "WEB_FETCH_MAX_CHARS", 12000)))
        self.qdrant_indexer = WebResearchQdrantIndexer()
        self.enabled = bool(getattr(settings, "WEB_RESEARCH_ENABLED", True))
        self.request_trust_env = bool(getattr(settings, "WEB_REQUESTS_TRUST_ENV", True))
        self.request_verify = _resolve_request_verify(trust_env=self.request_trust_env)
        self.request_proxies = _build_request_proxies()
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
        )
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        self.session.trust_env = self.request_trust_env

    def research_query(
        self,
        query: str,
        session_id: str = "default",
        max_results: int | None = None,
        max_fetch: int | None = None,
        allowed_domains: List[str] | None = None,
        bundle_name: str = "",
    ) -> Dict[str, Any]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            raise ValueError("query cannot be empty")
        self.provider = self.provider_config
        self.search_attempts = []
        self.search_providers_used = []

        bundle_dir = self._create_bundle_dir(session_id=session_id, bundle_name=bundle_name or normalized_query)
        sources_dir = bundle_dir / "sources"
        sources_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "query": normalized_query,
            "session_id": session_id,
            "provider": self.provider,
            "provider_config": self.provider_config,
            "enabled": self.enabled,
            "allowed_domains": list(allowed_domains or []),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        (bundle_dir / "query.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        qdrant_index_result = self.qdrant_indexer.default_result(status="disabled")

        if not self.enabled:
            result = {
                "status": "disabled",
                "message": "Web research is disabled by WEB_RESEARCH_ENABLED.",
                "query": normalized_query,
                "bundle_dir": str(bundle_dir),
                "docs": [],
                "sources": [],
                "qdrant_index": qdrant_index_result,
            }
            (bundle_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            return result

        search_results: List[Dict[str, Any]] = []
        fetched_sources: List[Dict[str, Any]] = []
        evidence_docs: List[Dict[str, Any]] = []
        try:
            search_results = self._search(
                normalized_query,
                max_results=max_results or self.max_results_default,
                allowed_domains=allowed_domains or [],
            )
            (bundle_dir / "search_results.json").write_text(
                json.dumps(search_results, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            for index, item in enumerate(search_results[: max_fetch or self.max_fetch_default], 1):
                try:
                    fetched = self._fetch_url(item.get("url", ""))
                except Exception as exc:
                    logger.warning("Web source fetch failed for '%s': %s", item.get("url", ""), exc)
                    fetched = {
                        "status": "failed",
                        "message": str(exc),
                        "url": str(item.get("url", "")).strip(),
                        "content_type": "",
                    }
                saved_path = sources_dir / f"{index:02d}_{_slugify(item.get('title') or item.get('url') or f'source_{index}', fallback=f'source_{index}')}.md"
                persisted = self._persist_source(saved_path, item, fetched)
                fetched_sources.append(persisted)
                if persisted.get("status") == "success":
                    evidence_docs.append(self._build_evidence_doc(index, item, persisted, saved_path))

            try:
                qdrant_index_result = self.qdrant_indexer.index_sources(
                    query=normalized_query,
                    session_id=session_id,
                    fetched_sources=fetched_sources,
                )
            except Exception as exc:
                logger.warning("Web research Qdrant indexing raised unexpected error: %s", exc)
                qdrant_index_result = self.qdrant_indexer.default_result(
                    status="failed",
                    sources_total=len(fetched_sources),
                    error=str(exc),
                )

            (bundle_dir / "fetched_sources.json").write_text(
                json.dumps(fetched_sources, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            summary_markdown = self._build_summary_markdown(normalized_query, search_results, fetched_sources)
            summary_path = bundle_dir / "evidence_summary.md"
            summary_path.write_text(summary_markdown, encoding="utf-8")

            modeling_brief = {
                "query": normalized_query,
                "summary_path": str(summary_path),
                "bundle_dir": str(bundle_dir),
                "successful_sources": sum(1 for item in fetched_sources if item.get("status") == "success"),
                "source_count": len(fetched_sources),
                "analysis_hint": (
                    "Use the local knowledge base to choose a supported MATLAB family/model. "
                    "Use the persisted web evidence only as supplemental assumptions and parameters."
                ),
                "source_paths": [item.get("saved_path", "") for item in fetched_sources if item.get("saved_path")],
                "qdrant_index": {
                    "status": str(qdrant_index_result.get("status", "")),
                    "collection": str(qdrant_index_result.get("collection", "")),
                    "scope": str(qdrant_index_result.get("scope", "")),
                    "points_upserted": int(qdrant_index_result.get("points_upserted", 0) or 0),
                },
            }
            brief_path = bundle_dir / "modeling_brief.json"
            brief_path.write_text(json.dumps(modeling_brief, ensure_ascii=False, indent=2), encoding="utf-8")

            result = {
                "status": "success",
                "query": normalized_query,
                "bundle_dir": str(bundle_dir),
                "summary_path": str(summary_path),
                "brief_path": str(brief_path),
                "provider": self.provider,
                "provider_config": self.provider_config,
                "search_attempts": list(self.search_attempts),
                "search_providers_used": list(self.search_providers_used),
                "search_results": search_results,
                "sources": fetched_sources,
                "docs": evidence_docs,
                "summary": _normalize_whitespace(summary_markdown)[:2000],
                "qdrant_index": qdrant_index_result,
            }
            (bundle_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            return result
        except Exception as exc:
            logger.warning("Web research failed for query '%s': %s", normalized_query, exc)
            result = {
                "status": "failed",
                "message": str(exc),
                "query": normalized_query,
                "bundle_dir": str(bundle_dir),
                "provider": self.provider,
                "provider_config": self.provider_config,
                "search_attempts": list(self.search_attempts),
                "search_providers_used": list(self.search_providers_used),
                "search_results": search_results,
                "sources": fetched_sources,
                "docs": evidence_docs,
                "qdrant_index": qdrant_index_result,
            }
            (bundle_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            return result

    def _search(self, query: str, max_results: int, allowed_domains: List[str]) -> List[Dict[str, Any]]:
        provider_order = _resolve_search_provider_order(self.provider_config)
        combined_results: List[Dict[str, Any]] = []
        seen_urls: set[str] = set()
        successful_providers: List[str] = []
        domain_filters = [item.strip().lower() for item in allowed_domains if str(item).strip()]

        for provider in provider_order:
            try:
                provider_results = self._search_with_provider(provider, query=query, max_results=max_results)
                self.search_attempts.append(
                    {
                        "provider": provider,
                        "status": "success",
                        "result_count": len(provider_results),
                    }
                )
                successful_providers.append(provider)
            except Exception as exc:
                logger.warning("Web search provider '%s' failed for query '%s': %s", provider, query, exc)
                self.search_attempts.append(
                    {
                        "provider": provider,
                        "status": "failed",
                        "message": str(exc),
                    }
                )
                continue

            for item in provider_results:
                url = str(item.get("url", "")).strip()
                if not url or url in seen_urls:
                    continue
                if domain_filters:
                    hostname = urlparse(url).netloc.lower()
                    if not any(domain in hostname for domain in domain_filters):
                        continue
                seen_urls.add(url)
                combined_results.append(
                    {
                        "title": str(item.get("title", "")).strip() or url,
                        "url": url,
                        "snippet": str(item.get("snippet", "")).strip(),
                        "domain": urlparse(url).netloc,
                        "provider": provider,
                    }
                )
                if len(combined_results) >= max_results:
                    break
            if len(combined_results) >= max_results:
                break

        self.search_providers_used = successful_providers
        if combined_results:
            providers_with_results: List[str] = []
            for item in combined_results:
                provider = str(item.get("provider", "")).strip()
                if provider and provider not in providers_with_results:
                    providers_with_results.append(provider)
            self.provider = providers_with_results[0] if len(providers_with_results) == 1 else "multi_source"
            return combined_results[:max_results]
        if successful_providers:
            self.provider = successful_providers[0] if len(successful_providers) == 1 else "multi_source"
            return []

        messages = [
            str(item.get("message", "")).strip()
            for item in self.search_attempts
            if str(item.get("status", "")).strip() == "failed" and str(item.get("message", "")).strip()
        ]
        raise RuntimeError(
            "; ".join(messages) if messages else f"all configured search providers failed: {provider_order}"
        )

    def _search_with_provider(self, provider: str, query: str, max_results: int) -> List[Dict[str, Any]]:
        if provider == "duckduckgo_html":
            return self._search_duckduckgo_html(query=query, max_results=max_results)
        if provider == "bing_rss":
            return self._search_bing_rss(query=query, max_results=max_results)
        raise ValueError(f"unsupported web search provider: {provider}")

    def _search_duckduckgo_html(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        response = self._request(
            f"https://duckduckgo.com/html/?q={quote_plus(query)}",
            context="search",
        )

        parser = SearchResultParser()
        parser.feed(response.text)
        return parser.results[:max_results]

    def _search_bing_rss(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        response = self._request(
            f"https://www.bing.com/search?q={quote_plus(query)}&format=rss&count={max_results}",
            context="search",
        )
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            raise RuntimeError(f"bing_rss returned invalid XML: {exc}") from exc

        results: List[Dict[str, Any]] = []
        for item in root.findall(".//item"):
            title = _normalize_whitespace(item.findtext("title", default=""))
            url = _normalize_whitespace(item.findtext("link", default=""))
            snippet = _normalize_whitespace(item.findtext("description", default=""))
            if title and url:
                results.append({"title": title, "url": url, "snippet": snippet})
            if len(results) >= max_results:
                break
        return results

    def _fetch_url(self, url: str) -> Dict[str, Any]:
        normalized_url = str(url or "").strip()
        if not normalized_url:
            return {"status": "failed", "message": "url is empty", "url": normalized_url}

        response = self._request(normalized_url, context="fetch")

        content_type = str(response.headers.get("content-type", "")).lower()
        raw_text = response.text or ""
        if "text/html" in content_type or "application/xhtml+xml" in content_type or not content_type:
            extractor = HTMLTextExtractor()
            extractor.feed(raw_text)
            title = extractor.title
            text = extractor.text
        elif content_type.startswith("text/") or "application/json" in content_type or "application/xml" in content_type:
            title = ""
            text = _normalize_whitespace(raw_text)
        else:
            return {
                "status": "skipped",
                "message": f"unsupported content type: {content_type}",
                "url": normalized_url,
                "content_type": content_type,
            }

        text = text[: self.max_chars]
        if not text:
            return {
                "status": "failed",
                "message": "empty extracted text",
                "url": normalized_url,
                "content_type": content_type,
            }

        return {
            "status": "success",
            "url": normalized_url,
            "final_url": str(response.url),
            "title": title,
            "content_type": content_type,
            "text": text,
            "excerpt": text[:400],
        }

    def _persist_source(self, saved_path: Path, search_item: Dict[str, Any], fetched: Dict[str, Any]) -> Dict[str, Any]:
        metadata = {
            "title": str(search_item.get("title", "")).strip(),
            "url": str(search_item.get("url", "")).strip(),
            "domain": str(search_item.get("domain", "")).strip(),
            "status": str(fetched.get("status", "failed")),
            "saved_path": str(saved_path),
            "content_type": str(fetched.get("content_type", "")).strip(),
            "message": str(fetched.get("message", "")).strip(),
        }
        lines = [
            f"# {metadata['title'] or metadata['url']}",
            "",
            f"- URL: {metadata['url']}",
            f"- Domain: {metadata['domain']}",
            f"- Status: {metadata['status']}",
        ]
        if metadata["content_type"]:
            lines.append(f"- Content-Type: {metadata['content_type']}")
        if metadata["message"]:
            lines.append(f"- Message: {metadata['message']}")
        lines.append("")
        if fetched.get("title"):
            lines.extend(["## Page Title", str(fetched.get("title", "")), ""])
        excerpt = str(fetched.get("excerpt", "")).strip()
        if excerpt:
            lines.extend(["## Excerpt", excerpt, ""])
        text = str(fetched.get("text", "")).strip()
        if text:
            lines.extend(["## Extracted Content", text, ""])
        saved_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        metadata["title"] = str(fetched.get("title", "")).strip() or metadata["title"]
        metadata["excerpt"] = excerpt
        metadata["text"] = text
        return metadata

    def _build_summary_markdown(
        self,
        query: str,
        search_results: List[Dict[str, Any]],
        fetched_sources: List[Dict[str, Any]],
    ) -> str:
        lines = [
            "# Web Research Summary",
            "",
            f"- Query: {query}",
            f"- Search results: {len(search_results)}",
            f"- Fetched sources: {len(fetched_sources)}",
            "",
            "## Sources",
        ]
        for item in fetched_sources:
            title = str(item.get("title", "")).strip() or str(item.get("url", "")).strip()
            status = str(item.get("status", "")).strip()
            lines.append(f"- [{status}] {title} | {item.get('url', '')}")
            excerpt = str(item.get("excerpt", "")).strip()
            if excerpt:
                lines.append(f"  - Evidence: {excerpt[:280]}")
        if len(lines) == 6:
            lines.append("- No sources were successfully fetched.")
        lines.extend(
            [
                "",
                "## Modeling Hint",
                (
                    "Use the repository knowledge base to choose a supported model family first; "
                    "then use the web evidence as supplemental assumptions, parameters, or scenario context."
                ),
            ]
        )
        return "\n".join(lines)

    def _build_evidence_doc(
        self,
        index: int,
        search_item: Dict[str, Any],
        persisted: Dict[str, Any],
        saved_path: Path,
    ) -> Dict[str, Any]:
        text = str(persisted.get("text", "")).strip()
        title = str(persisted.get("title", "")).strip() or str(search_item.get("title", "")).strip()
        url = str(search_item.get("url", "")).strip()
        return {
            "id": f"web_research_{index}",
            "score": round(max(0.05, 1.0 - ((index - 1) * 0.08)), 4),
            "text": f"web_source: {title}; url: {url}; content: {text[:1800]}",
            "payload": {
                "source": "web_research",
                "model_id": "",
                "template_family": "",
                "title": title,
                "url": url,
                "domain": str(search_item.get("domain", "")).strip(),
                "saved_path": str(saved_path),
            },
        }

    def _create_bundle_dir(self, session_id: str, bundle_name: str) -> Path:
        self.bundle_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = _slugify(bundle_name, fallback="research")
        session_slug = _slugify(session_id or "default", fallback="default")
        bundle_dir = self.bundle_root / session_slug / f"{stamp}_{slug}"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        return bundle_dir

    def _request(self, url: str, context: str) -> requests.Response:
        self._validate_request_configuration()
        try:
            response = self.session.get(
                url,
                timeout=(self.connect_timeout, self.request_timeout),
                proxies=self.request_proxies or None,
                verify=self.request_verify,
            )
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                _format_request_error(
                    url=url,
                    context=context,
                    exc=exc,
                    connect_timeout=self.connect_timeout,
                    read_timeout=self.request_timeout,
                )
            ) from exc

    def _validate_request_configuration(self) -> None:
        if isinstance(self.request_verify, str):
            ca_bundle = Path(self.request_verify).expanduser()
            if not ca_bundle.exists():
                raise RuntimeError(
                    "Configured web CA bundle was not found: "
                    f"{ca_bundle}. Check WEB_REQUESTS_CA_BUNDLE / REQUESTS_CA_BUNDLE / SSL_CERT_FILE."
                )


def _normalize_duckduckgo_href(href: str) -> str:
    raw = str(href or "").strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        return "https:" + raw
    if raw.startswith("/"):
        parsed = urlparse(raw)
        params = parse_qs(parsed.query)
        if "uddg" in params and params["uddg"]:
            return unquote(params["uddg"][0])
        return ""
    return raw


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(str(text or ""))).strip()


def _slugify(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "_", str(value or "").strip())
    normalized = normalized.strip("_-")
    return normalized or fallback


def _resolve_search_provider_order(provider_config: str) -> List[str]:
    raw_items = [item.strip() for item in str(provider_config or "").split(",") if item.strip()]
    if not raw_items:
        raw_items = ["auto"]

    resolved: List[str] = []
    for item in raw_items:
        if item == "auto":
            for provider in DEFAULT_SEARCH_PROVIDER_ORDER:
                if provider not in resolved:
                    resolved.append(provider)
            continue
        if item not in SUPPORTED_SEARCH_PROVIDERS:
            raise ValueError(f"unsupported web search provider: {item}")
        if item not in resolved:
            resolved.append(item)
    return resolved or list(DEFAULT_SEARCH_PROVIDER_ORDER)


def _resolve_request_verify(trust_env: bool) -> bool | str:
    if not bool(getattr(settings, "WEB_REQUESTS_VERIFY_SSL", True)):
        return False
    explicit_ca_bundle = _read_request_env_value("WEB_REQUESTS_CA_BUNDLE")
    if explicit_ca_bundle:
        return explicit_ca_bundle
    if trust_env:
        for key in ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE"):
            raw = str(os.getenv(key, "") or "").strip()
            if raw:
                return raw
    return True


def _build_request_proxies() -> Dict[str, str]:
    proxy_map: Dict[str, str] = {}
    http_proxy = _read_request_env_value("WEB_REQUESTS_HTTP_PROXY")
    https_proxy = _read_request_env_value("WEB_REQUESTS_HTTPS_PROXY")
    no_proxy = _read_request_env_value("WEB_REQUESTS_NO_PROXY")
    if http_proxy:
        proxy_map["http"] = http_proxy
    if https_proxy:
        proxy_map["https"] = https_proxy
    if no_proxy:
        proxy_map["no_proxy"] = no_proxy
    return proxy_map


def _read_request_env_value(name: str) -> str:
    settings_value = getattr(settings, name, "")
    if settings_value is not None and str(settings_value).strip():
        return str(settings_value).strip()
    return str(os.getenv(name, "") or "").strip()


def _format_request_error(
    url: str,
    context: str,
    exc: requests.exceptions.RequestException,
    connect_timeout: int,
    read_timeout: int,
) -> str:
    host = urlparse(str(url or "")).netloc or str(url or "")
    if isinstance(exc, requests.exceptions.Timeout):
        return (
            f"Web {context} timeout when reaching {host} "
            f"(connect_timeout={connect_timeout}s, read_timeout={read_timeout}s). "
            "Increase WEB_CONNECT_TIMEOUT_SEC / WEB_FETCH_TIMEOUT_SEC, or verify outbound network, DNS, and proxy settings."
        )
    if isinstance(exc, requests.exceptions.SSLError):
        return (
            f"Web {context} TLS verification failed for {host}: {exc}. "
            "Configure WEB_REQUESTS_CA_BUNDLE / REQUESTS_CA_BUNDLE with the enterprise CA, "
            "or set WEB_REQUESTS_VERIFY_SSL=false only as a temporary last resort."
        )
    if isinstance(exc, requests.exceptions.ConnectionError):
        return (
            f"Web {context} connection error when reaching {host}: {exc}. "
            "Verify outbound network access, DNS resolution, and WEB_REQUESTS_* / HTTP(S)_PROXY settings."
        )
    return f"Web {context} request failed for {host}: {exc}"
