from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.services.gap_detection import parse_tags, serialize_tags


class ReadListCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    tags: list[str] = []


class ReadListUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    tags: list[str] | None = None


class ReadListItemCreate(BaseModel):
    cv_volume_id: int
    cv_issue_id: int
    series: str
    issue_number: str
    volume_year: int | None = None
    cover_year: int | None = None
    issue_title: str | None = None
    publisher: str | None = None
    cover_image_url: str | None = None
    notes: str | None = None


class ReadListItemUpdate(BaseModel):
    notes: str | None = None


class ReadListItemResponse(BaseModel):
    id: int
    list_id: int
    sort_order: int
    cv_volume_id: int
    cv_issue_id: int
    series: str
    issue_number: str
    volume_year: int | None
    cover_year: int | None
    issue_title: str | None
    publisher: str | None
    cover_image_url: str | None
    notes: str | None = None

    model_config = {"from_attributes": True}


class ReadListResponse(BaseModel):
    id: int
    name: str
    description: str | None
    tags: list[str] = []
    created_at: datetime
    updated_at: datetime
    last_exported_at: datetime | None
    item_count: int = 0
    items: list[ReadListItemResponse] = []

    model_config = {"from_attributes": True}

    @field_validator("tags", mode="before")
    @classmethod
    def _tags_from_db(cls, v):
        if isinstance(v, list):
            return v
        return parse_tags(v if isinstance(v, str) else None)


class ReadListSummary(BaseModel):
    id: int
    name: str
    description: str | None
    tags: list[str] = []
    created_at: datetime
    updated_at: datetime
    last_exported_at: datetime | None
    item_count: int
    thumbnail_url: str | None = None

    model_config = {"from_attributes": True}

    @field_validator("tags", mode="before")
    @classmethod
    def _tags_from_db(cls, v):
        if isinstance(v, list):
            return v
        return parse_tags(v if isinstance(v, str) else None)


class ReorderRequest(BaseModel):
    item_ids: list[int]


class AddItemsRequest(BaseModel):
    items: list[ReadListItemCreate]


class AddItemsResult(BaseModel):
    read_list: ReadListResponse
    added_count: int
    skipped_count: int
    added_items: list[ReadListItemResponse]


class VolumeSearchResult(BaseModel):
    id: int
    name: str
    start_year: int | None
    publisher: str | None
    count_of_issues: int | None
    deck: str | None = None
    image_url: str | None = None


class IssueResult(BaseModel):
    id: int
    issue_number: str
    name: str | None
    cover_date: str | None
    volume_id: int
    volume_name: str | None = None
    volume_start_year: int | None = None
    publisher: str | None = None
    image_url: str | None = None


class IssuesPage(BaseModel):
    volume_id: int
    issues: list[IssueResult]
    offset: int
    limit: int
    total: int
    has_more: bool


class KapowarrPreviewItem(BaseModel):
    list_item_id: int
    list_id: int | None = None
    list_name: str | None = None
    cv_volume_id: int
    cv_issue_id: int
    series: str
    issue_number: str
    volume_year: int | None = None
    status: str
    kapowarr_volume_id: int | None = None
    kapowarr_issue_id: int | None = None
    kapowarr_issue_url: str | None = None
    message: str | None = None


class KapowarrVolumeToAdd(BaseModel):
    cv_volume_id: int
    series: str
    volume_year: int | None = None


class KapowarrPreviewResponse(BaseModel):
    items: list[KapowarrPreviewItem]
    volumes_to_add: list[KapowarrVolumeToAdd]
    issues_to_download: list[KapowarrPreviewItem]


class DownloadIssueRef(BaseModel):
    cv_volume_id: int
    cv_issue_id: int
    issue_number: str | None = None


class KapowarrSyncRequest(BaseModel):
    add_volume_ids: list[int] = []
    download_issues: list[DownloadIssueRef] = []


class KapowarrSyncResultItem(BaseModel):
    cv_volume_id: int
    cv_issue_id: int | None = None
    action: str
    success: bool
    message: str | None = None


class KapowarrSyncResponse(BaseModel):
    results: list[KapowarrSyncResultItem]
    queue_count: int | None = None


class ExportResponse(BaseModel):
    filename: str
    path: str
    exported_at: datetime


class KomgaPreviewItem(BaseModel):
    list_item_id: int
    cv_volume_id: int
    series: str
    issue_number: str
    volume_year: int | None = None
    status: str
    komga_book_id: str | None = None
    message: str | None = None
    candidates: list["KomgaMatchCandidate"] = []


class KomgaMatchCandidate(BaseModel):
    series_id: str | None = None
    series_title: str | None = None
    book_id: str | None = None
    book_number: str | None = None
    book_title: str | None = None


class KomgaSeriesResult(BaseModel):
    id: str
    name: str
    books_count: int
    year: int | None = None


class KomgaBookResult(BaseModel):
    id: str
    number: str
    title: str
    series_title: str | None = None
    filename: str | None = None


class KomgaVolumeMatchItem(BaseModel):
    list_item_id: int
    issue_number: str


class KomgaVolumeMatchRequest(BaseModel):
    items: list[KomgaVolumeMatchItem]


class KomgaVolumeMatchMapping(BaseModel):
    list_item_id: int
    komga_book_id: str
    label: str
    issue_number: str


class KomgaVolumeMatchUnmatched(BaseModel):
    list_item_id: int
    issue_number: str


class KomgaVolumeMatchResponse(BaseModel):
    mappings: list[KomgaVolumeMatchMapping]
    unmatched: list[KomgaVolumeMatchUnmatched]


class KomgaManualMapping(BaseModel):
    list_item_id: int
    komga_book_id: str
    label: str | None = None


class KomgaPreviewResponse(BaseModel):
    list_name: str
    list_error_code: str | None = None
    items: list[KomgaPreviewItem]
    matched_count: int
    unmatched_count: int
    existing_komga_read_list_id: str | None = None
    existing_komga_read_list_name: str | None = None


class KomgaPushRequest(BaseModel):
    allow_partial: bool = True
    manual_mappings: list[KomgaManualMapping] = []
    excluded_list_item_ids: list[int] = []


class KomgaPushResponse(BaseModel):
    action: str
    komga_read_list_id: str | None = None
    komga_read_list_name: str
    books_pushed: int
    books_skipped: int
    items: list[KomgaPreviewItem]


class VolumeGapInfo(BaseModel):
    cv_volume_id: int
    series: str
    volume_year: int | None = None
    collected_count: int
    collected_numbers: list[str]
    gaps: list[str]


class GapDetectionResponse(BaseModel):
    volumes: list[VolumeGapInfo]


class MissingIssuesPreviewResponse(BaseModel):
    items: list[KapowarrPreviewItem]
    kapowarr_url: str


class KapowarrDownloadQueueItem(BaseModel):
    id: int | None = None
    status: str
    title: str | None = None
    series: str | None = None
    issue_number: str | None = None
    list_id: int | None = None
    list_name: str | None = None
    volume_id: int | None = None
    issue_id: int | None = None
    source: str | None = None
    size: str | None = None
    speed: str | None = None
    progress: str | None = None
    web_link: str | None = None
    kapowarr_issue_url: str | None = None
    kapowarr_volume_url: str | None = None


class KapowarrSystemTaskItem(BaseModel):
    id: int | None = None
    action: str
    display_title: str
    status: str
    message: str | None = None
    series: str | None = None
    issue_number: str | None = None
    list_id: int | None = None
    list_name: str | None = None
    volume_id: int | None = None
    issue_id: int | None = None
    kapowarr_issue_url: str | None = None
    kapowarr_volume_url: str | None = None


class KapowarrDownloadHistoryItem(BaseModel):
    web_title: str | None = None
    web_sub_title: str | None = None
    file_title: str | None = None
    series: str | None = None
    issue_number: str | None = None
    list_id: int | None = None
    list_name: str | None = None
    volume_id: int | None = None
    issue_id: int | None = None
    source: str | None = None
    downloaded_at: int | None = None
    success: bool | None = None
    web_link: str | None = None
    kapowarr_issue_url: str | None = None
    kapowarr_volume_url: str | None = None


class KapowarrTaskHistoryItem(BaseModel):
    task_name: str
    display_title: str
    run_at: int | None = None


class MissingActivityResponse(BaseModel):
    kapowarr_url: str
    download_queue: list[KapowarrDownloadQueueItem]
    system_tasks: list[KapowarrSystemTaskItem]
    download_history: list[KapowarrDownloadHistoryItem]
    task_history: list[KapowarrTaskHistoryItem]
    app_sync_jobs: list["AppSyncJob"]
    history_offset: int
    has_active_work: bool


class AppSyncStep(BaseModel):
    id: str
    action: str
    status: str
    cv_volume_id: int | None = None
    cv_issue_id: int | None = None
    series: str | None = None
    issue_number: str | None = None
    list_id: int | None = None
    list_name: str | None = None
    message: str | None = None


class AppSyncJob(BaseModel):
    id: str
    source: str
    source_label: str
    status: str
    created_at: str
    completed_at: str | None = None
    steps: list[AppSyncStep]
    completed_count: int
    total_count: int
    current_message: str | None = None
    results: list[KapowarrSyncResultItem] | None = None
    queue_count: int | None = None
    error: str | None = None


class SyncJobCreatedResponse(BaseModel):
    job_id: str
    status: str


class BackupImportRequest(BaseModel):
    data: dict
    replace: bool = False


class BackupImportResponse(BaseModel):
    lists_imported: int
    items_imported: int


class CopyListRequest(BaseModel):
    name: str | None = None


class SettingsResponse(BaseModel):
    kapowarr_url: str
    kapowarr_root_folder_id: int
    komga_url: str
    comicvine_api_key_set: bool
    kapowarr_api_key_set: bool
    komga_api_key_set: bool
    updated_at: datetime | None = None


class SettingsUpdate(BaseModel):
    comicvine_api_key: str | None = None
    kapowarr_url: str | None = None
    kapowarr_api_key: str | None = None
    kapowarr_root_folder_id: int | None = None
    komga_url: str | None = None
    komga_api_key: str | None = None


class LocgPreviewRequest(BaseModel):
    url: str = Field(min_length=1)


class LocgMatchCandidate(BaseModel):
    cv_volume_id: int
    cv_issue_id: int
    series: str
    issue_number: str
    volume_year: int | None = None
    cover_year: int | None = None
    issue_title: str | None = None
    publisher: str | None = None
    cover_image_url: str | None = None


class LocgPreviewItem(BaseModel):
    index: int
    locg_id: int
    title: str
    series: str
    issue_number: str
    publisher: str | None = None
    store_date: str | None = None
    notes: str | None = None
    status: str
    message: str | None = None
    cv_volume_id: int | None = None
    cv_issue_id: int | None = None
    volume_year: int | None = None
    cover_year: int | None = None
    issue_title: str | None = None
    cover_image_url: str | None = None
    already_in_list: bool = False
    candidates: list[LocgMatchCandidate] = []


class LocgPreviewResponse(BaseModel):
    source_url: str
    source_type: str
    list_name: str
    list_description: str | None = None
    item_count: int
    matched_count: int
    ambiguous_count: int
    failed_count: int
    duplicate_count: int = 0
    existing_item_count: int = 0
    items: list[LocgPreviewItem]


class LocgImportItem(BaseModel):
    index: int
    cv_volume_id: int
    cv_issue_id: int
    series: str
    issue_number: str
    volume_year: int | None = None
    cover_year: int | None = None
    issue_title: str | None = None
    publisher: str | None = None
    cover_image_url: str | None = None
    notes: str | None = None


class LocgImportRequest(BaseModel):
    items: list[LocgImportItem]
    include_notes: bool = True
    update_list_meta: bool = False
    list_name: str | None = None
    list_description: str | None = None


class LocgImportResponse(BaseModel):
    added_count: int
    skipped_count: int
    read_list: ReadListResponse
