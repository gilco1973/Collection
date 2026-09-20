"""Confluence Cloud REST client (v1 content API), read and gated write."""

from kb_librarian.atlassian.client import AtlassianClient


class ConfluenceClient(AtlassianClient):
    def search(self, cql: str, limit: int = 10) -> list[dict]:
        data = self.get("/wiki/rest/api/content/search", cql=cql, limit=limit)
        return [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "type": item.get("type"),
                "url": f"{self.base_url}/wiki{item.get('_links', {}).get('webui', '')}",
            }
            for item in data.get("results", [])
        ]

    def get_page(self, page_id: str) -> dict:
        data = self.get(f"/wiki/rest/api/content/{page_id}", expand="body.storage,version,space")
        return {
            "id": data.get("id"),
            "title": data.get("title"),
            "space": data.get("space", {}).get("key"),
            "version": data.get("version", {}).get("number"),
            "body": data.get("body", {}).get("storage", {}).get("value", ""),
        }

    def find_page(self, space_key: str, title: str) -> dict | None:
        data = self.get("/wiki/rest/api/content", spaceKey=space_key, title=title, expand="version", limit=1)
        results = data.get("results", [])
        if not results:
            return None
        page = results[0]
        return {
            "id": page.get("id"),
            "title": page.get("title"),
            "version": page.get("version", {}).get("number"),
        }

    def create_page(self, space_key: str, title: str, storage_body: str, parent_id: str | None = None) -> dict:
        payload: dict = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {"storage": {"value": storage_body, "representation": "storage"}},
        }
        if parent_id:
            payload["ancestors"] = [{"id": parent_id}]
        data = self.post("/wiki/rest/api/content", payload, what=f"create Confluence page '{title}'")
        return {"id": data.get("id"), "title": data.get("title")}

    def update_page(self, page_id: str, title: str, storage_body: str, current_version: int) -> dict:
        payload = {
            "id": page_id,
            "type": "page",
            "title": title,
            "version": {"number": current_version + 1},
            "body": {"storage": {"value": storage_body, "representation": "storage"}},
        }
        data = self.put(f"/wiki/rest/api/content/{page_id}", payload, what=f"update Confluence page '{title}'")
        return {
            "id": data.get("id"),
            "title": data.get("title"),
            "version": data.get("version", {}).get("number"),
        }

    def publish(self, space_key: str, title: str, storage_body: str) -> dict:
        """Create or update by title. Refuses (no request sent) when writes are gated."""
        self.ensure_write_allowed(f"publish '{title}'")
        existing = self.find_page(space_key, title)
        if existing is None:
            return {"action": "created", **self.create_page(space_key, title, storage_body)}
        return {
            "action": "updated",
            **self.update_page(existing["id"], title, storage_body, existing["version"]),
        }
