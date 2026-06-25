import base64
import unittest
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from voice_agent.config import Settings
from voice_agent.routes import twilio_webhook


class FakeOrchestrator:
    def __init__(self) -> None:
        self.sessions = {}
        self.started_call_sid = None

    def start_call(self, call_sid=None):
        self.started_call_sid = call_sid
        session = SimpleNamespace(
            id="session-123",
            transcript=[
                SimpleNamespace(
                    text="您好，这里是停车场门岗，请问您来访需要找哪位？"
                )
            ],
        )
        self.sessions[session.id] = session
        return session

    def get_session(self, session_id):
        return self.sessions.get(session_id)


class TwilioWebhookTest(unittest.TestCase):
    def test_voice_webhook_returns_twiml_with_stream_parameter(self):
        client, orchestrator = self._client(public_base_url="https://example.ngrok-free.app")

        response = client.post("/twilio/voice", data={"CallSid": "CA123"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(orchestrator.started_call_sid, "CA123")

        root = ElementTree.fromstring(response.text)
        say = root.find("Say")
        stream = root.find("./Connect/Stream")
        parameter = root.find("./Connect/Stream/Parameter")

        self.assertIsNotNone(say)
        self.assertIn("停车场门岗", say.text)
        self.assertIsNotNone(stream)
        self.assertEqual(stream.attrib["url"], "wss://example.ngrok-free.app/twilio/media")
        self.assertNotIn("?", stream.attrib["url"])
        self.assertIsNotNone(parameter)
        self.assertEqual(parameter.attrib["name"], "session_id")
        self.assertEqual(parameter.attrib["value"], "session-123")

    def test_media_stream_counts_twilio_audio_frames(self):
        client, orchestrator = self._client()
        orchestrator.start_call(call_sid="CA123")
        payload = base64.b64encode(b"x" * 160).decode()

        with self.assertLogs("voice_agent.routes.twilio_webhook", level="INFO") as logs:
            with client.websocket_connect("/twilio/media") as websocket:
                websocket.send_json({"event": "connected"})
                websocket.send_json(
                    {
                        "event": "start",
                        "start": {
                            "callSid": "CA123",
                            "streamSid": "MZ123",
                            "customParameters": {"session_id": "session-123"},
                        },
                    }
                )
                websocket.send_json({"event": "media", "media": {"payload": payload}})
                websocket.send_json({"event": "media", "media": {"payload": payload}})
                websocket.send_json({"event": "stop", "stop": {"reason": "call-ended"}})

        output = "\n".join(logs.output)
        self.assertIn("twilio_media_start session_id=session-123", output)
        self.assertIn("frames=2 bytes=320 reason=call-ended", output)

    def test_media_stream_rejects_unknown_session(self):
        client, _ = self._client()

        with client.websocket_connect("/twilio/media") as websocket:
            websocket.send_json(
                {
                    "event": "start",
                    "start": {
                        "callSid": "CA123",
                        "streamSid": "MZ123",
                        "customParameters": {"session_id": "missing"},
                    },
                }
            )
            with self.assertRaises(WebSocketDisconnect) as caught:
                websocket.receive_text()

        self.assertEqual(caught.exception.code, 1008)

    def _client(self, public_base_url: str | None = "https://voice-agent.example") -> tuple[
        TestClient, FakeOrchestrator
    ]:
        app = FastAPI()
        app.state.settings = Settings(
            app_env="test",
            public_base_url=public_base_url,
            database_path=Path(":memory:"),
            wecom_webhook_url=None,
            notification_dry_run=True,
            twilio_account_sid=None,
            twilio_auth_token=None,
            twilio_phone_number=None,
            twilio_validate_signature=False,
            dashscope_api_key=None,
            qwen_realtime_model="qwen-omni-turbo-realtime",
        )
        orchestrator = FakeOrchestrator()
        app.state.orchestrator = orchestrator
        app.include_router(twilio_webhook.router)
        return TestClient(app), orchestrator


if __name__ == "__main__":
    unittest.main()
