from server import mcp_tool, ToolInput
import sqlite3
import os

DEFAULT_DB = "snippets.sqlite3"


def _get_conn() -> sqlite3.Connection:
    """Return a connection to the snippets DB ensuring the table exists."""
    path = os.getenv("SNIPPET_DB", DEFAULT_DB)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS snippets (
            id TEXT PRIMARY KEY,
            html TEXT,
            plain TEXT,
            markdown TEXT,
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    return conn


@mcp_tool(
    "snippet.search",
    "Search saved chat snippets",
    [ToolInput(name="query", type="string", description="keywords")],
)
async def snippet_search(params):
    q = f"%{params['query']}%"
    conn = _get_conn()
    cur = conn.execute(
        "SELECT id, substr(plain,1,160) FROM snippets "
        "WHERE plain LIKE ? ORDER BY created DESC LIMIT 10",
        (q,),
    )
    results = [
        {"id": r[0], "title": f"Snippet {r[0]}", "text": r[1], "url": f"/s/{r[0]}"}
        for r in cur
    ]
    conn.close()
    return {"results": results}


@mcp_tool(
    "snippet.fetch",
    "Fetch full saved snippet by id",
    [ToolInput(name="id", type="string", description="snippet id")],
)
async def snippet_fetch(params):
    conn = _get_conn()
    cur = conn.execute(
        "SELECT id, html, plain, markdown FROM snippets WHERE id=?",
        (params["id"],),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return {}
    return {
        "id": row[0],
        "title": f"Snippet {row[0]}",
        "html": row[1],
        "text": row[2],
        "markdown": row[3],
        "url": f"/s/{row[0]}",
    }
