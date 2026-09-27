
import json
import os
import time
import logging
from typing import Dict, List, Any, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class CognitiveWorkflowStore:
    STORE_PATH = 'data/self_code/cognitive_workflows.json'

    def __init__(self):
        self.workflows: Dict[str, Any] = {}
        self.outcomes: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        if os.path.exists(self.STORE_PATH):
            try:
                with open(self.STORE_PATH, 'r') as f:
                    data = json.load(f)
                    self.workflows = data.get('workflows', {})
                    self.outcomes = data.get('outcomes', [])
            except Exception:
                pass

    def save(self):
        os.makedirs(os.path.dirname(self.STORE_PATH), exist_ok=True)
        with open(self.STORE_PATH, 'w') as f:
            json.dump({'workflows': self.workflows, 'outcomes': self.outcomes[-1000:]}, f)

    def record(self, task_pattern: str, strategy: str, success: bool, reward: float,
               duration: float, error_type: Optional[str] = None):
        self.outcomes.append({
            'timestamp': time.time(),
            'task_pattern': task_pattern,
            'strategy': strategy,
            'success': success,
            'reward': reward,
            'duration': duration,
            'error_type': error_type,
        })

    def get_best_strategy(self, task_pattern: str, available: List[str]) -> Optional[str]:
        candidates = defaultdict(lambda: {'success': 0, 'total': 0, 'avg_reward': 0.0})
        for o in self.outcomes:
            if o['task_pattern'] == task_pattern and o['strategy'] in available:
                s = candidates[o['strategy']]
                s['total'] += 1
                if o['success']:
                    s['success'] += 1
                s['avg_reward'] += o['reward']
        if not candidates:
            return None
        best = max(candidates.items(),
                   key=lambda kv: (kv[1]['success'] / max(kv[1]['total'], 1)) * 0.7 +
                                  min(kv[1]['avg_reward'] / max(kv[1]['total'], 1), 5) * 0.3)
        return best[0] if best[1]['success'] / max(best[1]['total'], 1) > 0.3 else None


class CognitiveWorkflowModifier:
    def __init__(self, store: Optional[CognitiveWorkflowStore] = None):
        self.store = store or CognitiveWorkflowStore()
        self._pending_mods: List[Dict[str, Any]] = []

    def propose_route_change(self, task_type: str, current_route: str,
                            proposed_route: str, confidence: float) -> bool:
        if confidence < 0.5:
            return False
        self._pending_mods.append({
            'type': 'route',
            'task_type': task_type,
            'from': current_route,
            'to': proposed_route,
            'confidence': confidence,
            'timestamp': time.time(),
        })
        logger.info('Proposed route change: %s -> %s (confidence=%.2f)',
                    current_route, proposed_route, confidence)
        return True

    def apply_pending(self, approval: Optional[bool] = None) -> int:
        if approval is False:
            n = len(self._pending_mods)
            self._pending_mods.clear()
            return -n
        applied = 0
        for mod in self._pending_mods[:]:
            if approval is True or self._is_low_risk(mod):
                self._apply_mod(mod)
                applied += 1
            self._pending_mods.remove(mod)
        if applied:
            self.store.save()
        return applied

    def _is_low_risk(self, mod: Dict[str, Any]) -> bool:
        if mod['type'] == 'route':
            outcomes = [o for o in self.store.outcomes
                        if o['strategy'] == mod['to'] and o['success']]
            return len(outcomes) >= 3
        return False

    def _apply_mod(self, mod: Dict[str, Any]):
        if mod['type'] == 'route':
            self.store.workflows[mod['task_type']] = {
                'route_to': mod['to'],
                'confidence': mod['confidence'],
                'applied_at': mod['timestamp'],
            }
            logger.info('Applied route change: %s -> %s', mod['from'], mod['to'])


class SandboxExecutor:
    def __init__(self):
        self.allowed_builtins = {
            'len', 'range', 'enumerate', 'zip', 'isinstance',
            'hasattr', 'getattr', 'setattr', 'print', 'str', 'int',
            'float', 'list', 'dict', 'tuple', 'set', 'type',
        }

    def test_patch(self, source: str, test_input: Any) -> Dict[str, Any]:
        sandbox = {'__builtins__': {k: __builtins__[k] for k in self.allowed_builtins}}
        try:
            exec(source, sandbox)
        except SyntaxError as e:
            return {'valid': False, 'error': f'Syntax: {e}'}
        func_name = None
        for name, obj in sandbox.items():
            if callable(obj) and name.startswith('test_'):
                func_name = name
                break
        if func_name is None:
            return {'valid': False, 'error': 'No testable function found'}
        try:
            result = sandbox[func_name](test_input)
            return {'valid': True, 'result': result}
        except Exception as e:
            return {'valid': False, 'error': f'Runtime: {e}'}


workflow_store = CognitiveWorkflowStore()
workflow_modifier = CognitiveWorkflowModifier(store=workflow_store)
sandbox = SandboxExecutor()
