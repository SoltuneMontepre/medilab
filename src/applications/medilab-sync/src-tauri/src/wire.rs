use crate::api::{
    FileDetailDto, FileVersionDto, FolderDto, MemberDto, MemberUserDto, RuleDto, VersionActorDto,
};
use serde::{Deserialize, Serialize};

#[derive(Deserialize, Serialize)]
pub struct Device {
    pub id: i64,
    pub name: String,
    pub platform: String,
    pub status: String,
    pub current: bool,
}

#[derive(Deserialize)]
pub struct SignedIn {
    pub key: String,
    pub device: Device,
}
#[derive(Deserialize, Serialize)]
pub struct Devices {
    pub devices: Vec<Device>,
}

#[derive(Deserialize)]
pub struct Folder {
    pub id: i64,
    pub name: String,
    pub root: String,
    pub sync_mode: String,
    pub status: String,
    pub role: String,
    pub category: Option<String>,
    pub sample: Option<Sample>,
    pub can_share: bool,
}
#[derive(Deserialize)]
pub struct Sample {
    pub lab_code: String,
}
impl Folder {
    pub fn into_dto(self, rules: Vec<RuleDto>) -> FolderDto {
        FolderDto {
            id: self.id,
            name: self.name,
            logical_root: self.root,
            sync_mode: self.sync_mode,
            enabled: self.status == "in_use",
            device_id: 0,
            user_id: 0,
            rules,
            sample_name: None,
            sample_code: self.sample.map(|s| s.lab_code),
            category: self.category,
            workflow_status: None,
            nguon_thiet_bi: None,
            owner_name: None,
            my_role: Some(self.role),
            can_manage_members: self.can_share,
        }
    }
}
#[derive(Deserialize)]
pub struct Folders {
    pub folders: Vec<Folder>,
}
#[derive(Deserialize)]
pub struct OneFolder {
    pub folder: Folder,
}
#[derive(Deserialize)]
pub struct Rule {
    pub id: i64,
    pub kind: String,
    pub pattern: String,
    pub recursive: bool,
    pub enabled: bool,
}
impl From<Rule> for RuleDto {
    fn from(r: Rule) -> Self {
        Self {
            id: Some(r.id),
            r#type: r.kind,
            pattern: r.pattern,
            recursive: r.recursive,
            enabled: r.enabled,
        }
    }
}
#[derive(Deserialize)]
pub struct Rules {
    pub rules: Vec<Rule>,
}
#[derive(Deserialize)]
pub struct Members {
    pub members: Vec<MemberDto>,
}
#[derive(Deserialize)]
pub struct OneMember {
    pub member: MemberDto,
}
#[derive(Deserialize)]
pub struct Candidates {
    pub candidates: Vec<MemberUserDto>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Version {
    pub id: i64,
    pub number: i64,
    pub source: String,
    pub size: i64,
    pub sha256: String,
    pub parent_version_id: Option<i64>,
    pub restored_from_id: Option<i64>,
    pub saved_by: VersionActorDto,
    pub device: Option<VersionActorDto>,
    pub created_at: String,
}
impl Version {
    pub fn into_dto(self, file_id: i64, current: Option<i64>) -> FileVersionDto {
        FileVersionDto {
            id: self.id,
            file_id,
            version_number: self.number,
            size: self.size,
            content_hash: self.sha256,
            checksum_algorithm: "sha256".into(),
            is_canonical: current == Some(self.id),
            source: self.source,
            created_at: Some(self.created_at),
            created_by: Some(self.saved_by),
            device: self.device,
            parent_version_id: self.parent_version_id,
            parent_version_number: None,
            restored_from_version_id: self.restored_from_id,
            restored_from_version_number: None,
            object_available: None,
            can_restore: current != Some(self.id),
            current_version_id: current,
        }
    }
}
#[derive(Deserialize)]
pub struct Versions {
    pub versions: Vec<Version>,
}
#[derive(Deserialize)]
pub struct OneVersion {
    pub version: Version,
}
#[derive(Deserialize)]
pub struct File {
    pub id: i64,
    pub path: String,
    pub current_version: Option<Version>,
}
impl File {
    pub fn into_dto(self, folder_id: i64) -> FileDetailDto {
        let current = self.current_version.map(|v| {
            let id = v.id;
            v.into_dto(self.id, Some(id))
        });
        FileDetailDto {
            id: self.id,
            folder_id,
            name: self.path.rsplit('/').next().unwrap_or("").into(),
            logical_path: self.path,
            current_version_id: current.as_ref().map(|v| v.id),
            version_count: current.as_ref().map(|v| v.version_number).unwrap_or(0),
            updated_at: current.as_ref().and_then(|v| v.created_at.clone()),
            current_version: current,
        }
    }
}
#[derive(Deserialize)]
pub struct Files {
    pub files: Vec<File>,
    pub next_after: Option<i64>,
}
#[derive(Deserialize)]
pub struct ChangeFile {
    pub id: i64,
    pub path: String,
}
#[derive(Deserialize)]
pub struct Change {
    pub id: i64,
    pub file: ChangeFile,
    pub version: Version,
}
#[derive(Deserialize)]
pub struct Changes {
    pub changes: Vec<Change>,
    pub next_after: Option<i64>,
}
#[derive(Debug, Clone, Deserialize)]
pub struct Upload {
    pub expires_at: String,
    pub id: i64,
    pub path: String,
    pub status: String,
    pub failure_code: Option<String>,
    pub part_size: i64,
    pub part_count: i64,
    pub version: Option<Version>,
}
#[derive(Deserialize)]
pub struct OneUpload {
    pub upload: Upload,
}
#[derive(Deserialize)]
pub struct Part {
    pub number: i64,
    pub url: String,
}
#[derive(Deserialize)]
pub struct Parts {
    pub parts: Vec<Part>,
    pub expires_at: String,
}
#[derive(Deserialize)]
pub struct Download {
    pub url: String,
    pub expires_at: String,
}

pub fn ttl(expires: &str) -> i64 {
    chrono::DateTime::parse_from_rfc3339(expires)
        .map(|t| (t.timestamp() - chrono::Utc::now().timestamp()).max(0))
        .unwrap_or(0)
}
