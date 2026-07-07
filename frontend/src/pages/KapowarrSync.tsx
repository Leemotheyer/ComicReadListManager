import { useMutation, useQuery } from "@tanstack/react-query";

import { useMemo, useState } from "react";

import { Link, useNavigate, useParams } from "react-router-dom";

import { api, KapowarrPreviewItem } from "../api";



const STATUS_LABELS: Record<string, string> = {

  in_library: "In library",

  missing_file: "Missing file",

  volume_not_in_library: "Volume not in Kapowarr",

  issue_not_found: "Issue not in metadata",

  auto_search_issue: "Auto search issue",

};



function formatSeries(series: string, volumeYear: number | null | undefined) {

  return volumeYear ? `${series} (${volumeYear})` : series;

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



export default function KapowarrSync() {

  const { id } = useParams<{ id: string }>();

  const listId = Number(id);
  const navigate = useNavigate();



  const [showOnlyActionable, setShowOnlyActionable] = useState(true);

  const [selectedVolumes, setSelectedVolumes] = useState<Set<number>>(new Set());

  const [selectedIssues, setSelectedIssues] = useState<Set<string>>(new Set());



  const previewQuery = useQuery({

    queryKey: ["kapowarrPreview", listId],

    queryFn: () => api.kapowarrPreview(listId),

    enabled: !isNaN(listId),

  });



  const syncMutation = useMutation({

    mutationFn: () => {

      const itemByKey = new Map(

        preview!.items.map((i) => [`${i.cv_volume_id}:${i.cv_issue_id}`, i])

      );

      return api.kapowarrSync(listId, {

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

    onSuccess: () => {
      previewQuery.refetch();
      navigate("/missing?tab=queue");
    },

  });



  const preview = previewQuery.data;



  const visibleItems = useMemo(() => {

    if (!preview) return [];

    if (!showOnlyActionable) return preview.items;

    return preview.items.filter(

      (i) =>

        i.status === "missing_file" ||

        i.status === "volume_not_in_library" ||

        i.status === "issue_not_found"

    );

  }, [preview, showOnlyActionable]);



  const toggleVolume = (cvId: number) => {

    setSelectedVolumes((prev) => {

      const next = new Set(prev);

      if (next.has(cvId)) next.delete(cvId);

      else next.add(cvId);

      return next;

    });

  };



  const issueKey = (item: KapowarrPreviewItem) =>

    `${item.cv_volume_id}:${item.cv_issue_id}`;



  const toggleIssue = (item: KapowarrPreviewItem) => {

    const key = issueKey(item);

    setSelectedIssues((prev) => {

      const next = new Set(prev);

      if (next.has(key)) next.delete(key);

      else next.add(key);

      return next;

    });

  };



  const selectAllVolumes = () => {

    if (!preview) return;

    setSelectedVolumes(new Set(preview.volumes_to_add.map((v) => v.cv_volume_id)));

  };



  const selectAllDownloads = () => {

    if (!preview) return;

    setSelectedIssues(

      new Set(preview.issues_to_download.map((i) => issueKey(i)))

    );

  };



  if (previewQuery.isLoading) return <p className="muted">Loading preview...</p>;

  if (previewQuery.error)

    return <p className="error">{(previewQuery.error as Error).message}</p>;

  if (!preview) return null;



  return (

    <div>

      <p className="page-back">

        <Link to={`/lists/${listId}`}>← Back to list</Link>

      </p>



      <div className="card">

        <h2>Kapowarr sync</h2>

        <p className="muted">

          Review what needs to be added or downloaded before anything runs against

          Kapowarr.

        </p>



        <div className="filters">

          <label>

            <input

              type="checkbox"

              checked={showOnlyActionable}

              onChange={(e) => setShowOnlyActionable(e.target.checked)}

            />

            Show only actionable

          </label>

        </div>



        <div className="row-actions" style={{ marginBottom: "1rem" }}>

          <button className="btn btn-secondary" onClick={selectAllVolumes}>

            Select volumes ({preview.volumes_to_add.length})

          </button>

          <button className="btn btn-secondary" onClick={selectAllDownloads}>

            Select downloads ({preview.issues_to_download.length})

          </button>

        </div>



        {preview.volumes_to_add.length > 0 && (

          <div style={{ marginBottom: "1.5rem" }}>

            <h3>Volumes to add</h3>

            <div className="volume-check-list">

              {preview.volumes_to_add.map((vol) => (

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

                  <td className={`status-${item.status}`}>

                    {STATUS_LABELS[item.status] ?? item.status}

                  </td>

                  <td className="muted">{item.message}</td>

                </tr>

              ))}

            </tbody>

          </table>

        </div>



        <div className="row-actions" style={{ marginTop: "1rem" }}>

          <button

            className="btn"

            disabled={

              syncMutation.isPending ||

              (selectedVolumes.size === 0 && selectedIssues.size === 0)

            }

            onClick={() => syncMutation.mutate()}

          >

            Approve & run sync

          </button>

        </div>



        {syncMutation.error && (

          <p className="error">{(syncMutation.error as Error).message}</p>

        )}

      </div>

    </div>

  );

}

