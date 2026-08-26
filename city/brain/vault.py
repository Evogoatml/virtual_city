"""
city/brain — The Shared Knowledge Core ("the Brain").

Every agent reads from the Brain before it acts. This is the system's single
source of truth for strategy, SOPs, north-star metrics, domain knowledge, and
decisions. It is a markdown vault on disk (inspectable, version-controllable)
with a lightweight in-memory index. No vectors required to start; retrieval is
front-matter + keyword overlap (RAG-lite), pluggable to embeddings later.

Vault layout (repo-root/brain/vault):
    strategy.md
    north_star.md
    domains/crypto.md
    domains/ecommerce.md
    domains/content.md
    sops/affiliate_funnel.md
    personas/ecom_operator.md
    personas/full_multistream.md
    decisions/YYYY-MM-DD-<topic>.md
    proposed/   (agent-suggested notes awaiting human approval)

Notes may carry YAML front-matter:
    ---
    tags: [strategy, growth]
    buildings: [social_affiliates, content_creation]
    personas: [ecom_operator, full_multistream]
    priority: 2
    ---
"""
from __future__ import annotations

import os
import re
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VAULT_DIR = os.path.join(_ROOT, "brain", "vault")
PROPOSED_DIR = os.path.join(VAULT_DIR, "proposed")

_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_front_matter(text: str):
    """Minimal YAML: key: value | key: [a, b] | key: 'str'. Returns (meta, body)."""
    meta: dict = {}
    body = text
    m = _FRONT_MATTER.match(text)
    if m:
        block = m.group(1)
        body = text[m.end():]
        for line in block.splitlines():
            if not line.strip() or ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                items = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
                meta[key] = items
            else:
                meta[key] = val.strip("'\"")
    return meta, body


@dataclass
class Note:
    slug: str
    title: str
    path: str
    meta: dict
    body: str
    updated_at: float = 0.0

    @property
    def tags(self):
        return self.meta.get("tags", []) or []

    @property
    def buildings(self):
        return self.meta.get("buildings", []) or []

    @property
    def personas(self):
        return self.meta.get("personas", []) or []

    @property
    def priority(self):
        try:
            return int(self.meta.get("priority", 1))
        except (TypeError, ValueError):
            return 1

    def text(self) -> str:
        return f"## {self.title}\n\n{self.body}".strip()


class Vault:
    """Loads and indexes the markdown vault. Caches by directory mtime."""

    def __init__(self, vault_dir: str = VAULT_DIR):
        self.vault_dir = vault_dir
        self._notes: dict[str, Note] = {}
        self._mtime = 0.0
        self._last_load = 0.0
        self.reload()

    # ---------------------------------------------------------------- loading
    def reload(self, force: bool = False):
        now = time.time()
        mtime = 0.0
        if os.path.isdir(self.vault_dir):
            for root, _, files in os.walk(self.vault_dir):
                if os.path.basename(root) == "proposed":
                    continue
                for f in files:
                    if f.endswith(".md"):
                        try:
                            mtime = max(mtime, os.path.getmtime(os.path.join(root, f)))
                        except OSError:
                            pass
        if not force and mtime == self._mtime and now - self._last_load < 30:
            return
        self._mtime = mtime
        self._last_load = now
        notes: dict[str, Note] = {}
        if os.path.isdir(self.vault_dir):
            for root, _, files in os.walk(self.vault_dir):
                if os.path.basename(root) == "proposed":
                    continue
                for f in files:
                    if not f.endswith(".md"):
                        continue
                    path = os.path.join(root, f)
                    try:
                        text = open(path, "r", encoding="utf-8").read()
                    except OSError:
                        continue
                    meta, body = _parse_front_matter(text)
                    slug = os.path.splitext(os.path.relpath(path, self.vault_dir))[0]
                    title = meta.get("title") or slug.replace("_", " ").replace("-", " ").title()
                    notes[slug] = Note(
                        slug=slug, title=title, path=path, meta=meta,
                        body=body.strip(), updated_at=mtime,
                    )
        # proposed/ notes are loaded too but flagged
        proposed_root = os.path.join(self.vault_dir, "proposed")
        if os.path.isdir(proposed_root):
            for f in os.listdir(proposed_root):
                if not f.endswith(".md"):
                    continue
                path = os.path.join(proposed_root, f)
                try:
                    text = open(path, "r", encoding="utf-8").read()
                except OSError:
                    continue
                meta, body = _parse_front_matter(text)
                slug = "proposed/" + os.path.splitext(f)[0]
                notes[slug] = Note(
                    slug=slug, title="(proposed) " + (meta.get("title") or f),
                    path=path, meta={**meta, "proposed": True},
                    body=body.strip(), updated_at=mtime,
                )
        self._notes = notes
        logger.info("Brain vault loaded: %d notes", len(notes))

    def list_notes(self) -> list[Note]:
        self.reload()
        return list(self._notes.values())

    def get_note(self, slug: str) -> Optional[Note]:
        self.reload()
        return self._notes.get(slug)

    # ------------------------------------------------------------ retrieval
    def context_for(
        self,
        agent_name: str,
        persona: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 6,
    ) -> str:
        """Return the most relevant notes concatenated as context for an agent."""
        self.reload()
        q_tokens = set(re.findall(r"[a-z0-9_]+", (query or "").lower()))
        scored = []
        for note in self._notes.values():
            if note.meta.get("proposed"):
                continue
            score = 0
            if agent_name in note.buildings:
                score += 5
            if persona and persona in note.personas:
                score += 3
            # tag overlap with agent subject/persona/query
            for t in note.tags:
                tl = t.lower()
                if persona and tl in persona.lower():
                    score += 1
                if q_tokens and tl in q_tokens:
                    score += 1
            # body/title keyword overlap
            hay = (note.title + " " + note.body).lower()
            if q_tokens:
                score += sum(2 for tok in q_tokens if tok and tok in hay)
            score += note.priority
            if score > 0:
                scored.append((score, note))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [n for _, n in scored[:limit]]
        if not top:
            return "(no relevant Brain notes for this agent yet)"
        return "\n\n".join(n.text() for n in top)

    # --------------------------------------------------------------- writing
    def add_note(self, slug: str, title: str, body: str, meta: Optional[dict] = None) -> Note:
        """Write a note directly into the vault (operator-owned)."""
        os.makedirs(self.vault_dir, exist_ok=True)
        meta = dict(meta or {})
        meta.setdefault("title", title)
        fm = "---\n" + "\n".join(f"{k}: {v}" for k, v in meta.items()) + "\n---\n\n"
        path = os.path.join(self.vault_dir, slug + ".md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(fm + body.strip() + "\n")
        self.reload(force=True)
        return self.get_note(slug)

    def propose_note(self, slug: str, title: str, body: str, meta: Optional[dict] = None) -> str:
        """Agent-suggested note; lands in proposed/ for human approval."""
        os.makedirs(PROPOSED_DIR, exist_ok=True)
        meta = dict(meta or {})
        meta.setdefault("title", title)
        fm = "---\n" + "\n".join(f"{k}: {v}" for k, v in meta.items()) + "\n---\n\n"
        path = os.path.join(PROPOSED_DIR, slug + ".md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(fm + body.strip() + "\n")
        self.reload(force=True)
        return path


# Singleton
_BRAIN: Optional[Vault] = None


def brain() -> Vault:
    global _BRAIN
    if _BRAIN is None:
        _BRAIN = Vault()
    return _BRAIN
