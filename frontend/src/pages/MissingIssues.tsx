import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  api,
  AppSyncJob,
  AppSyncStep,
  KapowarrDownloadHistoryItem,
  KapowarrDownloadQueueItem,
  KapowarrPreviewItem,
  KapowarrSyncResponse,
  KapowarrSystemTaskItem,
  KapowarrTaskHistoryItem,
} from "../api";

const STATUS_LABELS: Record<string, string> = {
  in_library: "In library",
  missing_file: "Missing file",
  volume_not_in_library: "Volume not in Kapowarr",
  issue_not_found: "Issue not in metadata",
  auto_search_issue: "Auto search issue",
};

const QUEUE_STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  downloading: "Downloading",
  importing: "Importing",
  seeding: "Seeding",
  failed: "Failed",
  canceled: "Canceled",
  "shutting down": "Shutting down",
};

const TASK_STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  running: "Running",
};

const APP_ACTION_LABELS: Record<string, string> = {
  add_volume: "Add volume",
  refresh_volume: "Refresh metadata",
  auto_search_issue: "Search & download",
};

const APP_STEP_STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Done",
  failed: "Failed",
  skipped: "Skipped",
};

const SYNC_HISTORY_KEY = "crlm_missing_sync_history";
const MAX_SYNC_HISTORY = 20;

type PageTab = "missing" | "queue" | "history";
type HistorySubTab = "downloads" | "tasks" | "syncs";

interface StoredSyncRun {
  id: string;
  at: string;
  results: KapowarrSyncResponse["results"];
  queue_count: number | null;
}

function formatSeries(series: string, volumeYear: number | null | undefined) {
  return volumeYear ? `${series} (${volumeYear})` : series;
}

function formatEpoch(epoch: number | null | undefined) {
  if (!epoch) return "—";
  return new Date(epoch * 1000).toLocaleString();
}

function capitalizeStatus(status: string) {
  return QUEUE_STATUS_LABELS[status] ?? TASK_STATUS_LABELS[status] ?? status;
}

function loadSyncHistory(): StoredSyncRun[] {
  try {
    const raw = sessionStorage.getItem(SYNC_HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveSyncHistory(runs: StoredSyncRun[]) {
  sessionStorage.setItem(SYNC_HISTORY_KEY, JSON.stringify(runs.slice(0, MAX_SYNC_HISTORY)));
}

function IssueLink({ item }: { item: KapowarrPreviewItem }) {
  if (item.kapowarr_issue_url) {
    return (
      <a href={item.kapowarr_issue_url} target="_blank" rel="noopener noreferrer">
        #{item.issue_number}
      </a>
    );
  }
  return <>#{item.issue_number}</>;
}

function ActivityTitle({
  series,
  issueNumber,
  title,
  issueUrl,
  volumeUrl,
}: {
  series: string | null | undefined;
  issueNumber: string | null | undefined;
  title: string | null | undefined;
  issueUrl: string | null | undefined;
  volumeUrl: string | null | undefined;
}) {
  const label = series || title || "Unknown";
  const href = issueUrl || volumeUrl;
  if (href) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {label}
        {issueNumber ? ` #${issueNumber}` : ""}
      </a>
    );
  }
  return (
    <>
      {label}
      {issueNumber ? ` #${issueNumber}` : ""}
    </>
  );
}

function formatStepLabel(step: AppSyncStep) {
  const action = APP_ACTION_LABELS[step.action] ?? step.action;
  if (step.series && step.issue_number) {
    return `${action} — ${step.series} #${step.issue_number}`;
  }
  if (step.series) {
    return `${action} — ${step.series}`;
  }
  return action;
}

function AppSyncJobCard({ job }: { job: AppSyncJob }) {
  const progress =
    job.total_count > 0 ? Math.round((job.completed_count / job.total_count) * 100) : 0;

  return (
    <div className="app-sync-job">
      <div className="app-sync-job-header">
        <div>
          <strong>{job.source_label}</strong>
          <span className={`app-sync-job-status app-sync-job-status-${job.status}`}>
            {job.status === "running"
              ? "Running"
              : job.status === "completed"
                ? "Completed"
                : "Failed"}
          </span>
        </div>
        <span className="muted">
          {job.completed_count}/{job.total_count} steps
          {job.status === "running" && job.current_message ? ` · ${job.current_message}` : ""}
        </span>
      </div>
      {job.status === "running" && (
        <div className="app-sync-progress" aria-hidden>
          <div className="app-sync-progress-bar" style={{ width: `${progress}%` }} />
        </div>
      )}
      {job.error && <p className="error">{job.error}</p>}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Step</th>
              <th>List</th>
              <th>Status</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {job.steps.map((step) => (
              <tr key={step.id} className={`app-step-row app-step-${step.status}`}>
                <td>{formatStepLabel(step)}</td>
                <td>
                  {step.list_name && step.list_id ? (
                    <Link to={`/lists/${step.list_id}`}>{step.list_name}</Link>
                  ) : (
                    "—"
                  )}
                </td>
                <td className={`app-step-status app-step-status-${step.status}`}>
                  {APP_STEP_STATUS_LABELS[step.status] ?? step.status}
                </td>
                <td className="muted">{step.message || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function QueueSection({
  appSyncJobs,
  queue,
  tasks,
  kapowarrUrl,
}: {
  appSyncJobs: AppSyncJob[];
  queue: KapowarrDownloadQueueItem[];
  tasks: KapowarrSystemTaskItem[];
  kapowarrUrl: string;
}) {
  const activeAppJobs = appSyncJobs.filter((j) => j.status === "running");
  const recentAppJobs = appSyncJobs.filter((j) => j.status !== "running").slice(0, 2);
  const isEmpty =
    activeAppJobs.length === 0 &&
    recentAppJobs.length === 0 &&
    queue.length === 0 &&
    tasks.length === 0;

  return (
    <>
      <div className="activity-card-header">
        <p className="muted">
          App sync progress and Kapowarr download queue. Refreshes automatically while work
          is in progress.
        </p>
        <div className="row-actions activity-header-actions">
          {activeAppJobs.length > 0 && (
            <span className="badge ok">
              {activeAppJobs.length} app sync{activeAppJobs.length !== 1 ? "s" : ""}
            </span>
          )}
          {queue.length > 0 && (
            <span className="badge ok">{queue.length} download{queue.length !== 1 ? "s" : ""}</span>
          )}
          {tasks.length > 0 && (
            <span className="badge ok">
              {tasks.length} Kapowarr task{tasks.length !== 1 ? "s" : ""}
            </span>
          )}
          <a
            className="btn btn-secondary btn-sm"
            href={`${kapowarrUrl}/activity/queue`}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open in Kapowarr
          </a>
        </div>
      </div>

      {activeAppJobs.length > 0 && (
        <>
          <h3>App sync</h3>
          <div className="app-sync-job-list">
            {activeAppJobs.map((job) => (
              <AppSyncJobCard key={job.id} job={job} />
            ))}
          </div>
        </>
      )}

      {recentAppJobs.length > 0 && activeAppJobs.length === 0 && (
        <>
          <h3>Recent app sync</h3>
          <div className="app-sync-job-list">
            {recentAppJobs.map((job) => (
              <AppSyncJobCard key={job.id} job={job} />
            ))}
          </div>
        </>
      )}

      {isEmpty ? (
        <p className="muted">Nothing in the queue right now.</p>
      ) : (
        <>
          {tasks.length > 0 && (
            <>
              <h3 style={{ marginTop: activeAppJobs.length > 0 || recentAppJobs.length > 0 ? "1.25rem" : 0 }}>
                Kapowarr tasks
              </h3>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Task</th>
                      <th>Series</th>
                      <th>List</th>
                      <th>Status</th>
                      <th>Message</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tasks.map((task) => (
                      <tr key={`task-${task.id}`}>
                        <td>{task.display_title}</td>
                        <td>
                          <ActivityTitle
                            series={task.series}
                            issueNumber={task.issue_number}
                            title={task.message}
                            issueUrl={task.kapowarr_issue_url}
                            volumeUrl={task.kapowarr_volume_url}
                          />
                        </td>
                        <td>
                          {task.list_name && task.list_id ? (
                            <Link to={`/lists/${task.list_id}`}>{task.list_name}</Link>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className={`queue-status queue-status-${task.status}`}>
                          {capitalizeStatus(task.status)}
                        </td>
                        <td className="muted">{task.message || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {queue.length > 0 && (
            <>
              <h3
                style={{
                  marginTop:
                    tasks.length > 0 || activeAppJobs.length > 0 || recentAppJobs.length > 0
                      ? "1.25rem"
                      : 0,
                }}
              >
                Kapowarr downloads
              </h3>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Title</th>
                      <th>List</th>
                      <th>Status</th>
                      <th>Source</th>
                      <th>Progress</th>
                      <th>Speed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {queue.map((item) => (
                      <tr key={`dl-${item.id}`}>
                        <td>
                          <ActivityTitle
                            series={item.series}
                            issueNumber={item.issue_number}
                            title={item.title}
                            issueUrl={item.kapowarr_issue_url}
                            volumeUrl={item.kapowarr_volume_url}
                          />
                        </td>
                        <td>
                          {item.list_name && item.list_id ? (
                            <Link to={`/lists/${item.list_id}`}>{item.list_name}</Link>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className={`queue-status queue-status-${item.status}`}>
                          {capitalizeStatus(item.status)}
                        </td>
                        <td>
                          {item.web_link ? (
                            <a href={item.web_link} target="_blank" rel="noopener noreferrer">
                              {item.source || "Source"}
                            </a>
                          ) : (
                            item.source || "—"
                          )}
                        </td>
                        <td>{item.progress || item.size || "—"}</td>
                        <td>{item.speed || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </>
  );
}

function HistorySection({
  downloadHistory,
  taskHistory,
  syncHistory,
  historyOffset,
  onHistoryOffsetChange,
  kapowarrUrl,
  onRefresh,
  isRefreshing,
}: {
  downloadHistory: KapowarrDownloadHistoryItem[];
  taskHistory: KapowarrTaskHistoryItem[];
  syncHistory: StoredSyncRun[];
  historyOffset: number;
  onHistoryOffsetChange: (offset: number) => void;
  kapowarrUrl: string;
  onRefresh: () => void;
  isRefreshing: boolean;
}) {
  const [subTab, setSubTab] = useState<HistorySubTab>("downloads");

  return (
    <>
      <div className="activity-card-header">
        <p className="muted">Recent Kapowarr downloads, tasks, and sync runs from this app.</p>
        <div className="row-actions activity-header-actions">
          <button className="btn btn-secondary btn-sm" onClick={onRefresh} disabled={isRefreshing}>
            {isRefreshing ? "Refreshing..." : "Refresh"}
          </button>
          <a
            className="btn btn-secondary btn-sm"
            href={`${kapowarrUrl}/activity/history`}
            target="_blank"
            rel="noopener noreferrer"
          >
            Kapowarr history
          </a>
        </div>
      </div>

      <div className="history-sub-tabs">
        <button
          type="button"
          className={`history-sub-tab ${subTab === "downloads" ? "history-sub-tab-active" : ""}`}
          onClick={() => setSubTab("downloads")}
        >
          Downloads ({downloadHistory.length})
        </button>
        <button
          type="button"
          className={`history-sub-tab ${subTab === "tasks" ? "history-sub-tab-active" : ""}`}
          onClick={() => setSubTab("tasks")}
        >
          Tasks ({taskHistory.length})
        </button>
        <button
          type="button"
          className={`history-sub-tab ${subTab === "syncs" ? "history-sub-tab-active" : ""}`}
          onClick={() => setSubTab("syncs")}
        >
          App syncs ({syncHistory.length})
        </button>
      </div>

      {subTab === "downloads" && (
        <>
          {downloadHistory.length === 0 ? (
            <p className="muted">No download history on this page.</p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Series</th>
                    <th>List</th>
                    <th>Source</th>
                    <th>When</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {downloadHistory.map((item, idx) => (
                    <tr key={`dh-${idx}-${item.downloaded_at}`}>
                      <td>
                        {item.web_link ? (
                          <a href={item.web_link} target="_blank" rel="noopener noreferrer">
                            {item.web_title || item.file_title || "Download"}
                          </a>
                        ) : (
                          item.web_title || item.file_title || "—"
                        )}
                      </td>
                      <td>
                        <ActivityTitle
                          series={item.series}
                          issueNumber={item.issue_number}
                          title={item.file_title}
                          issueUrl={item.kapowarr_issue_url}
                          volumeUrl={item.kapowarr_volume_url}
                        />
                      </td>
                      <td>
                        {item.list_name && item.list_id ? (
                          <Link to={`/lists/${item.list_id}`}>{item.list_name}</Link>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>{item.source || "—"}</td>
                      <td>{formatEpoch(item.downloaded_at)}</td>
                      <td
                        className={
                          item.success === true
                            ? "status-in_library"
                            : item.success === false
                              ? "status-issue_not_found"
                              : "muted"
                        }
                      >
                        {item.success === true
                          ? "Success"
                          : item.success === false
                            ? "Failed"
                            : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="history-pagination">
            <button
              className="btn btn-secondary btn-sm"
              disabled={historyOffset === 0}
              onClick={() => onHistoryOffsetChange(Math.max(0, historyOffset - 1))}
            >
              Newer
            </button>
            <span className="muted">Page {historyOffset + 1}</span>
            <button
              className="btn btn-secondary btn-sm"
              disabled={downloadHistory.length < 50 && taskHistory.length < 50}
              onClick={() => onHistoryOffsetChange(historyOffset + 1)}
            >
              Older
            </button>
          </div>
        </>
      )}

      {subTab === "tasks" && (
        <>
          {taskHistory.length === 0 ? (
            <p className="muted">No Kapowarr task history on this page.</p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Task</th>
                    <th>When</th>
                  </tr>
                </thead>
                <tbody>
                  {taskHistory.map((item, idx) => (
                    <tr key={`th-${idx}-${item.run_at}`}>
                      <td>{item.display_title}</td>
                      <td>{formatEpoch(item.run_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {subTab === "syncs" && (
        <>
          {syncHistory.length === 0 ? (
            <p className="muted">
              Sync runs triggered from this page appear here for the current browser session.
            </p>
          ) : (
            <div className="sync-history-list">
              {syncHistory.map((run) => (
                <details key={run.id} className="sync-history-entry">
                  <summary>
                    <span>{new Date(run.at).toLocaleString()}</span>
                    <span className="muted">
                      {run.results.length} action{run.results.length !== 1 ? "s" : ""}
                      {run.queue_count !== null && ` · queue ${run.queue_count}`}
                    </span>
                  </summary>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Action</th>
                          <th>Volume</th>
                          <th>Issue</th>
                          <th>Result</th>
                        </tr>
                      </thead>
                      <tbody>
                        {run.results.map((r, idx) => (
                          <tr key={idx}>
                            <td>{r.action}</td>
                            <td>{r.cv_volume_id}</td>
                            <td>{r.cv_issue_id ?? "—"}</td>
                            <td
                              className={
                                r.success ? "status-in_library" : "status-issue_not_found"
                              }
                            >
                              {r.success ? "OK" : "Failed"} — {r.message}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}

export default function MissingIssues() {
  const queryClient = useQueryClient();
  const [, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedVolumes, setSelectedVolumes] = useState<Set<number>>(new Set());
  const [selectedIssues, setSelectedIssues] = useState<Set<string>>(new Set());
  const [historyOffset, setHistoryOffset] = useState(0);
  const [pageTab, setPageTab] = useState<PageTab>(() => {
    const tab = new URLSearchParams(window.location.search).get("tab");
    return tab === "queue" || tab === "history" ? tab : "missing";
  });
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [syncHistory, setSyncHistory] = useState<StoredSyncRun[]>(() => loadSyncHistory());

  const setTab = useCallback(
    (tab: PageTab) => {
      setPageTab(tab);
      setSearchParams(tab === "missing" ? {} : { tab }, { replace: true });
    },
    [setSearchParams]
  );

  const previewQuery = useQuery({
    queryKey: ["missingPreview"],
    queryFn: api.missingPreview,
  });

  const activityQuery = useQuery({
    queryKey: ["missingActivity", historyOffset],
    queryFn: () => api.missingActivity(historyOffset),
    refetchInterval: (query) => (query.state.data?.has_active_work ? 3000 : 30000),
  });

  const appendSyncHistory = useCallback(
    (data: { results: KapowarrSyncResponse["results"]; queue_count: number | null }) => {
      const entry: StoredSyncRun = {
        id: crypto.randomUUID(),
        at: new Date().toISOString(),
        results: data.results,
        queue_count: data.queue_count,
      };
      setSyncHistory((prev) => {
        const next = [entry, ...prev].slice(0, MAX_SYNC_HISTORY);
        saveSyncHistory(next);
        return next;
      });
    },
    []
  );

  const preview = previewQuery.data;

  const syncMutation = useMutation({
    mutationFn: () => {
      const itemByKey = new Map(
        preview!.items.map((i) => [`${i.cv_volume_id}:${i.cv_issue_id}`, i])
      );
      return api.missingSync({
        add_volume_ids: [...selectedVolumes],
        download_issues: [...selectedIssues].map((key) => {
          const item = itemByKey.get(key);
          const [cv_volume_id, cv_issue_id] = key.split(":").map(Number);
          return {
            cv_volume_id,
            cv_issue_id,
            issue_number: item?.issue_number,
          };
        }),
      });
    },
    onSuccess: (data) => {
      setActiveJobId(data.job_id);
      setTab("queue");
      queryClient.invalidateQueries({ queryKey: ["missingActivity"] });
    },
  });

  const activity = activityQuery.data;

  const volumesToAdd = useMemo(() => {
    if (!preview) return [];
    const seen = new Map<number, { cv_volume_id: number; series: string; volume_year: number | null }>();
    for (const item of preview.items) {
      if (item.status === "volume_not_in_library" && !seen.has(item.cv_volume_id)) {
        seen.set(item.cv_volume_id, {
          cv_volume_id: item.cv_volume_id,
          series: item.series,
          volume_year: item.volume_year,
        });
      }
    }
    return [...seen.values()];
  }, [preview]);

  const visibleItems = useMemo(() => {
    if (!preview) return [];
    const q = search.trim().toLowerCase();
    return preview.items.filter((item) => {
      if (statusFilter && item.status !== statusFilter) return false;
      if (!q) return true;
      const haystack = [
        item.series,
        item.issue_number,
        item.list_name ?? "",
        STATUS_LABELS[item.status] ?? item.status,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [preview, search, statusFilter]);

  const issueKey = (item: KapowarrPreviewItem) =>
    `${item.cv_volume_id}:${item.cv_issue_id}`;

  const toggleVolume = (cvId: number) => {
    setSelectedVolumes((prev) => {
      const next = new Set(prev);
      if (next.has(cvId)) next.delete(cvId);
      else next.add(cvId);
      return next;
    });
  };

  const toggleIssue = (item: KapowarrPreviewItem) => {
    const key = issueKey(item);
    setSelectedIssues((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const selectAllDownloads = () => {
    if (!preview) return;
    setSelectedIssues(
      new Set(
        preview.items
          .filter((i) => i.status === "missing_file")
          .map((i) => issueKey(i))
      )
    );
  };

  const selectAllVolumes = () => {
    setSelectedVolumes(new Set(volumesToAdd.map((v) => v.cv_volume_id)));
  };

  useEffect(() => {
    setSyncHistory(loadSyncHistory());
  }, []);

  useEffect(() => {
    if (!activeJobId || !activity?.app_sync_jobs) return;
    const job = activity.app_sync_jobs.find((j) => j.id === activeJobId);
    if (job && job.status !== "running" && job.results) {
      appendSyncHistory({ results: job.results, queue_count: job.queue_count });
      setActiveJobId(null);
      previewQuery.refetch();
    }
  }, [activity, activeJobId, appendSyncHistory, previewQuery]);

  if (previewQuery.isLoading) return <p className="muted">Loading missing issues...</p>;
  if (previewQuery.error)
    return <p className="error">{(previewQuery.error as Error).message}</p>;
  if (!preview) return null;

  const kapowarrUrl = activity?.kapowarr_url || preview.kapowarr_url;
  const appSyncActive =
    activity?.app_sync_jobs.filter((j) => j.status === "running").length ?? 0;
  const queueCount =
    (activity?.download_queue.length ?? 0) +
    (activity?.system_tasks.length ?? 0) +
    appSyncActive;

  return (
    <div>
      <div className="card missing-page">
        <div className="page-tabs" role="tablist" aria-label="Missing page sections">
          <button
            type="button"
            role="tab"
            aria-selected={pageTab === "missing"}
            className={`page-tab ${pageTab === "missing" ? "page-tab-active" : ""}`}
            onClick={() => setTab("missing")}
          >
            Missing
            {preview.items.length > 0 && (
              <span className="page-tab-count">{preview.items.length}</span>
            )}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={pageTab === "queue"}
            className={`page-tab ${pageTab === "queue" ? "page-tab-active" : ""}`}
            onClick={() => setTab("queue")}
          >
            Queue
            {queueCount > 0 && <span className="page-tab-count">{queueCount}</span>}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={pageTab === "history"}
            className={`page-tab ${pageTab === "history" ? "page-tab-active" : ""}`}
            onClick={() => setTab("history")}
          >
            History
          </button>
        </div>

        {activityQuery.error && pageTab !== "missing" && (
          <p className="error">{(activityQuery.error as Error).message}</p>
        )}

        <div className="page-tab-panel">
          {pageTab === "missing" && (
            <>
              <p className="muted">
                All actionable missing issues across your read lists. Select items to add
                volumes or trigger Kapowarr downloads — then check the Queue tab for progress.
              </p>

              <div className="filters">
                <input
                  placeholder="Search series, issue #, list, status..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  style={{ flex: 1, minWidth: "12rem" }}
                />
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  aria-label="Filter by status"
                >
                  <option value="">All statuses</option>
                  <option value="missing_file">Missing file</option>
                  <option value="volume_not_in_library">Volume not in Kapowarr</option>
                  <option value="issue_not_found">Issue not in metadata</option>
                </select>
              </div>

              <div className="row-actions" style={{ marginBottom: "1rem" }}>
                <button className="btn btn-secondary" onClick={selectAllVolumes}>
                  Select volumes ({volumesToAdd.length})
                </button>
                <button className="btn btn-secondary" onClick={selectAllDownloads}>
                  Select downloads (
                  {preview.items.filter((i) => i.status === "missing_file").length})
                </button>
              </div>

              {volumesToAdd.length > 0 && (
                <div style={{ marginBottom: "1.5rem" }}>
                  <h3>Volumes to add</h3>
                  <div className="volume-check-list">
                    {volumesToAdd.map((vol) => (
                      <label key={vol.cv_volume_id} className="volume-check-item">
                        <input
                          type="checkbox"
                          checked={selectedVolumes.has(vol.cv_volume_id)}
                          onChange={() => toggleVolume(vol.cv_volume_id)}
                        />
                        {formatSeries(vol.series, vol.volume_year)}
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {visibleItems.length === 0 ? (
                <p className="muted">No missing issues match your filters.</p>
              ) : (
                <>
                  <div className="sync-item-list mobile-only">
                    {visibleItems.map((item) => (
                      <div key={item.list_item_id} className="sync-item">
                        <div>
                          {item.status === "missing_file" && (
                            <input
                              type="checkbox"
                              checked={selectedIssues.has(issueKey(item))}
                              onChange={() => toggleIssue(item)}
                            />
                          )}
                          {item.status === "volume_not_in_library" && (
                            <input
                              type="checkbox"
                              checked={selectedVolumes.has(item.cv_volume_id)}
                              onChange={() => toggleVolume(item.cv_volume_id)}
                            />
                          )}
                        </div>
                        <div className="sync-item-main">
                          <div className="sync-item-issue">
                            <IssueLink item={item} />
                          </div>
                          <div className="sync-item-series muted">
                            {formatSeries(item.series, item.volume_year)}
                          </div>
                          {item.list_name && item.list_id && (
                            <div className="muted" style={{ fontSize: "0.85rem" }}>
                              <Link to={`/lists/${item.list_id}`}>{item.list_name}</Link>
                            </div>
                          )}
                          <div className={`sync-item-status status-${item.status}`}>
                            {STATUS_LABELS[item.status] ?? item.status}
                          </div>
                          {item.message && (
                            <div className="sync-item-note muted">{item.message}</div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="table-scroll desktop-table">
                    <table>
                      <thead>
                        <tr>
                          <th></th>
                          <th>Issue</th>
                          <th>Series</th>
                          <th>List</th>
                          <th>Status</th>
                          <th>Notes</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleItems.map((item) => (
                          <tr key={item.list_item_id}>
                            <td>
                              {item.status === "missing_file" && (
                                <input
                                  type="checkbox"
                                  checked={selectedIssues.has(issueKey(item))}
                                  onChange={() => toggleIssue(item)}
                                />
                              )}
                              {item.status === "volume_not_in_library" && (
                                <input
                                  type="checkbox"
                                  checked={selectedVolumes.has(item.cv_volume_id)}
                                  onChange={() => toggleVolume(item.cv_volume_id)}
                                />
                              )}
                            </td>
                            <td>
                              <IssueLink item={item} />
                            </td>
                            <td>{formatSeries(item.series, item.volume_year)}</td>
                            <td>
                              {item.list_name && item.list_id ? (
                                <Link to={`/lists/${item.list_id}`}>{item.list_name}</Link>
                              ) : (
                                "—"
                              )}
                            </td>
                            <td className={`status-${item.status}`}>
                              {STATUS_LABELS[item.status] ?? item.status}
                            </td>
                            <td className="muted">{item.message}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}

              <div className="row-actions" style={{ marginTop: "1rem" }}>
                <button
                  className="btn"
                  disabled={
                    syncMutation.isPending ||
                    (selectedVolumes.size === 0 && selectedIssues.size === 0)
                  }
                  onClick={() => syncMutation.mutate()}
                >
                  {syncMutation.isPending ? "Syncing..." : "Approve & run sync"}
                </button>
              </div>

              {syncMutation.error && (
                <p className="error">{(syncMutation.error as Error).message}</p>
              )}
            </>
          )}

          {pageTab === "queue" &&
            (activity ? (
              <QueueSection
                appSyncJobs={activity.app_sync_jobs}
                queue={activity.download_queue}
                tasks={activity.system_tasks}
                kapowarrUrl={kapowarrUrl}
              />
            ) : activityQuery.isLoading ? (
              <p className="muted">Loading queue...</p>
            ) : (
              <p className="muted">Queue unavailable — check Kapowarr settings.</p>
            ))}

          {pageTab === "history" &&
            (activity ? (
              <HistorySection
                downloadHistory={activity.download_history}
                taskHistory={activity.task_history}
                syncHistory={syncHistory}
                historyOffset={historyOffset}
                onHistoryOffsetChange={setHistoryOffset}
                kapowarrUrl={kapowarrUrl}
                onRefresh={() => activityQuery.refetch()}
                isRefreshing={activityQuery.isFetching}
              />
            ) : activityQuery.isLoading ? (
              <p className="muted">Loading history...</p>
            ) : (
              <p className="muted">History unavailable — check Kapowarr settings.</p>
            ))}
        </div>
      </div>
    </div>
  );
}
