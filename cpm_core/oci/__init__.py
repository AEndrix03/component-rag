"""OCI client package for CPM."""

from .client import OciClient, build_artifact_spec
from .errors import (
    OciAuthError,
    OciCommandError,
    OciError,
    OciNotSupportedError,
    OciSecurityError,
)
from .types import (
    OciArtifactSpec,
    OciClientConfig,
    OciPullResult,
    OciPushResult,
    OciReferrer,
    OciVerificationReport,
)
from .packaging import (
    CPM_LAYER_MEDIATYPE,
    CPM_LOCK_MEDIATYPE,
    CPM_MANIFEST_MEDIATYPE,
    CPM_OCI_LOCK,
    CPM_OCI_MANIFEST,
    OciPacketLayout,
    build_oci_layout,
    digest_ref_for,
    package_ref_for,
)
from .packet_metadata import (
    PACKET_METADATA_SCHEMA,
    PACKET_METADATA_SCHEMA_VERSION,
    build_packet_metadata,
    validate_packet_metadata,
)
from .catalog import CPM_CATALOG_MEDIATYPE, parse_catalog_jsonl, write_catalog_jsonl
from .install_state import (
    install_lock_path,
    read_install_lock,
    read_install_lock_as_of,
    write_install_lock,
)

__all__ = [
    "OciClient",
    "OciClientConfig",
    "OciArtifactSpec",
    "OciPullResult",
    "OciPushResult",
    "OciReferrer",
    "OciVerificationReport",
    "OciError",
    "OciCommandError",
    "OciSecurityError",
    "OciAuthError",
    "OciNotSupportedError",
    "build_artifact_spec",
    "CPM_OCI_MANIFEST",
    "CPM_OCI_LOCK",
    "CPM_LAYER_MEDIATYPE",
    "CPM_MANIFEST_MEDIATYPE",
    "CPM_LOCK_MEDIATYPE",
    "OciPacketLayout",
    "build_oci_layout",
    "package_ref_for",
    "digest_ref_for",
    "PACKET_METADATA_SCHEMA",
    "PACKET_METADATA_SCHEMA_VERSION",
    "build_packet_metadata",
    "validate_packet_metadata",
    "CPM_CATALOG_MEDIATYPE",
    "parse_catalog_jsonl",
    "write_catalog_jsonl",
    "install_lock_path",
    "read_install_lock",
    "read_install_lock_as_of",
    "write_install_lock",
]
