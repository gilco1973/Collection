"""Jira Cloud REST client (v3), read and gated write."""

from kb_librarian.atlassian.client import AtlassianClient


def _adf(text: str) -> dict:
    """Wrap plain text as an Atlassian Document Format paragraph."""
    return {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


class JiraClient(AtlassianClient):
    def search(self, jql: str, limit: int = 10) -> list[dict]:
        data = self.get("/rest/api/3/search", jql=jql, maxResults=limit, fields="summary,status")
        return [
            {
                "key": issue.get("key"),
                "summary": issue.get("fields", {}).get("summary"),
                "status": issue.get("fields", {}).get("status", {}).get("name"),
            }
            for issue in data.get("issues", [])
        ]

    def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str,
        *,
        issue_type: str = "Task",
        labels: list[str] | None = None,
    ) -> dict:
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": _adf(description),
                "issuetype": {"name": issue_type},
                "labels": list(labels or []),
            }
        }
        data = self.post("/rest/api/3/issue", payload, what=f"create Jira issue '{summary}'")
        return {"key": data.get("key"), "url": f"{self.base_url}/browse/{data.get('key')}"}
