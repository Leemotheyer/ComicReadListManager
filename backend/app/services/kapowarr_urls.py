def kapowarr_volume_url(base_url: str, kapowarr_volume_id: int) -> str:
    return f"{base_url.rstrip('/')}/volumes/{kapowarr_volume_id}"


def kapowarr_issue_url(
    base_url: str, kapowarr_volume_id: int, kapowarr_issue_id: int
) -> str:
    return f"{base_url.rstrip('/')}/volumes/{kapowarr_volume_id}#issue-{kapowarr_issue_id}"
