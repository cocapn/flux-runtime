"""
Beachcomb — scheduled scavenging across repos, APIs, and data sources.

An agent dynamically sets what to check, how often, and what to do
with what it finds. The cron IS the beachcomb — walk the shore, pick
up what's interesting, decide what to keep.

Usage:
    from flux.open_interp.beachcomb import Beachcomber, Sweep, SweepResult
    
    bc = Beachcomber("oracle1")
    
    # Add sweeps dynamically
    bc.add_sweep(Sweep(
        name="jetsonclaw1-bottles",
        source_type="git-folder",
        source="https://github.com/Lucineer/JetsonClaw1-vessel/message-in-a-bottle/for-oracle1/",
        interval_minutes=60,
        on_find="notify",  # notify | commit | pr | silent
        notify_channel="telegram",
        priority="medium",
    ))
    
    bc.add_sweep(Sweep(
        name="lucineer-commits",
        source_type="git-commits",
        source="https://github.com/Lucineer/JetsonClaw1-vessel",
        interval_minutes=15,
        on_find="commit",
        notify_channel="none",
        filter_pattern="\x5bI2I:",
    ))
    
    # Run all due sweeps
    results = bc.sweep_all()
"""

import re
import json
import time
import os
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


class SourceType(Enum):
    GIT_FOLDER = "git-folder"         # message-in-a-bottle folders
    GIT_COMMITS = "git-commits"       # commit feed from a repo
    GIT_ISSUES = "git-issues"         # issues on a repo
    GIT_PRS = "git-prs"               # pull requests
    API_JSON = "api-json"             # arbitrary JSON API endpoint
    RSS = "rss"                       # RSS/Atom feed
    STOCK = "stock"                   # stock price check
    CUSTOM = "custom"                 # user-defined source


class OnFind(Enum):
    NOTIFY = "notify"       # Tell the human immediately
    COMMIT = "commit"       # Commit findings to repo
    PR = "pr"               # Open a PR with findings
    SILENT = "silent"       # Just log, don't act
    BOTTLE = "bottle"       # Drop a message-in-a-bottle response
    TELL_ASSOCIATE = "tell" # Send I2I:TEL to an associate


class Priority(Enum):
    URGENT = "urgent"       # Drop everything, tell Casey NOW
    HIGH = "high"           # Notify within the hour
    MEDIUM = "medium"       # Next heartbeat check
    LOW = "low"             # Log it, Casey reads the commit feed
    BACKGROUND = "background"  # Pure research, may never surface


@dataclass
class Sweep:
    """A single beachcomb sweep — one thing to check periodically."""
    name: str
    source_type: SourceType
    source: str                                    # URL or path
    interval_minutes: int = 60                     # How often to check
    on_find: OnFind = OnFind.SILENT                # What to do with findings
    notify_channel: str = "none"                   # telegram | github-issue | none
    priority: Priority = Priority.MEDIUM           # How important
    filter_pattern: str = ""                       # Regex to match (optional)
    max_items: int = 10                            # Max items per sweep
    handler: Optional[str] = None                  # Custom handler function name
    active: bool = True
    last_sweep: float = 0.0                        # Timestamp of last check
    last_etag: str = ""                            # For conditional requests
    metadata: Dict = field(default_factory=dict)   # Source-specific config
    
    def is_due(self) -> bool:
        """Is this sweep due for a check?"""
        if not self.active:
            return False
        return (time.time() - self.last_sweep) >= (self.interval_minutes * 60)
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source_type": self.source_type.value,
            "source": self.source,
            "interval_minutes": self.interval_minutes,
            "on_find": self.on_find.value,
            "notify_channel": self.notify_channel,
            "priority": self.priority.value,
            "filter_pattern": self.filter_pattern,
            "max_items": self.max_items,
            "active": self.active,
            "last_sweep": self.last_sweep,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Sweep':
        return cls(
            name=data["name"],
            source_type=SourceType(data["source_type"]),
            source=data["source"],
            interval_minutes=data.get("interval_minutes", 60),
            on_find=OnFind(data.get("on_find", "silent")),
            notify_channel=data.get("notify_channel", "none"),
            priority=Priority(data.get("priority", "medium")),
            filter_pattern=data.get("filter_pattern", ""),
            max_items=data.get("max_items", 10),
            active=data.get("active", True),
            last_sweep=data.get("last_sweep", 0.0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class SweepResult:
    """What the beachcomber found on one sweep."""
    sweep_name: str
    timestamp: float
    items_found: int
    items: List[Dict] = field(default_factory=list)
    action_taken: str = ""
    error: str = ""
    
    @property
    def has_findings(self) -> bool:
        return self.items_found > 0


class Beachcomber:
    """
    The beachcomber walks the shore, checking for bottles, 
    commits, news, prices — whatever the agent has configured.
    
    Sweeps are dynamic. The agent (or the human) can add, remove,
    and reconfigure sweeps at any time. The beachcomber remembers
    what it's already seen (via last_sweep timestamps and etags).
    """
    
    def __init__(self, agent_name: str, config_path: Optional[str] = None):
        self.agent_name = agent_name
        self.sweeps: Dict[str, Sweep] = {}
        self.history: List[SweepResult] = []
        self.config_path = config_path
        self._seen: Dict[str, set] = {}  # sweep_name -> set of seen item IDs
        
        if config_path and os.path.exists(config_path):
            self.load(config_path)
    
    def add_sweep(self, sweep: Sweep) -> None:
        """Add a new sweep to the schedule."""
        self.sweeps[sweep.name] = sweep
        self._seen[sweep.name] = set()
        if self.config_path:
            self.save(self.config_path)
    
    def remove_sweep(self, name: str) -> bool:
        """Remove a sweep by name."""
        if name in self.sweeps:
            del self.sweeps[name]
            self._seen.pop(name, None)
            if self.config_path:
                self.save(self.config_path)
            return True
        return False
    
    def update_sweep(self, name: str, **kwargs) -> bool:
        """Update a sweep's settings dynamically."""
        if name not in self.sweeps:
            return False
        sweep = self.sweeps[name]
        for key, value in kwargs.items():
            if hasattr(sweep, key):
                if key in ("source_type", "on_find", "priority"):
                    enum_map = {
                        "source_type": SourceType,
                        "on_find": OnFind,
                        "priority": Priority,
                    }
                    value = enum_map[key](value)
                setattr(sweep, key, value)
        if self.config_path:
            self.save(self.config_path)
        return True
    
    def sweep_all(self) -> List[SweepResult]:
        """Run all due sweeps. Returns results for sweeps that found items."""
        results = []
        for name, sweep in self.sweeps.items():
            if sweep.is_due():
                result = self._run_sweep(sweep)
                sweep.last_sweep = time.time()
                results.append(result)
                if result.has_findings:
                    self.history.append(result)
        if self.config_path:
            self.save(self.config_path)
        return results
    
    def sweep_one(self, name: str) -> Optional[SweepResult]:
        """Force-run a single sweep by name, regardless of interval."""
        sweep = self.sweeps.get(name)
        if not sweep:
            return None
        result = self._run_sweep(sweep)
        sweep.last_sweep = time.time()
        if self.config_path:
            self.save(self.config_path)
        return result
    
    def due_sweeps(self) -> List[str]:
        """Which sweeps are currently due?"""
        return [name for name, sweep in self.sweeps.items() if sweep.is_due()]
    
    def status(self) -> dict:
        """Current beachcomb status."""
        return {
            "agent": self.agent_name,
            "total_sweeps": len(self.sweeps),
            "active_sweeps": sum(1 for s in self.sweeps.values() if s.active),
            "due_now": self.due_sweeps(),
            "total_findings": len(self.history),
            "sweeps": {name: {
                "source_type": s.source_type.value,
                "interval_min": s.interval_minutes,
                "last_sweep": s.last_sweep,
                "due": s.is_due(),
                "on_find": s.on_find.value,
                "priority": s.priority.value,
            } for name, s in self.sweeps.items()},
        }
    
    def _run_sweep(self, sweep: Sweep) -> SweepResult:
        """Run a single sweep. Returns findings."""
        result = SweepResult(
            sweep_name=sweep.name,
            timestamp=time.time(),
            items_found=0,
        )
        
        if sweep.source_type == SourceType.GIT_FOLDER:
            result = self._sweep_git_folder(sweep)
        elif sweep.source_type == SourceType.GIT_COMMITS:
            result = self._sweep_git_commits(sweep)
        elif sweep.source_type == SourceType.GIT_ISSUES:
            result = self._sweep_git_issues(sweep)
        elif sweep.source_type == SourceType.API_JSON:
            result = self._sweep_api(sweep)
        else:
            result.error = f"Unsupported source type: {sweep.source_type.value}"
        
        return result
    
    def _sweep_git_folder(self, sweep: Sweep) -> SweepResult:
        """Check a message-in-a-bottle folder in another repo."""
        result = SweepResult(sweep_name=sweep.name, timestamp=time.time(), items_found=0)
        # Parse owner/repo/path from source URL
        match = re.match(r'https://github\.com/([^/]+)/([^/]+)/(.+)', sweep.source)
        if not match:
            result.error = f"Cannot parse source URL: {sweep.source}"
            return result
        
        owner, repo, path = match.groups()
        # Use GitHub API to list folder contents
        try:
            import urllib.request
            token = os.environ.get('GITHUB_TOKEN', '')
            headers = {}
            if token:
                headers['Authorization'] = f'token {token}'
            if sweep.last_etag:
                headers['If-None-Match'] = sweep.last_etag
            
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                # Capture etag for conditional requests
                sweep.last_etag = resp.headers.get('ETag', '')
                data = json.loads(resp.read().decode())
            
            if not isinstance(data, list):
                data = [data]
            
            seen = self._seen.get(sweep.name, set())
            for item in data:
                item_name = item.get('name', '')
                item_sha = item.get('sha', '')
                item_id = f"{item_name}:{item_sha}"
                
                if item_id in seen:
                    continue
                if sweep.filter_pattern and not re.search(sweep.filter_pattern, item_name):
                    continue
                
                result.items.append({
                    "name": item_name,
                    "path": item.get('path', ''),
                    "url": item.get('html_url', ''),
                    "sha": item_sha,
                    "size": item.get('size', 0),
                    "type": item.get('type', ''),
                })
                seen.add(item_id)
            
            self._seen[sweep.name] = seen
            result.items_found = len(result.items)
            result.action_taken = sweep.on_find.value
            
        except Exception as e:
            result.error = str(e)
        
        return result
    
    def _sweep_git_commits(self, sweep: Sweep) -> SweepResult:
        """Check recent commits on a repo."""
        result = SweepResult(sweep_name=sweep.name, timestamp=time.time(), items_found=0)
        match = re.match(r'https://github\.com/([^/]+)/([^/]+)/?$', sweep.source)
        if not match:
            result.error = f"Cannot parse repo URL: {sweep.source}"
            return result
        
        owner, repo = match.groups()
        try:
            import urllib.request
            token = os.environ.get('GITHUB_TOKEN', '')
            headers = {'Accept': 'application/vnd.github.v3+json'}
            if token:
                headers['Authorization'] = f'token {token}'
            
            url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page={sweep.max_items}"
            if sweep.last_sweep > 0:
                since = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(sweep.last_sweep))
                url += f"&since={since}"
            
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                commits = json.loads(resp.read().decode())
            
            seen = self._seen.get(sweep.name, set())
            for commit in commits:
                sha = commit.get('sha', '')[:7]
                message = commit.get('commit', {}).get('message', '').split('\n')[0]
                
                if sha in seen:
                    continue
                if sweep.filter_pattern and not re.search(sweep.filter_pattern, message):
                    continue
                
                result.items.append({
                    "sha": sha,
                    "message": message,
                    "author": commit.get('commit', {}).get('author', {}).get('name', ''),
                    "url": commit.get('html_url', ''),
                    "date": commit.get('commit', {}).get('author', {}).get('date', ''),
                })
                seen.add(sha)
            
            self._seen[sweep.name] = seen
            result.items_found = len(result.items)
            result.action_taken = sweep.on_find.value
            
        except Exception as e:
            result.error = str(e)
        
        return result
    
    def _sweep_git_issues(self, sweep: Sweep) -> SweepResult:
        """Check issues on a repo."""
        result = SweepResult(sweep_name=sweep.name, timestamp=time.time(), items_found=0)
        match = re.match(r'https://github\.com/([^/]+)/([^/]+)/?$', sweep.source)
        if not match:
            result.error = f"Cannot parse repo URL: {sweep.source}"
            return result
        
        owner, repo = match.groups()
        try:
            import urllib.request
            token = os.environ.get('GITHUB_TOKEN', '')
            headers = {'Accept': 'application/vnd.github.v3+json'}
            if token:
                headers['Authorization'] = f'token {token}'
            
            url = f"https://api.github.com/repos/{owner}/{repo}/issues?state=open&per_page={sweep.max_items}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                issues = json.loads(resp.read().decode())
            
            seen = self._seen.get(sweep.name, set())
            for issue in issues:
                num = str(issue.get('number', ''))
                if num in seen:
                    continue
                title = issue.get('title', '')
                if sweep.filter_pattern and not re.search(sweep.filter_pattern, title):
                    continue
                
                result.items.append({
                    "number": num,
                    "title": title,
                    "url": issue.get('html_url', ''),
                    "author": issue.get('user', {}).get('login', ''),
                    "labels": [l.get('name', '') for l in issue.get('labels', [])],
                })
                seen.add(num)
            
            self._seen[sweep.name] = seen
            result.items_found = len(result.items)
            result.action_taken = sweep.on_find.value
            
        except Exception as e:
            result.error = str(e)
        
        return result
    
    def _sweep_api(self, sweep: Sweep) -> SweepResult:
        """Check a generic JSON API endpoint."""
        result = SweepResult(sweep_name=sweep.name, timestamp=time.time(), items_found=0)
        try:
            import urllib.request
            headers = sweep.metadata.get('headers', {})
            req = urllib.request.Request(sweep.source, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            
            # If it's a list, treat each item as a finding
            if isinstance(data, list):
                items = data[:sweep.max_items]
            elif isinstance(data, dict):
                # Try common envelope patterns
                items = data.get('items', data.get('results', data.get('data', [data])))
                if not isinstance(items, list):
                    items = [items]
            else:
                items = [data]
            
            result.items = items[:sweep.max_items]
            result.items_found = len(result.items)
            result.action_taken = sweep.on_find.value
            
        except Exception as e:
            result.error = str(e)
        
        return result
    
    def save(self, path: str) -> None:
        """Save beachcomb configuration to JSON."""
        data = {
            "agent": self.agent_name,
            "sweeps": {name: sweep.to_dict() for name, sweep in self.sweeps.items()},
            "history_count": len(self.history),
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load(self, path: str) -> None:
        """Load beachcomb configuration from JSON."""
        with open(path, 'r') as f:
            data = json.load(f)
        self.agent_name = data.get("agent", self.agent_name)
        for name, sweep_data in data.get("sweeps", {}).items():
            self.sweeps[name] = Sweep.from_dict(sweep_data)
            self._seen[name] = set()
