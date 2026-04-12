#!/usr/bin/env python3
"""
search_engine.py - Fleet Knowledge Search Engine

Full-text search across the fleet knowledge index with:
- TF-IDF scoring for ranked results
- Fuzzy matching for misspelled queries (Levenshtein distance)
- Filtering by domain, language, organization, date, artifact type
- Context excerpts in search results
- Aggregate statistics and domain suggestions

Usage:
    python search_engine.py search "CUDA kernel optimization"
    python search_engine.py search "memory allocator" --domain runtimes
    python search_engine.py search "parser combinator" --language rust --limit 10
    python search_engine.py suggest "how does the fleet handle agent dispatch?"
    python search_engine.py stats
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from domain_classifier import DomainClassifier

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_INDEX_FILE = os.path.join(
    os.path.dirname(__file__), "index_output", "fleet_knowledge_index.json"
)

# Stop words for query processing
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "and", "but", "or",
    "nor", "not", "so", "yet", "of", "at", "by", "for", "with", "about",
    "against", "between", "through", "during", "before", "after", "above",
    "below", "to", "from", "up", "down", "in", "out", "on", "off", "over",
    "under", "again", "further", "then", "once", "here", "there", "when",
    "where", "why", "how", "all", "each", "every", "both", "few", "more",
    "most", "other", "some", "such", "no", "this", "that", "these", "those",
    "it", "its", "we", "you", "they", "them", "their", "which", "what",
    "who", "if", "also", "use", "using", "used", "into", "get",
    "find", "show", "me", "my", "i", "want", "like", "please",
}


# ---------------------------------------------------------------------------
# Fuzzy Matching Utilities
# ---------------------------------------------------------------------------

def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Compute the Levenshtein distance between two strings.
    Used for fuzzy matching misspelled queries.
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost: 0 if chars match, 1 otherwise
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def fuzzy_similarity(s1: str, s2: str) -> float:
    """
    Compute a normalized similarity score between two strings.
    Returns a value between 0.0 (completely different) and 1.0 (identical).
    """
    if not s1 or not s2:
        return 0.0

    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0

    distance = levenshtein_distance(s1.lower(), s2.lower())
    return 1.0 - (distance / max_len)


def sequence_similarity(s1: str, s2: str) -> float:
    """
    Compute similarity using SequenceMatcher (difflib).
    Good for catching transpositions and common subsequences.
    """
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


def combined_similarity(s1: str, s2: str) -> float:
    """Combine multiple similarity metrics for robust fuzzy matching."""
    lev_sim = fuzzy_similarity(s1, s2)
    seq_sim = sequence_similarity(s1, s2)
    # Weighted combination favoring SequenceMatcher for short strings
    # and Levenshtein for longer strings
    if len(s1) <= 5 or len(s2) <= 5:
        return max(lev_sim, seq_sim)
    return 0.4 * lev_sim + 0.6 * seq_sim


def find_fuzzy_matches(
    query_term: str,
    candidates: Set[str],
    threshold: float = 0.7,
    max_matches: int = 5,
) -> List[Tuple[str, float]]:
    """
    Find fuzzy matches for a query term among a set of candidates.

    Args:
        query_term: The term to search for (possibly misspelled).
        candidates: Set of candidate strings to match against.
        threshold: Minimum similarity score to include.
        max_matches: Maximum number of matches to return.

    Returns:
        List of (candidate, similarity_score) tuples, sorted by score descending.
    """
    matches = []
    for candidate in candidates:
        sim = combined_similarity(query_term, candidate)
        if sim >= threshold:
            matches.append((candidate, sim))

    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[:max_matches]


# ---------------------------------------------------------------------------
# TF-IDF Scoring
# ---------------------------------------------------------------------------

class TFIDFScorer:
    """
    Term Frequency - Inverse Document Frequency scorer.

    Ranks search results by relevance using standard TF-IDF weighting
    with optional BM25-style term saturation.
    """

    def __init__(self, index_data: Dict[str, Any]):
        """
        Initialize the scorer with index data.

        Args:
            index_data: The loaded fleet knowledge index dictionary.
        """
        self.index_data = index_data
        self.inverted_index = index_data.get("inverted_index", {})
        self.domain_index = index_data.get("domain_index", {})
        self.total_artifacts = index_data.get("total_artifacts", 1)

        # Pre-compute document frequency for each term
        self.doc_freq: Dict[str, int] = {}
        for term, postings in self.inverted_index.items():
            # Document frequency: number of unique (repo, file) pairs
            unique_docs = set()
            for posting in postings:
                doc_key = f"{posting['repo']}:{posting['file']}"
                unique_docs.add(doc_key)
            self.doc_freq[term] = len(unique_docs)

        # Pre-compute average document length (for BM25)
        self._compute_avg_doc_length()

    def _compute_avg_doc_length(self) -> None:
        """Compute average document length for BM25 scoring."""
        total_length = 0
        doc_count = 0
        for postings in self.inverted_index.values():
            for posting in postings:
                excerpt_len = len(posting.get("excerpt", ""))
                total_length += excerpt_len
                doc_count += 1
        self.avg_doc_length = total_length / max(doc_count, 1)

    def idf(self, term: str) -> float:
        """
        Compute Inverse Document Frequency for a term.

        Uses smoothed IDF: log((N - df + 0.5) / (df + 0.5) + 1)
        """
        df = self.doc_freq.get(term, 0)
        if df == 0:
            return 0.0

        # BM25-style IDF with smoothing
        n = self.total_artifacts
        idf_val = math.log((n - df + 0.5) / (df + 0.5) + 1.0)
        return max(idf_val, 0.0)

    def tf_idf_score(self, term: str, posting: Dict[str, Any]) -> float:
        """
        Compute TF-IDF score for a term in a specific document/posting.

        Uses BM25-style scoring with k1=1.5, b=0.75.
        """
        # Term frequency: count occurrences in excerpt (simplified)
        excerpt = posting.get("excerpt", "").lower()
        title = posting.get("title", "").lower()
        text = f"{title} {title} {excerpt}"  # Boost title with double weight

        tf = text.count(term.lower())
        if tf == 0:
            return 0.0

        # BM25 TF saturation: (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl/avgdl))
        k1 = 1.5
        b = 0.75
        doc_length = len(excerpt)
        tf_component = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_length / self.avg_doc_length))

        idf_component = self.idf(term)

        return tf_component * idf_component

    def score_query(
        self,
        query_terms: List[str],
        postings: List[Dict[str, Any]],
        fuzzy_terms: Optional[Dict[str, float]] = None,
    ) -> float:
        """
        Score a set of postings against a query.

        Args:
            query_terms: Original query terms.
            postings: List of posting entries for matched documents.
            fuzzy_terms: Dict mapping original term -> best fuzzy match score.

        Returns:
            Combined TF-IDF score.
        """
        total_score = 0.0
        matched_terms = set()

        for posting in postings:
            for term in query_terms:
                term_lower = term.lower()
                # Check if this posting is relevant to the term
                title_lower = posting.get("title", "").lower()
                excerpt_lower = posting.get("excerpt", "").lower()

                if term_lower in title_lower or term_lower in excerpt_lower:
                    score = self.tf_idf_score(term, posting)
                    total_score += score
                    matched_terms.add(term_lower)

        # Add bonus for fuzzy matches
        if fuzzy_terms:
            for original_term, fuzzy_score in fuzzy_terms.items():
                if original_term.lower() not in matched_terms:
                    total_score += fuzzy_score * 0.5  # Reduced weight for fuzzy matches

        return total_score

    def score_document(
        self,
        query_terms: List[str],
        document_key: str,
        posting_entries: List[Dict[str, Any]],
    ) -> float:
        """
        Score a single document (identified by repo:file) against the query.

        This provides more accurate scoring by considering all term matches
        for a specific document.
        """
        total_score = 0.0
        matched_count = 0

        for term in query_terms:
            term_lower = term.lower()
            term_idf = self.idf(term)

            # Find if this term matches the document
            for entry in posting_entries:
                entry_key = f"{entry['repo']}:{entry['file']}"
                if entry_key != document_key:
                    continue

                title_lower = entry.get("title", "").lower()
                excerpt_lower = entry.get("excerpt", "").lower()

                if term_lower in title_lower or term_lower in excerpt_lower:
                    # Boost for title matches
                    boost = 2.0 if term_lower in title_lower else 1.0
                    total_score += term_idf * boost
                    matched_count += 1
                    break

        # Normalize by number of query terms for query coverage
        if query_terms:
            coverage = matched_count / len(query_terms)
            total_score *= (0.5 + 0.5 * coverage)

        return total_score


# ---------------------------------------------------------------------------
# Search Result
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    """A single search result with scoring metadata."""
    repo: str
    file: str
    title: str
    artifact_type: str
    domains: List[str]
    language: Optional[str]
    excerpt: str
    score: float
    matched_terms: List[str]
    fuzzy_corrections: List[Tuple[str, str, float]]  # (original, corrected, similarity)
    rank: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rank": self.rank,
            "repo": self.repo,
            "file": self.file,
            "title": self.title,
            "artifact_type": self.artifact_type,
            "domains": self.domains,
            "language": self.language,
            "excerpt": self.excerpt,
            "score": round(self.score, 4),
            "matched_terms": self.matched_terms,
            "fuzzy_corrections": [
                {"original": o, "corrected": c, "similarity": round(s, 3)}
                for o, c, s in self.fuzzy_corrections
            ],
        }


# ---------------------------------------------------------------------------
# Search Query
# ---------------------------------------------------------------------------

@dataclass
class SearchQuery:
    """A parsed search query with filters."""
    raw_query: str
    terms: List[str]
    domains: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    orgs: List[str] = field(default_factory=list)
    artifact_types: List[str] = field(default_factory=list)
    since_date: Optional[str] = None  # ISO timestamp
    until_date: Optional[str] = None   # ISO timestamp
    limit: int = 20
    offset: int = 0
    fuzzy: bool = True
    min_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "terms": self.terms,
            "filters": {
                "domains": self.domains,
                "languages": self.languages,
                "orgs": self.orgs,
                "artifact_types": self.artifact_types,
                "since_date": self.since_date,
                "until_date": self.until_date,
            },
            "limit": self.limit,
            "offset": self.offset,
            "fuzzy": self.fuzzy,
            "min_score": self.min_score,
        }


# ---------------------------------------------------------------------------
# Search Engine
# ---------------------------------------------------------------------------

class FleetSearchEngine:
    """
    Full-text search engine for the fleet knowledge index.

    Features:
    - TF-IDF scoring with BM25-style term saturation
    - Fuzzy matching for misspelled queries
    - Multi-dimensional filtering (domain, language, org, type, date)
    - Domain-aware query expansion
    - Aggregate search statistics
    """

    def __init__(self, index_file: Optional[str] = None):
        """
        Initialize the search engine.

        Args:
            index_file: Path to the fleet knowledge index JSON file.
        """
        self.index_file = index_file or DEFAULT_INDEX_FILE
        self.index_data: Dict[str, Any] = {}
        self.classifier = DomainClassifier()
        self.tfidf_scorer: Optional[TFIDFScorer] = None
        self._all_terms: Set[str] = set()
        self._all_domains: Set[str] = set()
        self._all_languages: Set[str] = set()
        self._all_orgs: Set[str] = set()

    def load_index(self, index_file: Optional[str] = None) -> None:
        """Load the fleet knowledge index from disk."""
        path = index_file or self.index_file

        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Index file not found: {path}\n"
                "Run 'python index_builder.py build' first."
            )

        with open(path, "r") as f:
            self.index_data = json.load(f)

        self.tfidf_scorer = TFIDFScorer(self.index_data)

        # Pre-compute index metadata for filtering
        self._all_terms = set(self.index_data.get("inverted_index", {}).keys())
        self._all_domains = set(self.index_data.get("domain_index", {}).keys())
        self._all_languages = set(self.index_data.get("language_index", {}).keys())
        self._all_orgs = set(self.index_data.get("org_index", {}).keys())
        self.inverted_index = self.index_data.get("inverted_index", {})
        self.domain_index = self.index_data.get("domain_index", {})

        print(f"Loaded index: {self.index_data.get('total_repos', 0)} repos, "
              f"{self.index_data.get('total_artifacts', 0)} artifacts, "
              f"{len(self._all_terms)} indexed terms, "
              f"{len(self._all_domains)} domains")

    def parse_query(
        self,
        query: str,
        domains: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        orgs: Optional[List[str]] = None,
        artifact_types: Optional[List[str]] = None,
        since_date: Optional[str] = None,
        until_date: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        fuzzy: bool = True,
        min_score: float = 0.0,
    ) -> SearchQuery:
        """
        Parse a search query string into a SearchQuery object.

        Handles quoted phrases, negation, and implicit domain hints.
        """
        # Extract quoted phrases
        phrases = re.findall(r'"([^"]+)"', query)
        # Remove quoted phrases from query for tokenization
        remaining = re.sub(r'"[^"]*"', "", query)

        # Tokenize remaining query
        tokens = re.findall(r"[a-zA-Z_][\w.-]*", remaining.lower())

        # Remove stop words
        terms = [t for t in tokens if t not in STOP_WORDS and len(t) >= 2]

        # Add phrase terms
        for phrase in phrases:
            phrase_terms = phrase.lower().split()
            terms.extend([t for t in phrase_terms if t not in STOP_WORDS])

        return SearchQuery(
            raw_query=query,
            terms=terms,
            domains=domains or [],
            languages=languages or [],
            orgs=orgs or [],
            artifact_types=artifact_types or [],
            since_date=since_date,
            until_date=until_date,
            limit=limit,
            offset=offset,
            fuzzy=fuzzy,
            min_score=min_score,
        )

    def _find_fuzzy_corrections(
        self, query: SearchQuery
    ) -> Tuple[List[Tuple[str, str, float]], Dict[str, List[Tuple[str, float]]]]:
        """
        Find fuzzy corrections for query terms that don't match any index terms.

        Returns:
            corrections: List of (original_term, corrected_term, similarity)
            fuzzy_expansions: Dict mapping original_term -> list of (matched_term, score)
        """
        corrections = []
        expansions = {}

        for term in query.terms:
            term_lower = term.lower()

            # Check if exact match exists
            if term_lower in self._all_terms:
                continue

            # Also check common variations (plural, -ing, -ed, etc.)
            stem_variants = {
                term_lower,
                term_lower.rstrip("s"),
                term_lower.rstrip("es"),
                term_lower.rstrip("ing"),
                term_lower.rstrip("ed"),
                term_lower.rstrip("tion"),
                term_lower.rstrip("ment"),
            }
            if stem_variants & self._all_terms:
                continue

            # Find fuzzy matches
            fuzzy_matches = find_fuzzy_matches(
                term_lower, self._all_terms, threshold=0.65
            )
            if fuzzy_matches:
                best_match, best_score = fuzzy_matches[0]
                corrections.append((term_lower, best_match, best_score))
                expansions[term_lower] = fuzzy_matches

        return corrections, expansions

    def _expand_with_domains(
        self, query: SearchQuery
    ) -> List[str]:
        """
        Expand query terms based on domain classification.

        If the query strongly suggests a specific domain, add domain-specific
        keywords to improve recall.
        """
        expanded_terms = list(query.terms)

        # Classify the query itself
        suggestions = self.classifier.suggest_domains_for_query(query.raw_query)
        if suggestions and suggestions[0][1] >= 0.6:
            primary_domain = suggestions[0][0]
            domain_info = self.classifier.domains.get(primary_domain)
            if domain_info:
                # Add top domain keywords as expansion terms
                for keyword in domain_info.keywords[:5]:
                    kw_lower = keyword.lower()
                    if kw_lower not in expanded_terms and len(kw_lower.split()) <= 2:
                        expanded_terms.append(kw_lower)

        return expanded_terms

    def _apply_filters(
        self,
        postings: List[Dict[str, Any]],
        query: SearchQuery,
    ) -> List[Dict[str, Any]]:
        """Apply domain, language, org, type, and date filters to postings."""
        filtered = postings

        if query.domains:
            domain_set = set(d.lower() for d in query.domains)
            filtered = [
                p for p in filtered
                if any(d.lower() in domain_set for d in p.get("domains", []))
            ]

        if query.languages:
            lang_set = set(l.lower() for l in query.languages)
            filtered = [
                p for p in filtered
                if p.get("language", "").lower() in lang_set
            ]

        if query.orgs:
            org_set = set(o.lower() for o in query.orgs)
            filtered = [
                p for p in filtered
                if p.get("repo", "").split("/")[0].lower() in org_set
                or p.get("repo", "").lower().startswith(tuple(o.lower() for o in query.orgs))
            ]

        if query.artifact_types:
            type_set = set(t.lower() for t in query.artifact_types)
            filtered = [
                p for p in filtered
                if p.get("type", "").lower() in type_set
            ]

        return filtered

    def search(self, query: SearchQuery) -> List[SearchResult]:
        """
        Execute a search against the fleet knowledge index.

        Args:
            query: A parsed SearchQuery object.

        Returns:
            List of SearchResult objects, ranked by relevance score.
        """
        start_time = time.time()

        if not self.tfidf_scorer:
            raise RuntimeError("Index not loaded. Call load_index() first.")

        # Find fuzzy corrections for misspelled terms
        fuzzy_corrections = []
        fuzzy_expansions = {}
        if query.fuzzy:
            fuzzy_corrections, fuzzy_expansions = self._find_fuzzy_corrections(query)

        # Expand query with domain-aware terms
        expanded_terms = self._expand_with_domains(query)

        # Collect candidate postings from inverted index
        all_postings: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        matched_terms = set()

        for term in expanded_terms:
            term_lower = term.lower()

            # Exact match
            if term_lower in self.inverted_index:
                for posting in self.inverted_index[term_lower]:
                    doc_key = f"{posting['repo']}:{posting['file']}"
                    all_postings[doc_key].append(posting)
                    matched_terms.add(term_lower)

            # Fuzzy expansion matches
            if term_lower in fuzzy_expansions:
                for fuzzy_match, score in fuzzy_expansions[term_lower]:
                    if fuzzy_match in self.inverted_index:
                        for posting in self.inverted_index[fuzzy_match]:
                            doc_key = f"{posting['repo']}:{posting['file']}"
                            all_postings[doc_key].append(posting)
                            matched_terms.add(term_lower)

        # Flatten postings for filtering
        flat_postings = []
        for doc_key, postings in all_postings.items():
            # Use the first posting as representative (merge domains)
            merged = dict(postings[0])
            merged["_doc_key"] = doc_key
            merged["_all_postings"] = postings
            merged["_posting_count"] = len(postings)
            # Merge domains from all postings
            all_domains = set()
            for p in postings:
                all_domains.update(p.get("domains", []))
            merged["domains"] = list(all_domains)
            flat_postings.append(merged)

        # Apply filters
        filtered_postings = self._apply_filters(flat_postings, query)

        # Score each document
        scored_results: List[SearchResult] = []
        for posting in filtered_postings:
            doc_key = posting["_doc_key"]
            all_postings = posting["_all_postings"]

            # Compute TF-IDF score
            score = self.tfidf_scorer.score_document(
                query.terms, doc_key, all_postings
            )

            # Boost for multiple matching terms (breadth of relevance)
            breadth_boost = 1.0 + (posting["_posting_count"] - 1) * 0.1
            score *= breadth_boost

            if score < query.min_score:
                continue

            # Determine fuzzy corrections relevant to this result
            result_corrections = []
            for original, corrected, similarity in fuzzy_corrections:
                excerpt_lower = posting.get("excerpt", "").lower()
                title_lower = posting.get("title", "").lower()
                if corrected.lower() in title_lower or corrected.lower() in excerpt_lower:
                    result_corrections.append((original, corrected, similarity))

            result = SearchResult(
                repo=posting.get("repo", ""),
                file=posting.get("file", ""),
                title=posting.get("title", ""),
                artifact_type=posting.get("type", ""),
                domains=posting.get("domains", []),
                language=posting.get("language"),
                excerpt=posting.get("excerpt", ""),
                score=score,
                matched_terms=list(matched_terms),
                fuzzy_corrections=result_corrections,
            )
            scored_results.append(result)

        # Sort by score descending
        scored_results.sort(key=lambda r: r.score, reverse=True)

        # Apply pagination
        paginated = scored_results[query.offset : query.offset + query.limit]

        # Assign ranks
        for i, result in enumerate(paginated):
            result.rank = query.offset + i + 1

        elapsed = time.time() - start_time

        print(f"\nSearch completed in {elapsed:.3f}s")
        print(f"  Query: '{query.raw_query}'")
        print(f"  Terms: {query.terms}")
        if fuzzy_corrections:
            print(f"  Fuzzy corrections: {[(o, c) for o, c, _ in fuzzy_corrections]}")
        print(f"  Results: {len(paginated)} shown, {len(scored_results)} total matches")

        return paginated

    def search_simple(
        self,
        query_str: str,
        domain: Optional[str] = None,
        language: Optional[str] = None,
        org: Optional[str] = None,
        artifact_type: Optional[str] = None,
        limit: int = 20,
        fuzzy: bool = True,
    ) -> List[SearchResult]:
        """
        Convenience method for simple searches.

        Args:
            query_str: Raw query string.
            domain: Filter by domain name.
            language: Filter by programming language.
            org: Filter by organization.
            artifact_type: Filter by artifact type (code, doc, test, readme, config).
            limit: Maximum results to return.
            fuzzy: Enable fuzzy matching.

        Returns:
            List of SearchResult objects.
        """
        query = self.parse_query(
            query_str,
            domains=[domain] if domain else None,
            languages=[language] if language else None,
            orgs=[org] if org else None,
            artifact_types=[artifact_type] if artifact_type else None,
            limit=limit,
            fuzzy=fuzzy,
        )
        return self.search(query)

    def get_domain_stats(self, domain_name: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a specific knowledge domain."""
        stats = self.index_data.get("domain_statistics", {}).get(domain_name)
        if stats:
            domain_info = self.classifier.domains.get(domain_name)
            if domain_info:
                stats["name"] = domain_info.name
                stats["display_name"] = domain_info.display_name
                stats["description"] = domain_info.description
                stats["category"] = domain_info.category.value
                stats["related"] = list(domain_info.related_domains)
        return stats

    def list_available_domains(self) -> List[Dict[str, Any]]:
        """List all domains available in the index with statistics."""
        domain_stats = self.index_data.get("domain_statistics", {})
        results = []

        for domain_name, stats in domain_stats.items():
            domain_info = self.classifier.domains.get(domain_name)
            results.append({
                "name": domain_name,
                "display_name": domain_info.display_name if domain_info else domain_name,
                "description": domain_info.description if domain_info else "",
                "category": domain_info.category.value if domain_info else "unknown",
                "artifact_count": stats.get("artifact_count", 0),
                "repo_count": stats.get("repo_count", 0),
                "avg_score": stats.get("avg_score", 0),
                "top_languages": stats.get("top_languages", {}),
                "sample_repos": stats.get("representative_repos", [])[:5],
            })

        results.sort(key=lambda x: x["artifact_count"], reverse=True)
        return results

    def list_available_languages(self) -> List[Tuple[str, int]]:
        """List all languages available in the index."""
        lang_index = self.index_data.get("language_index", {})
        return sorted(
            [(lang, len(repos)) for lang, repos in lang_index.items()],
            key=lambda x: x[1],
            reverse=True,
        )

    def list_available_orgs(self) -> List[Tuple[str, int]]:
        """List all organizations available in the index."""
        org_index = self.index_data.get("org_index", {})
        return sorted(
            [(org, len(repos)) for org, repos in org_index.items()],
            key=lambda x: x[1],
            reverse=True,
        )

    def suggest_query(self, query_str: str) -> Dict[str, Any]:
        """
        Suggest query improvements including fuzzy corrections and domain hints.

        Returns:
            Dict with suggestions, corrections, and recommended domains.
        """
        query = self.parse_query(query_str)
        corrections, expansions = self._find_fuzzy_corrections(query)
        domain_suggestions = self.classifier.suggest_domains_for_query(query_str)

        # Check which terms have index matches
        term_status = {}
        for term in query.terms:
            term_lower = term.lower()
            has_match = term_lower in self._all_terms
            fuzzy_for_term = expansions.get(term_lower, [])
            term_status[term] = {
                "in_index": has_match,
                "fuzzy_matches": [(m, round(s, 3)) for m, s in fuzzy_for_term[:3]],
            }

        return {
            "original_query": query_str,
            "parsed_terms": query.terms,
            "term_status": term_status,
            "fuzzy_corrections": [
                {"original": o, "suggested": c, "confidence": round(s, 3)}
                for o, c, s in corrections
            ],
            "suggested_domains": [
                {"domain": d, "confidence": round(c, 3)}
                for d, c in domain_suggestions
            ],
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get overall search engine statistics."""
        return {
            "total_repos": self.index_data.get("total_repos", 0),
            "total_artifacts": self.index_data.get("total_artifacts", 0),
            "indexed_terms": len(self._all_terms),
            "indexed_domains": len(self._all_domains),
            "languages": len(self._all_languages),
            "organizations": len(self._all_orgs),
            "index_version": self.index_data.get("index_version", "unknown"),
            "build_timestamp": self.index_data.get("build_timestamp", "unknown"),
        }


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def format_results_text(results: List[SearchResult], verbose: bool = False) -> str:
    """Format search results as human-readable text."""
    if not results:
        return "No results found."

    lines = []
    for result in results:
        lines.append(f"--- Result #{result.rank} (score: {result.score:.4f}) ---")
        lines.append(f"  Repo:     {result.repo}")
        lines.append(f"  File:     {result.file}")
        lines.append(f"  Title:    {result.title}")
        lines.append(f"  Type:     {result.artifact_type}")
        lines.append(f"  Domains:  {', '.join(result.domains)}")
        if result.language:
            lines.append(f"  Language: {result.language}")
        lines.append(f"  Excerpt:  {result.excerpt[:250]}")
        if result.fuzzy_corrections:
            corrections_str = ", ".join(
                f"'{orig}' → '{corr}' ({sim:.0%})"
                for orig, corr, sim in result.fuzzy_corrections
            )
            lines.append(f"  Fuzzy:    {corrections_str}")
        if verbose:
            lines.append(f"  Matched:  {', '.join(result.matched_terms)}")
        lines.append("")

    return "\n".join(lines)


def format_results_json(results: List[SearchResult], query: Optional[SearchQuery] = None) -> str:
    """Format search results as JSON."""
    output = {
        "query": query.to_dict() if query else None,
        "result_count": len(results),
        "results": [r.to_dict() for r in results],
    }
    return json.dumps(output, indent=2)


def format_suggestions_text(suggestions: Dict[str, Any]) -> str:
    """Format query suggestions as human-readable text."""
    lines = ["Query Suggestions:", ""]

    if suggestions.get("fuzzy_corrections"):
        lines.append("Fuzzy corrections:")
        for corr in suggestions["fuzzy_corrections"]:
            lines.append(f"  '{corr['original']}' → '{corr['suggested']}' "
                         f"(confidence: {corr['confidence']:.0%})")
        lines.append("")

    if suggestions.get("suggested_domains"):
        lines.append("Suggested knowledge domains:")
        for dom in suggestions["suggested_domains"]:
            lines.append(f"  {dom['domain']}: {dom['confidence']:.0%}")
        lines.append("")

    term_status = suggestions.get("term_status", {})
    missing_terms = [t for t, s in term_status.items() if not s["in_index"]]
    if missing_terms:
        lines.append(f"Terms not found in index: {', '.join(missing_terms)}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI Interface
# ---------------------------------------------------------------------------

def main():
    """CLI entry point for the search engine."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fleet Knowledge Search Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic search
  %(prog)s search "CUDA kernel optimization"

  # Filter by domain
  %(prog)s search "memory allocator" --domain runtimes

  # Filter by language
  %(prog)s search "parser combinator" --language rust

  # Filter by organization
  %(prog)s search "agent dispatch" --org SuperInstance

  # Fuzzy search (handles misspellings)
  %(prog)s search "kernl optimiztion" --fuzzy

  # Get query suggestions
  %(prog)s suggest "how does the fleet handle agent dispatch?"

  # View statistics
  %(prog)s stats

  # List domains
  %(prog)s list-domains

  # List languages
  %(prog)s list-languages
        """,
    )

    parser.add_argument(
        "--index-file", default=None,
        help=f"Path to index file (default: {DEFAULT_INDEX_FILE})",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # search command
    search_parser = subparsers.add_parser("search", help="Search the fleet knowledge index")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--domain", default=None, help="Filter by domain")
    search_parser.add_argument("--language", default=None, help="Filter by language")
    search_parser.add_argument("--org", default=None, help="Filter by organization")
    search_parser.add_argument("--type", dest="artifact_type", default=None,
                               help="Filter by artifact type (code, doc, test, readme, config)")
    search_parser.add_argument("--limit", type=int, default=20, help="Max results")
    search_parser.add_argument("--offset", type=int, default=0, help="Result offset")
    search_parser.add_argument("--no-fuzzy", action="store_true", help="Disable fuzzy matching")
    search_parser.add_argument("--json", action="store_true", help="Output as JSON")
    search_parser.add_argument("--verbose", action="store_true", help="Verbose output")

    # suggest command
    suggest_parser = subparsers.add_parser("suggest", help="Get query suggestions")
    suggest_parser.add_argument("query", help="Query to analyze")
    suggest_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # stats command
    subparsers.add_parser("stats", help="Show search engine statistics")

    # list-domains command
    subparsers.add_parser("list-domains", help="List all indexed domains")

    # list-languages command
    subparsers.add_parser("list-languages", help="List all indexed languages")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    engine = FleetSearchEngine(index_file=args.index_file)

    try:
        engine.load_index()
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.command == "search":
        results = engine.search_simple(
            query_str=args.query,
            domain=args.domain,
            language=args.language,
            org=args.org,
            artifact_type=args.artifact_type,
            limit=args.limit,
            fuzzy=not args.no_fuzzy,
        )

        if args.json:
            query_obj = engine.parse_query(args.query)
            print(format_results_json(results, query_obj))
        else:
            print(format_results_text(results, verbose=args.verbose))

    elif args.command == "suggest":
        suggestions = engine.suggest_query(args.query)
        if args.json:
            print(json.dumps(suggestions, indent=2))
        else:
            print(format_suggestions_text(suggestions))

    elif args.command == "stats":
        stats = engine.get_stats()
        print("Fleet Knowledge Index Statistics")
        print("=" * 40)
        for key, value in stats.items():
            print(f"  {key}: {value}")

    elif args.command == "list-domains":
        domains = engine.list_available_domains()
        print(f"Indexed Knowledge Domains ({len(domains)}):")
        print("=" * 60)
        for d in domains:
            print(f"\n  {d['display_name']} ({d['name']})")
            print(f"    Category: {d['category']}")
            print(f"    Artifacts: {d['artifact_count']} across {d['repo_count']} repos")
            print(f"    Avg Score: {d['avg_score']:.4f}")
            if d.get("top_languages"):
                langs = ", ".join(f"{l}({c})" for l, c in list(d["top_languages"].items())[:3])
                print(f"    Languages: {langs}")

    elif args.command == "list-languages":
        languages = engine.list_available_languages()
        print(f"Indexed Languages ({len(languages)}):")
        print("=" * 40)
        for lang, count in languages:
            print(f"  {lang}: {count} repos")


if __name__ == "__main__":
    main()
