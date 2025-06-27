from server import mcp_tool, ToolInput

COMPANIES = [
    {"id": 1, "name": "Acme Corp", "industry": "Manufacturing", "employees": 250},
    {"id": 2, "name": "Globex Inc", "industry": "Technology", "employees": 500},
    {"id": 3, "name": "Soylent Corp", "industry": "Food", "employees": 300},
]

@mcp_tool(
    "company.search",
    "Search the sample company database",
    [ToolInput(name="query", type="string", description="Name or industry")],
)
async def company_search_tool(params):
    term = params["query"].lower()
    matches = [c for c in COMPANIES if term in c["name"].lower() or term in c["industry"].lower()]
    return {"results": matches}
