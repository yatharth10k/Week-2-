import os
import json
from openai import OpenAI
from dotenv import load_dotenv
import sys
import argparse
import asyncio
import sys
import webbrowser
from urllib.parse import parse_qs, urlparse
import httpx
from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, Input, RichLog
from textual.containers import Vertical
from textual.containers import Horizontal


load_dotenv(".env")


client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)


MODEL = "openai/gpt-4o-mini"
ALPHAXIV_MCP_URL = "https://api.alphaxiv.org/mcp/v1"
REDIRECT_URI = "http://localhost:8765/callback"
TOKEN_FILE = ".alphaxiv_tokens.json"



# --- Token storage ---
# The MCP SDK calls these methods to persist OAuth tokens between runs.


class FileTokenStorage(TokenStorage):
    def __init__(self):
        self.tokens: OAuthToken | None = None
        self.client_info: OAuthClientInformationFull | None = None
        if os.path.exists(TOKEN_FILE):
            try:
                data = json.loads(open(TOKEN_FILE).read())
                if data.get("tokens"):
                    self.tokens = OAuthToken(**data["tokens"])
                if data.get("client_info"):
                    self.client_info = OAuthClientInformationFull(**data["client_info"])
            except Exception:
                pass

    def _save(self):
        # mode="json" converts Pydantic types like AnyUrl to plain strings
        data = {}
        if self.tokens:
            data["tokens"] = self.tokens.model_dump(mode="json")
        if self.client_info:
            data["client_info"] = self.client_info.model_dump(mode="json")
        open(TOKEN_FILE, "w").write(json.dumps(data, indent=2))



    async def get_tokens(self) -> OAuthToken | None:
        return self.tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.tokens = tokens
        self._save()

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self.client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.client_info = client_info
        self._save()



# --- OAuth browser flow ---
# The MCP SDK calls redirect_handler with the auth URL, then callback_handler
# once the user has authorized and the browser is redirected to localhost.


async def open_browser(auth_url: str) -> None:
    print(f"Opening browser for login...\nIf it doesn't open: {auth_url}\n")
    webbrowser.open(auth_url)



async def wait_for_callback() -> tuple[str, str | None]:
    from http.server import BaseHTTPRequestHandler, HTTPServer
    code = state = None

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal code, state
            params = parse_qs(urlparse(self.path).query)
            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Authorized. You can close this tab.</h1>")


        def log_message(self, *args):
            pass  # silence request logs


    print(f"Waiting for callback on {REDIRECT_URI} ...")
    server = HTTPServer(("localhost", 8765), Handler)
    server.timeout = 120
    server.handle_request()
    server.server_close()

    if not code:
        raise RuntimeError("OAuth callback received no authorization code.")
    return code, state


# --- Output ---


# --- Main ---



async def run_mcpserver(user_message:str, tool_callback=None):
    storage = FileTokenStorage()

    auth = OAuthClientProvider(
        server_url=ALPHAXIV_MCP_URL,
        client_metadata=OAuthClientMetadata(
            client_name="AlphaXiv ResearchBot",
            redirect_uris=[REDIRECT_URI],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope="read",
        ),

        storage=storage,
        redirect_handler=open_browser,
        callback_handler=wait_for_callback,
    )

    async with httpx.AsyncClient(
        auth=auth,
        follow_redirects=True,
        timeout=60,
    ) as http:
        async with streamable_http_client(
            ALPHAXIV_MCP_URL,
            http_client=http,
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                my_tools=await session.list_tools()
                openai_tools=[]
                for tool in my_tools.tools:
                    openai_tools.append({
                        "type":"function",
                        "function":{
                            "name":tool.name,
                            "description":tool.description,
                            "parameters":tool.inputSchema,
                        }
                    })
                messages = [
                    {"role": "system", "content": "You are a helpful research assistant."},
                    {"role": "user", "content": user_message},
                ]

                for _ in range(10):
                    response=client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=openai_tools,
                    )

                    message=response.choices[0].message
                    if not message.tool_calls:
                        return message.content
                    messages.append(message)
                    for tool_call in message.tool_calls:
                        args=json.loads(tool_call.function.arguments)
                        result=await session.call_tool(
                            tool_call.function.name,
                            arguments=args,
                        )

                        if tool_callback:
                            tool_callback(
                                f"Calling tool: {tool_call.function.name}"
                            )
                        content = result.content[0].text if result.content else ""
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": content,
                        })
                return ("Hit iteration limit!!")

            

#-         -        -TUI     -    -    -     -
















MAX_HISTORY_TURNS = 20  
def trim_history(messages: list[dict], max_turns: int) -> list[dict]:
    messages=[messages[0]]+messages[-(2*max_turns):]
    return messages



class ChatApp(App):
    """A full-screen terminal chatbot."""
    TITLE = "Week 2 Chatbot TUI"
    CSS = """
    Screen {
        layout: vertical;
    }

    RichLog {
        height: 1fr;
        border: solid $primary;
        padding: 0 1;
    }
    Input {
        dock: bottom;
        height: 3;
    }
    """


    BINDINGS = [
        Binding("ctrl+l", "clear_display", "Clear display"),
        Binding("ctrl+r", "clear_history", "Clear history"),
        Binding("ctrl+q", "quit", "Quit"),
    ]


    def __init__(self):
        super().__init__()
        self.messages: list[dict] = [
            {"role": "system", "content": "You are a helpful assistant."}
        ]


    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield RichLog(
                id="chat_log",
                wrap=True,
                markup=True,
                highlight=True,
            )
            yield RichLog(
                id="tool_log",
                wrap=True,
                markup=True,
                highlight=True,
            )

        yield Input(placeholder="Type a message and press Enter...")
        yield Footer()




    def on_mount(self) -> None:
        chat_log = self.query_one("#chat_log", RichLog)
        tool_log=self.query_one("#tool_log", RichLog)
        chat_log.write("[bold green]Chat started.[/bold green] Ctrl+Q to quit, Ctrl+L to clear, Ctrl+R to clear history.\n")
        tool_log.write("[bold green]Tool Activity[/bold green]\n")        
        self.query_one(Input).focus()

    # -----------------------------------------------------------------------
    # Event handlers
    # -----------------------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Called when the user presses Enter."""
        user_text = event.value.strip()
        self.current_user_text=user_text
        if not user_text:
            return

        event.input.clear()
        chat_log = self.query_one("#chat_log", RichLog)
        chat_log.write(f"[bold cyan][You][/bold cyan] {user_text}\n")

        # Append user message to history
        self.messages.append({"role": "user", "content": user_text})
        self.messages = trim_history(self.messages, MAX_HISTORY_TURNS)

        # Run the API call in a background thread so the UI stays responsive

        self.run_worker(self._get_response())


    async def _get_response(self) -> None:
        chat_log = self.query_one("#chat_log", RichLog)
        tool_log = self.query_one("#tool_log", RichLog)

        def log_tool(text):
            tool_log.write(text + "\n")
        try:
            ai_reply=await (run_mcpserver(self.current_user_text, tool_callback=log_tool))
            self.messages.append({"role":"assistant", "content":ai_reply})
            chat_log.write(f"[bold yellow][Agent][/bold yellow] {ai_reply}\n")
        except Exception as e:
            chat_log.write(f"[red]Error:[/red] {e}\n")


    # -----------------------------------------------------------------------
    # Actions (bound to keyboard shortcuts)
    # -----------------------------------------------------------------------

    def action_clear_display(self) -> None:
        chat_log = self.query_one("#chat_log", RichLog)
        chat_log.clear()


    def action_clear_history(self) -> None:
        self.messages=[{"role": "system", "content": "You are a helpful assistant."}]
        chat_log = self.query_one("#chat_log", RichLog)
        chat_log.clear()
        chat_log.write("History cleared")
















def main():

    ChatApp().run()







if __name__ == "__main__":

    main()