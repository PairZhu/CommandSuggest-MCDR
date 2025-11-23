import json
import re
import socket
import threading
from dataclasses import dataclass

import mcdreforged.api.all as mcdr
from mcdreforged.command.command_manager import CommandManager
from mcdreforged.command.command_source import PlayerCommandSource
from mcdreforged.mcdr_server import MCDReforgedServer
from mcdreforged.info_reactor.info import Info, InfoSource

from command_suggest.node import CommandNode
from command_suggest.suggest_server import SuggestHttpServer


@dataclass
class Config(mcdr.Serializable):
    mode: str = "http"  # "http" 或 "stdio"
    host: str = "localhost"
    port: int = 0
    force_load: bool = False


class ServerManager:
    def __init__(self, server: mcdr.PluginServerInterface):
        self._lock = threading.RLock()
        self._mcdr_server: MCDReforgedServer = server._mcdr_server
        self._command_manager: CommandManager = self._mcdr_server.command_manager
        self._plugin_server: mcdr.PluginServerInterface = server
        self._original_registry_handler: callable | None = None

    @property
    def mcdr_server(self):
        return self._mcdr_server

    @property
    def command_manager(self):
        return self._command_manager

    @property
    def plugin_server(self):
        return self._plugin_server

    def setup_registry_hook(self, callback: callable) -> None:
        with self._lock:
            self._original_registry_handler = (
                self._mcdr_server.on_plugin_registry_changed
            )

            def new_on_plugin_registry_changed():
                if self._plugin_server:
                    self._plugin_server.logger.debug(
                        "Plugin registry changed, updating commands..."
                    )
                self._original_registry_handler()
                callback()

            self._mcdr_server.on_plugin_registry_changed = (
                new_on_plugin_registry_changed
            )

    def restore_registry_hook(self) -> None:
        with self._lock:
            if (
                self._mcdr_server.on_plugin_registry_changed
                != self._original_registry_handler
            ):
                self._mcdr_server.on_plugin_registry_changed = (
                    self._original_registry_handler
                )


server_manager: ServerManager
config: Config
suggest_http_server: SuggestHttpServer | None = None
is_mod_loaded = False


def tr(key: str, /, *args, **kwargs):
    return server_manager.plugin_server.tr("command_suggest." + key, *args, **kwargs)


def get_suggestions(player: str, command: str) -> list[str]:
    command_source = PlayerCommandSource(
        server_manager.mcdr_server, Info(InfoSource.SERVER, ""), player
    )
    suggestions = server_manager.command_manager.suggest_command(
        command, command_source
    )
    return list({s.suggest_input for s in suggestions})


def get_command_tree() -> list[dict] | None:
    command_nodes: list[dict] = []
    for command_name, pch_list in server_manager.command_manager.root_nodes.items():
        plugin_command_holder = pch_list[0]
        command_nodes.append(
            CommandNode.from_mcdr_node(
                command_name, plugin_command_holder.node
            ).to_dict()
        )
    return command_nodes


def send_command_tree() -> None:
    global is_mod_loaded
    if not server_manager.plugin_server.is_server_startup():
        return
    if is_mod_loaded is False:
        if not config.force_load:
            server_manager.plugin_server.logger.error(tr("mod_not_detected"))
            return
        else:
            server_manager.plugin_server.logger.warning(tr("force_load_warning"))
            is_mod_loaded = True

    command_tree = get_command_tree()
    if command_tree is None:
        return
    data = {
        "nodes": command_tree,
        "mode": config.mode,
        "host": config.host,
        "port": config.port,
    }
    server_manager.plugin_server.logger.debug(
        f"Sending command tree:\n{json.dumps(command_tree, indent=2)}"
    )
    server_manager.plugin_server.execute(
        "__mcdrcmdsuggest_register " + json.dumps(data)
    )


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def on_info(server: mcdr.PluginServerInterface, info: mcdr.Info):
    global is_mod_loaded
    if is_mod_loaded:
        return
    if info.is_user:
        return
    if re.match(r"^\s*[\\\|-]* mcdrcmdsuggest\b", info.content):
        server.logger.debug(f"Detected CommandSuggest mod message: {info.content}")
        is_mod_loaded = True


def on_load(server: mcdr.PluginServerInterface, old):
    global config, server_manager, suggest_http_server, is_mod_loaded
    # 读取旧数据，恢复 is_mod_loaded 状态
    if old:
        is_mod_loaded = getattr(old, "is_mod_loaded", False) or is_mod_loaded

    config = server.load_config_simple("config.json", target_class=Config)
    if config.mode == "http":
        if config.port == 0:
            config.port = get_free_port()
            server.logger.info(f"Auto-selected free port: {config.port}")
        suggest_http_server = SuggestHttpServer(config.host, config.port)
        suggest_http_server.start()
    elif config.mode == "stdio":
        raise NotImplementedError(
            "STDIO mode is not implemented yet, please use HTTP mode."
        )
    else:
        raise ValueError("Invalid mode in config. Use 'http' or 'stdio'.")

    server_manager = ServerManager(server)
    server_manager.setup_registry_hook(send_command_tree)
    if server.is_server_startup():
        send_command_tree()


def on_server_startup(server: mcdr.PluginServerInterface):
    send_command_tree()


def on_unload(server: mcdr.PluginServerInterface):
    server_manager.restore_registry_hook()
    if suggest_http_server:
        suggest_http_server.stop()
