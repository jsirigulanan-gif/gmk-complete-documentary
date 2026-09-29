from __future__ import annotations
from dataclasses import dataclass, field, asdict
from copy import deepcopy
from typing import Any, Iterable
from gmk_semantics.model import sha256_json

ARTIFACT_REGISTRY_ID = 'ARTIFACT_REGISTRY'

ARTIFACT_ENVELOPE_FIELDS = {
    'schema_header','artifact_id','artifact_type','version','supersedes_version',
    'uri','sha256','created_at'
}


def artifact_payload_projection(artifact: dict[str, Any]) -> dict[str, Any]:
    """Immutable artifact content covered by ArtifactRef.sha256.

    This intentionally excludes transport/identity envelope fields. It matches the
    frozen v1 convention used by Dependency Impact artifacts: the public artifact
    checksum proves the artifact payload, while the registry record hash proves the
    complete stored record.
    """
    return {k: deepcopy(v) for k, v in artifact.items() if k not in ARTIFACT_ENVELOPE_FIELDS}


def artifact_payload_sha256(artifact: dict[str, Any]) -> str:
    return sha256_json(artifact_payload_projection(artifact))


def artifact_uri(artifact_id: str, version: int) -> str:
    return f'gmk://artifacts/{artifact_id}/v{int(version)}'


@dataclass(frozen=True)
class ArtifactVersionLocator:
    version: int
    uri: str
    artifact_sha256: str
    record_sha256: str
    created_at: str
    schema_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ArtifactVersionLocator':
        return cls(
            version=int(data['version']), uri=str(data['uri']),
            artifact_sha256=str(data['artifact_sha256']),
            record_sha256=str(data['record_sha256']),
            created_at=str(data['created_at']), schema_id=str(data['schema_id'])
        )


@dataclass
class ArtifactRegistryEntry:
    artifact_id: str
    artifact_type: str
    head_version: int
    versions: dict[int, ArtifactVersionLocator] = field(default_factory=dict)

    def clone(self) -> 'ArtifactRegistryEntry':
        return ArtifactRegistryEntry(self.artifact_id, self.artifact_type, self.head_version, dict(self.versions))

    def to_dict(self) -> dict[str, Any]:
        return {
            'artifact_id': self.artifact_id,
            'artifact_type': self.artifact_type,
            'head_version': int(self.head_version),
            'versions': {str(k): v.to_dict() for k, v in sorted(self.versions.items())},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ArtifactRegistryEntry':
        return cls(
            artifact_id=str(data['artifact_id']), artifact_type=str(data['artifact_type']),
            head_version=int(data['head_version']),
            versions={int(k): ArtifactVersionLocator.from_dict(v) for k, v in (data.get('versions') or {}).items()},
        )


@dataclass
class ArtifactRegistrySnapshot:
    registry_id: str = ARTIFACT_REGISTRY_ID
    version: int = 1
    entries: dict[str, ArtifactRegistryEntry] = field(default_factory=dict)

    def clone(self) -> 'ArtifactRegistrySnapshot':
        return ArtifactRegistrySnapshot(self.registry_id, self.version, {k: v.clone() for k, v in self.entries.items()})

    def body(self) -> dict[str, Any]:
        return {
            'registry_id': self.registry_id,
            'version': int(self.version),
            'entries': {k: v.to_dict() for k, v in sorted(self.entries.items())},
        }

    @property
    def sha256(self) -> str:
        return sha256_json(self.body())

    def to_dict(self) -> dict[str, Any]:
        out = self.body(); out['sha256'] = self.sha256; return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ArtifactRegistrySnapshot':
        return cls(
            registry_id=str(data['registry_id']), version=int(data['version']),
            entries={k: ArtifactRegistryEntry.from_dict(v) for k, v in (data.get('entries') or {}).items()},
        )


def locator_for_artifact(artifact: dict[str, Any]) -> ArtifactVersionLocator:
    return ArtifactVersionLocator(
        version=int(artifact['version']),
        uri=str(artifact.get('uri') or artifact_uri(str(artifact['artifact_id']),int(artifact['version']))),
        artifact_sha256=str(artifact['sha256']),
        record_sha256=sha256_json(artifact),
        created_at=str(artifact.get('created_at') or ''),
        schema_id=str((artifact.get('schema_header') or {}).get('schema_id', '')),
    )


def build_artifact_registry(artifacts: Iterable[dict[str, Any]], *, version: int = 1) -> ArtifactRegistrySnapshot:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for artifact in artifacts:
        grouped.setdefault(str(artifact['artifact_id']), []).append(artifact)
    entries: dict[str, ArtifactRegistryEntry] = {}
    for aid, versions in grouped.items():
        versions.sort(key=lambda a: int(a['version']))
        typ = str(versions[-1]['artifact_type'])
        locators = {int(a['version']): locator_for_artifact(a) for a in versions}
        entries[aid] = ArtifactRegistryEntry(aid, typ, int(versions[-1]['version']), locators)
    return ArtifactRegistrySnapshot(version=int(version), entries=entries)
