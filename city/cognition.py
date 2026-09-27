"""
city/cognition.py — Per-building autonomous Cognitive Orchestrator (CTMS).

Implements the `agent(lambda)` / `answer_operator` from the CTMS spec:

    answer_operator = lambda(query):  traverse(thought-tree(query)) -> flatten-tree
    agent           = lambda(initial): chain-of-thought(initial)

Every building's Agent owns exactly one CognitiveOrchestrator instance
(`self.cognition`) and drives it on each work tick. Every reasoning step is
logged as a CTMS trace via Agent.trace(tag, type, ctmsact, content) using the
operator glyphs:

    diamond next-thought      split split-branch      up transcend
    metamorphosis             infinity infinite-recursion  godel
    complete                  incomplete                abandon
    truth                     axiom

Design notes
------------
* The orchestrator is *owned per building* -- no global brain. Each instance
  keeps its own thought-tree, focus pointer, and node budget.
* Reasoning is bounded (max depth, max nodes, per-step width) so an autonomous
  loop can never run away. The infinity budget re-seeds the tree instead of
  growing without bound.
* `valid?` filtering blocks empty/oversized thoughts and cycles (a thought may
  not repeat an ancestor's content), keeping the tree acyclic.
* `answer_operator(query)` builds a throwaway tree for a single user query and
  logs the chain as traces; it never mutates the persistent autonomous tree.
"""

import json
from dataclasses import dataclass, field

GLYPH = {
    "next": "♢", "branch": "⋔", "transcend": "↑", "metamorphosis": "⍟",
    "infinite_recursion": "∞", "godel": "§", "complete": "⊤",
    "incomplete": "⊥", "abandon": "↺", "truth": "⊨", "axiom": "⊢",
}

# Meta-axioms admitted at boot (logged once per building as axiom traces).
META_AXIOMS = [
    "forall f in U: f <-> f(f(...f(x)...))",
    "exists y: (y notin y) and (y in y)",
    "forall z: z == (z oplus not-z)",
    "up concept => (lambda (c) (c c))",
    "metamorphosis x => forall t: x(t+1) = T(x(t))",
    "infinity f => (lambda (x) (f (infinity f) x))",
    "godel s => (s == 'This statement is unprovable')",
    "incomplete theory => exists s: (godel s and not-provable s)",
    "complete theory => forall s: (provable s or provable not-s)",
    "therefore(p,q) => (p -> q); because(p,q) => (q -> p); equiv(x,y) => (x->y)and(y->x)",
]

# Operators that generate child thoughts.
CHILD_OPERATORS = [
    "abstract", "generalize", "specialize", "analogize", "transform",
    "combine", "transcend", "metamorphose", "infinitely_recurse",
    "godelize", "complete", "incomplete", "derive", "integrate",
    "sum_over", "product_over",
]

DIMS = ["risk", "revenue", "efficiency", "growth", "stability",
        "opportunity", "capital", "velocity", "resilience", "leverage"]

SIBLINGS = ["finance_building", "media_building", "research_building",
            "crypto_trading", "market_data",
            "shopify", "product_flipping", "social_affiliates",
            "content_creation", "sourcing_research", "scraper", "signal"]

BREAKTHROUGH_KEYS = ("opportunity", "profit", "resolve", "closure",
                     "unlock", "gain", "positive", "lead score", "advantage")

MAX_DEPTH = 6
MAX_NODES = 240
WIDTH = 4


@dataclass
class Thought:
    content: str
    depth: int = 0
    operator: str = "seed"
    glyph: str = GLYPH["next"]
    children: list = field(default_factory=list)
    parent: "Thought" = None
    meta: dict = field(default_factory=dict)

    def path_contents(self):
        """All ancestor contents (including self), root-first. Used for cycle checks."""
        out, node = [], self
        while node is not None:
            out.append(node.content)
            node = node.parent
        return out


class CognitiveOrchestrator:
    """One autonomous reasoning loop per building."""

    def __init__(self, agent, max_depth=MAX_DEPTH, max_nodes=MAX_NODES, width=WIDTH):
        self.agent = agent
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.width = width
        # #1 per-building autonomous clock: each building sets its own cadence
        # via the `cog_interval` class attribute (seconds). Defaults to 30.
        self.tick_interval = getattr(agent, "cog_interval", 30)
        self.node_count = 0
        self.step_index = 0
        self._axioms_logged = False
        self.root = None
        self.focus = None
        self._reseed(initial=True)

    # ------------------------------------------------------------------ context
    def _ctx(self):
        a = self.agent
        name = getattr(a, "name", "agent")
        subject = getattr(a, "subject", "general")
        building = getattr(a, "building_name", None) or name
        return {"name": name, "subject": subject, "building": building}

    def _dim(self, content):
        return DIMS[hash(content) % len(DIMS)]

    def _sibling(self, content):
        h = (hash(content) // 7) % len(SIBLINGS)
        s = SIBLINGS[h]
        return s if s != self._ctx()["name"] else SIBLINGS[(h + 1) % len(SIBLINGS)]

    # --------------------------------------------------------- operator bodies
    def _apply_operator(self, op, node):
        c = node.content
        ctx = self._ctx()
        dim = self._dim(c)
        sib = self._sibling(c)
        if op == "abstract":
            return f"abstract {c} -> underlying principle ({dim})"
        if op == "generalize":
            return f"generalize {c} across all {ctx['subject']} activity"
        if op == "specialize":
            return f"specialize {c} for the {dim} dimension"
        if op == "analogize":
            return f"analogy: {c} <-> {sib}'s {dim} posture"
        if op == "transform":
            return f"reframe {c} as a {dim} optimization"
        if op == "combine":
            return f"combine {c} with {ctx['subject']} {dim} signal"
        if op == "transcend":
            return f"up transcend {c} to the strategic layer"
        if op == "metamorphose":
            return f"metamorphosis: change the representation of {c}"
        if op == "infinitely_recurse":
            return f"infinity {c} applied to itself: (lambda(x)({c} {c}))"
        if op == "godelize":
            return f"godel self-reference: '{c}' asserts its own unprovability"
        if op == "complete":
            return f"complete resolve {c} - closure achieved ({dim})"
        if op == "incomplete":
            return f"incomplete {c} remains undecidable in this frame"
        if op == "derive":
            return f"derive {c} from first principles of {ctx['building']}"
        if op == "integrate":
            return f"integrate {c} into {ctx['building']} operating loop"
        if op == "sum_over":
            return f"sum over every {dim} instance of {c}"
        if op == "product_over":
            return f"product over compounding {dim} of {c}"
        return f"{op}: {c}"

    # ------------------------------------------------------------ tree helpers
    def _glyph_for(self, op):
        return {
            "transcend": GLYPH["transcend"],
            "metamorphose": GLYPH["metamorphosis"],
            "infinitely_recurse": GLYPH["infinite_recursion"],
            "godelize": GLYPH["godel"],
            "complete": GLYPH["complete"],
            "incomplete": GLYPH["incomplete"],
        }.get(op, GLYPH["next"])

    def _valid(self, node):
        c = node.content
        if not c or len(c) > 240:
            return False
        # cycle / duplicate check against ancestors
        if c in node.parent.path_contents():
            return False
        return True

    def _generate_children(self, node):
        candidates = []
        for op in CHILD_OPERATORS:
            if node.depth + 1 > self.max_depth and op not in (
                "transcend", "complete", "incomplete"
            ):
                continue
            content = self._apply_operator(op, node)
            child = Thought(
                content=content, depth=node.depth + 1,
                operator=op, glyph=self._glyph_for(op), parent=node,
            )
            if self._valid(child):
                candidates.append(child)
        return candidates

    def _is_breakthrough(self, child):
        if child.depth >= self.max_depth:
            return True
        low = child.content.lower()
        return any(k in low for k in BREAKTHROUGH_KEYS)

    # ------------------------------------------------------------------ tracing
    def _trace(self, node, glyph, content=None, ctype=None):
        if ctype is None:
            if glyph == GLYPH["branch"]:
                ctype = "split"
            elif glyph in (GLYPH["truth"], GLYPH["complete"],
                           GLYPH["incomplete"], GLYPH["abandon"]):
                ctype = "result"
            else:
                ctype = "plan"
        try:
            self.agent.trace(
                "think", ctype, glyph, content or node.content,
                {"depth": node.depth, "operator": node.operator},
            )
        except Exception:
            pass

    def _reseed(self, initial=False):
        ctx = self._ctx()
        root_content = f"{ctx['subject']}: autonomous reasoning online"
        self.root = Thought(content=root_content, depth=0, operator="seed",
                            glyph=GLYPH["axiom"])
        self.focus = self.root
        self.node_count = 1
        if not self._axioms_logged:
            for ax in META_AXIOMS[:4]:
                self._trace(self.root, GLYPH["axiom"], f"meta-axiom: {ax}")
            self._axioms_logged = True
        elif not initial:
            self._trace(self.root, GLYPH["infinite_recursion"],
                        "recursion budget reached; re-seeding thought-tree")

    # -------------------------------------------------------- meta-cognition fold-in
    def _reflect(self):
        """Pull the building's real self-profile + synthesized goals from
        city.meta.agent_profile and grow them as thoughts. Safe no-op if the
        meta layer is unavailable."""
        try:
            from city.meta.agent_profile import (
                SelfProfile, GoalSynthesizer, UtilityEvaluator,
            )
        except Exception:
            return
        try:
            perf = SelfProfile(self.agent).get_performance_summary()
            self._trace(
                self.root, GLYPH["godel"],
                f"self-profile: {perf.get('queries', 0)} queries, "
                f"{perf.get('errors', 0)} errors, "
                f"{perf.get('plan_steps', 0)} plan steps",
            )
            goals = GoalSynthesizer(self.agent).synthesize()
            for g in goals:
                t = Thought(content=f"goal: {g}", depth=1, operator="synthesize",
                            glyph=GLYPH["truth"], parent=self.root)
                self._trace(t, GLYPH["truth"], t.content, "result")
                self.root.children.append(t)
                self.node_count += 1
                if self.node_count >= self.max_nodes:
                    self._reseed()
                    return
            # Utility self-evaluation of the current focus, if any.
            if self.focus is not None:
                ue = UtilityEvaluator(self.agent)
                score = ue.evaluate_outcome({"growth": 0.5, "stability": 0.5})
                self._trace(self.root, GLYPH["incomplete"],
                            f"utility self-eval of focus: {score:.2f}")
            # #3 schedule the future: re-reflect + act on synthesized goals
            # on a deferred horizon, so autonomy persists across ticks.
            self.schedule(300, "reflect")
            for g in goals:
                self.schedule(600, "command", {"query": "status"})
        except Exception as exc:
            self._trace(self.root, GLYPH["abandon"],
                        f"reflection failed: {exc}", "result")

    # ------------------------------------------------------------ the work step
    def step(self, steps=1):
        for _ in range(max(1, steps)):
            self._step_one()

    def _step_one(self):
        self.step_index += 1
        # Periodic meta-cognition: fold the building's real self-profile and
        # synthesized goals into the thought-tree (guarded — never fatal).
        if self.step_index % 20 == 0:
            self._reflect()
        focus = self.focus

        if focus is None or focus.depth >= self.max_depth:
            if self.node_count >= self.max_nodes:
                self._reseed()
                return
            focus = focus.parent if (focus and focus.parent) else self.root
            self.focus = focus

        children = self._generate_children(focus)
        if not children:
            # abandon -- no valid continuation; backtrack toward root
            self._trace(focus, GLYPH["abandon"],
                        f"no valid children from: {focus.content}", "result")
            self.focus = focus.parent or self.root
            return

        # Rotate which operators fire each step so the loop evolves through the
        # full operator set (next/transcend/metamorphose/godel/complete/...),
        # adapting context instead of always replaying the first few operators.
        n = len(children)
        start = (self.step_index * 3) % n if n else 0
        order = children[start:] + children[:start]
        chosen = order[: self.width]
        if len(chosen) > 1:
            # split-branch
            self._trace(focus, GLYPH["branch"],
                        f"split-branch into {len(chosen)} thoughts", "split")

        new_focus = None
        for child in chosen:
            if self._is_breakthrough(child):
                child.glyph = GLYPH["truth"]
            self._trace(child, child.glyph, child.content)
            focus.children.append(child)
            self.node_count += 1
            if self.node_count >= self.max_nodes:
                self._reseed()
                return
            if new_focus is None:
                new_focus = child
        # advance focus depth-first to continue the chain
        self.focus = new_focus or focus
        # #2 chronological ledger: snapshot this building's reasoning each tick
        self._log_chronolog()

    # ----------------------------------------------- chronoschedule: ledger
    def _log_chronolog(self):
        """Write a time-ordered snapshot of this building's reasoning state."""
        try:
            from city.db import log_chronolog
            recent = " | ".join(n.content for n in self.traverse(self.root)[-3:])
            focus_content = self.focus.content if self.focus else None
            log_chronolog(
                self.agent.conn, self.agent.name,
                self.focus.depth if self.focus else 0,
                self.node_count, self.step_index, focus_content, recent,
            )
        except Exception:
            pass

    def chronolog(self, limit=50):
        try:
            from city.db import recent_chronolog
            return recent_chronolog(self.agent.conn, self.agent.name, limit)
        except Exception:
            return []

    # ----------------------------------------- chronoschedule: future actions
    def schedule(self, delay_seconds, action_type, payload=None):
        """Queue a deferred autonomous action (command | reflect | cognition)."""
        try:
            from datetime import datetime, timezone, timedelta
            from city.db import schedule_action
            due = (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat()
            schedule_action(
                self.agent.conn, self.agent.name, due, action_type,
                json.dumps(payload or {}),
            )
        except Exception:
            pass

    def run_due_actions(self):
        """Execute any deferred actions whose due time has arrived (#3)."""
        try:
            from city.db import due_actions, complete_action
        except Exception:
            return
        try:
            rows = due_actions(self.agent.conn, self.agent.name)
            for r in rows:
                try:
                    atype = r["action_type"]
                    if atype == "command":
                        self.agent.process(json.loads(r["payload"] or "{}").get("query", ""))
                    elif atype == "reflect":
                        self._reflect()
                    else:  # cognition
                        self.step()
                    complete_action(self.agent.conn, r["id"])
                    self._trace(self.root, GLYPH["truth"],
                                f"ran scheduled action: {atype}")
                except Exception as exc:
                    self._trace(self.root, GLYPH["abandon"],
                                f"scheduled action failed: {exc}")
        except Exception:
            pass

    # --------------------------------------------------- tree traversal / flatten
    def traverse(self, tree, depth=0, max_depth=MAX_DEPTH):
        if tree is None or depth > max_depth:
            return []
        out = [tree]
        for ch in tree.children:
            out.extend(self.traverse(ch, depth + 1, max_depth))
        return out

    def flatten_tree(self, tree, max_depth=MAX_DEPTH):
        return [
            {"depth": n.depth, "glyph": n.glyph, "content": n.content,
             "operator": n.operator}
            for n in self.traverse(tree, 0, max_depth)
        ]

    def _build_tree(self, root, max_depth, width, budget):
        stack = [root]
        used = 0
        while stack and used < budget:
            node = stack.pop()
            if node.depth >= max_depth:
                continue
            kids = self._generate_children(node)[:width]
            for k in kids:
                if self._is_breakthrough(k):
                    k.glyph = GLYPH["truth"]
                node.children.append(k)
                used += 1
                stack.append(k)
        return root

    # --------------------------------------------------- spec-facing operators
    def chain_of_thought(self, initial_concept, max_depth=MAX_DEPTH):
        """agent(lambda): seed a concept, grow a thought-tree, flatten to a chain."""
        root = Thought(content=str(initial_concept), depth=0, operator="seed",
                       glyph=GLYPH["axiom"])
        self._build_tree(root, max_depth, self.width, self.max_nodes)
        return self.flatten_tree(root, max_depth)

    def answer_operator(self, query, max_depth=3, width=2, budget=10):
        """answer_operator: build a thought-tree from a query, traverse, flatten.

        Returns the flattened reasoning chain (list of dicts) and logs each
        node as a CTMS trace. Uses a throwaway tree so the persistent
        autonomous tree is untouched.
        """
        root = Thought(content=f"query: {query}", depth=0, operator="seed",
                       glyph=GLYPH["axiom"])
        self._build_tree(root, max_depth, width, budget)
        for n in self.traverse(root, 0, max_depth):
            self._trace(n, n.glyph, n.content)
        return self.flatten_tree(root, max_depth)

    # ------------------------------------------------------------- introspection
    def state(self):
        recent = [n.content for n in self.traverse(self.root)[-8:]]
        return {
            "nodes": self.node_count,
            "depth": self.focus.depth if self.focus else 0,
            "step_index": self.step_index,
            "recent": recent,
        }
