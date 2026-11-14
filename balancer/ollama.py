"""Client HTTP pour un serveur Ollama local."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

LOCAL_MODELS = (
    "qwen3:8b",
    "qwen3:4b",
    "qwen3:1.7b",
    "qwen3:0.6b",
    "qwen3:14b",
    "qwen3:latest",
)


class OllamaError(RuntimeError):
    """Le serveur local n'a pas pu satisfaire la requête."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OllamaClient:
    def __init__(
        self,
        model: str = "qwen3:8b",
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 120,
    ):
        model = "qwen3:latest" if model == "qwen3" else model
        if model not in LOCAL_MODELS:
            raise ValueError("Sélectionnez une variante locale de Qwen3 prise en charge.")

        address = urlsplit(base_url)
        if (
            address.scheme != "http"
            or address.hostname not in {"127.0.0.1", "localhost", "::1"}
            or address.username is not None
            or address.password is not None
            or address.path not in {"", "/"}
            or address.query
            or address.fragment
        ):
            raise ValueError("L’adresse Ollama doit être une adresse HTTP de boucle locale.")
        port = address.port or 11434
        host = "[::1]" if address.hostname == "::1" else "127.0.0.1"

        self.model = model
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    def _request(self, path, payload=None, timeout=3):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with self._opener.open(request, timeout=timeout) as response:
                data = response.read(4_000_001)
        except HTTPError as exc:
            if exc.code == 404 and path == "/api/chat":
                raise OllamaError(f"Modèle absent. Téléchargez-le avec ollama pull {self.model}.") from exc
            raise OllamaError(f"Le serveur Ollama a renvoyé une erreur HTTP {exc.code}.") from exc
        except TimeoutError as exc:
            raise OllamaError("Le délai de réponse du modèle local a été dépassé.") from exc
        except (URLError, OSError) as exc:
            raise OllamaError("Ollama est inaccessible. Lancez le serveur Ollama local.") from exc

        if len(data) > 4_000_000:
            raise OllamaError("La réponse Ollama dépasse la taille attendue.")
        try:
            result = json.loads(data)
        except (ValueError, UnicodeError) as exc:
            raise OllamaError("La réponse du serveur Ollama est illisible.") from exc
        if not isinstance(result, dict) or result.get("error"):
            raise OllamaError("Le serveur Ollama n’a pas fourni de résultat exploitable.")
        return result

    def _models(self, path):
        entries = self._request(path).get("models")
        if not isinstance(entries, list):
            raise OllamaError("La liste des modèles Ollama est illisible.")
        return [item for item in entries if isinstance(item, dict)]

    def _match(self, entries):
        return next(
            (
                item
                for item in entries
                if (item.get("name") == self.model or item.get("model") == self.model)
                and not any(item.get(key) for key in ("remote_model", "remote_host"))
            ),
            None,
        )

    def status(self):
        state = {
            "available": False,
            "installed": False,
            "model": self.model,
            "version": None,
            "digest": None,
            "message": "",
        }
        try:
            state["version"] = self._request("/api/version").get("version")
            model = self._match(self._models("/api/tags"))
        except OllamaError as exc:
            state["message"] = str(exc)
            return state

        if model is None:
            state["message"] = f"Modèle absent. Exécutez ollama pull {self.model}."
            return state

        state.update(available=True, installed=True, digest=model.get("digest"), message="Modèle local prêt.")
        return state

    def runtime(self):
        state = {
            "running": False,
            "model": self.model,
            "device": "Non mesuré",
            "vram_bytes": None,
            "model_bytes": None,
        }
        try:
            item = self._match(self._models("/api/ps"))
        except OllamaError:
            return state
        if item is None:
            return state
        total, vram = item.get("size"), item.get("size_vram")
        state.update(running=True, vram_bytes=vram, model_bytes=total)
        if type(total) is int and type(vram) is int and total > 0 and 0 <= vram <= total:
            state["device"] = "CPU" if vram == 0 else "GPU" if vram == total else "GPU et CPU"
        return state

    def chat(self, messages, *, tools=None, schema=None, timeout=None):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": "2m",
            "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 1200},
        }
        if tools:
            payload["tools"] = tools
        if schema:
            payload["format"] = schema
        result = self._request("/api/chat", payload, timeout=timeout or self.timeout)
        if result.get("remote_host") or result.get("remote_model"):
            raise OllamaError("La réponse n’a pas été générée par un modèle local.")
        message = result.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise OllamaError("Ollama n’a pas renvoyé de réponse de modèle exploitable.")
        return message
