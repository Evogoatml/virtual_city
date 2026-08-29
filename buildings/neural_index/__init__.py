"""Neural Index — builds a knowledge graph over the codebase and auto-generates
AGENT.md context files for every building folder. Feeds the Shared Knowledge
Core (city.brain) so every building reads file-system context before acting.

Adapted from the pasted 'Distributed Agent System' script into the Virtual
City building contract: an Agent subclass with setup_schema + register_rules
+ work() + report() + employee_duty().
"""
from city.department import Department
from city.db import now_iso, log_event
import os
import json
import hashlib
import pickle
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Optional: watchdog for reactive file-change indexing
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler as _WDHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    class _WDHandler:  # fallback base when watchdog isn't installed
        def on_created(self, event): pass
        def on_modified(self, event): pass
        def on_deleted(self, event): pass
        def on_moved(self, event): pass


class CentralNeuralBackend:
    """Central neural network — single source of truth for file indexing.

    Stores a knowledge graph, file registry, and agent (AGENT.md) registry
    under .backend/ in the project root.
    """

    def __init__(self, root_dir=None):
        self.root_dir = root_dir or os.getcwd()
        self.backend_dir = os.path.join(self.root_dir, '.backend')

        # Central storage paths
        self.graph_db = os.path.join(self.backend_dir, 'knowledge_graph.pkl')
        self.registry_db = os.path.join(self.backend_dir, 'file_registry.json')
        self.agents_db = os.path.join(self.backend_dir, 'agents.json')

        # Neural state
        self.knowledge_graph = {}
        self.file_registry = {}
        self.agent_registry = {}  # track all AGENT.md files

        self._initialize()

    def _initialize(self):
        """Initialize central backend."""
        os.makedirs(self.backend_dir, exist_ok=True)
        os.makedirs(os.path.join(self.backend_dir, 'agents'), exist_ok=True)
        self._load_state()

    def _load_state(self):
        """Load neural network state from disk."""
        try:
            if os.path.exists(self.graph_db):
                with open(self.graph_db, 'rb') as f:
                    self.knowledge_graph = pickle.load(f)
        except Exception:
            self.knowledge_graph = {}

        try:
            if os.path.exists(self.registry_db):
                with open(self.registry_db, 'r') as f:
                    self.file_registry = json.load(f)
        except Exception:
            self.file_registry = {}

        try:
            if os.path.exists(self.agents_db):
                with open(self.agents_db, 'r') as f:
                    self.agent_registry = json.load(f)
        except Exception:
            self.agent_registry = {}

    def _save_state(self):
        """Save neural network state to disk."""
        with open(self.graph_db, 'wb') as f:
            pickle.dump(self.knowledge_graph, f)
        with open(self.registry_db, 'w') as f:
            json.dump(self.file_registry, f, indent=2)
        with open(self.agents_db, 'w') as f:
            json.dump(self.agent_registry, f, indent=2)

    def register_agent(self, folder_path, agent_path):
        """Register a new agent (AGENT.md) in the system."""
        agent_id = hashlib.md5(folder_path.encode()).hexdigest()[:8]
        self.agent_registry[agent_id] = {
            'folder': folder_path,
            'agent_file': agent_path,
            'created': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
        }
        self._save_state()
        return agent_id

    def get_folder_context(self, folder_path):
        """Get all files and metadata for a specific folder."""
        folder_files = {}
        for filepath, metadata in self.file_registry.items():
            if filepath.startswith(folder_path):
                rel_path = os.path.relpath(filepath, folder_path)
                folder_files[rel_path] = metadata
        return folder_files

    def index_file(self, filepath):
        """Index a single file into the neural network."""
        try:
            stat = os.stat(filepath)
            metadata = {
                'path': filepath,
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'extension': Path(filepath).suffix,
                'hash': self._calculate_hash(filepath),
            }
            self.file_registry[filepath] = metadata
            self.knowledge_graph[filepath] = {
                'metadata': metadata,
                'indexed_at': datetime.now().isoformat(),
            }
            self._save_state()
        except Exception:
            pass

    def _calculate_hash(self, filepath):
        """Calculate file hash for change detection."""
        hasher = hashlib.sha256()
        try:
            with open(filepath, 'rb') as f:
                hasher.update(f.read())
            return hasher.hexdigest()
        except Exception:
            return None

    def index_all(self, extensions=None, exclude_dirs=None):
        """Recursively index all files from root_dir down through subdirectories."""
        if exclude_dirs is None:
            exclude_dirs = {'.git', '.backend', '__pycache__', 'node_modules', '.venv',
                            'venv', '.idea', 'AGENT.md'}
        if extensions is None:
            extensions = {'.py', '.js', '.json', '.txt', '.md', '.yaml', '.yml',
                          '.toml', '.csv', '.html', '.css'}

        scanned = 0
        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for filename in files:
                filepath = os.path.join(root, filename)
                if filename == 'AGENT.md':
                    continue
                if extensions and Path(filepath).suffix not in extensions:
                    continue
                self.index_file(filepath)
                scanned += 1
        return scanned


class FolderAgent:
    """Agent for a specific folder — auto-populates AGENT.md."""

    def __init__(self, folder_path, neural_backend):
        self.folder_path = folder_path
        self.backend = neural_backend
        self.agent_file = os.path.join(folder_path, 'AGENT.md')
        self.agent_id = None

    def generate_agent_file(self):
        """Auto-populate AGENT.md with folder context."""
        folder_files = self.backend.get_folder_context(self.folder_path)
        agent_content = self._build_agent_content(folder_files)
        with open(self.agent_file, 'w') as f:
            f.write(agent_content)
        self.agent_id = self.backend.register_agent(self.folder_path, self.agent_file)

    def _build_agent_content(self, folder_files):
        """Build the AGENT.md content."""
        folder_name = os.path.basename(self.folder_path)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        files_by_ext = defaultdict(list)
        for rel_path, metadata in folder_files.items():
            ext = metadata.get('extension', 'no extension')
            files_by_ext[ext].append((rel_path, metadata))

        total_size = sum(m.get('size', 0) for m in folder_files.values())
        total_size_str = f"{total_size / 1024 / 1024:.2f}MB" if total_size > 1024 * 1024 else f"{total_size / 1024:.1f}KB"

        lines = [
            f"# AGENT - {folder_name}",
            "",
            f"**Auto-generated folder agent**  ",
            f"**Last Updated:** {timestamp}  ",
            f"**Folder Path:** `{self.folder_path}`  ",
            f"**Agent ID:** `{self.agent_id or 'pending'}`",
            "",
            "---",
            "",
            f"## Folder Context",
            "",
            f"This agent maintains awareness of all files in this folder.",
            "",
            f"### Files Tracked ({len(folder_files)})",
        ]

        for ext, files in sorted(files_by_ext.items()):
            label = ext if ext else 'No Extension'
            lines.append(f"")
            lines.append(f"#### {label} Files ({len(files)})")
            lines.append("")
            for rel_path, metadata in sorted(files):
                size = metadata.get('size', 0)
                size_str = f"{size / 1024:.1f}KB" if size > 1024 else f"{size}B"
                modified = metadata.get('modified', 'unknown')[:10]
                lines.append(f"- `{rel_path}`")
                lines.append(f"  - Size: {size_str}")
                lines.append(f"  - Modified: {modified}")

        lines.extend([
            "",
            "---",
            "",
            "## Statistics",
            "",
            f"- **Total Files:** {len(folder_files)}",
            f"- **Total Size:** {total_size_str}",
            f"- **File Types:** {len(files_by_ext)}",
            "",
            "---",
            "",
            "## Neural Network Connection",
            "",
            "This agent is connected to the central neural backend:",
            "- **Backend Path:** `.backend/`",
            "- **Knowledge Graph:** Shared across all agents",
            "- **Agent Registry:** `.backend/agents.json`",
            "",
            "---",
            "",
            "## Purpose",
            "",
            "This AGENT.md file provides:",
            "1. **Folder Awareness** - Know what files exist here",
            "2. **Context for AI** - Help AI understand this folder's purpose",
            "3. **Navigation** - Quick reference for developers",
            "4. **Neural Link** - Connection to central knowledge graph",
            "",
            "**Note:** This file is auto-generated. Do not edit manually.",
            "",
            "---",
            "",
            f"*Generated by Central Neural Ordinance System*  ",
            f"*Last scan: {timestamp}*",
        ])
        return '\n'.join(lines) + '\n'

    def update_agent_file(self):
        """Update existing AGENT.md with latest context."""
        self.generate_agent_file()


class FileMonitorHandler(_WDHandler):
    """Reactive file system event handler for live re-indexing."""

    def __init__(self, neural_system, extensions, agent_ref):
        self.neural_system = neural_system
        self.extensions = extensions
        self.agent = agent_ref

    def _should_process(self, filepath):
        if self.neural_system.backend_dir in filepath:
            return False
        if self.extensions and Path(filepath).suffix not in self.extensions:
            return False
        return True

    def on_created(self, event):
        if event.is_directory or not self._should_process(event.src_path):
            return
        self.neural_system.index_file(event.src_path)

    def on_modified(self, event):
        if event.is_directory or not self._should_process(event.src_path):
            return
        self.neural_system.index_file(event.src_path)

    def on_deleted(self, event):
        if event.is_directory or not self._should_process(event.src_path):
            return
        if event.src_path in self.neural_system.file_registry:
            del self.neural_system.file_registry[event.src_path]
        if event.src_path in self.neural_system.knowledge_graph:
            del self.neural_system.knowledge_graph[event.src_path]

    def on_moved(self, event):
        if event.is_directory:
            return
        if self._should_process(event.src_path):
            self.neural_system.file_registry.pop(event.src_path, None)
            self.neural_system.knowledge_graph.pop(event.src_path, None)
        if self._should_process(event.dest_path):
            self.neural_system.index_file(event.dest_path)


class NeuralIndexAgent(Department):
    """Neural Index — indexes the codebase, generates AGENT.md files,
    and feeds context into the Shared Knowledge Core (brain).

    Information gathering department of the Controll Panel command center.
    """

    building_name = "controll_panel"
    name = "neural_index"
    subject = "Neural Index"
    district = "Knowledge Core"
    color = "#9c27b0"

    job_title = "Knowledge Engineer"
    mission = "Keep the codebase knowledge graph fresh and every folder's AGENT.md current."
    cog_interval = 120  # re-scan every 2 min

    # Files to skip during indexing
    _EXCLUDE_DIRS = {'.git', '.backend', '__pycache__', 'node_modules', '.venv',
                     'venv', '.idea', '.hermes'}
    _EXTENSIONS = {'.py', '.js', '.json', '.txt', '.md', '.yaml', '.yml',
                   '.toml', '.csv', '.html', '.css'}

    def __init__(self, conn):
        self._backend = None
        self._observer = None
        super().__init__(conn)

    @property
    def backend(self):
        if self._backend is None:
            self._backend = CentralNeuralBackend()
        return self._backend

    def setup_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS neural_index_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filepath TEXT NOT NULL UNIQUE,
                extension TEXT,
                size INTEGER,
                modified TEXT,
                file_hash TEXT,
                indexed_at TEXT NOT NULL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS neural_agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL UNIQUE,
                folder TEXT NOT NULL,
                agent_file TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_updated TEXT NOT NULL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS neural_index_stats (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def register_rules(self):
        self.rule(r"^status$")(self._status)
        self.rule(r"^report$")(self._report)
        self.rule(r"^scan$")(self._scan)
        self.rule(r"^regenerate$")(self._regenerate_all)
        self.rule(r"^stats$")(self._stats)
        self.rule(r"^agents$")(self._list_agents)
        self.rule(r"^find related\s+(?P<filepath>.+)$")(self._find_related)
        self.rule(r"^query\s+(?P<term>.+)$")(self._query_graph)

    # ── handlers ──────────────────────────────────────────────────

    def _status(self):
        return self.report()

    def report(self):
        """Summary for City Hall's daily meeting."""
        stats = self._stats()
        return {
            "agent": self.name,
            "subject": self.subject,
            "backend_dir": self.backend.backend_dir,
            "indexed_files": stats.get("indexed_files", 0),
            "agents_generated": stats.get("agents_generated", 0),
            "monitoring": self._observer is not None,
        }

    def _report(self):
        return self.report()

    def _scan(self):
        """Run one indexing pass over the whole repo."""
        count = self.backend.index_all(
            extensions=self._EXTENSIONS,
            exclude_dirs=self._EXCLUDE_DIRS,
        )
        self._sync_to_db()
        self._save_stats()
        log_event(self.conn, self.name, "scan", f"indexed {count} files", {"count": count})
        return {"ok": True, "files_indexed": count}

    def _regenerate_all(self):
        """Regenerate AGENT.md for every folder with files."""
        folders_with_files = set()
        for filepath in self.backend.file_registry:
            folder = os.path.dirname(filepath)
            if folder != self.backend.root_dir:
                folders_with_files.add(folder)

        count = 0
        for folder in sorted(folders_with_files):
            # Skip the .backend and venv dirs
            if '.backend' in folder or '__pycache__' in folder or 'node_modules' in folder:
                continue
            agent = FolderAgent(folder, self.backend)
            agent.generate_agent_file()
            count += 1

        self._sync_agents_to_db()
        log_event(self.conn, self.name, "regenerate",
                  f"regenerated {count} AGENT.md files", {"count": count})
        return {"ok": True, "agents_regenerated": count}

    def _stats(self):
        return {
            "indexed_files": len(self.backend.file_registry),
            "knowledge_nodes": len(self.backend.knowledge_graph),
            "agents_generated": len(self.backend.agent_registry),
            "backend_dir": self.backend.backend_dir,
        }

    def _list_agents(self):
        self._sync_agents_to_db()
        rows = self.conn.execute("SELECT * FROM neural_agents ORDER BY last_updated DESC").fetchall()
        return {"agents": [dict(r) for r in rows]}

    def _find_related(self, filepath):
        """Find files related to a given file via the knowledge graph."""
        abs_path = os.path.abspath(filepath)
        if abs_path not in self.backend.file_registry:
            # Try matching by basename
            for fp in self.backend.file_registry:
                if os.path.basename(fp) == os.path.basename(abs_path):
                    abs_path = fp
                    break
        if abs_path not in self.backend.knowledge_graph:
            return {"error": f"file not indexed: {filepath}"}
        node = self.backend.knowledge_graph[abs_path]
        return {
            "file": abs_path,
            "metadata": node.get("metadata", {}),
            "connections": node.get("connections", []),
        }

    def _query_graph(self, term):
        """Search the file registry for files matching the term."""
        term_lower = term.lower()
        matches = []
        for filepath, metadata in self.backend.file_registry.items():
            if term_lower in filepath.lower() or term_lower in str(metadata):
                matches.append({"path": filepath, "size": metadata.get("size", 0)})
        return {"query": term, "matches": matches[:20], "total": len(matches)}

    # ── db sync ───────────────────────────────────────────────────

    def _sync_to_db(self):
        """Sync the backend file registry into the neural_index_files table."""
        for filepath, metadata in self.backend.file_registry.items():
            self.conn.execute(
                """INSERT OR REPLACE INTO neural_index_files
                   (filepath, extension, size, modified, file_hash, indexed_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (filepath, metadata.get('extension', ''),
                 metadata.get('size', 0), metadata.get('modified', ''),
                 metadata.get('hash', ''), now_iso()),
            )
        self.conn.commit()

    def _sync_agents_to_db(self):
        """Sync the backend agent registry into neural_agents table."""
        for agent_id, info in self.backend.agent_registry.items():
            self.conn.execute(
                """INSERT OR REPLACE INTO neural_agents
                   (agent_id, folder, agent_file, created_at, last_updated)
                   VALUES (?, ?, ?, ?, ?)""",
                (agent_id, info['folder'], info['agent_file'],
                 info.get('created', now_iso()), info.get('last_updated', now_iso())),
            )
        self.conn.commit()

    def _save_stats(self):
        stats = self._stats()
        for k, v in stats.items():
            self.conn.execute(
                """INSERT OR REPLACE INTO neural_index_stats (key, value) VALUES (?, ?)""",
                (k, str(v)),
            )
        self.conn.commit()

    # ── background work ──────────────────────────────────────────

    def work(self):
        """Tick: if monitoring is off, do a periodic re-scan."""
        if self._observer is None:
            count = self.backend.index_all(
                extensions=self._EXTENSIONS,
                exclude_dirs=self._EXCLUDE_DIRS,
            )
            if count:
                self._sync_to_db()
                self._save_stats()

    def start_monitoring(self):
        """Start reactive file-system monitoring (optional, requires watchdog)."""
        if not HAS_WATCHDOG:
            return {"ok": False, "error": "watchdog not installed"}
        if self._observer is not None:
            return {"ok": True, "note": "already monitoring"}

        # Initial scan
        self._scan()

        event_handler = FileMonitorHandler(self, self._EXTENSIONS, self)
        self._observer = Observer()
        self._observer.schedule(event_handler, self.backend.root_dir, recursive=True)
        self._observer.daemon = True
        self._observer.start()
        log_event(self.conn, self.name, "monitor_start", "reactive monitoring active")
        return {"ok": True, "monitoring": True}

    def stop_monitoring(self):
        """Stop file-system monitoring."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            log_event(self.conn, self.name, "monitor_stop", "monitoring stopped")
            return {"ok": True, "stopped": True}
        return {"ok": True, "stopped": False}

    def employee_duty(self):
        """Auto-generate AGENT.md files for building folders during idle shifts."""
        from city.registry import get_registry
        registry = get_registry(self.conn)

        # Generate AGENT.md for every building in the registry
        created = 0
        for name, agent in registry.items():
            building_dir = self._building_dir(name)
            if building_dir and os.path.isdir(building_dir):
                agent_md = os.path.join(building_dir, 'AGENT.md')
                if not os.path.exists(agent_md):
                    fa = FolderAgent(building_dir, self.backend)
                    fa.generate_agent_file()
                    created += 1

        if created:
            self.log("agent_gen", f"generated {created} AGENT.md files")
        return None

    @staticmethod
    def _building_dir(name):
        """Resolve the building directory for an agent name."""
        import buildings as buildings_pkg
        pkg_dir = buildings_pkg.__path__[0]
        candidate = os.path.join(pkg_dir, name)
        return candidate if os.path.isdir(candidate) else None

    def dashboard_payload(self, conn):
        """Self-contained dashboard data for this building."""
        self._sync_to_db()
        self._sync_agents_to_db()
        rows = conn.execute(
            "SELECT * FROM neural_index_files ORDER BY indexed_at DESC LIMIT 30"
        ).fetchall()
        agents = conn.execute("SELECT * FROM neural_agents ORDER BY last_updated DESC LIMIT 20").fetchall()
        stats = conn.execute("SELECT key, value FROM neural_index_stats").fetchall()
        return {
            "indexed_files": [dict(r) for r in rows],
            "agents": [dict(r) for r in agents],
            "stats": {r["key"]: r["value"] for r in stats},
        }
