"""File-backed store with in-memory cache. Sessions and manifests survive restarts."""
import json
from datetime import datetime, timezone
from pathlib import Path

from ..models.manifest import DeploymentRecord, SpecialistManifest, StoredSpecialist
from ..models.session import ArchitectSession


class Store:
    def __init__(self, manifests_dir: Path):
        self.dir = Path(manifests_dir)
        self.sessions_dir = self.dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, ArchitectSession] = {}
        self._specialists: dict[str, StoredSpecialist] = {}

    # sessions ---------------------------------------------------------------
    def save_session(self, s: ArchitectSession) -> None:
        self._sessions[s.session_id] = s
        (self.sessions_dir / f"{s.session_id}.json").write_text(s.model_dump_json(indent=2))

    def get_session(self, sid: str) -> ArchitectSession | None:
        if sid in self._sessions:
            return self._sessions[sid]
        f = self.sessions_dir / f"{sid}.json"
        if f.exists():
            s = ArchitectSession.model_validate_json(f.read_text())
            self._sessions[sid] = s
            return s
        return None

    # specialists ------------------------------------------------------------
    def save_specialist(self, manifest: SpecialistManifest, sha256: str) -> None:
        stored = StoredSpecialist(manifest=manifest, sha256=sha256)
        f = self.dir / f"{manifest.specialist_id}.json"
        if f.exists():
            raise FileExistsError("manifests are immutable once written")
        f.write_text(stored.model_dump_json(indent=2))
        self._specialists[manifest.specialist_id] = stored
        self.save_status(manifest.specialist_id, DeploymentRecord(
            status="compiled", updated_at=datetime.now(timezone.utc)))

    def get_specialist(self, sid: str) -> StoredSpecialist | None:
        if sid in self._specialists:
            return self._specialists[sid]
        f = self.dir / f"{sid}.json"
        if f.exists():
            st = StoredSpecialist.model_validate_json(f.read_text())
            self._specialists[sid] = st
            return st
        return None

    def save_status(self, sid: str, rec: DeploymentRecord) -> None:
        (self.dir / f"{sid}.status.json").write_text(rec.model_dump_json(indent=2))

    def get_status(self, sid: str) -> DeploymentRecord | None:
        f = self.dir / f"{sid}.status.json"
        return DeploymentRecord.model_validate_json(f.read_text()) if f.exists() else None

    def list_specialists(self) -> list[dict]:
        out = []
        for f in sorted(self.dir.glob("spec_*.json")):
            if f.name.endswith(".status.json"):
                continue
            sid = f.stem
            st = self.get_specialist(sid)
            rec = self.get_status(sid)
            if st:
                m = st.manifest
                out.append({"id": sid, "name": m.identity.name, "role": m.identity.role,
                            "status": rec.status if rec else "compiled"})
        return out
