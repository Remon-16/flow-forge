"""Tests for the pure-Python RocketMQ remoting client (processors/rocketmq_client.py).

所有测试通过 mock socket 层完成，不连接真实 broker。
All tests mock the socket layer; no real broker is contacted.
"""

import json
import struct
from unittest.mock import MagicMock, patch

import pytest

import processors.rocketmq_client as rmq


# ---------------------------------------------------------------------------
# 测试辅助 / Test helpers
# ---------------------------------------------------------------------------

def _extract_opaque(frame: bytes) -> int:
    """从请求帧 JSON 头中提取 opaque。Extract opaque from a request frame."""
    mark = struct.unpack_from(">i", frame, 4)[0]
    header_len = mark & 0x00FFFFFF
    header = json.loads(frame[8:8 + header_len].decode("utf-8"))
    return header["opaque"]


def _build_response(opaque: int, code: int = 0, ext_fields=None, body: bytes = None, flag: int = 1) -> bytes:
    """构造服务端响应帧。Build a server response frame."""
    header = {
        "code": code,
        "language": "JAVA",
        "version": 407,
        "opaque": opaque,
        "flag": flag,
        "remark": "",
        "extFields": ext_fields or {},
    }
    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload = struct.pack(">i", len(header_bytes)) + header_bytes
    if body is not None:
        payload += body
    return struct.pack(">i", len(payload)) + payload


def _build_message(queue_id: int, offset: int, topic: str, tags: str, body: bytes) -> bytes:
    """按存储格式构造一条消息。Build one stored-format message."""
    topic_bytes = topic.encode("utf-8")
    props = ("TAGS\u0001%s" % tags).encode("utf-8") if tags else b""
    payload = bytearray()
    payload += struct.pack(">i", 0)  # magic code
    payload += struct.pack(">i", 0)  # body crc
    payload += struct.pack(">i", queue_id)
    payload += struct.pack(">i", 0)  # flag
    payload += struct.pack(">q", offset)
    payload += struct.pack(">q", 0)  # physical offset
    payload += struct.pack(">i", 0)  # sys flag
    payload += struct.pack(">q", 0)  # born timestamp
    payload += b"\x00" * 8  # born host
    payload += struct.pack(">q", 0)  # store timestamp
    payload += b"\x00" * 8  # store host
    payload += struct.pack(">i", 0)  # reconsume times
    payload += struct.pack(">q", 0)  # prepared transaction offset
    payload += struct.pack(">i", len(body)) + body
    payload += struct.pack(">B", len(topic_bytes)) + topic_bytes
    payload += struct.pack(">H", len(props)) + props
    return struct.pack(">i", len(payload) + 4) + bytes(payload)


class FakeConnection:
    """按脚本返回响应的假连接。Fake connection that replays scripted responses."""

    def __init__(self, addr: str, timeout: float = 5.0):
        self.addr = addr
        self.timeout = timeout
        self.sent = b""
        self.script = []  # (code, ext_fields, body) 三元组 / triples
        self.closed = False

    def send(self, frame: bytes) -> None:
        self.sent = frame

    def read_frame(self) -> bytes:
        code, ext, body = self.script.pop(0)
        return _build_response(_extract_opaque(self.sent), code=code, ext_fields=ext, body=body)

    def close(self) -> None:
        self.closed = True


def _patch_connections(fakes):
    """用假连接替换 _Connection，按调用顺序返回。Replace _Connection with fakes."""
    iterator = iter(fakes)
    mock_conn = MagicMock()
    mock_conn.side_effect = lambda addr, timeout=5.0: next(iterator)
    return patch("processors.rocketmq_client._Connection", mock_conn)


_ROUTE_OK_BODY = (
    '{"brokerDatas":[{"brokerAddrs":{0:"192.168.1.157:10911"},"brokerName":"broker-a",'
    '"cluster":"DefaultCluster"}],"queueDatas":[{"brokerName":"broker-a","perm":7,'
    '"readQueueNums":8,"writeQueueNums":8}]}'
).encode("utf-8")


# ---------------------------------------------------------------------------
# 帧编解码 / Frame encode & decode
# ---------------------------------------------------------------------------

class TestFrameCodec:
    def test_encode_decode_roundtrip(self):
        frame = rmq._encode_command(105, {"topic": "order-topic"}, opaque=7)
        resp = rmq._decode_frame(frame)
        assert resp["code"] == 105
        assert resp["opaque"] == 7
        assert resp["header"].get("extFields") == {"topic": "order-topic"}

    def test_decode_response_with_ext_fields(self):
        frame = _build_response(9, code=0, ext_fields={"msgId": "M", "queueId": "0", "queueOffset": "3"})
        resp = rmq._decode_frame(frame)
        assert resp["code"] == 0
        assert resp["opaque"] == 9
        assert resp["header"]["msgId"] == "M"
        assert resp["header"]["queueOffset"] == "3"

    def test_lenient_json_accepts_unquoted_int_keys(self):
        data = rmq._lenient_json_loads('{"brokerAddrs":{0:"192.168.1.157:10911"}}')
        assert data["brokerAddrs"]["0"] == "192.168.1.157:10911"

    def test_decode_messages_parses_stored_format(self):
        body = b'{"event": "order_created"}'
        buf = _build_message(0, 5, "order-topic", "order_create", body)
        msgs = rmq._decode_messages(buf)
        assert len(msgs) == 1
        assert msgs[0]["queue_id"] == 0
        assert msgs[0]["queue_offset"] == 5
        assert msgs[0]["topic"] == "order-topic"
        assert msgs[0]["tags"] == "order_create"
        assert msgs[0]["body"] == body


# ---------------------------------------------------------------------------
# 客户端行为 / Client behaviour
# ---------------------------------------------------------------------------

class TestGetRoute:
    def test_parses_route_success(self):
        fakes = [FakeConnection("localhost:9876")]
        fakes[0].script.append((0, {}, _ROUTE_OK_BODY))
        with _patch_connections(fakes):
            client = rmq.RocketMQClient("localhost:9876")
            queues = client.get_route("TBW102", use_cache=False)

        assert queues[0] == ("192.168.1.157:10911", 0)
        assert len(queues) == 8

    def test_returns_empty_on_topic_not_exist(self):
        fakes = [FakeConnection("localhost:9876")]
        fakes[0].script.append((17, {}, None))
        with _patch_connections(fakes):
            client = rmq.RocketMQClient("localhost:9876")
            assert client.get_route("order-topic", use_cache=False) == []


class TestSendMessage:
    def test_send_message_success(self):
        fakes = [FakeConnection("h:9876"), FakeConnection("h:9876"), FakeConnection("192.168.1.157:10911")]
        fakes[0].script.append((17, {}, None))  # 目标主题无路由 / target topic has no route
        fakes[1].script.append((0, {}, _ROUTE_OK_BODY))  # 默认主题路由 / default topic route
        fakes[2].script.append((0, {"msgId": "M", "queueId": "0", "queueOffset": "3"}, None))  # 发送响应
        with _patch_connections(fakes):
            client = rmq.RocketMQClient("h:9876")
            meta = client.send_message("order-topic", b"hello", tags="t", keys="k", group="g")

        assert meta["broker_addr"] == "192.168.1.157:10911"
        assert meta["queue_id"] == 0
        assert meta["queue_offset"] == 3
        assert meta["msg_id"] == "M"
        # 校验发送请求头中的 extFields / verify the send request extFields
        send_frame = fakes[2].sent
        mark = struct.unpack_from(">i", send_frame, 4)[0]
        header_len = mark & 0x00FFFFFF
        header = json.loads(send_frame[8:8 + header_len].decode("utf-8"))
        ext = header["extFields"]
        assert ext["topic"] == "order-topic"
        assert ext["producerGroup"] == "g"
        assert ext["queueId"] == "0"

    def test_send_message_failure_raises(self):
        fakes = [FakeConnection("h:9876"), FakeConnection("h:9876"), FakeConnection("192.168.1.157:10911")]
        fakes[0].script.append((17, {}, None))
        fakes[1].script.append((0, {}, _ROUTE_OK_BODY))
        fakes[2].script.append((1, {"remark": "boom"}, None))
        with _patch_connections(fakes):
            client = rmq.RocketMQClient("h:9876")
            with pytest.raises(rmq.RocketMQSendError, match="send_failed|发送消息到主题|Failed to send"):
                client.send_message("order-topic", b"hello")


class TestReceiveMessage:
    def test_receive_returns_parsed_messages(self):
        body = json.dumps({"event": "order_created"}).encode("utf-8")
        msg_buf = _build_message(0, 5, "order-topic", "order_create", body)
        fakes = [
            FakeConnection("h:9876"),  # 路由查询 / route query
            FakeConnection("192.168.1.157:10911"),  # 心跳 / heartbeat
            FakeConnection("192.168.1.157:10911"),  # pull
        ]
        fakes[0].script.append((0, {}, _ROUTE_OK_BODY))
        fakes[1].script.append((0, {}, None))
        fakes[2].script.append((0, {}, msg_buf))
        with _patch_connections(fakes):
            client = rmq.RocketMQClient("h:9876")
            msgs = client.receive_message("order-topic", "g-verify", 0, 5, timeout=5)

        assert msgs is not None
        assert len(msgs) == 1
        assert msgs[0]["body"] == body
        assert msgs[0]["tags"] == "order_create"

    def test_receive_times_out_when_no_message(self):
        fakes = [FakeConnection("192.168.1.157:10911"), FakeConnection("192.168.1.157:10911")]
        fakes[0].script.append((0, {}, None))  # 心跳 / heartbeat
        fakes[1].script.append((rmq.PULL_NOT_FOUND, {}, None))  # pull 无消息 / no message

        with _patch_connections(fakes), \
             patch("processors.rocketmq_client.time.sleep") as mock_sleep, \
             patch("processors.rocketmq_client.time.time", side_effect=[100.0, 100.5, 101.0, 103.0]):
            client = rmq.RocketMQClient("h:9876")
            result = client.receive_message("order-topic", "g-verify", 0, 5, broker_addr="192.168.1.157:10911", timeout=1)

        assert result is None
        assert mock_sleep.called
