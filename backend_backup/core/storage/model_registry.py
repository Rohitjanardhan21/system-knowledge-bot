"""
CVIS v9 — Model Version Registry
Stores model snapshots to disk, supports rollback, best-model tracking.
All metadata persisted in JSON; weights in .pt / .json files.
"""
import json, time, uuid, logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

log = logging.getLogger("cvis.versioning")

VERSION_DIR   = Path("model_versions")
REGISTRY_FILE = VERSION_DIR / "registry.json"
MAX_VERSIONS_PER_MODEL = 10   # auto-prune oldest beyond this


@dataclass
class VersionEntry:
    version_id:    str
    model_name:    str   # "lstm" | "vae" | "ensemble"
    saved_at:      float
    description:   str
    metrics:       dict  # training metrics snapshot
    path:          str
    active:        bool  = False
    is_best:       bool  = False
    training_steps: int  = 0
    ensemble_score: float = 0.0
    tag:           str   = ""   # e.g. "stable", "experimental"


class ModelVersionRegistry:
    def __init__(self, base_dir: str = "model_versions"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.base_dir / "registry.json"
        self._registry: dict[str, list[dict]] = {}
        self._load()

    # ── persistence ───────────────────────────────────────
    def _load(self):
        if self.registry_file.exists():
            try:
                with open(self.registry_file) as f:
                    self._registry = json.load(f)
                log.info("Registry loaded: %d model families", len(self._registry))
            except Exception as e:
                log.warning("Registry load failed: %s", e)
                self._registry = {}

    def _save(self):
        tmp = self.registry_file.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(self._registry, f, indent=2)
        tmp.replace(self.registry_file)

    # ── save version ──────────────────────────────────────
    def save_version(
        self,
        model_name: str,
        state_dict: dict,
        metrics: dict,
        description: str = "",
        tag: str = "",
    ) -> VersionEntry:
        vid = f"{model_name}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        path = self.base_dir / f"{vid}.json"
        with open(path, "w") as f:
            json.dump(state_dict, f)

        entry = VersionEntry(
            version_id    = vid,
            model_name    = model_name,
            saved_at      = time.time(),
            description   = description or f"Auto-save at step {metrics.get('steps_lstm', 0)}",
            metrics       = metrics,
            path          = str(path),
            active        = False,
            training_steps= metrics.get("steps_lstm", 0) + metrics.get("steps_vae", 0),
            ensemble_score= float(metrics.get("ensemble_score", 0)),
            tag           = tag,
        )

        if model_name not in self._registry:
            self._registry[model_name] = []

        # Check if this is the best so far
        scores = [v.get("ensemble_score", 0) for v in self._registry[model_name]]
        entry.is_best = entry.ensemble_score >= max(scores, default=0)
        if entry.is_best:
            for v in self._registry[model_name]:
                v["is_best"] = False

        self._registry[model_name].append(asdict(entry))
        self._prune(model_name)
        self._save()
        log.info("Saved version %s (score=%.4f, best=%s)", vid, entry.ensemble_score, entry.is_best)
        return entry

    def _prune(self, model_name: str):
        versions = self._registry.get(model_name, [])
        if len(versions) <= MAX_VERSIONS_PER_MODEL:
            return
        # Keep: best, active, and most recent up to limit
        sorted_v = sorted(versions, key=lambda v: v["saved_at"])
        to_delete: list[dict] = []
        for v in sorted_v:
            if v.get("is_best") or v.get("active"):
                continue
            if len(versions) - len(to_delete) > MAX_VERSIONS_PER_MODEL:
                to_delete.append(v)
        for v in to_delete:
            p = Path(v["path"])
            if p.exists():
                p.unlink()
            versions.remove(v)
            log.debug("Pruned version %s", v["version_id"])
        self._registry[model_name] = versions

    # ── activate / rollback ───────────────────────────────
    def activate(self, model_name: str, version_id: str) -> Optional[dict]:
        """Load and return the state_dict for a version; mark it active."""
        versions = self._registry.get(model_name, [])
        target = next((v for v in versions if v["version_id"] == version_id), None)
        if not target:
            return None
        path = Path(target["path"])
        if not path.exists():
            log.error("Version file missing: %s", path)
            return None
        # Mark active
        for v in versions:
            v["active"] = False
        target["active"] = True
        self._save()
        with open(path) as f:
            return json.load(f)

    def rollback(self, model_name: str) -> Optional[tuple[str, dict]]:
        """Rollback to the second-most-recent version."""
        versions = sorted(
            self._registry.get(model_name, []),
            key=lambda v: v["saved_at"], reverse=True
        )
        if len(versions) < 2:
            return None
        target = versions[1]   # previous version
        state = self.activate(model_name, target["version_id"])
        return target["version_id"], state

    def rollback_to_best(self, model_name: str) -> Optional[tuple[str, dict]]:
        versions = self._registry.get(model_name, [])
        best = next((v for v in versions if v.get("is_best")), None)
        if not best:
            return None
        state = self.activate(model_name, best["version_id"])
        return best["version_id"], state

    # ── queries ───────────────────────────────────────────
    def list_versions(self, model_name: str = None) -> list[dict]:
        if model_name:
            return sorted(
                self._registry.get(model_name, []),
                key=lambda v: v["saved_at"], reverse=True
            )
        out = []
        for versions in self._registry.values():
            out.extend(versions)
        return sorted(out, key=lambda v: v["saved_at"], reverse=True)

    def get_active_version(self, model_name: str) -> Optional[dict]:
        return next(
            (v for v in self._registry.get(model_name, []) if v.get("active")),
            None
        )

    def get_best_version(self, model_name: str) -> Optional[dict]:
        return next(
            (v for v in self._registry.get(model_name, []) if v.get("is_best")),
            None
        )

    def delete_version(self, model_name: str, version_id: str) -> bool:
        versions = self._registry.get(model_name, [])
        target = next((v for v in versions if v["version_id"] == version_id), None)
        if not target:
            return False
        if target.get("active"):
            log.warning("Cannot delete active version %s", version_id)
            return False
        p = Path(target["path"])
        if p.exists():
            p.unlink()
        versions.remove(target)
        self._save()
        return True

    def stats(self) -> dict:
        return {
            model: {
                "total_versions": len(versions),
                "active": next((v["version_id"] for v in versions if v.get("active")), None),
                "best": next((v["version_id"] for v in versions if v.get("is_best")), None),
                "latest_score": versions[-1]["ensemble_score"] if versions else 0,
            }
            for model, versions in self._registry.items()
        }


# singleton
_registry: Optional[ModelVersionRegistry] = None

def get_registry() -> ModelVersionRegistry:
    global _registry
    if _registry is None:
        _registry = ModelVersionRegistry()
    return _registry
