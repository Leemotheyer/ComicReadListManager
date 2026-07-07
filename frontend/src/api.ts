export interface ReadListSummary {
  id: number;
  name: string;
  description: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
  last_exported_at: string | null;
  item_count: number;
  thumbnail_url: string | null;
}

export interface ReadListItem {
  id: number;
  list_id: number;
  sort_order: number;
  cv_volume_id: number;
  cv_issue_id: number;
  series: string;
  issue_number: string;
  volume_year: number | null;
  cover_year: number | null;
  issue_title: string | null;
  publisher: string | null;
  cover_image_url: string | null;
  notes: string | null;
}

export interface ReadList {
  id: number;
  name: string;
  description: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
  last_exported_at: string | null;
  item_count: number;
  items: ReadListItem[];
}

export interface VolumeSearchResult {
  id: number;
  name: string;
  start_year: number | null;
  publisher: string | null;
  count_of_issues: number | null;
  deck: string | null;
  image_url: string | null;
}

export interface IssueResult {
  id: number;
  issue_number: string;
  name: string | null;
  cover_date: string | null;
  volume_id: number;
  volume_name: string | null;
  volume_start_year: number | null;
  publisher: string | null;
  image_url: string | null;
}

export interface IssuesPage {
  volume_id: number;
  issues: IssueResult[];
  offset: number;
  limit: number;
  total: number;
  has_more: boolean;
}

export interface KapowarrPreviewItem {
  list_item_id: number;
  list_id?: number | null;
  list_name?: string | null;
  cv_volume_id: number;
  cv_issue_id: number;
  series: string;
  issue_number: string;
  volume_year: number | null;
  status: string;
  kapowarr_volume_id: number | null;
  kapowarr_issue_id: number | null;
  kapowarr_issue_url: string | null;
  message: string | null;
}

export interface KapowarrVolumeToAdd {
  cv_volume_id: number;
  series: string;
  volume_year: number | null;
}

export interface KapowarrPreview {
  items: KapowarrPreviewItem[];
  volumes_to_add: KapowarrVolumeToAdd[];
  issues_to_download: KapowarrPreviewItem[];
}

export interface KapowarrSyncResult {
  cv_volume_id: number;
  cv_issue_id: number | null;
  action: string;
  success: boolean;
  message: string | null;
}

export interface KapowarrSyncResponse {
  results: KapowarrSyncResult[];
  queue_count: number | null;
}

export interface KomgaMatchCandidate {
  series_id: string | null;
  series_title: string | null;
  book_id: string | null;
  book_number: string | null;
  book_title: string | null;
}

export interface KomgaPreviewItem {
  list_item_id: number;
  cv_volume_id: number;
  series: string;
  issue_number: string;
  volume_year: number | null;
  status: string;
  komga_book_id: string | null;
  message: string | null;
  candidates: KomgaMatchCandidate[];
}

export interface KomgaSeriesResult {
  id: string;
  name: string;
  books_count: number;
  year: number | null;
}

export interface KomgaBookResult {
  id: string;
  number: string;
  title: string;
  series_title: string | null;
  filename?: string | null;
}

export interface KomgaPreview {
  list_name: string;
  list_error_code: string | null;
  items: KomgaPreviewItem[];
  matched_count: number;
  unmatched_count: number;
  existing_komga_read_list_id: string | null;
  existing_komga_read_list_name: string | null;
}

export interface KomgaPushResponse {
  action: string;
  komga_read_list_id: string | null;
  komga_read_list_name: string;
  books_pushed: number;
  books_skipped: number;
  items: KomgaPreviewItem[];
}

export interface AddItemsResult {
  read_list: ReadList;
  added_count: number;
  skipped_count: number;
  added_items: ReadListItem[];
}

export interface LocgMatchCandidate {
  cv_volume_id: number;
  cv_issue_id: number;
  series: string;
  issue_number: string;
  volume_year: number | null;
  cover_year: number | null;
  issue_title: string | null;
  publisher: string | null;
  cover_image_url: string | null;
}

export interface LocgPreviewItem {
  index: number;
  locg_id: number;
  title: string;
  series: string;
  issue_number: string;
  publisher: string | null;
  store_date: string | null;
  notes: string | null;
  status: string;
  message: string | null;
  cv_volume_id: number | null;
  cv_issue_id: number | null;
  volume_year: number | null;
  cover_year: number | null;
  issue_title: string | null;
  cover_image_url: string | null;
  already_in_list: boolean;
  candidates: LocgMatchCandidate[];
}

export interface LocgPreview {
  source_url: string;
  source_type: "community_list" | "collected_edition";
  list_name: string;
  list_description: string | null;
  item_count: number;
  matched_count: number;
  ambiguous_count: number;
  failed_count: number;
  duplicate_count: number;
  existing_item_count: number;
  items: LocgPreviewItem[];
}

export interface LocgImportResponse {
  added_count: number;
  skipped_count: number;
  read_list: ReadList;
}

export interface AppSettings {
  kapowarr_url: string;
  kapowarr_root_folder_id: number;
  komga_url: string;
  comicvine_api_key_set: boolean;
  kapowarr_api_key_set: boolean;
  komga_api_key_set: boolean;
  updated_at: string | null;
}

export interface VolumeGapInfo {
  cv_volume_id: number;
  series: string;
  volume_year: number | null;
  collected_count: number;
  collected_numbers: string[];
  gaps: string[];
}

export interface MissingIssuesPreview {
  items: KapowarrPreviewItem[];
  kapowarr_url: string;
}

export interface KapowarrDownloadQueueItem {
  id: number | null;
  status: string;
  title: string | null;
  series: string | null;
  issue_number: string | null;
  list_id: number | null;
  list_name: string | null;
  volume_id: number | null;
  issue_id: number | null;
  source: string | null;
  size: string | null;
  speed: string | null;
  progress: string | null;
  web_link: string | null;
  kapowarr_issue_url: string | null;
  kapowarr_volume_url: string | null;
}

export interface KapowarrSystemTaskItem {
  id: number | null;
  action: string;
  display_title: string;
  status: string;
  message: string | null;
  series: string | null;
  issue_number: string | null;
  list_id: number | null;
  list_name: string | null;
  volume_id: number | null;
  issue_id: number | null;
  kapowarr_issue_url: string | null;
  kapowarr_volume_url: string | null;
}

export interface KapowarrDownloadHistoryItem {
  web_title: string | null;
  web_sub_title: string | null;
  file_title: string | null;
  series: string | null;
  issue_number: string | null;
  list_id: number | null;
  list_name: string | null;
  volume_id: number | null;
  issue_id: number | null;
  source: string | null;
  downloaded_at: number | null;
  success: boolean | null;
  web_link: string | null;
  kapowarr_issue_url: string | null;
  kapowarr_volume_url: string | null;
}

export interface KapowarrTaskHistoryItem {
  task_name: string;
  display_title: string;
  run_at: number | null;
}

export interface AppSyncStep {
  id: string;
  action: string;
  status: string;
  cv_volume_id: number | null;
  cv_issue_id: number | null;
  series: string | null;
  issue_number: string | null;
  list_id: number | null;
  list_name: string | null;
  message: string | null;
}

export interface AppSyncJob {
  id: string;
  source: string;
  source_label: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  steps: AppSyncStep[];
  completed_count: number;
  total_count: number;
  current_message: string | null;
  results: KapowarrSyncResponse["results"] | null;
  queue_count: number | null;
  error: string | null;
}

export interface SyncJobCreatedResponse {
  job_id: string;
  status: string;
}

export interface MissingActivity {
  kapowarr_url: string;
  download_queue: KapowarrDownloadQueueItem[];
  system_tasks: KapowarrSystemTaskItem[];
  download_history: KapowarrDownloadHistoryItem[];
  task_history: KapowarrTaskHistoryItem[];
  app_sync_jobs: AppSyncJob[];
  history_offset: number;
  has_active_work: boolean;
}

export interface BackupImportResult {
  lists_imported: number;
  items_imported: number;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || response.statusText);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const api = {
  health: () =>
    request<{
      status: string;
      comicvine_configured: boolean;
      kapowarr_configured: boolean;
      komga_configured: boolean;
    }>("/api/health"),

  listLists: () => request<ReadListSummary[]>("/api/lists"),

  createList: (name: string, description?: string, tags?: string[]) =>
    request<ReadList>("/api/lists", {
      method: "POST",
      body: JSON.stringify({ name, description, tags: tags ?? [] }),
    }),

  getList: (id: number) => request<ReadList>(`/api/lists/${id}`),

  updateList: (id: number, data: { name?: string; description?: string; tags?: string[] }) =>
    request<ReadList>(`/api/lists/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  copyList: (id: number, name?: string) =>
    request<ReadList>(`/api/lists/${id}/copy`, {
      method: "POST",
      body: JSON.stringify({ name: name ?? null }),
    }),

  getListGaps: (id: number) =>
    request<{ volumes: VolumeGapInfo[] }>(`/api/lists/${id}/gaps`),

  deleteList: (id: number) =>
    request<void>(`/api/lists/${id}`, { method: "DELETE" }),

  addItems: (
    listId: number,
    items: Omit<ReadListItem, "id" | "list_id" | "sort_order">[]
  ) =>
    request<AddItemsResult>(`/api/lists/${listId}/items`, {
      method: "POST",
      body: JSON.stringify({ items }),
    }),

  updateItem: (listId: number, itemId: number, data: { notes?: string | null }) =>
    request<ReadListItem>(`/api/lists/${listId}/items/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  reorderItems: (listId: number, itemIds: number[]) =>
    request<ReadList>(`/api/lists/${listId}/items/reorder`, {
      method: "PATCH",
      body: JSON.stringify({ item_ids: itemIds }),
    }),

  removeItem: (listId: number, itemId: number) =>
    request<ReadList>(`/api/lists/${listId}/items/${itemId}`, { method: "DELETE" }),

  searchVolumes: (q: string) =>
    request<VolumeSearchResult[]>(`/api/comicvine/volumes/search?q=${encodeURIComponent(q)}`),

  getVolumeIssues: (volumeId: number, offset = 0) =>
    request<IssuesPage>(
      `/api/comicvine/volumes/${volumeId}/issues?offset=${offset}&limit=100`
    ),

  getIssue: (issueId: string) =>
    request<IssueResult>(`/api/comicvine/issues/${encodeURIComponent(issueId)}`),

  exportCblUrl: (listId: number) => `/api/lists/${listId}/export.cbl`,

  kapowarrPreview: (listId: number) =>
    request<KapowarrPreview>(`/api/lists/${listId}/kapowarr/preview`, { method: "POST" }),

  kapowarrSync: (
    listId: number,
    data: {
      add_volume_ids: number[];
      download_issues: {
        cv_volume_id: number;
        cv_issue_id: number;
        issue_number?: string;
      }[];
    }
  ) =>
    request<SyncJobCreatedResponse>(`/api/lists/${listId}/kapowarr/sync`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  komgaPreview: (listId: number) =>
    request<KomgaPreview>(`/api/lists/${listId}/komga/preview`, { method: "POST" }),

  komgaSearchSeries: (q: string) =>
    request<KomgaSeriesResult[]>(
      `/api/komga/series/search?q=${encodeURIComponent(q)}`
    ),

  komgaSeriesBooks: (seriesId: string) =>
    request<KomgaBookResult[]>(`/api/komga/series/${encodeURIComponent(seriesId)}/books`),

  komgaMatchVolume: (
    seriesId: string,
    items: { list_item_id: number; issue_number: string }[]
  ) =>
    request<{
      mappings: {
        list_item_id: number;
        komga_book_id: string;
        label: string;
        issue_number: string;
      }[];
      unmatched: { list_item_id: number; issue_number: string }[];
    }>(`/api/komga/series/${encodeURIComponent(seriesId)}/match-issues`, {
      method: "POST",
      body: JSON.stringify({ items }),
    }),

  komgaPush: (
    listId: number,
    data: {
      allow_partial?: boolean;
      manual_mappings?: {
        list_item_id: number;
        komga_book_id: string;
        label?: string;
      }[];
    }
  ) =>
    request<KomgaPushResponse>(`/api/lists/${listId}/komga/push`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getSettings: () => request<AppSettings>("/api/settings"),

  updateSettings: (data: {
    kapowarr_url?: string;
    kapowarr_root_folder_id?: number;
    komga_url?: string;
    comicvine_api_key?: string;
    kapowarr_api_key?: string;
    komga_api_key?: string;
  }) =>
    request<AppSettings>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  missingPreview: () => request<MissingIssuesPreview>("/api/missing/preview"),

  missingActivity: (historyOffset = 0) =>
    request<MissingActivity>(
      `/api/missing/activity?history_offset=${historyOffset}`
    ),

  missingSync: (data: {
    add_volume_ids: number[];
    download_issues: {
      cv_volume_id: number;
      cv_issue_id: number;
      issue_number?: string;
    }[];
  }) =>
    request<SyncJobCreatedResponse>("/api/missing/sync", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  missingSyncJob: (jobId: string) =>
    request<AppSyncJob>(`/api/missing/sync/jobs/${encodeURIComponent(jobId)}`),

  backupExportUrl: () => "/api/backup/export",

  backupImport: (data: object, replace = false) =>
    request<BackupImportResult>("/api/backup/import", {
      method: "POST",
      body: JSON.stringify({ data, replace }),
    }),

  locgPreview: (listId: number, url: string) =>
    request<LocgPreview>(`/api/lists/${listId}/locg/preview`, {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  locgImport: (
    listId: number,
    data: {
      items: {
        index: number;
        cv_volume_id: number;
        cv_issue_id: number;
        series: string;
        issue_number: string;
        volume_year?: number | null;
        cover_year?: number | null;
        issue_title?: string | null;
        publisher?: string | null;
        cover_image_url?: string | null;
        notes?: string | null;
      }[];
      include_notes?: boolean;
      update_list_meta?: boolean;
      list_name?: string;
      list_description?: string | null;
    }
  ) =>
    request<LocgImportResponse>(`/api/lists/${listId}/locg/import`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
