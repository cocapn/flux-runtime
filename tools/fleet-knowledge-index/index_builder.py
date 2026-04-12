#!/usr/bin/env python3
"""
index_builder.py - Fleet Knowledge Index Builder

Scans fleet repositories (local or via GitHub API) and builds a searchable
inverted index of knowledge domains. Supports incremental updates by tracking
the last scan timestamp and only processing changed repos.

Extracts knowledge artifacts from:
- README files (summaries, descriptions)
- Documentation files (titles, headings, sections)
- Source code (module names, function signatures, class names)
- Test files (test descriptions, fixture names)
- Configuration files (tool names, dependency names)

Outputs:
- JSON index file with inverted index structure
- Markdown summary report of the fleet's knowledge landscape

Usage:
    python index_builder.py build --repos-dir /path/to/repos --output-dir ./index_output
    python index_builder.py build --github-orgs SuperInstance,Lucineer --github-token $GITHUB_TOKEN
    python index_builder.py build --incremental --state-file ./state.json
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Import our domain classifier
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from domain_classifier import DomainClassifier, ClassificationResult


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "index_output")
DEFAULT_STATE_FILE = os.path.join(os.path.dirname(__file__), "scan_state.json")
DEFAULT_INDEX_FILE = "fleet_knowledge_index.json"
DEFAULT_SUMMARY_FILE = "fleet_knowledge_summary.md"

# Directories to skip during repo scanning
SKIP_DIRS = {
    ".git", "node_modules", "target", "build", "__pycache__",
    ".next", ".cache", "vendor", "third_party", "third-party",
    "dist", ".tox", ".mypy_cache", ".pytest_cache", "venv",
    ".venv", "env", ".env", "site-packages", ".gradle",
    ".idea", ".vscode", ".settings", "cmake-build-*",
    "out", "bin", "obj", ".dart_tool", ".pub-cache",
}

# File extensions to include in scanning
SCAN_EXTENSIONS = {
    # Source code
    ".rs", ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java",
    ".c", ".cpp", ".h", ".hpp", ".cu", ".cuh",
    ".zig", ".nim", ".swift", ".kt", ".scala",
    ".rb", ".lua", ".r", ".jl", ".ex", ".exs",
    ".ml", ".hs", ".clj", ".cljs",
    # Web
    ".html", ".css", ".scss", ".sass", ".less",
    ".graphql", ".gql",
    # Documentation
    ".md", ".rst", ".txt", ".adoc", ".org",
    # Config
    ".toml", ".yaml", ".yml", ".json", ".json5",
    ".dockerfile", ".tf", ".hcl",
    # Build
    ".cmake", ".make", ".mk",
}

# File names to always include (regardless of extension)
ALWAYS_INCLUDE = {
    "README", "README.md", "README.rst", "README.txt", "README.adoc",
    "CONTRIBUTING", "CONTRIBUTING.md", "CHANGELOG", "CHANGELOG.md",
    "ARCHITECTURE", "ARCHITECTURE.md", "DESIGN", "DESIGN.md",
    "Cargo.toml", "package.json", "pyproject.toml", "go.mod",
    "setup.py", "setup.cfg", "build.gradle", "pom.xml",
    "Makefile", "CMakeLists.txt", "Dockerfile", "docker-compose.yml",
    ".gitignore", ".env.example",
}

# Maximum file size to read (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024

# Maximum number of files per repo to scan
MAX_FILES_PER_REPO = 500


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeArtifact:
    """A single knowledge artifact extracted from a file."""
    artifact_id: str  # SHA256 hash of content
    repo_name: str
    file_path: str  # relative to repo root
    file_name: str
    artifact_type: str  # readme, doc, code, test, config
    language: Optional[str]
    domains: List[str]  # primary + secondary domain names
    domain_scores: Dict[str, float]
    title: str  # first meaningful heading/line
    excerpt: str  # first ~200 chars of relevant content
    keywords: List[str]
    line_count: int
    file_size: int
    last_modified: str  # ISO timestamp

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RepoScanResult:
    """Results from scanning a single repository."""
    repo_name: str
    org: str
    scan_timestamp: str
    repo_root: str
    total_files: int
    scanned_files: int
    artifacts: List[KnowledgeArtifact] = field(default_factory=list)
    domain_distribution: Dict[str, int] = field(default_factory=dict)
    languages: Dict[str, int] = field(default_factory=dict)
    scan_duration_seconds: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo_name": self.repo_name,
            "org": self.org,
            "scan_timestamp": self.scan_timestamp,
            "repo_root": self.repo_root,
            "total_files": int(self.total_files),
            "scanned_files": int(self.scanned_files),
            "artifacts": [a.to_dict() for a in self.artifacts],
            "domain_distribution": self.domain_distribution,
            "languages": self.languages,
            "scan_duration_seconds": self.scan_duration_seconds,
            "error": self.error,
        }


@dataclass
class FleetIndex:
    """The complete fleet knowledge index."""
    index_version: str
    build_timestamp: str
    total_repos: int
    total_artifacts: int
    repos: Dict[str, RepoScanResult] = field(default_factory=dict)
    inverted_index: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    domain_index: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    language_index: Dict[str, List[str]] = field(default_factory=dict)
    domain_statistics: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    org_index: Dict[str, List[str]] = field(default_factory=dict)
    file_index: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index_version": self.index_version,
            "build_timestamp": self.build_timestamp,
            "total_repos": self.total_repos,
            "total_artifacts": self.total_artifacts,
            "repos": {k: v.to_dict() for k, v in self.repos.items()},
            "inverted_index": self.inverted_index,
            "domain_index": self.domain_index,
            "language_index": self.language_index,
            "domain_statistics": self.domain_statistics,
            "org_index": self.org_index,
            "file_index": self.file_index,
        }


# ---------------------------------------------------------------------------
# File Type Detection
# ---------------------------------------------------------------------------

EXTENSION_TO_LANGUAGE = {
    ".rs": "rust", ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".jsx": "javascript", ".go": "go", ".java": "java",
    ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
    ".cu": "cuda", ".cuh": "cuda",
    ".zig": "zig", ".nim": "nim", ".swift": "swift",
    ".kt": "kotlin", ".scala": "scala",
    ".rb": "ruby", ".lua": "lua", ".r": "r", ".jl": "julia",
    ".ex": "elixir", ".exs": "elixir",
    ".ml": "ocaml", ".hs": "haskell", ".clj": "clojure",
    ".html": "html", ".css": "css", ".scss": "scss",
    ".graphql": "graphql", ".gql": "graphql",
    ".md": "markdown", ".rst": "restructuredtext",
    ".toml": "toml", ".yaml": "yaml", ".yml": "yaml",
    ".json": "json", ".tf": "hcl", ".hcl": "hcl",
    ".cmake": "cmake", ".make": "makefile", ".mk": "makefile",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".sql": "sql",
}


def detect_language(file_path: str) -> Optional[str]:
    """Detect the programming language from a file extension."""
    _, ext = os.path.splitext(file_path.lower())
    return EXTENSION_TO_LANGUAGE.get(ext)


def detect_artifact_type(file_path: str, content: str = "") -> str:
    """Detect the type of knowledge artifact."""
    fname = os.path.basename(file_path).lower()

    if fname.startswith("readme") or fname.startswith("read_me"):
        return "readme"
    if fname in ("contributing", "changelog", "architecture", "design", "roadmap"):
        return "doc"
    if fname.startswith(("adr", "rfc", "spec")):
        return "doc"
    if any(fname.startswith(t) for t in ("test_", "_test.", "tests.")):
        return "test"
    if any(fname.startswith(t) for t in ("spec_", "_spec.")):
        return "test"
    if fname.endswith(("test.rs", "test.py", "test.js", "test.ts",
                       "_test.go", "_test.exs", "_test.clj")):
        return "test"
    if fname.endswith((".md", ".rst", ".adoc", ".txt", ".org")):
        return "doc"
    if fname.endswith((".toml", ".yaml", ".yml", ".json", ".json5")):
        return "config"
    if fname in ("dockerfile", "docker-compose.yml", "makefile", "cmakelists.txt"):
        return "config"
    if fname.endswith((".tf", ".hcl")):
        return "config"
    if any(fname.endswith(f) for f in (".cu", ".cuh")):
        return "code"

    # Check content for test patterns
    if content and any(p in content[:2000] for p in ["# [test]", "#[cfg(test)]", "@test", "def test_", "func Test"]):
        return "test"

    return "code"


# ---------------------------------------------------------------------------
# Content Extraction
# ---------------------------------------------------------------------------

def extract_title(content: str, artifact_type: str) -> str:
    """Extract a meaningful title from file content."""
    lines = content.strip().split("\n")

    # For markdown/rst, look for the first heading
    if artifact_type in ("readme", "doc"):
        for line in lines[:20]:
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped.lstrip("#").strip()
            if stripped.startswith("## "):
                return stripped.lstrip("#").strip()
            if stripped and not stripped.startswith(("<", "!", "[", "-", "=", "*", "{")):
                # First non-empty, non-marker line
                return stripped[:100]

    # For code, look for module/class/function declarations
    code_patterns = [
        r"^(?:pub\s+)?(?:async\s+)?(?:fn|def|func|function|sub|method)\s+(\w+)",
        r"^(?:pub\s+)?(?:struct|class|enum|trait|interface|type|protocol)\s+(\w+)",
        r"^(?:module|namespace|package|crate)\s+(\w+)",
    ]
    for line in lines[:30]:
        for pattern in code_patterns:
            match = re.match(pattern, line.strip())
            if match:
                return match.group(1)

    # Fall back to first non-empty line
    for line in lines[:5]:
        stripped = line.strip()
        if stripped:
            return stripped[:100]

    return "(untitled)"


def extract_excerpt(content: str, max_length: int = 300) -> str:
    """Extract a representative excerpt from file content."""
    # Remove leading whitespace and comments
    lines = content.strip().split("\n")
    clean_lines = []

    for line in lines[:50]:
        stripped = line.strip()
        # Skip empty lines, comment-only lines, and marker lines
        if not stripped:
            continue
        if stripped.startswith(("//", "#", "/*", "*", "*/", "---", "+++")):
            continue
        if stripped in ("```", "```rust", "```python", "```json", "```yaml"):
            continue
        clean_lines.append(stripped)
        excerpt = " ".join(clean_lines)
        if len(excerpt) >= max_length:
            break

    excerpt = " ".join(clean_lines)[:max_length]
    if not excerpt:
        # Fall back to raw first line
        excerpt = content.strip().split("\n")[0].strip()[:max_length]
    return excerpt


def extract_keywords(content: str, max_keywords: int = 20) -> List[str]:
    """Extract significant keywords from content using frequency analysis."""
    # Tokenize: split on non-alphanumeric, filter short words and common stop words
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "dare", "ought",
        "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
        "neither", "each", "every", "all", "any", "few", "more", "most",
        "other", "some", "such", "no", "only", "own", "same", "than",
        "too", "very", "just", "because", "as", "until", "while", "of",
        "at", "by", "for", "with", "about", "against", "between", "through",
        "during", "before", "after", "above", "below", "to", "from", "up",
        "down", "in", "out", "on", "off", "over", "under", "again",
        "further", "then", "once", "here", "there", "when", "where",
        "why", "how", "all", "each", "every", "both", "few", "more",
        "most", "other", "some", "such", "no", "nor", "not",
        "this", "that", "these", "those", "it", "its", "we", "you",
        "they", "them", "their", "our", "your", "my", "me", "he", "she",
        "him", "her", "us", "which", "what", "who", "whom", "if", "also",
        "use", "using", "used", "make", "made", "into", "get", "got",
        "new", "old", "like", "well", "back", "still", "even", "way",
        "pub", "fn", "let", "mut", "impl", "self", "super", "crate",
        "mod", "use", "return", "true", "false", "none", "null",
        "import", "from", "class", "def", "print", "pass",
    }

    words = re.findall(r"[a-zA-Z_][\w]{2,}", content.lower())
    word_freq = Counter(words)

    # Remove stop words and very common words
    for word in stop_words:
        word_freq.pop(word, None)

    # Remove single occurrences and very short words (keep as Counter for most_common)
    filtered = Counter({w: c for w, c in word_freq.items() if c >= 2 and len(w) >= 3})

    return [w for w, _ in filtered.most_common(max_keywords)]


def extract_module_names(content: str, language: Optional[str]) -> List[str]:
    """Extract module/class/function names from source code."""
    names = []

    if language == "rust":
        # pub fn, pub struct, pub enum, pub trait, mod
        for m in re.finditer(r"pub\s+(?:async\s+)?(?:fn|struct|enum|trait|const|type|mod)\s+(\w+)", content):
            names.append(m.group(1))
        for m in re.finditer(r"(?:impl|use)\s+(\w+)", content):
            names.append(m.group(1))

    elif language == "python":
        for m in re.finditer(r"^(?:async\s+)?(?:def|class)\s+(\w+)", content, re.MULTILINE):
            names.append(m.group(1))
        for m in re.finditer(r"^(?:from|import)\s+([\w.]+)", content, re.MULTILINE):
            names.append(m.group(1).split(".")[-1])

    elif language in ("javascript", "typescript"):
        for m in re.finditer(r"(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class|const|let)\s+(\w+)", content):
            names.append(m.group(1))
        for m in re.finditer(r"(?:export\s+)?(?:interface|type|enum)\s+(\w+)", content):
            names.append(m.group(1))

    elif language == "go":
        for m in re.finditer(r"^(?:func|type|interface)\s+(\w+)", content, re.MULTILINE):
            names.append(m.group(1))
        for m in re.finditer(r"import\s+\(\s*\n([\s\S]*?)\n\s*\)", content):
            for im in re.finditer(r'"([\w/]+)"', m.group(1)):
                names.append(im.group(1).split("/")[-1])

    elif language in ("c", "cpp"):
        for m in re.finditer(r"(?:typedef\s+struct|struct|enum|class|union)\s+(\w+)", content):
            names.append(m.group(1))
        for m in re.finditer(r"(?:(?:static\s+)?(?:inline\s+)?(?:void|int|char|float|double|bool|long|short|unsigned|size_t)\s*\*?\s+)(\w+)\s*\(", content):
            names.append(m.group(1))

    elif language == "cuda":
        # Same as C/C++ plus CUDA-specific
        for m in re.finditer(r"__(?:global|device|host)__\s+(?:void|float|int|double)\s+(\w+)", content):
            names.append(m.group(1))
        for m in re.finditer(r"(?:typedef\s+struct|struct|enum|class|union)\s+(\w+)", content):
            names.append(m.group(1))

    elif language == "java":
        for m in re.finditer(r"(?:public|private|protected)?\s*(?:static\s+)?(?:class|interface|enum|abstract\s+class)\s+(\w+)", content):
            names.append(m.group(1))
        for m in re.finditer(r"(?:public|private|protected)?\s*(?:static\s+)?(?:void|int|String|boolean|float|double)\s+(\w+)\s*\(", content):
            names.append(m.group(1))

    else:
        # Generic extraction for other languages
        for m in re.finditer(r"(?:function|def|fn|func|sub|proc|procedure|method)\s+(\w+)", content):
            names.append(m.group(1))
        for m in re.finditer(r"(?:class|struct|enum|interface|trait|protocol|module)\s+(\w+)", content):
            names.append(m.group(1))

    return list(dict.fromkeys(names))  # deduplicate preserving order


# ---------------------------------------------------------------------------
# Repository Scanner
# ---------------------------------------------------------------------------

class RepoScanner:
    """Scans a single repository for knowledge artifacts."""

    def __init__(self, classifier: DomainClassifier, repo_path: str, repo_name: str, org: str = ""):
        self.classifier = classifier
        self.repo_path = repo_path
        self.repo_name = repo_name
        self.org = org
        self._skip_dirs = SKIP_DIRS.copy()

    def scan(self, max_files: int = MAX_FILES_PER_REPO) -> RepoScanResult:
        """Scan the repository and return results."""
        start_time = time.time()
        result = RepoScanResult(
            repo_name=self.repo_name,
            org=self.org,
            scan_timestamp=datetime.now(timezone.utc).isoformat(),
            repo_root=self.repo_path,
            total_files=0,
            scanned_files=0,
        )

        try:
            self._scan_directory(result, self.repo_path, max_files)
        except Exception as e:
            result.error = str(e)

        result.scan_duration_seconds = round(time.time() - start_time, 2)

        # Build domain distribution
        domain_counter = Counter()
        for artifact in result.artifacts:
            if artifact.domains:
                domain_counter[artifact.domains[0]] += 1
        result.domain_distribution = dict(domain_counter.most_common())

        # Build language distribution
        lang_counter = Counter()
        for artifact in result.artifacts:
            if artifact.language:
                lang_counter[artifact.language] += 1
        result.languages = dict(lang_counter.most_common())

        return result

    def _scan_directory(self, result: RepoScanResult, dir_path: str, max_files: int) -> None:
        """Recursively scan a directory."""
        if result.scanned_files >= max_files:
            return

        try:
            entries = os.listdir(dir_path)
        except PermissionError:
            return

        dirs = []
        files = []
        for entry in entries:
            full_path = os.path.join(dir_path, entry)
            if os.path.isdir(full_path):
                if entry not in self._skip_dirs and not entry.startswith("."):
                    dirs.append(full_path)
            elif os.path.isfile(full_path):
                files.append(full_path)

        # Process files
        for file_path in sorted(files):
            if result.scanned_files >= max_files:
                break

            fname = os.path.basename(file_path)

            # Check if we should include this file
            _, ext = os.path.splitext(fname.lower())
            include = ext in SCAN_EXTENSIONS or fname in ALWAYS_INCLUDE

            if not include:
                result.total_files += 1
                continue

            result.total_files += 1

            # Check file size
            try:
                file_size = os.path.getsize(file_path)
            except OSError:
                continue

            if file_size > MAX_FILE_SIZE:
                continue

            # Read file
            try:
                content = self._read_file(file_path)
            except Exception:
                continue

            if not content or len(content.strip()) < 10:
                continue

            # Extract artifact
            artifact = self._extract_artifact(file_path, content, file_size)
            if artifact:
                result.artifacts.append(artifact)
                result.scanned_files += 1

        # Process subdirectories
        for subdir in sorted(dirs):
            if result.scanned_files >= max_files:
                break
            self._scan_directory(result, subdir, max_files)

    def _read_file(self, file_path: str) -> str:
        """Read file content, trying UTF-8 first, then latin-1."""
        try:
            return Path(file_path).read_text(encoding="utf-8", errors="strict")
        except UnicodeDecodeError:
            return Path(file_path).read_text(encoding="latin-1", errors="replace")

    def _extract_artifact(self, file_path: str, content: str, file_size: int) -> Optional[KnowledgeArtifact]:
        """Extract a knowledge artifact from a file."""
        rel_path = os.path.relpath(file_path, self.repo_path)
        file_name = os.path.basename(file_path)
        language = detect_language(file_path)
        artifact_type = detect_artifact_type(file_path, content)

        # Classify into domains
        classification = self.classifier.classify_text(
            content[:5000],  # Use first 5000 chars for classification speed
            filename=file_name,
            metadata={"repo": self.repo_name, "path": rel_path},
        )

        if not classification.is_classified:
            return None  # Skip unclassifiable files

        domains = [classification.primary_domain] + classification.secondary_domains

        title = extract_title(content, artifact_type)
        excerpt = extract_excerpt(content)
        keywords = extract_keywords(content)
        line_count = content.count("\n") + 1

        # Get last modified time
        try:
            mtime = os.path.getmtime(file_path)
            last_modified = datetime.fromtimestamp(mtime, timezone.utc).isoformat()
        except OSError:
            last_modified = datetime.now(timezone.utc).isoformat()

        artifact_id = hashlib.sha256(
            f"{self.repo_name}:{rel_path}:{content[:1000]}".encode("utf-8")
        ).hexdigest()[:16]

        return KnowledgeArtifact(
            artifact_id=artifact_id,
            repo_name=self.repo_name,
            file_path=rel_path,
            file_name=file_name,
            artifact_type=artifact_type,
            language=language,
            domains=domains,
            domain_scores=classification.domain_scores,
            title=title,
            excerpt=excerpt,
            keywords=keywords,
            line_count=line_count,
            file_size=file_size,
            last_modified=last_modified,
        )


# ---------------------------------------------------------------------------
# GitHub API Scanner
# ---------------------------------------------------------------------------

class GitHubScanner:
    """Scans repositories via the GitHub API."""

    def __init__(self, token: Optional[str] = None, per_page: int = 100):
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.per_page = per_page
        self.session_headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            self.session_headers["Authorization"] = f"Bearer {self.token}"

    def list_org_repos(self, org: str) -> List[Dict[str, Any]]:
        """List all repositories in a GitHub organization."""
        repos = []
        page = 1
        url = f"https://api.github.com/orgs/{org}/repos"

        while True:
            params = {"per_page": self.per_page, "page": page, "sort": "updated", "type": "all"}
            response = self._make_request(url, params)

            if not response or not isinstance(response, list):
                break

            repos.extend(response)
            if len(response) < self.per_page:
                break
            page += 1

        return repos

    def get_repo_contents(self, owner: str, repo: str, path: str = "") -> List[Dict[str, Any]]:
        """Get contents of a repository path."""
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        return self._make_request(url)

    def get_file_content(self, download_url: str) -> Optional[str]:
        """Download a file's content from GitHub."""
        import urllib.request
        req = urllib.request.Request(download_url, headers=self.session_headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception:
            return None

    def _make_request(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Make an HTTP request to the GitHub API."""
        import urllib.request
        import urllib.parse

        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        req = urllib.request.Request(url, headers=self.session_headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"  GitHub API error for {url}: {e}")
            return None


# ---------------------------------------------------------------------------
# Index Builder
# ---------------------------------------------------------------------------

class IndexBuilder:
    """Builds and maintains the fleet knowledge index."""

    def __init__(
        self,
        output_dir: str = DEFAULT_OUTPUT_DIR,
        state_file: str = DEFAULT_STATE_FILE,
        classifier: Optional[DomainClassifier] = None,
    ):
        self.output_dir = output_dir
        self.state_file = state_file
        self.classifier = classifier or DomainClassifier()
        self.index = FleetIndex(
            index_version="2.0.0",
            build_timestamp="",
            total_repos=0,
            total_artifacts=0,
        )
        self._state: Dict[str, Any] = {}

    def load_state(self) -> None:
        """Load incremental scan state from disk."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    self._state = json.load(f)
                print(f"  Loaded scan state: {len(self._state.get('repo_timestamps', {}))} repos tracked")
            except Exception as e:
                print(f"  Warning: Could not load state file: {e}")
                self._state = {}
        else:
            self._state = {"repo_timestamps": {}, "last_full_scan": None}

    def save_state(self) -> None:
        """Save incremental scan state to disk."""
        os.makedirs(os.path.dirname(self.state_file) or ".", exist_ok=True)
        try:
            with open(self.state_file, "w") as f:
                json.dump(self._state, f, indent=2, default=str)
        except Exception as e:
            print(f"  Warning: Could not save state file: {e}")

    def _repo_needs_scan(self, repo_path: str) -> bool:
        """Check if a repo needs scanning (has been modified since last scan)."""
        timestamps = self._state.get("repo_timestamps", {})
        last_scan = timestamps.get(repo_path)

        if last_scan is None:
            return True  # Never scanned

        # Check git log for changes since last scan
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%ct", "--since", last_scan],
                cwd=repo_path,
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return True  # There are commits since last scan
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return False

    def build_from_local_repos(
        self,
        repos_dir: str,
        incremental: bool = False,
        max_repos: Optional[int] = None,
    ) -> FleetIndex:
        """
        Build the index by scanning local repositories.

        Args:
            repos_dir: Directory containing repository subdirectories.
            incremental: Only scan changed repos.
            max_repos: Maximum number of repos to scan.
        """
        if incremental:
            self.load_state()

        repos_path = Path(repos_dir)
        if not repos_path.is_dir():
            raise NotADirectoryError(f"Repos directory not found: {repos_dir}")

        # Discover repositories (directories with .git subdirectory)
        repo_dirs = []
        for entry in sorted(repos_path.iterdir()):
            if not entry.is_dir():
                continue
            if (entry / ".git").exists() or entry.name.endswith(".git"):
                if not incremental or self._repo_needs_scan(str(entry)):
                    repo_dirs.append(entry)

        if max_repos:
            repo_dirs = repo_dirs[:max_repos]

        print(f"\nBuilding index from {len(repo_dirs)} local repositories...")
        print(f"  Repos directory: {repos_dir}")
        print(f"  Incremental mode: {incremental}")

        self._scan_repos(repo_dirs, incremental)

        # Build the inverted indexes
        self._build_inverted_index()
        self._build_domain_index()
        self._build_language_index()
        self._build_org_index()
        self._compute_statistics()

        self.index.build_timestamp = datetime.now(timezone.utc).isoformat()

        if incremental:
            self.save_state()

        return self.index

    def build_from_github(
        self,
        orgs: List[str],
        clone_dir: Optional[str] = None,
        incremental: bool = False,
        github_token: Optional[str] = None,
        max_repos: Optional[int] = None,
    ) -> FleetIndex:
        """
        Build the index by scanning GitHub organizations.

        Args:
            orgs: List of GitHub organization names.
            clone_dir: Directory to clone repos into (optional).
            incremental: Only scan changed repos.
            github_token: GitHub API token.
            max_repos: Maximum number of repos to scan.
        """
        if incremental:
            self.load_state()

        scanner = GitHubScanner(token=github_token)
        if clone_dir:
            os.makedirs(clone_dir, exist_ok=True)

        total_repo_count = 0
        scanned_count = 0

        for org in orgs:
            print(f"\nScanning organization: {org}")
            repos = scanner.list_org_repos(org)
            print(f"  Found {len(repos)} repositories")

            for repo_info in repos:
                if max_repos and scanned_count >= max_repos:
                    break

                repo_name = repo_info["name"]
                full_name = repo_info["full_name"]
                repo_path = os.path.join(clone_dir, repo_name) if clone_dir else None
                total_repo_count += 1

                if incremental and repo_path and not self._repo_needs_scan(repo_path):
                    # Load cached results
                    if full_name in self.index.repos:
                        continue

                # Clone if needed
                if clone_dir and not os.path.exists(repo_path):
                    clone_url = repo_info["clone_url"]
                    print(f"  Cloning {full_name}...")
                    try:
                        subprocess.run(
                            ["git", "clone", "--depth", "1", clone_url, repo_path],
                            capture_output=True, timeout=120,
                        )
                    except Exception as e:
                        print(f"  Clone failed: {e}")
                        continue

                if repo_path and os.path.exists(repo_path):
                    repo_scanner = RepoScanner(
                        self.classifier, repo_path, repo_name, org
                    )
                    result = repo_scanner.scan()
                    self.index.repos[full_name] = result
                    scanned_count += 1

                    print(f"  Scanned {repo_name}: {result.scanned_files} artifacts")

                if scanned_count % 25 == 0:
                    print(f"  Progress: {scanned_count}/{total_repo_count} repos scanned")

        print(f"\nScan complete: {scanned_count} repos, {total_repo_count} total")

        self._build_inverted_index()
        self._build_domain_index()
        self._build_language_index()
        self._build_org_index()
        self._compute_statistics()

        self.index.build_timestamp = datetime.now(timezone.utc).isoformat()

        if incremental:
            self.save_state()

        return self.index

    def _scan_repos(self, repo_dirs: List[Path], incremental: bool) -> None:
        """Scan a list of repository directories."""
        total = len(repo_dirs)

        for i, repo_dir in enumerate(repo_dirs):
            repo_name = repo_dir.name
            print(f"  [{i + 1}/{total}] Scanning {repo_name}...")

            scanner = RepoScanner(self.classifier, str(repo_dir), repo_name)
            result = scanner.scan()

            self.index.repos[repo_name] = result
            self._state.setdefault("repo_timestamps", {})[str(repo_dir)] = result.scan_timestamp

            if result.error:
                print(f"    Error: {result.error}")
            else:
                print(f"    {result.scanned_files} artifacts extracted "
                      f"({result.scan_duration_seconds}s)")

            if (i + 1) % 25 == 0:
                print(f"  Progress: {i + 1}/{total} repos scanned")

    def _build_inverted_index(self) -> None:
        """Build inverted index: keyword → list of artifacts."""
        inverted: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for repo_name, result in self.index.repos.items():
            for artifact in result.artifacts:
                # Index by title words
                title_words = re.findall(r"[a-zA-Z_][\w]{2,}", artifact.title.lower())
                for word in title_words:
                    inverted[word].append({
                        "repo": repo_name,
                        "file": artifact.file_path,
                        "title": artifact.title,
                        "type": artifact.artifact_type,
                        "domains": artifact.domains,
                        "excerpt": artifact.excerpt[:200],
                        "language": artifact.language,
                    })

                # Index by keywords
                for keyword in artifact.keywords:
                    inverted[keyword].append({
                        "repo": repo_name,
                        "file": artifact.file_path,
                        "title": artifact.title,
                        "type": artifact.artifact_type,
                        "domains": artifact.domains,
                        "excerpt": artifact.excerpt[:200],
                        "language": artifact.language,
                    })

                # Index by module/function names (from title)
                if artifact.artifact_type == "code":
                    for word in title_words:
                        if word not in inverted:
                            inverted[word].append({
                                "repo": repo_name,
                                "file": artifact.file_path,
                                "title": artifact.title,
                                "type": artifact.artifact_type,
                                "domains": artifact.domains,
                                "excerpt": artifact.excerpt[:200],
                                "language": artifact.language,
                            })

        # Deduplicate entries per keyword
        for keyword in inverted:
            seen = set()
            deduped = []
            for entry in inverted[keyword]:
                key = f"{entry['repo']}:{entry['file']}"
                if key not in seen:
                    seen.add(key)
                    deduped.append(entry)
            inverted[keyword] = deduped

        self.index.inverted_index = dict(inverted)

    def _build_domain_index(self) -> None:
        """Build domain index: domain → list of artifacts."""
        domain_index: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for repo_name, result in self.index.repos.items():
            for artifact in result.artifacts:
                for domain in artifact.domains:
                    domain_index[domain].append({
                        "repo": repo_name,
                        "file": artifact.file_path,
                        "title": artifact.title,
                        "type": artifact.artifact_type,
                        "score": artifact.domain_scores.get(domain, 0.0),
                        "language": artifact.language,
                        "excerpt": artifact.excerpt[:200],
                    })

        # Sort each domain's entries by score
        for domain in domain_index:
            domain_index[domain].sort(key=lambda x: x["score"], reverse=True)

        self.index.domain_index = dict(domain_index)

    def _build_language_index(self) -> None:
        """Build language index: language → list of repo names."""
        lang_index: Dict[str, List[str]] = defaultdict(set)

        for repo_name, result in self.index.repos.items():
            for artifact in result.artifacts:
                if artifact.language:
                    lang_index[artifact.language].add(repo_name)

        self.index.language_index = {k: sorted(v) for k, v in lang_index.items()}

    def _build_org_index(self) -> None:
        """Build organization index: org → list of repo names."""
        org_index: Dict[str, List[str]] = defaultdict(list)

        for repo_name, result in self.index.repos.items():
            if result.org:
                org_index[result.org].append(repo_name)

        self.index.org_index = dict(org_index)

    def _compute_statistics(self) -> None:
        """Compute fleet-wide statistics."""
        total_repos = len(self.index.repos)
        total_artifacts = sum(
            len(r.artifacts) for r in self.index.repos.values()
        )

        # Domain statistics
        domain_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "artifact_count": 0,
            "repo_count": 0,
            "total_score": 0.0,
            "languages": Counter(),
            "repos": set(),
        })

        for repo_name, result in self.index.repos.items():
            repo_domains = set()
            for artifact in result.artifacts:
                if artifact.domains:
                    primary = artifact.domains[0]
                    domain_stats[primary]["artifact_count"] += 1
                    domain_stats[primary]["total_score"] += artifact.domain_scores.get(primary, 0.0)
                    repo_domains.add(primary)
                    if artifact.language:
                        domain_stats[primary]["languages"][artifact.language] += 1

            for domain in repo_domains:
                domain_stats[domain]["repo_count"] += 1
                domain_stats[domain]["repos"].add(repo_name)

        # Format statistics
        self.index.domain_statistics = {}
        for domain_name, stats in sorted(domain_stats.items()):
            self.index.domain_statistics[domain_name] = {
                "artifact_count": stats["artifact_count"],
                "repo_count": stats["repo_count"],
                "avg_score": round(
                    stats["total_score"] / max(stats["artifact_count"], 1), 4
                ),
                "top_languages": dict(stats["languages"].most_common(5)),
                "representative_repos": sorted(list(stats["repos"]))[:10],
            }

        self.index.total_repos = total_repos
        self.index.total_artifacts = total_artifacts

    def save_index(self, filename: Optional[str] = None) -> str:
        """Save the index to a JSON file."""
        os.makedirs(self.output_dir, exist_ok=True)
        output_file = os.path.join(
            self.output_dir, filename or DEFAULT_INDEX_FILE
        )

        index_dict = self.index.to_dict()
        with open(output_file, "w") as f:
            json.dump(index_dict, f, indent=2, default=str)

        print(f"\nIndex saved to: {output_file}")
        print(f"  Total repos: {self.index.total_repos}")
        print(f"  Total artifacts: {self.index.total_artifacts}")
        print(f"  Domains indexed: {len(self.index.domain_index)}")
        print(f"  Keywords indexed: {len(self.index.inverted_index)}")
        print(f"  Languages: {len(self.index.language_index)}")

        return output_file

    def generate_summary_markdown(self, filename: Optional[str] = None) -> str:
        """Generate a markdown summary of the fleet knowledge index."""
        os.makedirs(self.output_dir, exist_ok=True)
        output_file = os.path.join(
            self.output_dir, filename or DEFAULT_SUMMARY_FILE
        )

        lines = []
        lines.append("# Fleet Knowledge Index Summary")
        lines.append("")
        lines.append(f"**Generated:** {self.index.build_timestamp}")
        lines.append(f"**Version:** {self.index.index_version}")
        lines.append(f"**Total Repositories:** {self.index.total_repos}")
        lines.append(f"**Total Knowledge Artifacts:** {self.index.total_artifacts}")
        lines.append(f"**Knowledge Domains:** {len(self.index.domain_index)}")
        lines.append(f"**Languages:** {len(self.index.language_index)}")
        lines.append("")

        # Domain overview table
        lines.append("## Knowledge Domain Distribution")
        lines.append("")
        lines.append("| Domain | Artifacts | Repos | Avg Score | Top Languages |")
        lines.append("|--------|----------|-------|-----------|---------------|")

        for domain_name, stats in sorted(
            self.index.domain_statistics.items(),
            key=lambda x: x[1]["artifact_count"],
            reverse=True,
        ):
            domain_info = self.classifier.domains.get(domain_name)
            display_name = domain_info.display_name if domain_info else domain_name
            langs = ", ".join(
                f"{lang}({count})" for lang, count in list(stats["top_languages"].items())[:3]
            )
            lines.append(
                f"| {display_name} | {stats['artifact_count']} | "
                f"{stats['repo_count']} | {stats['avg_score']:.3f} | {langs} |"
            )
        lines.append("")

        # Language distribution
        lines.append("## Language Distribution")
        lines.append("")
        lines.append("| Language | Repos |")
        lines.append("|----------|-------|")

        for language, repos in sorted(
            self.index.language_index.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )[:20]:
            lines.append(f"| {language} | {len(repos)} |")
        lines.append("")

        # Organization breakdown
        if self.index.org_index:
            lines.append("## Organization Breakdown")
            lines.append("")
            for org, repos in sorted(
                self.index.org_index.items(),
                key=lambda x: len(x[1]),
                reverse=True,
            ):
                lines.append(f"### {org} ({len(repos)} repos)")
                lines.append("")
                for repo in sorted(repos)[:20]:
                    result = self.index.repos.get(repo)
                    artifact_count = len(result.artifacts) if result else 0
                    domains = ", ".join(
                        list(result.domain_distribution.keys())[:3]
                    ) if result and result.domain_distribution else "N/A"
                    lines.append(f"- **{repo}** — {artifact_count} artifacts, domains: {domains}")
                if len(repos) > 20:
                    lines.append(f"- ... and {len(repos) - 20} more repos")
                lines.append("")

        # Top repos by knowledge density
        lines.append("## Top Repos by Knowledge Density")
        lines.append("")
        repo_artifact_counts = sorted(
            [(name, len(r.artifacts)) for name, r in self.index.repos.items()],
            key=lambda x: x[1],
            reverse=True,
        )[:30]

        lines.append("| Repository | Artifacts | Domains | Languages |")
        lines.append("|------------|----------|---------|-----------|")
        for repo_name, count in repo_artifact_counts:
            result = self.index.repos.get(repo_name)
            if result:
                domains = ", ".join(list(result.domain_distribution.keys())[:3])
                langs = ", ".join(list(result.languages.keys())[:3])
                lines.append(f"| {repo_name} | {count} | {domains} | {langs} |")
        lines.append("")

        # Integration section
        lines.append("## Integration with Fleet Tools")
        lines.append("")
        lines.append("### fleet-context-inference")
        lines.append("")
        lines.append("This knowledge index complements the `fleet-context-inference` tool:")
        lines.append("")
        lines.append("- **fleet-context-inference** profiles *individual agents* — their capabilities, context needs, and expertise areas.")
        lines.append("- **fleet-knowledge-index** indexes the *collective knowledge* across all repos — what knowledge domains exist, where they live, and how they connect.")
        lines.append("")
        lines.append("Use both together to:")
        lines.append("1. Find which repos contain knowledge needed for a given agent's task")
        lines.append("2. Identify knowledge gaps in the fleet")
        lines.append("3. Route agents to the most relevant repositories")
        lines.append("")
        lines.append("### Searching the Index")
        lines.append("")
        lines.append("Use the `search_engine.py` tool to query the index:")
        lines.append("")
        lines.append("```bash")
        lines.append("# Search for CUDA-related knowledge")
        lines.append("python search_engine.py search 'CUDA kernel optimization'")
        lines.append("")
        lines.append("# Filter by domain")
        lines.append("python search_engine.py search 'memory allocator' --domain runtimes")
        lines.append("")
        lines.append("# Filter by language")
        lines.append("python search_engine.py search 'parser combinator' --language rust")
        lines.append("```")
        lines.append("")

        content = "\n".join(lines)
        with open(output_file, "w") as f:
            f.write(content)

        print(f"Summary saved to: {output_file}")
        return output_file

    def load_index(self, index_file: Optional[str] = None) -> FleetIndex:
        """Load a previously built index from disk."""
        path = index_file or os.path.join(self.output_dir, DEFAULT_INDEX_FILE)

        if not os.path.exists(path):
            raise FileNotFoundError(f"Index file not found: {path}")

        with open(path, "r") as f:
            data = json.load(f)

        self.index = FleetIndex(
            index_version=data["index_version"],
            build_timestamp=data["build_timestamp"],
            total_repos=data["total_repos"],
            total_artifacts=data["total_artifacts"],
            repos={},  # Skip full repo data for search
            inverted_index=data.get("inverted_index", {}),
            domain_index=data.get("domain_index", {}),
            language_index=data.get("language_index", {}),
            domain_statistics=data.get("domain_statistics", {}),
            org_index=data.get("org_index", {}),
            file_index=data.get("file_index", {}),
        )

        print(f"Loaded index: {self.index.total_repos} repos, "
              f"{self.index.total_artifacts} artifacts")
        return self.index


# ---------------------------------------------------------------------------
# CLI Interface
# ---------------------------------------------------------------------------

def main():
    """CLI entry point for the index builder."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fleet Knowledge Index Builder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Build from local repos
  %(prog)s build --repos-dir /path/to/repos

  # Build from GitHub orgs
  %(prog)s build --github-orgs SuperInstance,Lucineer --github-token $GITHUB_TOKEN

  # Incremental update
  %(prog)s build --repos-dir /path/to/repos --incremental

  # Generate markdown summary only
  %(prog)s summary --index-file ./index_output/fleet_knowledge_index.json
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # build command
    build_parser = subparsers.add_parser("build", help="Build the knowledge index")
    build_parser.add_argument(
        "--repos-dir", default=None,
        help="Directory containing local repositories",
    )
    build_parser.add_argument(
        "--github-orgs", default=None,
        help="Comma-separated list of GitHub orgs to scan",
    )
    build_parser.add_argument(
        "--github-token", default=None,
        help="GitHub API token (or set GITHUB_TOKEN env var)",
    )
    build_parser.add_argument(
        "--clone-dir", default=None,
        help="Directory to clone GitHub repos into",
    )
    build_parser.add_argument(
        "--output-dir", default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    build_parser.add_argument(
        "--state-file", default=DEFAULT_STATE_FILE,
        help=f"State file for incremental scanning (default: {DEFAULT_STATE_FILE})",
    )
    build_parser.add_argument(
        "--incremental", action="store_true",
        help="Only scan repos changed since last run",
    )
    build_parser.add_argument(
        "--max-repos", type=int, default=None,
        help="Maximum number of repos to scan",
    )

    # summary command
    summary_parser = subparsers.add_parser("summary", help="Generate markdown summary")
    summary_parser.add_argument(
        "--index-file", required=True,
        help="Path to the index JSON file",
    )
    summary_parser.add_argument(
        "--output", default=None,
        help="Output markdown file path",
    )

    args = parser.parse_args()

    if args.command == "build":
        if not args.repos_dir and not args.github_orgs:
            print("Error: Specify --repos-dir or --github-orgs")
            sys.exit(1)

        builder = IndexBuilder(
            output_dir=args.output_dir,
            state_file=args.state_file,
        )

        if args.repos_dir:
            builder.build_from_local_repos(
                repos_dir=args.repos_dir,
                incremental=args.incremental,
                max_repos=args.max_repos,
            )
        elif args.github_orgs:
            orgs = [o.strip() for o in args.github_orgs.split(",")]
            builder.build_from_github(
                orgs=orgs,
                clone_dir=args.clone_dir,
                incremental=args.incremental,
                github_token=args.github_token,
                max_repos=args.max_repos,
            )

        builder.save_index()
        builder.generate_summary_markdown()

    elif args.command == "summary":
        builder = IndexBuilder()
        builder.load_index(args.index_file)
        builder.generate_summary_markdown(args.output)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
