"""RocketMQ remoting 协议纯 Python 客户端（跨平台，仅标准库）。
Pure-Python RocketMQ remoting client (cross-platform, stdlib only).

背景 / Background:
    官方 ``rocketmq-client-python`` 不支持 Windows（导入即抛
    NotImplementedError），因此这里按 RocketMQ 4.x remoting 协议实现一个
    最小客户端，供 RocketMQ 处理器在 Windows/Linux 上收发消息。
    The official ``rocketmq-client-python`` does not support Windows (it
    raises NotImplementedError on import), so a minimal client is implemented
    here following the RocketMQ 4.x remoting protocol, letting the RocketMQ
    processors send and receive messages on both Windows and Linux.

仅实现插件演示所需的最小协议子集 / Only the minimal protocol subset needed
by the plugin demos is implemented:
    - 获取主题路由 / fetch topic route (GET_ROUTEINFO_BY_TOPIC)
    - 发送消息 / send message (SEND_MESSAGE)
    - 消费心跳注册 / consumer heartbeat (HEART_BEAT)
    - 拉取消息 / pull message (PULL_MESSAGE)
"""

import json
import logging
import re
import socket
import struct
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from i18n import _

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 协议常量 / Protocol constants
# ---------------------------------------------------------------------------

# 请求码 / Request codes
GET_ROUTEINFO_BY_TOPIC = 105
SEND_MESSAGE = 10
HEART_BEAT = 34
PULL_MESSAGE = 11

# 响应码 / Response codes
SUCCESS = 0
TOPIC_NOT_EXIST = 17
PULL_NOT_FOUND = 19
PULL_RETRY_IMMEDIATELY = 20
PULL_OFFSET_MOVED = 21
SUBSCRIPTION_NOT_LATEST = 23
SUBSCRIPTION_GROUP_NOT_EXIST = 24

# 序列化类型：0 = JSON / Serialize type: 0 = JSON
_SERIALIZE_TYPE_JSON = 0
# 语言：0 = JAVA / Language: 0 = JAVA
_LANGUAGE_JAVA = 0
# 拉取 sysFlag 位标记 / Pull sysFlag bit flags
_FLAG_SUSPEND = 1
_FLAG_COMMIT_OFFSET = 2
_FLAG_SUBSCRIPTION = 4
# 默认主题（broker 自动建主题时使用）/ Default topic used for auto topic creation
DEFAULT_TOPIC = "TBW102"

# fastjson 会把 Map<Integer,...> 的整数键写成不带引号的 {0:"..."}，需补引号
# fastjson writes integer map keys without quotes (e.g. {0:"..."}); they need quoting
_UNQUOTED_KEY_RE = re.compile(r"([{,]\s*)(-?\d+)(\s*:)")


# ---------------------------------------------------------------------------
# 自定义异常 / Custom exceptions
# ---------------------------------------------------------------------------

class RocketMQClientError(Exception):
    """RocketMQ 客户端错误。RocketMQ client error."""


class RocketMQConnectError(RocketMQClientError):
    """连接失败。Connection failure."""


class RocketMQSendError(RocketMQClientError):
    """消息发送失败。Message send failure."""


class RocketMQReceiveError(RocketMQClientError):
    """消息消费失败。Message receive failure."""


# ---------------------------------------------------------------------------
# 协议编解码 / Protocol encode/decode
# ---------------------------------------------------------------------------

def _encode_command(
    code: int,
    header: Dict[str, Any],
    body: Optional[bytes] = None,
    opaque: int = 0,
    remark: str = "",
) -> bytes:
    """把 RemotingCommand 编码为字节流（长度帧 + JSON 头）。
    Encode a RemotingCommand into bytes (length-prefixed frame + JSON header)."""
    # 4.x 协议：code/opaque/flag 等固定字段放在 JSON 头内，自定义头字段放 extFields（字符串值）
    # 4.x protocol: code/opaque/flag live inside the JSON header; custom header
    # fields go into extFields with string values
    ext_fields = {
        key: _to_str(value)
        for key, value in header.items()
        if value is not None
    }
    header_json = {
        "code": code,
        "language": "JAVA",
        "version": 0,
        "opaque": opaque,
        "flag": 0,
        "remark": remark or "",
        "extFields": ext_fields,
    }
    header_bytes = json.dumps(header_json, separators=(",", ":")).encode("utf-8")
    payload = bytearray()
    # 序列化类型与头长度合并为一个 int：高 8 位 serializeType，低 24 位 header 长度
    # Serialize type and header length share one int: high byte serializeType, low 24 bits header length
    payload += struct.pack(">i", (_SERIALIZE_TYPE_JSON << 24) | len(header_bytes))
    payload += header_bytes
    if body is not None:
        payload += body
    # 总长度字段表示其后全部字节数（mark + 头 + body）
    # The length field counts all following bytes (mark + header + body)
    return struct.pack(">i", len(payload)) + bytes(payload)


def _decode_frame(data: bytes) -> Dict[str, Any]:
    """解析服务端响应帧。Parse a server response frame."""
    if len(data) < 4:
        raise RocketMQClientError(_("rocketmq_client.bad_frame"))
    buf = data[4:]  # 长度字段本身不参与解析 / the length field itself is not parsed
    pos = 0
    header: Dict[str, Any] = {}
    body: Optional[bytes] = None
    # 序列化类型与头长度合并为一个 int / serialize type + header length share one int
    mark = struct.unpack_from(">i", buf, pos)[0]
    pos += 4
    header_len = mark & 0x00FFFFFF
    if header_len > 0:
        try:
            parsed = _lenient_json_loads(buf[pos:pos + header_len].decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            parsed = {}
        if isinstance(parsed, dict):
            header = parsed
        pos += header_len
    body = bytes(buf[pos:])
    ext_fields = header.get("extFields") or {}
    merged = dict(header)
    if isinstance(ext_fields, dict):
        merged.update(ext_fields)
    return {
        "code": header.get("code", -1),
        "opaque": header.get("opaque", 0),
        "flag": header.get("flag", 0),
        "header": merged,
        "body": body,
    }


def _lenient_json_loads(text: str) -> Any:
    """兼容 fastjson 未加引号的数字键（如 {0:"addr"}）。
    Tolerate fastjson's unquoted numeric keys (e.g. {0:"addr"})."""
    fixed = _UNQUOTED_KEY_RE.sub(
        lambda m: m.group(1) + '"' + m.group(2) + '"' + m.group(3),
        text,
    )
    return json.loads(fixed)


def _to_str(value: Any) -> str:
    """把 extFields 的值转换为字符串（布尔值转小写，与 Java 一致）。
    Convert extFields values to strings (lowercase booleans, matching Java)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _parse_properties(raw: bytes) -> Dict[str, str]:
    """解析消息属性串（\u0001 分隔键值、\u0002 分隔键值对）。
    Parse the message property string (\u0001 separates key/value, \u0002 separates pairs)."""
    props: Dict[str, str] = {}
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return props
    for pair in text.split("\u0002"):
        if "\u0001" in pair:
            key, value = pair.split("\u0001", 1)
            props[key] = value
    return props


def _build_properties(tags: str = "", keys: str = "") -> str:
    """构造消息属性串。Build the message property string."""
    props: Dict[str, str] = {}
    if tags:
        props["TAGS"] = tags
    if keys:
        props["KEYS"] = keys
    return "\u0002".join("%s\u0001%s" % (k, v) for k, v in props.items())


def _read_host(data: bytes, pos: int, v6_flag: int) -> bytes:
    """读取 host 字段（IPv4 4 字节或 IPv6 16 字节 + 4 字节端口）。
    Read a host field (4-byte IPv4 or 16-byte IPv6 plus a 4-byte port)."""
    # MessageSysFlag.BORNHOST_V6 = 0x10，STOREHOSTADDR_V6 = 0x20
    # MessageSysFlag.BORNHOST_V6 = 0x10, STOREHOSTADDR_V6 = 0x20
    if v6_flag & 0x10:
        return bytes(data[pos:pos + 20])
    return bytes(data[pos:pos + 8])


def _decode_messages(data: bytes) -> List[Dict[str, Any]]:
    """解析拉取响应中的消息列表。Parse the message list from a pull response."""
    msgs: List[Dict[str, Any]] = []
    pos = 0
    while pos + 4 <= len(data):
        total_size = struct.unpack_from(">i", data, pos)[0]
        if total_size < 4 or pos + total_size > len(data):
            break  # 尾部不完整 / trailing incomplete data
        end = pos + total_size
        p = pos + 4
        p += 4  # magic code
        p += 4  # body crc
        queue_id = struct.unpack_from(">i", data, p)[0]
        p += 4
        p += 4  # flag
        queue_offset = struct.unpack_from(">q", data, p)[0]
        p += 8
        p += 8  # physical offset
        sys_flag = struct.unpack_from(">i", data, p)[0]
        p += 4
        p += 8  # born timestamp
        p += len(_read_host(data, p, sys_flag))  # born host
        p += 8  # store timestamp
        p += len(_read_host(data, p, sys_flag | 0x20))  # store host
        p += 4  # reconsume times
        p += 8  # prepared transaction offset
        body_len = struct.unpack_from(">i", data, p)[0]
        p += 4
        body = bytes(data[p:p + body_len])
        p += body_len
        # 存储格式：主题长度 1 字节 / stored format: topic length is 1 byte
        topic_len = struct.unpack_from(">B", data, p)[0]
        p += 1
        topic = data[p:p + topic_len].decode("utf-8", "replace")
        p += topic_len
        # 存储格式：属性长度 2 字节 / stored format: properties length is 2 bytes
        props_len = struct.unpack_from(">H", data, p)[0]
        p += 2
        props = _parse_properties(bytes(data[p:p + props_len]))
        p += props_len
        # 过滤 bitmap（可选字段，按剩余字节判断）/ optional filter bitmap
        if end - p >= 4:
            bitmap_len = struct.unpack_from(">i", data, p)[0]
            p += 4
            if bitmap_len > 0 and p + bitmap_len <= end:
                p += bitmap_len
        msgs.append({
            "queue_id": queue_id,
            "queue_offset": queue_offset,
            "topic": topic,
            "tags": props.get("TAGS", ""),
            "keys": props.get("KEYS", ""),
            "body": body,
        })
        pos = end
    return msgs


def _parse_addr(addr: str, default_port: int) -> Tuple[str, int]:
    """解析 host:port。Parse a host:port address."""
    addr = (addr or "").strip()
    if not addr:
        raise RocketMQConnectError(_("rocketmq_client.empty_addr"))
    if ":" in addr:
        host, _, port = addr.rpartition(":")
        try:
            return host or "localhost", int(port)
        except ValueError:
            return addr, default_port
    return addr, default_port


# ---------------------------------------------------------------------------
# 连接与客户端 / Connection and client
# ---------------------------------------------------------------------------

class _Connection:
    """单次请求连接（用后即关，天然线程安全）。
    One-shot connection (closed after each request; naturally thread-safe)."""

    def __init__(self, addr: str, timeout: float = 5.0):
        host, port = _parse_addr(addr, 9876)
        try:
            self._sock = socket.create_connection((host, port), timeout=timeout)
        except OSError as e:
            raise RocketMQConnectError(_("rocketmq_client.conn_failed", addr=addr, error=e)) from e
        self._sock.settimeout(timeout)

    def invoke(self, frame: bytes) -> bytes:
        """发送请求并读取一帧。Send a request and read a single frame."""
        self.send(frame)
        return self.read_frame()

    def send(self, frame: bytes) -> None:
        """发送请求帧。Send a request frame."""
        try:
            self._sock.sendall(frame)
        except socket.timeout as e:
            raise RocketMQConnectError(_("rocketmq_client.conn_timeout", addr=self._sock.getpeername()[0])) from e
        except OSError as e:
            raise RocketMQConnectError(_("rocketmq_client.conn_failed", addr=self._sock.getpeername()[0], error=e)) from e

    def read_frame(self) -> bytes:
        """读取一帧数据。Read a single frame."""
        head = self._recv_exact(4)
        total_len = struct.unpack(">i", head)[0]
        if total_len < 4:
            raise RocketMQClientError(_("rocketmq_client.bad_frame"))
        # 长度字段值表示其后全部字节数（mark + 头 + body）
        # The length field counts all bytes after it (mark + header + body)
        rest = self._recv_exact(total_len)
        return head + rest

    def _recv_exact(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise RocketMQConnectError(_("rocketmq_client.conn_closed"))
            buf += chunk
        return bytes(buf)

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


class RocketMQClient:
    """RocketMQ remoting 客户端（线程安全，连接用后即关）。
    RocketMQ remoting client (thread-safe; connections are closed after use)."""

    def __init__(self, namesrv_addr: str = "localhost:9876", timeout: float = 5.0):
        self.namesrv_addr = namesrv_addr
        self.timeout = timeout
        self._opaque = 0
        self._opaque_lock = threading.Lock()
        self._route_cache: Dict[str, Tuple[float, List[Tuple[str, int]]]] = {}
        self._route_lock = threading.Lock()
        self._rr_index: Dict[str, int] = {}

    # ── 基础调用 / Basic invocation ──────────────────────────────────────

    def _next_opaque(self) -> int:
        with self._opaque_lock:
            self._opaque += 1
            return self._opaque

    def _invoke(
        self,
        addr: str,
        code: int,
        header: Dict[str, Any],
        body: Optional[bytes] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        opaque = self._next_opaque()
        frame = _encode_command(code, header, body, opaque=opaque)
        conn = _Connection(addr, timeout or self.timeout)
        try:
            conn.send(frame)
            # broker 可能在响应前推送请求帧（如 NOTIFY_CONSUMER_IDS_CHANGED），
            # 以 opaque 匹配为准（推送帧使用 broker 自己的 opaque）
            # The broker may push request frames (e.g. NOTIFY_CONSUMER_IDS_CHANGED)
            # before the response; match by opaque (pushed frames use the broker's
            # own opaque)
            for _ in range(10):
                resp = _decode_frame(conn.read_frame())
                if resp.get("opaque") == opaque:
                    return resp
            raise RocketMQClientError(_("rocketmq_client.no_matching_response"))
        finally:
            conn.close()

    # ── 路由 / Topic route ───────────────────────────────────────────────

    def get_route(self, topic: str, use_cache: bool = True) -> List[Tuple[str, int]]:
        """获取主题的可写队列路由 [(broker_addr, queue_id), ...]。
        Fetch the writable queue route [(broker_addr, queue_id), ...] for a topic."""
        if use_cache:
            with self._route_lock:
                cached = self._route_cache.get(topic)
                if cached and time.time() - cached[0] < 30:
                    return cached[1]
        resp = self._invoke(self.namesrv_addr, GET_ROUTEINFO_BY_TOPIC, {"topic": topic})
        queues: List[Tuple[str, int]] = []
        if resp["code"] == SUCCESS and resp["body"]:
            try:
                data = _lenient_json_loads(resp["body"].decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                data = {}
            queue_datas = data.get("queueDatas") or []
            broker_datas = data.get("brokerDatas") or []
            for i, qd in enumerate(queue_datas):
                bd = broker_datas[i] if i < len(broker_datas) else {}
                addrs = bd.get("brokerAddrs") or {}
                addr = addrs.get("0") or addrs.get(0)
                if not addr:
                    continue
                for qid in range(int(qd.get("writeQueueNums", 1))):
                    queues.append((addr, qid))
        elif resp["code"] != TOPIC_NOT_EXIST:
            raise RocketMQSendError(
                _("rocketmq_client.route_failed", topic=topic, code=resp["code"],
                  remark=resp["header"].get("remark", "")),
            )
        if use_cache:
            with self._route_lock:
                self._route_cache[topic] = (time.time(), queues)
        return queues

    def _pick_queue(self, queues: List[Tuple[str, int]], topic: str) -> Tuple[str, int]:
        """轮询选择一个队列。Round-robin pick a queue."""
        idx = self._rr_index.get(topic, 0)
        self._rr_index[topic] = idx + 1
        return queues[idx % len(queues)]

    # ── 发送 / Send ──────────────────────────────────────────────────────

    def send_message(
        self,
        topic: str,
        body: bytes,
        tags: str = "",
        keys: str = "",
        group: str = "DEFAULT_PRODUCER",
    ) -> Dict[str, Any]:
        """发送消息，返回 {broker_addr, queue_id, queue_offset, msg_id}。
        Send a message and return {broker_addr, queue_id, queue_offset, msg_id}."""
        queues = self.get_route(topic)
        if not queues:
            # 主题尚未创建：借默认主题路由，由 broker 自动建主题
            # Topic not created yet: use the default-topic route and let the broker create it
            queues = self.get_route(DEFAULT_TOPIC)
            if not queues:
                raise RocketMQSendError(_("rocketmq_client.no_route", topic=topic))
        addr, queue_id = self._pick_queue(queues, topic)
        header = {
            "producerGroup": group,
            "topic": topic,
            "defaultTopic": DEFAULT_TOPIC,
            "defaultTopicQueueNums": 4,
            "queueId": queue_id,
            "sysFlag": 0,
            "bornTimestamp": int(time.time() * 1000),
            "flag": 0,
            "properties": _build_properties(tags, keys),
            "reconsumeTimes": 0,
            "unitMode": False,
            "batch": False,
            "maxReconsumeTimes": 0,
        }
        resp = self._invoke(addr, SEND_MESSAGE, header, body)
        if resp["code"] != SUCCESS:
            raise RocketMQSendError(
                _("rocketmq_client.send_failed", topic=topic, code=resp["code"],
                  remark=resp["header"].get("remark", "")),
            )
        h = resp["header"]
        meta = {
            "broker_addr": addr,
            "queue_id": int(h.get("queueId", queue_id)),
            "queue_offset": int(h.get("queueOffset", -1)),
            "msg_id": h.get("msgId", ""),
        }
        logger.info(
            _("rocketmq_client.sent", topic=topic, queue_id=meta["queue_id"],
              queue_offset=meta["queue_offset"]),
        )
        return meta

    # ── 消费 / Receive ───────────────────────────────────────────────────

    def heartbeat(self, broker_addr: str, group: str, topic: str, sub_version: int) -> None:
        """注册消费者心跳。Register the consumer heartbeat."""
        sub_data = {
            "classFilterMode": False,
            "topic": topic,
            "subString": "*",
            "tagsSet": [],
            "codeSet": [],
            "subVersion": sub_version,
            "expressionType": "TAG",
        }
        consumer_data = {
            "groupName": group,
            "consumeType": "CONSUME_PASSIVELY",
            "messageModel": "CLUSTERING",
            "consumeFromWhere": "CONSUME_FROM_LAST_OFFSET",
            "subscriptionDataSet": [sub_data],
            "unitMode": False,
        }
        body = json.dumps(
            {
                "clientID": "flow-forge-%d" % threading.get_ident(),
                "consumerDataSet": [consumer_data],
                "producerDataSet": [],
            },
            separators=(",", ":"),
        ).encode("utf-8")
        resp = self._invoke(broker_addr, HEART_BEAT, {}, body)
        if resp["code"] != SUCCESS:
            raise RocketMQReceiveError(
                _("rocketmq_client.heartbeat_failed", code=resp["code"],
                  remark=resp["header"].get("remark", "")),
            )

    def pull_message(
        self,
        broker_addr: str,
        group: str,
        topic: str,
        queue_id: int,
        offset: int,
        max_nums: int = 32,
        suspend_ms: int = 3000,
        sub_version: int = 0,
    ) -> Dict[str, Any]:
        """拉取消息，返回原始响应。Pull messages; return the raw response."""
        header = {
            "consumerGroup": group,
            "topic": topic,
            "queueId": queue_id,
            "queueOffset": offset,
            "maxMsgNums": max_nums,
            "sysFlag": _FLAG_SUSPEND | _FLAG_COMMIT_OFFSET | _FLAG_SUBSCRIPTION,
            "commitOffset": 0,
            "suspendTimeoutMillis": suspend_ms,
            "subscription": "*",
            "subVersion": sub_version,
            "expressionType": "TAG",
        }
        # 拉取可能挂起 suspend_ms 毫秒，读超时必须留足余量
        # Pull may suspend for suspend_ms; leave headroom in the read timeout
        return self._invoke(broker_addr, PULL_MESSAGE, header, timeout=suspend_ms / 1000 + 5)

    def receive_message(
        self,
        topic: str,
        group: str,
        queue_id: int,
        offset: int,
        broker_addr: Optional[str] = None,
        tags: str = "",
        timeout: float = 10.0,
        poll_interval: float = 1.0,
    ) -> Optional[List[Dict[str, Any]]]:
        """从指定偏移拉取消息直到超时；返回匹配的消息列表或 None。
        Pull messages from the given offset until timeout; return matching
        messages or None."""
        if broker_addr is None:
            queues = self.get_route(topic, use_cache=False)
            broker_addr = next((a for a, q in queues if q == queue_id), queues[0][0] if queues else None)
            if not broker_addr:
                raise RocketMQReceiveError(_("rocketmq_client.no_route", topic=topic))
        sub_version = int(time.time() * 1000)
        self.heartbeat(broker_addr, group, topic, sub_version)
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = self.pull_message(broker_addr, group, topic, queue_id, offset, sub_version=sub_version)
            code = resp["code"]
            if code == SUCCESS:
                msgs = _decode_messages(resp["body"]) if resp["body"] else []
                if msgs:
                    if tags:
                        msgs = [m for m in msgs if m["tags"] == tags]
                    return msgs or None
            elif code in (PULL_NOT_FOUND, PULL_RETRY_IMMEDIATELY, PULL_OFFSET_MOVED):
                pass  # 暂无消息，继续等待 / no message yet, keep waiting
            elif code in (SUBSCRIPTION_NOT_LATEST, SUBSCRIPTION_GROUP_NOT_EXIST):
                # 订阅尚未就绪，重新心跳后重试 / subscription not ready; re-heartbeat and retry
                self.heartbeat(broker_addr, group, topic, sub_version)
            else:
                raise RocketMQReceiveError(
                    _("rocketmq_client.receive_failed", topic=topic, code=code,
                      remark=resp["header"].get("remark", "")),
                )
            time.sleep(poll_interval)
        return None
