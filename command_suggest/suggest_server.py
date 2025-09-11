import threading

import uvicorn
from fastapi import FastAPI

import command_suggest


class SuggestHttpServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.server: uvicorn.Server | None = None
        self.thread: threading.Thread | None = None

    def start(self):
        app = FastAPI()
        app.get("/suggest")(command_suggest.get_suggestions)
        config = uvicorn.Config(
            app=app,
            host=self.host,
            port=self.port,
            log_level="critical",  # 防止影响MCDR日志
            lifespan="off",
        )
        self.server = uvicorn.Server(config)

        def run_server():
            self.server.run()

        self.thread = threading.Thread(
            target=run_server, daemon=True, name="CommandSuggest-HTTP-Server"
        )
        self.thread.start()

    def stop(self):
        if self.server and self.server.should_exit is False:
            self.server.should_exit = True
        if self.thread and self.thread.is_alive():
            self.thread.join()
        self.server = None
        self.thread = None
