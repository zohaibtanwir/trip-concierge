# Trip Concierge MCP server

Stdio + HTTP MCP server. Talks to the backend over HTTP — no direct DB
or Redis access. Slice 3.1 ships the skeleton: token storage, the
`@requires_auth` decorator, and the dev CLI for issuing tokens. Tool
implementations land in slices 3.2 onward.

## Manual test against Claude Desktop

Per BUILD_PLAN.md slice 3.1 acceptance: "Claude Desktop can connect to
the MCP server. First call returns instructions to obtain a dev token.
Subsequent calls use the token." Recipe:

1. **Issue a dev token** (from the repo root):

   ```bash
   make services.up
   make db.migrate
   uv run --project backend tc-issue-mcp-token --email your@email.com
   ```

   Prints a JWT to stdout.

2. **Store the token**:

   ```bash
   mkdir -p ~/.config/trip-concierge
   echo "<paste the JWT here>" > ~/.config/trip-concierge/token
   chmod 600 ~/.config/trip-concierge/token
   ```

3. **Wire MCP into Claude Desktop** — edit
   `~/Library/Application Support/Claude/claude_desktop_config.json`:

   ```json
   {
     "mcpServers": {
       "trip-concierge": {
         "command": "uv",
         "args": ["run", "--project", "<absolute-path>/trip-concierge/mcp_server",
                  "python", "-m", "trip_mcp.server"]
       }
     }
   }
   ```

4. **Restart Claude Desktop**.

5. **Smoke test in a fresh conversation**: open the MCP tool list — should
   show `trip-concierge` connected with zero tools (correct for 3.1).
   Once tools land in 3.2 they appear automatically.

## Pre-token UX

If the token file is missing or empty, every tool returns a message
instructing the user to run the dev CLI (see `tools/_base.py:_DEV_CLI_HINT`).
Production magic-link flow lands in slice 4.1.

## Layout

```
mcp_server/
├── pyproject.toml          # workspace member, depends on trip-concierge-agents
├── src/trip_mcp/
│   ├── server.py           # MCP Server, registers tools
│   ├── config.py           # BACKEND_URL, token-file path (XDG)
│   ├── auth.py             # load/save/clear token file
│   ├── http_client.py      # authed httpx wrapper for backend calls
│   └── tools/
│       ├── _base.py        # @requires_auth decorator
│       └── <future tools>  # one file per tool, slice 3.2+
└── tests/
```
